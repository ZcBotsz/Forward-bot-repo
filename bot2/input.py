"""Durable conversation-input router.

All setup messages are deleted after being read. Secrets are never written to logs or plain
flow documents; phone-login client objects live only in memory and require a restart if lost.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from typing import Any

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError, SessionPasswordNeeded
from pyrogram.types import Message

from ..engine import EngineError
from ..modes import parse_buttons
from ..services import Services
from ..ui import back, button, markup, sc
from .common import animated_edit, is_allowed, owner_only, safe_delete
from .forward import confirmation_text

log = logging.getLogger(__name__)
_LOGIN_CLIENTS: dict[int, tuple[Client, Any, str]] = {}


async def _stop_login(user_id: int) -> None:
    record = _LOGIN_CLIENTS.pop(user_id, None)
    if not record:
        return
    client = record[0]
    try:
        await client.disconnect()
    except Exception as exc:  # noqa: BLE001 - cleanup must not expose login data to a user
        log.debug("Login client disconnect failed: %s", type(exc).__name__)
        try:
            await client.stop()
        except Exception as stop_exc:  # noqa: BLE001 - best-effort cleanup only
            log.debug("Login client stop failed: %s", type(stop_exc).__name__)


async def _export_session(client: Client) -> str:
    result = client.export_session_string()
    return await result if inspect.isawaitable(result) else result


async def _save_userbot(user_id: int, client: Client, services: Services) -> tuple[str, int, str]:
    me = await client.get_me()
    session = await _export_session(client)
    await services.db.add_userbot(user_id, session, me.first_name or "Userbot", me.username or "", me.id)
    return me.first_name or "Userbot", me.id, me.username or ""


async def _send(message: Message, text: str, keyboard: Any = None) -> Message:
    """Send without replying to the setup input (which has already been deleted)."""
    client = getattr(message, "_client", None)
    if client is not None:
        sent = await client.send_message(
            message.chat.id, sc(text), reply_markup=keyboard, disable_web_page_preview=True
        )
    else:
        # Fallback keeps unit-test fakes and unusual library builds usable.
        sent = await message.reply_text(sc(text), reply_markup=keyboard)
    if sent is None:
        raise RuntimeError("Telegram did not return the status message")
    return sent


async def _done(message: Message, text: str, keyboard: Any = None) -> None:
    await _send(message, text, keyboard)


async def _flow_error(message: Message, text: str) -> None:
    await _done(message, f"❌ {text}", back(message.from_user.id, "settings:home"))


def _text(message: Message) -> str:
    return str(message.text or message.caption or "").strip()


async def _update_nested(services: Services, user_id: int, top: str, sub: str, value: Any) -> None:
    settings = await services.db.get_settings(user_id)
    current = dict(settings.get(top, {}))
    current[sub] = value
    await services.db.set_setting(user_id, top, current)


async def _handle_input(message: Message, services: Services, flow: dict[str, Any], content: str) -> None:
    user_id, kind, data = message.from_user.id, flow["kind"], dict(flow.get("data", {}))

    if kind == "BOT_TOKEN":
        token = content
        if ":" not in token or len(token) < 25:
            await _flow_error(message, "That does not look like a valid bot token.")
            return
        await _done(message, "🔄 Connecting to bot…")
        identity = {"kind": "bot", "_id": f"check{user_id}", "token_enc": services.db.encrypt(token)}
        client = await services.engine._new_identity_client(identity, "check", updates=False)
        try:
            await client.start()
            me = await client.get_me()
            await services.db.add_bot(user_id, token, me.first_name or "Bot", me.username or "", me.id)
            await services.db.clear_flow(user_id)
            await _done(
                message,
                f"✅ Bot added successfully!\n📝 Name: {me.first_name}\n🆔 Bot ID: {me.id}\n🤖 Username: @{me.username or 'none'}",
                markup([[button(user_id, "🔵 Back to Settings", "settings:bots")]]),
            )
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await _flow_error(message, f"Bot token error: {services.engine.clean_error(exc)}")
        finally:
            try:
                await client.stop()
            except Exception as stop_exc:  # noqa: BLE001 - token-validation cleanup is best effort
                log.debug("Bot validation client stop failed: %s", type(stop_exc).__name__)
        return

    if kind == "USERBOT_PHONE":
        phone = content.replace(" ", "")
        if not re.fullmatch(r"\+\d{7,15}", phone):
            await _flow_error(message, "Send a valid phone number with + and country code.")
            return
        await _stop_login(user_id)
        client = Client(
            name=f"zc_login_{user_id}",
            api_id=services.config.api_id,
            api_hash=services.config.api_hash,
            in_memory=True,
            no_updates=True,
            workdir=str(services.config.workdir),
        )
        status = await _send(message, "📨 Sending OTP code.")
        try:
            await client.connect()
            animation = asyncio.create_task(animated_edit(status, "📨 Sending OTP code"))
            sent = await client.send_code(phone)
            await animation
            _LOGIN_CLIENTS[user_id] = (client, sent, phone)
            # Keep phone/code-hash state only in process memory, never in a flow document.
            await services.db.set_flow(user_id, "USERBOT_OTP")
            await status.edit_text(
                sc(
                    "✅ OTP code sent successfully!\n\n🔐 Send the OTP code received from Telegram.\n⚠️ Important: add ZC before your code. Example: if OTP is 12345, send <code>ZC12345</code>"
                )
            )
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await _stop_login(user_id)
            await _flow_error(message, f"User Bot Error: {services.engine.clean_error(exc)}")
        return

    if kind == "USERBOT_OTP":
        if not content.upper().startswith("ZC") or not content[2:].strip():
            await _done(message, "⚠️ Send the code with the ZC prefix. Example: <code>ZC12345</code>")
            return
        login = _LOGIN_CLIENTS.get(user_id)
        if not login:
            await services.db.clear_flow(user_id)
            await _flow_error(message, "The login session expired or the bot restarted. Start phone login again.")
            return
        client, sent, phone = login
        try:
            await _done(message, "🔄 Verifying session…")
            await client.sign_in(phone, sent.phone_code_hash, content[2:].strip())
            name, account_id, username = await _save_userbot(user_id, client, services)
            await services.db.clear_flow(user_id)
            await _stop_login(user_id)
            await _done(
                message,
                f"✅ Userbot added successfully!\n📝 Name: {name}\n🆔 User ID: {account_id}\n👤 Username: @{username or 'none'}",
                markup([[button(user_id, "🔵 Back to Settings", "settings:bots")]]),
            )
        except SessionPasswordNeeded:
            await services.db.set_flow(user_id, "USERBOT_PASSWORD")
            await _done(message, "🔒 Your account has 2FA enabled. Send your password. /cancel")
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await _done(
                message,
                f"❌ User Bot Error: {services.engine.clean_error(exc)}\nTry again with a fresh ZC-prefixed OTP or /cancel.",
            )
        return

    if kind == "USERBOT_PASSWORD":
        login = _LOGIN_CLIENTS.get(user_id)
        if not login:
            await services.db.clear_flow(user_id)
            await _flow_error(message, "The login session expired. Start phone login again.")
            return
        client = login[0]
        try:
            await _done(message, "🔄 Verifying session…")
            await client.check_password(content)
            name, account_id, username = await _save_userbot(user_id, client, services)
            await services.db.clear_flow(user_id)
            await _stop_login(user_id)
            await _done(
                message,
                f"✅ Userbot added successfully!\n📝 Name: {name}\n🆔 User ID: {account_id}\n👤 Username: @{username or 'none'}",
                markup([[button(user_id, "🔵 Back to Settings", "settings:bots")]]),
            )
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await _done(message, f"❌ User Bot Error: {services.engine.clean_error(exc)}")
        return

    if kind == "USERBOT_SESSION":
        if len(content) < 50:
            await _flow_error(message, "That session string is too short.")
            return
        client = Client(
            name=f"zc_session_check_{user_id}",
            api_id=services.config.api_id,
            api_hash=services.config.api_hash,
            session_string=content,
            in_memory=True,
            no_updates=True,
            workdir=str(services.config.workdir),
        )
        try:
            await _done(message, "🔄 Verifying session…")
            await client.start()
            me = await client.get_me()
            canonical_session = await _export_session(client)
            await services.db.add_userbot(
                user_id, canonical_session, me.first_name or "Userbot", me.username or "", me.id
            )
            await services.db.clear_flow(user_id)
            await _done(
                message,
                f"✅ Userbot added successfully!\n📝 Name: {me.first_name}\n🆔 User ID: {me.id}\n👤 Username: @{me.username or 'none'}",
                markup([[button(user_id, "🔵 Back to Settings", "settings:bots")]]),
            )
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await _flow_error(message, f"User Bot Error: {services.engine.clean_error(exc)}")
        finally:
            try:
                await client.stop()
            except Exception as stop_exc:  # noqa: BLE001 - session-validation cleanup is best effort
                log.debug("Session validation client stop failed: %s", type(stop_exc).__name__)
        return

    if kind == "CAPTION":
        await services.db.set_setting(user_id, "caption", content)
        await services.db.clear_flow(user_id)
        await _done(
            message, "✅ Caption successfully updated", markup([[button(user_id, "🔵 Back", "settings:caption")]])
        )
        return

    if kind == "DATABASE_URI":
        if not content.startswith("mongodb"):
            await _flow_error(message, "A MongoDB URI must start with mongodb:// or mongodb+srv://.")
            return
        try:
            await _done(message, "🔄 Testing database connection…")
            await services.db.test_user_mongo_uri(content)
            await services.db.set_setting(user_id, "db_uri_enc", services.db.encrypt(content))
            await services.db.clear_flow(user_id)
            await _done(
                message, "✅ Personal duplicate database connected and encrypted.", back(user_id, "settings:database")
            )
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await _flow_error(message, f"Database connection failed: {services.engine.clean_error(exc)}")
        return

    if kind == "CUSTOM_BUTTON":
        try:
            parsed = parse_buttons(content)
            await services.db.set_setting(user_id, "buttons", [[list(item) for item in row] for row in parsed])
            await services.db.clear_flow(user_id)
            await _done(message, "✅ Successfully button added", back(user_id, "settings:button"))
        except ValueError as exc:
            await _done(message, f"❌ {exc}")
        return

    if kind in {"SKIP_EXTENSIONS", "SKIP_KEYWORDS", "MAX_SIZE"}:
        settings = await services.db.get_settings(user_id)
        values = dict(settings["filters"])
        try:
            if kind == "SKIP_EXTENSIONS":
                values["skip_extensions"] = (
                    []
                    if content.lower() == "clear"
                    else [part.strip().lower().lstrip(".") for part in content.split(",") if part.strip()]
                )
            elif kind == "SKIP_KEYWORDS":
                values["skip_keywords"] = (
                    [] if content.lower() == "clear" else [part.strip() for part in content.split(",") if part.strip()]
                )
            else:
                size = float(content)
                if size < 0 or size > 102400:
                    raise ValueError
                values["max_size_mb"] = size
        except ValueError:
            await _done(message, "❌ Send a valid non-negative size in MB.")
            return
        await services.db.set_setting(user_id, "filters", values)
        await services.db.clear_flow(user_id)
        await _done(message, "✅ Skip rule saved.", back(user_id, "settings:rules"))
        return

    if kind in {"WATERMARK_PREFIX", "WATERMARK_SUFFIX"}:
        await _update_nested(services, user_id, "watermark", kind.rsplit("_", 1)[1].lower(), content)
        await services.db.clear_flow(user_id)
        await _done(message, "✅ Watermark option saved.", back(user_id, "manager:watermark"))
        return

    if kind in {"REPLACER_LINK", "REPLACER_USERNAME"}:
        key = "link" if kind.endswith("LINK") else "username"
        if key == "link" and content.lower() != "clear" and not content.startswith(("https://", "http://")):
            await _done(message, "❌ Send a full https:// link or clear.")
            return
        if key == "username" and content.lower() != "clear" and not re.fullmatch(r"@?[A-Za-z0-9_]{4,}", content):
            await _done(message, "❌ Send a valid @username or clear.")
            return
        await _update_nested(services, user_id, "replacer", key, "" if content.lower() == "clear" else content)
        await services.db.clear_flow(user_id)
        await _done(message, "✅ Replacer option saved.", back(user_id, "manager:replacer"))
        return

    if kind == "REPLACER_PAIR_OLD":
        await services.db.set_flow(user_id, "REPLACER_PAIR_NEW", {"old": content})
        await _done(message, "Send the replacement text. /cancel")
        return

    if kind == "REPLACER_PAIR_NEW":
        settings = await services.db.get_settings(user_id)
        values = dict(settings["replacer"])
        pairs = list(values.get("pairs", []))
        pairs.append({"old": data["old"], "new": content})
        values["pairs"] = pairs[:100]
        await services.db.set_setting(user_id, "replacer", values)
        await services.db.clear_flow(user_id)
        await _done(message, "✅ Word pair saved.", back(user_id, "manager:replacer"))
        return

    if kind == "NUMBERING_START":
        try:
            number = int(content)
            if number < 0 or number > 1_000_000:
                raise ValueError
        except ValueError:
            await _done(message, "❌ Send a whole number from 0 to 1000000.")
            return
        await _update_nested(services, user_id, "numbering", "start", number)
        await services.db.clear_flow(user_id)
        await _done(message, "✅ Numbering start saved.", back(user_id, "manager:numbering"))
        return

    if kind == "BULLETS":
        items = [item.strip() for item in content.split(",") if item.strip()]
        if not items or any(len(item) > 16 for item in items):
            await _done(message, "❌ Send one or more short emoji values, separated by commas.")
            return
        await _update_nested(services, user_id, "bullets", "items", items[:30])
        await services.db.clear_flow(user_id)
        await _done(message, "✅ Bullet options saved.", back(user_id, "manager:bullets"))
        return

    if kind == "SELLER":
        await _update_nested(services, user_id, "seller", "name", content[:100])
        await services.db.clear_flow(user_id)
        await _done(message, "✅ Seller name saved.", back(user_id, "manager:seller"))
        return

    if kind == "PI_TARGET":
        try:
            services.engine.chat_input(content)
        except EngineError as exc:
            await _done(message, f"❌ {exc}")
            return
        settings = await services.db.get_settings(user_id)
        pi_targets = list(settings.get("pi_targets", []))
        if content not in pi_targets:
            pi_targets.append(content)
        await services.db.set_setting(user_id, "pi_targets", pi_targets[:20])
        await services.db.clear_flow(user_id)
        await _done(message, "✅ Pi target saved.", back(user_id, "manager:pi"))
        return

    if kind == "DELTA_SOURCE":
        try:
            services.engine.chat_input(content)
        except EngineError as exc:
            await _done(message, f"❌ {exc}")
            return
        await services.db.set_flow(user_id, "DELTA_TARGET", {"source": content})
        await _done(message, "Send the Delta target channel ID or @username. /cancel")
        return

    if kind == "DELTA_TARGET":
        try:
            services.engine.chat_input(content)
        except EngineError as exc:
            await _done(message, f"❌ {exc}")
            return
        await services.db.set_flow(user_id, "DELTA_CLIENT", {"source": data["source"], "target": content})
        identities = await services.db.list_identities(user_id)
        if not identities:
            await _flow_error(message, "Add a bot or userbot first.")
            return
        rows = [
            [
                button(
                    user_id,
                    f"{'🤖' if identity['kind'] == 'bot' else '👤'} {identity.get('name')}",
                    f"delta:client:{identity['ref']}",
                )
            ]
            for identity in identities
        ]
        await _done(message, "Choose the identity for this Delta job.", markup(rows))
        return

    if kind == "FW_SOURCE":
        try:
            source, _ = await services.engine.resolve_source(user_id, data["ref"], content)
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await _done(message, f"❌ Source validation failed: {services.engine.clean_error(exc)}")
            return
        data["source"] = source
        await services.db.set_flow(user_id, "FW_TARGET", data)
        await _done(
            message,
            "Send the TARGET channel ID, @username, or link. The selected bot/userbot must be admin there. /cancel",
        )
        return

    if kind == "FW_TARGET":
        try:
            target = await services.engine.resolve_target(user_id, data["ref"], content)
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await _done(message, f"❌ Target validation failed: {services.engine.clean_error(exc)}")
            return
        data["target"] = target
        await services.db.set_flow(user_id, "FW_SKIP", data)
        await _done(
            message, "How many source messages should be skipped from the start? Send <code>0</code> for none. /cancel"
        )
        return

    if kind == "FW_SKIP":
        try:
            skip = int(content)
            if skip < 0 or skip > 100_000_000:
                raise ValueError
        except ValueError:
            await _done(message, "❌ Send a non-negative whole number.")
            return
        data["skip"] = skip
        await services.db.set_flow(user_id, "FW_END", data)
        await _done(message, "Send the last source message ID or a link to that source message. /cancel")
        return

    if kind == "FW_END":
        try:
            _, linked_id = services.engine.chat_input(content)
            end_id = linked_id or int(content)
            if end_id <= int(data["skip"]):
                raise ValueError
        except (EngineError, ValueError):
            await _done(message, "❌ Send a valid last message ID/link after the skipped range.")
            return
        settings = await services.db.get_settings(user_id)
        data.update({"end_id": end_id, "modes": settings.get("modes", {})})
        await services.db.set_flow(user_id, "FW_CONFIRM", data)
        await _done(
            message,
            confirmation_text(data),
            markup(
                [
                    [button(user_id, "🟢 Yes", "fw:confirm"), button(user_id, "🔴 No", "fw:no")],
                    [button(user_id, "🔵 Back", "fw:no")],
                ]
            ),
        )
        return

    if kind == "UNEQUIFY_CHANNEL":
        status = await _send(message, "🔄 Scanning for duplicate media…")
        try:

            async def progress(text: str) -> None:
                await status.edit_text(text)

            scanned, deleted = await services.engine.unequify(user_id, data["ref"], content, progress)
            await services.db.clear_flow(user_id)
            await status.edit_text(
                sc(f"✅ Unequify complete.\nScanned: {scanned}\nDuplicates deleted: {deleted}"),
                reply_markup=back(user_id, "home"),
            )
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            await status.edit_text(
                sc(f"❌ Unequify failed: {services.engine.clean_error(exc)}"), reply_markup=back(user_id, "home")
            )
        return

    # Admin flows remain owner-checked even though callbacks are hidden from non-owners.
    if kind.startswith("ADMIN_"):
        if not owner_only(user_id, services):
            await services.db.clear_flow(user_id)
            return
        if kind == "ADMIN_GRANT_ID":
            try:
                target_id = int(content)
            except ValueError:
                await _done(message, "❌ Send a numeric user ID.")
                return
            if not await services.db.get_user(target_id):
                await _done(message, "❌ That user has not started the bot.")
                return
            await services.db.set_flow(user_id, "ADMIN_GRANT_PLAN", {"target": target_id})
            await _done(
                message,
                "Choose a plan.",
                markup(
                    [
                        [
                            button(user_id, "⭐ Plus", "admin:grantplan:plus"),
                            button(user_id, "💎 Pro", "admin:grantplan:pro"),
                        ],
                        [
                            button(user_id, "♾️ Infinity", "admin:grantplan:infinity"),
                            button(user_id, "🚀 Ultra", "admin:grantplan:ultra"),
                        ],
                    ]
                ),
            )
        elif kind == "ADMIN_GRANT_DAYS":
            try:
                days = int(content or "30")
                if days < 1 or days > 3650:
                    raise ValueError
            except ValueError:
                await _done(message, "❌ Send a day count from 1 to 3650.")
                return
            ok = await services.db.set_plan(int(data["target"]), str(data["plan"]), days)
            await services.db.clear_flow(user_id)
            await _done(
                message,
                f"✅ {'Granted' if ok else 'Could not grant'} {data['plan'].title()} for {days} days.",
                back(user_id, "admin:home"),
            )
        elif kind == "ADMIN_REVOKE_ID":
            try:
                target_id = int(content)
            except ValueError:
                await _done(message, "❌ Send a numeric user ID.")
                return
            await services.db.set_plan(target_id, "free")
            await services.db.clear_flow(user_id)
            await _done(message, "✅ Plan revoked.", back(user_id, "admin:home"))
        elif kind == "ADMIN_BAN_ID" or kind == "ADMIN_UNBAN_ID":
            try:
                target_id = int(content)
            except ValueError:
                await _done(message, "❌ Send a numeric user ID.")
                return
            await services.db.set_banned(target_id, kind == "ADMIN_BAN_ID")
            await services.db.clear_flow(user_id)
            await _done(message, "✅ User updated.", back(user_id, "admin:home"))
        elif kind == "ADMIN_BROADCAST":
            delivered = failed = 0
            for broadcast_user_id in [user async for user in services.db.all_user_ids()]:
                try:
                    await services.engine.retry(
                        lambda broadcast_user_id=broadcast_user_id: services.app.send_message(
                            broadcast_user_id, content, parse_mode=ParseMode.HTML, disable_web_page_preview=True
                        )
                    )
                    delivered += 1
                except (OSError, RPCError):
                    failed += 1
            await services.db.clear_flow(user_id)
            await _done(
                message,
                f"✅ Broadcast finished. Delivered: {delivered}; failed/blocked: {failed}.",
                back(user_id, "admin:home"),
            )
        return

    if kind == "TRANSFER":
        try:
            transfer_target_id = int(content)
        except ValueError:
            await _done(message, "❌ Send a numeric Telegram user ID.")
            return
        ok, result = await services.db.transfer_plan(user_id, transfer_target_id)
        if ok:
            await services.db.clear_flow(user_id)
        await _done(message, ("✅ " if ok else "❌ ") + result, back(user_id, "home"))
        return


def register(app: Client, services: Services) -> None:
    @app.on_message(
        filters.private
        & ~filters.command(
            ["start", "help", "settings", "forward", "unequify", "myplan", "transfer", "cancel", "reset", "admin"],
            prefixes="/",
        ),
        group=0,
    )
    async def input_router(_: Client, message: Message) -> None:
        if not message.from_user or message.from_user.is_bot:
            return
        await services.db.ensure_user(message.from_user.id, message.from_user.first_name or "User")
        if not await is_allowed(message, services):
            return
        flow = await services.db.get_flow(message.from_user.id)
        if not flow:
            return
        content = _text(message)
        await safe_delete(message)
        if not content:
            await _done(message, "❌ Send text for this step, or /cancel.")
            return
        try:
            await _handle_input(message, services, flow, content)
        except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
            # Do not leak raw internals; errors remain logged server-side by the main exception logger.
            await _done(message, f"❌ Something went wrong: {services.engine.clean_error(exc)}")
