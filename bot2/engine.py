"""Resilient, copy-based forwarding engine.

It intentionally uses Telegram's copy/send APIs only. It never downloads protected content or
attempts to bypass Telegram's content-protection controls.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import FloodWait, RPCError
from pyrogram.handlers import MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import Settings
from .db import Database
from .modes import (
    MediaInfo,
    apply_pipeline,
    media_info,
    source_post_link,
)
from .ui import button, markup, sc

log = logging.getLogger(__name__)
_LINK = re.compile(r"(?:https?://)?t\.me/(c/)?([^/\s]+)/?(\d+)?", re.IGNORECASE)


class EngineError(RuntimeError):
    """A clean, expected validation/forwarding error that can be shown to a user."""


class ForwardEngine:
    def __init__(self, config: Settings, db: Database, control_bot: Client) -> None:
        self.config = config
        self.db = db
        self.control_bot = control_bot
        self._clients: dict[str, Client] = {}
        self._client_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._live: dict[tuple[str, int], str] = {}
        self._history_tasks: dict[str, asyncio.Task[None]] = {}
        self._runtime_handler_added: set[str] = set()

    # --- Telegram identity lifecycle ---------------------------------------
    async def _new_identity_client(self, identity: dict[str, Any], name_suffix: str, updates: bool = False) -> Client:
        kind = identity["kind"]
        session_name = f"zc_{kind}_{str(identity['_id'])[-10:]}_{name_suffix}"
        kwargs: dict[str, Any] = {
            "name": session_name,
            "api_id": self.config.api_id,
            "api_hash": self.config.api_hash,
            "in_memory": True,
            "no_updates": not updates,
            "workdir": str(self.config.workdir),
        }
        if kind == "bot":
            kwargs["bot_token"] = self.db.decrypt(identity["token_enc"])
        else:
            kwargs["session_string"] = self.db.decrypt(identity["session_enc"])
        return Client(**kwargs)

    async def runtime_client(self, owner_id: int, ref: str) -> Client:
        """Return a started managed bot/userbot. Ownership is checked before every startup."""
        cached = self._clients.get(ref)
        if cached:
            return cached
        async with self._client_locks[ref]:
            cached = self._clients.get(ref)
            if cached:
                return cached
            identity = await self.db.get_identity(owner_id, ref)
            if not identity:
                raise EngineError("That bot or userbot no longer exists.")
            client = await self._new_identity_client(identity, "live", updates=True)
            try:
                await client.start()
            except RPCError as exc:
                raise EngineError(f"Could not connect this identity: {self.clean_error(exc)}") from exc
            self._clients[ref] = client
            self._add_runtime_handler(ref, client)
            return client

    def _add_runtime_handler(self, ref: str, client: Client) -> None:
        if ref in self._runtime_handler_added:
            return

        async def live_handler(_: Client, message: Any) -> None:
            job_id = self._live.get((ref, int(message.chat.id)))
            if job_id:
                await self._process_live(job_id, message)

        client.add_handler(MessageHandler(live_handler, filters.channel), group=50)
        self._runtime_handler_added.add(ref)

    async def stop(self) -> None:
        for task in self._history_tasks.values():
            task.cancel()
        await asyncio.gather(*self._history_tasks.values(), return_exceptions=True)
        self._history_tasks.clear()
        for client in self._clients.values():
            try:
                await client.stop()
            except Exception:
                log.exception("Managed identity did not stop cleanly")
        self._clients.clear()

    # --- Validation ----------------------------------------------------------
    @staticmethod
    def chat_input(value: str) -> tuple[int | str, int | None]:
        """Accept @username, -100 ID, or t.me post link and return (chat, linked message id)."""
        value = value.strip()
        link = _LINK.search(value)
        if link:
            private, raw_chat, msg_id = link.groups()
            chat: int | str = int(f"-100{raw_chat}") if private else f"@{raw_chat}"
            return chat, int(msg_id) if msg_id else None
        if value.startswith("@"):
            return value, None
        try:
            return int(value), None
        except ValueError as exc:
            raise EngineError("Send a channel ID, @username, or a t.me message link.") from exc

    async def resolve_source(self, owner_id: int, ref: str, raw: str) -> tuple[dict[str, Any], int | None]:
        chat_input, linked_id = self.chat_input(raw)
        client = await self.runtime_client(owner_id, ref)
        try:
            chat = await self.retry(lambda: client.get_chat(chat_input))
            if linked_id:
                message = await self.retry(lambda: client.get_messages(chat.id, linked_id))
                if not message:
                    raise EngineError("The linked source message could not be read.")
        except EngineError:
            raise
        except RPCError as exc:
            raise EngineError(f"Cannot access source: {self.clean_error(exc)}") from exc
        return {
            "id": chat.id,
            "title": chat.title or chat.username or str(chat.id),
            "username": chat.username or "",
        }, linked_id

    async def resolve_target(self, owner_id: int, ref: str, raw: str) -> dict[str, Any]:
        chat_input, _ = self.chat_input(raw)
        client = await self.runtime_client(owner_id, ref)
        try:
            chat = await self.retry(lambda: client.get_chat(chat_input))
            me = await self.retry(client.get_me)
            membership = await self.retry(lambda: client.get_chat_member(chat.id, me.id))
            status = getattr(membership, "status", None)
            allowed = status in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, "owner", "administrator"}
            privileges = getattr(membership, "privileges", None)
            can_post = getattr(privileges, "can_post_messages", True) if privileges else True
            if not allowed or not can_post:
                raise EngineError("This bot/userbot must be an admin with permission to post in the target channel.")
        except EngineError:
            raise
        except RPCError as exc:
            raise EngineError(f"Cannot use target: {self.clean_error(exc)}") from exc
        return {"id": chat.id, "title": chat.title or chat.username or str(chat.id), "username": chat.username or ""}

    async def latest_message_id(self, owner_id: int, ref: str, chat_id: int) -> int:
        client = await self.runtime_client(owner_id, ref)
        try:
            async for message in client.get_chat_history(chat_id, limit=1):
                return int(message.id)
        except RPCError as exc:
            raise EngineError(f"Cannot read source history: {self.clean_error(exc)}") from exc
        raise EngineError("The source channel has no messages to forward.")

    # --- Job setup and scheduling -------------------------------------------
    async def create_job(
        self,
        owner_id: int,
        ref: str,
        source: dict[str, Any],
        targets: list[dict[str, Any]],
        skip: int,
        end_id: int,
        settings_snapshot: dict[str, Any],
        progress_chat_id: int | None = None,
        progress_message_id: int | None = None,
    ) -> str:
        active = await self.db.get_active_job(owner_id)
        if active:
            raise EngineError("You already have an active forwarding job. Cancel it first.")
        start_id = max(1, int(skip) + 1)
        if end_id < start_id:
            raise EngineError("The last message must be after the skipped range.")
        document = {
            "owner_id": owner_id,
            "bot_ref": ref,
            "source": source,
            "targets": targets,
            "start_id": start_id,
            "end_id": end_id,
            "last_id": start_id - 1,
            "stats": {
                "fetched": 0,
                "forwarded": 0,
                "duplicate": 0,
                "deleted": 0,
                "filtered": 0,
                "skipped": 0,
                "errors": 0,
            },
            "settings_snapshot": settings_snapshot,
            "mode_flags": dict(settings_snapshot.get("modes", {})),
            "progress_chat_id": progress_chat_id,
            "progress_message_id": progress_message_id,
        }
        job_id = await self.db.create_job(document)
        job = await self.db.get_job(owner_id, job_id)
        if not job:
            raise EngineError("Could not save the forwarding job.")
        await self._attach_live(job)
        self._spawn_history(job)
        return job_id

    async def create_delta_job(
        self, owner_id: int, ref: str, source: dict[str, Any], target: dict[str, Any], settings: dict[str, Any]
    ) -> str:
        settings = {**settings, "modes": {**settings.get("modes", {}), "delta": True}}
        end_id = await self.latest_message_id(owner_id, ref, int(source["id"]))
        return await self.create_job(owner_id, ref, source, [target], 0, end_id, settings)

    async def restore_jobs(self) -> None:
        """Reattach live listeners and resume uncompleted history after a clean restart."""
        async for job in self.db.active_jobs():
            try:
                await self._attach_live(job)
                if not job.get("history_done"):
                    self._spawn_history(job)
            except Exception:
                log.exception("Could not restore job %s", job.get("_id"))
                await self.db.update_job(str(job["_id"]), {"state": "paused", "last_error": "Startup recovery failed"})

    async def _attach_live(self, job: dict[str, Any]) -> None:
        owner_id, ref = int(job["owner_id"]), str(job["bot_ref"])
        await self.runtime_client(owner_id, ref)
        self._live[(ref, int(job["source"]["id"]))] = str(job["_id"])

    def _spawn_history(self, job: dict[str, Any]) -> None:
        job_id = str(job["_id"])
        existing = self._history_tasks.get(job_id)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self._run_history(job_id), name=f"zc-history-{job_id}")
        self._history_tasks[job_id] = task

    async def cancel_job(self, owner_id: int, job_id: str) -> bool:
        cancelled = await self.db.cancel_job(owner_id, job_id)
        if cancelled:
            job = await self.db.get_job(owner_id, job_id)
            if job:
                self._live.pop((str(job["bot_ref"]), int(job["source"]["id"])), None)
            task = self._history_tasks.get(job_id)
            if task:
                task.cancel()
        return cancelled

    # --- History and live forwarding ----------------------------------------
    async def _run_history(self, job_id: str) -> None:
        job = await self._get_job_any_owner(job_id)
        if not job:
            return
        start = max(int(job.get("start_id", 1)), int(job.get("last_id", 0)) + 1)
        end = int(job["end_id"])
        last_progress = 0.0
        try:
            client = await self.runtime_client(int(job["owner_id"]), str(job["bot_ref"]))
            for first in range(start, end + 1, 100):
                current = await self._get_job_any_owner(job_id)
                if not current or current.get("state") != "running":
                    return
                ids = list(range(first, min(first + 100, end + 1)))
                source_id = int(current["source"]["id"])
                messages = await self.retry(
                    lambda source_id=source_id, message_ids=ids: client.get_messages(source_id, message_ids)
                )
                for message_id, message in zip(ids, messages, strict=False):
                    current = await self._get_job_any_owner(job_id)
                    if not current or current.get("state") != "running":
                        return
                    await self._process_message(current, message, message_id)
                    # A checkpoint is committed for every ID; resilient restarts matter more than a few writes.
                    await self.db.update_job(job_id, {"last_id": message_id})
                    if time.monotonic() - last_progress >= 6:
                        await self._update_progress(job_id)
                        last_progress = time.monotonic()
                    await asyncio.sleep(0.35)
            await self.db.update_job(job_id, {"history_done": True})
            await self._update_progress(job_id, final_history=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("History worker failed for job %s", job_id)
            await self.db.update_job(job_id, {"state": "paused", "last_error": self.clean_error(exc)})
            await self._update_progress(job_id, error=self.clean_error(exc))

    async def _process_live(self, job_id: str, message: Any) -> None:
        job = await self._get_job_any_owner(job_id)
        if not job or job.get("state") != "running":
            return
        # History and channel updates can overlap during setup. The checkpoint prevents a double send.
        if not job.get("history_done") and int(message.id) <= int(job.get("end_id", 0)):
            return
        await self._process_message(job, message, int(message.id))
        await self.db.update_job(job_id, {"last_id": max(int(job.get("last_id", 0)), int(message.id))})
        await self._update_progress(job_id)

    async def _process_message(self, job: dict[str, Any], message: Any, message_id: int) -> None:
        job_id = str(job["_id"])
        stats = dict(job.get("stats", {}))
        stats["fetched"] = int(stats.get("fetched", 0)) + 1
        if not message or getattr(message, "empty", False) or getattr(message, "service", None):
            stats["skipped"] = int(stats.get("skipped", 0)) + 1
            await self.db.update_job(job_id, {"stats": stats})
            return

        info = media_info(message)
        source = job["source"]
        info.source_link = source_post_link(source["id"], source.get("username"), message_id)
        settings = dict(job.get("settings_snapshot", {}))
        result = apply_pipeline(info, settings, sequence=int(stats.get("forwarded", 0)))
        if not result.accepted:
            stats["filtered" if result.reason in {"filtered", "mode"} else "skipped"] = (
                int(stats.get("filtered" if result.reason in {"filtered", "mode"} else "skipped", 0)) + 1
            )
            await self.db.update_job(job_id, {"stats": stats})
            return
        claimed_signature = ""
        if result.signature:
            claimed = await self.db.claim_seen(
                int(job["owner_id"]), result.signature, {"name": info.filename, "size": info.size}
            )
            if not claimed:
                stats["duplicate"] = int(stats.get("duplicate", 0)) + 1
                await self.db.update_job(job_id, {"stats": stats})
                return
            claimed_signature = result.signature

        try:
            await self._copy_to_targets(job, message, info, result.text)
            stats["forwarded"] = int(stats.get("forwarded", 0)) + 1
        except RPCError as exc:
            if claimed_signature:
                await self.db.release_seen(int(job["owner_id"]), claimed_signature)
            stats["errors"] = int(stats.get("errors", 0)) + 1
            log.warning("Forward copy failed for %s: %s", job_id, self.clean_error(exc))
        except Exception:
            if claimed_signature:
                await self.db.release_seen(int(job["owner_id"]), claimed_signature)
            stats["errors"] = int(stats.get("errors", 0)) + 1
            log.exception("Unexpected forwarding error for %s", job_id)
        await self.db.update_job(job_id, {"stats": stats})

    async def _copy_to_targets(self, job: dict[str, Any], message: Any, info: MediaInfo, text: str) -> None:
        client = await self.runtime_client(int(job["owner_id"]), str(job["bot_ref"]))
        rows = settings_buttons(job.get("settings_snapshot", {}).get("buttons", []))
        reply_markup = (
            InlineKeyboardMarkup([[InlineKeyboardButton(label, url=url) for label, url in row] for row in rows])
            if rows
            else None
        )
        for index, target in enumerate(job["targets"]):
            target_id = int(target["id"])
            if info.is_text:
                await self.retry(
                    lambda target_id=target_id: client.send_message(
                        target_id,
                        text or "‎",
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_markup=reply_markup,
                    )
                )
            else:
                # copy_message retains media in Telegram's cloud and does not download it to this server.
                # Telegram only accepts replacement captions for caption-capable media.
                copy_kwargs: dict[str, Any] = {"reply_markup": reply_markup}
                if info.kind in {"photo", "video", "document", "audio", "voice", "animation"}:
                    copy_kwargs.update({"caption": text, "parse_mode": ParseMode.HTML})
                await self.retry(
                    lambda target_id=target_id, copy_kwargs=copy_kwargs: client.copy_message(
                        target_id,
                        int(job["source"]["id"]),
                        int(message.id),
                        **copy_kwargs,
                    )
                )
            if index < len(job["targets"]) - 1:
                await asyncio.sleep(0.45)

    # --- Progress and clean error handling ---------------------------------
    async def _update_progress(self, job_id: str, final_history: bool = False, error: str = "") -> None:
        job = await self._get_job_any_owner(job_id)
        if not job:
            return
        chat_id, message_id = job.get("progress_chat_id"), job.get("progress_message_id")
        if not chat_id or not message_id:
            return
        stats = job.get("stats", {})
        total = max(1, int(job.get("end_id", 0)) - int(job.get("start_id", 1)) + 1)
        completed = max(0, int(job.get("last_id", 0)) - int(job.get("start_id", 1)) + 1)
        percent = min(100, int(completed * 100 / total))
        state_line = (
            "✅ History complete — live forwarding remains active." if final_history else "🔄 Forwarding in progress"
        )
        if error:
            state_line = f"⚠️ Paused: {error}"
        text = sc(
            f"{state_line}\n\n"
            f"📦 Fetched: {stats.get('fetched', 0)}\n"
            f"✅ Forwarded: {stats.get('forwarded', 0)}\n"
            f"♻️ Duplicate: {stats.get('duplicate', 0)}\n"
            f"🚫 Filtered: {stats.get('filtered', 0)}\n"
            f"⏭️ Skipped: {stats.get('skipped', 0)}\n"
            f"❌ Errors: {stats.get('errors', 0)}\n"
            f"📊 Progress: {percent}% ({completed}/{total})"
        )
        try:
            await self.control_bot.edit_message_text(
                int(chat_id),
                int(message_id),
                text,
                reply_markup=markup(
                    [
                        [
                            button(int(job["owner_id"]), "🔴 Cancel", f"fw:cancel:{job_id}"),
                            button(int(job["owner_id"]), "🔵 Refresh", f"fw:refresh:{job_id}"),
                        ]
                    ]
                ),
            )
        except RPCError:
            # Users can delete the progress message. The job must carry on regardless.
            pass

    async def _get_job_any_owner(self, job_id: str) -> dict[str, Any] | None:
        try:
            return await self.db.jobs.find_one({"_id": ObjectId(job_id)})
        except (InvalidId, TypeError):
            return None

    @staticmethod
    async def retry(operation: Callable[[], Awaitable[Any]]) -> Any:
        while True:
            try:
                return await operation()
            except FloodWait as exc:
                seconds = int(getattr(exc, "value", 1) or 1)
                await asyncio.sleep(seconds)

    @staticmethod
    def clean_error(error: BaseException) -> str:
        text = str(error).replace("\n", " ")
        # Tokens/session strings must never accidentally be surfaced.
        text = re.sub(r"\d{7,}:[A-Za-z0-9_-]{20,}", "[redacted]", text)
        return text[:260] or error.__class__.__name__

    async def unequify(
        self, owner_id: int, ref: str, raw_chat: str, progress: Callable[[str], Awaitable[None]] | None = None
    ) -> tuple[int, int]:
        """Delete repeated media only where the chosen identity has ordinary delete rights."""
        chat, _ = self.chat_input(raw_chat)
        client = await self.runtime_client(owner_id, ref)
        seen: set[str] = set()
        scanned = deleted = 0
        batch: list[int] = []
        try:
            async for message in client.get_chat_history(chat):
                scanned += 1
                signature = media_info(message).unique_id
                if signature and signature in seen:
                    batch.append(int(message.id))
                elif signature:
                    seen.add(signature)
                if len(batch) >= 100:
                    await self.retry(lambda: client.delete_messages(chat, batch))
                    deleted += len(batch)
                    batch.clear()
                if progress and scanned % 100 == 0:
                    await progress(sc(f"🔄 Scanned {scanned} messages; deleted {deleted} duplicates."))
            if batch:
                await self.retry(lambda: client.delete_messages(chat, batch))
                deleted += len(batch)
        except RPCError as exc:
            raise EngineError(f"Could not scan/delete in that channel: {self.clean_error(exc)}") from exc
        return scanned, deleted


def settings_buttons(value: Any) -> list[list[tuple[str, str]]]:
    """Stored structured button rows are already validated by modes.parse_buttons."""
    if not isinstance(value, list):
        return []
    rows: list[list[tuple[str, str]]] = []
    for row in value:
        if not isinstance(row, list):
            continue
        clean = []
        for item in row:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                label, url = str(item[0]), str(item[1])
                if url.startswith(("http://", "https://")):
                    clean.append((label[:64], url))
        if clean:
            rows.append(clean)
    return rows
