"""MongoDB persistence with encrypted secret fields and owner-scoped queries."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from bson.errors import InvalidId
from cryptography.fernet import Fernet
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import ConfigurationError, DuplicateKeyError, PyMongoError

from .config import default_settings

log = logging.getLogger(__name__)
UTC = UTC


def now() -> datetime:
    return datetime.now(UTC)


class Database:
    """Repository layer. All methods that expose user-owned data require owner_id."""

    def __init__(self, mongo_uri: str, encryption_key: str) -> None:
        self._client: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=8000)
        try:
            self._db: AsyncIOMotorDatabase = self._client.get_default_database()
        except ConfigurationError:
            # Atlas URIs are often supplied without a trailing database name.
            self._db = self._client["zc_forward_bot"]
        self._fernet = Fernet(encryption_key.encode())
        self._user_db_clients: dict[int, AsyncIOMotorClient] = {}
        self._user_db_lock = asyncio.Lock()

    @property
    def users(self) -> AsyncIOMotorCollection:
        return self._db.users

    @property
    def bots(self) -> AsyncIOMotorCollection:
        return self._db.bots

    @property
    def userbots(self) -> AsyncIOMotorCollection:
        return self._db.userbots

    @property
    def chats(self) -> AsyncIOMotorCollection:
        return self._db.chats

    @property
    def jobs(self) -> AsyncIOMotorCollection:
        return self._db.jobs

    @property
    def seen(self) -> AsyncIOMotorCollection:
        return self._db.seen

    @property
    def flows(self) -> AsyncIOMotorCollection:
        return self._db.flows

    async def connect(self) -> None:
        await self._db.command("ping")
        await self._ensure_indexes()

    async def close(self) -> None:
        self._client.close()
        for client in self._user_db_clients.values():
            client.close()

    async def mongo_version(self) -> str:
        try:
            info = await self._db.client.server_info()
            return str(info.get("version", "unknown"))
        except PyMongoError:
            return "unavailable"

    async def _ensure_indexes(self) -> None:
        await asyncio.gather(
            self.bots.create_index([("owner_id", ASCENDING), ("username", ASCENDING)]),
            self.userbots.create_index([("owner_id", ASCENDING), ("username", ASCENDING)]),
            self.chats.create_index(
                [("owner_id", ASCENDING), ("chat_id", ASCENDING), ("role", ASCENDING)], unique=True
            ),
            self.jobs.create_index([("owner_id", ASCENDING), ("state", ASCENDING)]),
            self.jobs.create_index([("state", ASCENDING), ("updated_at", DESCENDING)]),
            self.seen.create_index([("owner_id", ASCENDING), ("signature", ASCENDING)], unique=True),
            self.flows.create_index("updated_at"),
            self.users.create_index([("plan", ASCENDING), ("plan_expires_at", ASCENDING)]),
        )

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()

    # --- Users and settings -------------------------------------------------
    async def ensure_user(self, user_id: int, name: str) -> dict[str, Any]:
        document = {
            "_id": user_id,
            "name": name[:128],
            "registered_at": now(),
            "plan": "free",
            "plan_expires_at": None,
            "banned": False,
            "settings": default_settings(),
        }
        await self.users.update_one(
            {"_id": user_id}, {"$setOnInsert": document, "$set": {"name": name[:128]}}, upsert=True
        )
        return await self.get_user(user_id) or document

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        return await self.users.find_one({"_id": user_id})

    async def get_settings(self, user_id: int) -> dict[str, Any]:
        user = await self.get_user(user_id)
        if not user:
            await self.ensure_user(user_id, "User")
            user = await self.get_user(user_id)
        settings = default_settings()
        saved = (user or {}).get("settings") or {}
        # One-level recursive merge is enough for this deliberately compact schema.
        for key, value in saved.items():
            if isinstance(settings.get(key), dict) and isinstance(value, dict):
                settings[key].update(value)
            else:
                settings[key] = value
        return settings

    async def set_setting(self, user_id: int, key: str, value: Any) -> None:
        await self.users.update_one({"_id": user_id}, {"$set": {f"settings.{key}": value}})

    async def patch_settings(self, user_id: int, patch: dict[str, Any]) -> None:
        await self.users.update_one(
            {"_id": user_id}, {"$set": {f"settings.{key}": value for key, value in patch.items()}}
        )

    async def reset_settings(self, user_id: int) -> None:
        await self.users.update_one({"_id": user_id}, {"$set": {"settings": default_settings()}})
        await asyncio.gather(
            self.bots.delete_many({"owner_id": user_id}),
            self.userbots.delete_many({"owner_id": user_id}),
            self.chats.delete_many({"owner_id": user_id}),
            self.flows.delete_one({"_id": user_id}),
            self.seen.delete_many({"owner_id": user_id}),
            self.jobs.update_many(
                {"owner_id": user_id, "state": {"$in": ["running", "paused"]}},
                {"$set": {"state": "cancelled", "updated_at": now()}},
            ),
        )

    async def set_plan(self, user_id: int, plan: str, days: int = 30) -> bool:
        expires = None if plan == "free" else now() + timedelta(days=max(1, min(days, 3650)))
        result = await self.users.update_one({"_id": user_id}, {"$set": {"plan": plan, "plan_expires_at": expires}})
        return bool(result.matched_count)

    async def expire_plans(self) -> list[dict[str, Any]]:
        query = {"plan": {"$ne": "free"}, "plan_expires_at": {"$lte": now()}}
        expired = [item async for item in self.users.find(query)]
        if expired:
            await self.users.update_many(query, {"$set": {"plan": "free", "plan_expires_at": None}})
        return expired

    async def set_banned(self, user_id: int, banned: bool) -> bool:
        result = await self.users.update_one({"_id": user_id}, {"$set": {"banned": banned}})
        return bool(result.matched_count)

    async def transfer_plan(self, source_id: int, target_id: int) -> tuple[bool, str]:
        source = await self.get_user(source_id)
        target = await self.get_user(target_id)
        if not source or not target:
            return False, "Both users must have started the bot first."
        if source.get("plan", "free") == "free" or not source.get("plan_expires_at"):
            return False, "You have no active paid plan to transfer."
        if target.get("plan", "free") != "free":
            return False, "The recipient already has a paid plan."
        await self.users.update_one(
            {"_id": target_id}, {"$set": {"plan": source["plan"], "plan_expires_at": source["plan_expires_at"]}}
        )
        await self.users.update_one({"_id": source_id}, {"$set": {"plan": "free", "plan_expires_at": None}})
        return True, "Plan transferred successfully."

    # --- Encrypted bot identities ------------------------------------------
    async def add_bot(self, owner_id: int, token: str, name: str, username: str, bot_id: int) -> str:
        document = {
            "owner_id": owner_id,
            "token_enc": self.encrypt(token),
            "name": name[:128],
            "username": username.lstrip("@"),
            "bot_id": bot_id,
            "created_at": now(),
        }
        result = await self.bots.insert_one(document)
        return str(result.inserted_id)

    async def add_userbot(self, owner_id: int, session: str, name: str, username: str, account_id: int) -> str:
        document = {
            "owner_id": owner_id,
            "session_enc": self.encrypt(session),
            "name": name[:128],
            "username": username.lstrip("@"),
            "account_id": account_id,
            "created_at": now(),
        }
        result = await self.userbots.insert_one(document)
        return str(result.inserted_id)

    async def list_identities(self, owner_id: int) -> list[dict[str, Any]]:
        bots = [
            dict(item, ref=f"bot:{item['_id']}", kind="bot") async for item in self.bots.find({"owner_id": owner_id})
        ]
        userbots = [
            dict(item, ref=f"userbot:{item['_id']}", kind="userbot")
            async for item in self.userbots.find({"owner_id": owner_id})
        ]
        return bots + userbots

    async def get_identity(self, owner_id: int, ref: str) -> dict[str, Any] | None:
        try:
            kind, object_id = ref.split(":", 1)
            from bson import ObjectId

            oid = ObjectId(object_id)
        except (InvalidId, TypeError, ValueError):
            return None
        collection = self.bots if kind == "bot" else self.userbots if kind == "userbot" else None
        if collection is None:
            return None
        item = await collection.find_one({"_id": oid, "owner_id": owner_id})
        if item:
            item["kind"] = kind
            item["ref"] = ref
        return item

    async def delete_identity(self, owner_id: int, ref: str) -> bool:
        try:
            kind, object_id = ref.split(":", 1)
            from bson import ObjectId

            oid = ObjectId(object_id)
        except (InvalidId, TypeError, ValueError):
            return False
        collection = self.bots if kind == "bot" else self.userbots if kind == "userbot" else None
        if collection is None:
            return False
        result = await collection.delete_one({"_id": oid, "owner_id": owner_id})
        return bool(result.deleted_count)

    # --- Chats, jobs and dedupe --------------------------------------------
    async def save_chat(self, owner_id: int, chat_id: int | str, title: str, role: str) -> None:
        await self.chats.update_one(
            {"owner_id": owner_id, "chat_id": chat_id, "role": role},
            {"$set": {"title": title[:256], "updated_at": now()}},
            upsert=True,
        )

    async def chat_count(self) -> int:
        return await self.chats.count_documents({})

    async def create_job(self, document: dict[str, Any]) -> str:
        document.update({"created_at": now(), "updated_at": now(), "state": "running", "history_done": False})
        result = await self.jobs.insert_one(document)
        return str(result.inserted_id)

    async def get_job(self, owner_id: int, job_id: str) -> dict[str, Any] | None:
        try:
            from bson import ObjectId

            oid = ObjectId(job_id)
        except (InvalidId, TypeError):
            return None
        return await self.jobs.find_one({"_id": oid, "owner_id": owner_id})

    async def get_active_job(self, owner_id: int) -> dict[str, Any] | None:
        return await self.jobs.find_one(
            {"owner_id": owner_id, "state": {"$in": ["running", "paused"]}}, sort=[("updated_at", DESCENDING)]
        )

    async def active_jobs(self) -> AsyncIterator[dict[str, Any]]:
        async for job in self.jobs.find({"state": "running"}):
            yield job

    async def update_job(self, job_id: str, patch: dict[str, Any]) -> None:
        from bson import ObjectId

        patch["updated_at"] = now()
        await self.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": patch})

    async def cancel_job(self, owner_id: int, job_id: str) -> bool:
        try:
            from bson import ObjectId

            oid = ObjectId(job_id)
        except (InvalidId, TypeError):
            return False
        result = await self.jobs.update_one(
            {"_id": oid, "owner_id": owner_id, "state": {"$in": ["running", "paused"]}},
            {"$set": {"state": "cancelled", "updated_at": now()}},
        )
        return bool(result.modified_count)

    async def seen_collection(self, owner_id: int) -> AsyncIOMotorCollection:
        settings = await self.get_settings(owner_id)
        encrypted_uri = str(settings.get("db_uri_enc") or "")
        if not encrypted_uri:
            return self.seen
        async with self._user_db_lock:
            client = self._user_db_clients.get(owner_id)
            if client is None:
                uri = self.decrypt(encrypted_uri)
                client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=8000)
                self._user_db_clients[owner_id] = client
                collection = client[f"zc_forward_{owner_id}"].seen
                await collection.create_index("signature", unique=True)
            return client[f"zc_forward_{owner_id}"].seen

    async def claim_seen(self, owner_id: int, signature: str, metadata: dict[str, Any]) -> bool:
        """Atomically claim a media signature. False means another message already used it."""
        settings = await self.get_settings(owner_id)
        uses_personal_db = bool(settings.get("db_uri_enc"))
        collection = await self.seen_collection(owner_id)
        document = {"signature": signature, "created_at": now(), **metadata}
        if not uses_personal_db:
            document["owner_id"] = owner_id
        try:
            await collection.insert_one(document)
            return True
        except DuplicateKeyError:
            return False

    async def release_seen(self, owner_id: int, signature: str) -> None:
        """Release a pre-copy dedupe claim when all target copies failed."""
        settings = await self.get_settings(owner_id)
        collection = await self.seen_collection(owner_id)
        query: dict[str, Any] = {"signature": signature}
        if not settings.get("db_uri_enc"):
            query["owner_id"] = owner_id
        await collection.delete_one(query)

    # --- Durable user-input flow state -------------------------------------
    async def set_flow(self, owner_id: int, kind: str, data: dict[str, Any] | None = None) -> None:
        await self.flows.update_one(
            {"_id": owner_id},
            {"$set": {"kind": kind, "data": data or {}, "updated_at": now()}},
            upsert=True,
        )

    async def get_flow(self, owner_id: int) -> dict[str, Any] | None:
        return await self.flows.find_one({"_id": owner_id})

    async def clear_flow(self, owner_id: int) -> None:
        await self.flows.delete_one({"_id": owner_id})

    # --- Admin reports ------------------------------------------------------
    async def stats(self) -> dict[str, int]:
        return {
            "users": await self.users.count_documents({}),
            "paid_users": await self.users.count_documents({"plan": {"$ne": "free"}}),
            "bots": await self.bots.count_documents({}),
            "userbots": await self.userbots.count_documents({}),
            "channels": await self.chats.count_documents({}),
        }

    async def all_user_ids(self) -> AsyncIterator[int]:
        async for item in self.users.find({}, {"_id": 1, "banned": 1}):
            if not item.get("banned", False):
                yield int(item["_id"])

    async def test_user_mongo_uri(self, uri: str) -> None:
        client: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=8000)
        try:
            await client.admin.command("ping")
        finally:
            client.close()
