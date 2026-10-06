"""Shared callback, message, and safety helpers for handlers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pyrogram.errors import RPCError

from ..ui import action_for, sc

log = logging.getLogger(__name__)


async def is_allowed(update: Any, services: Any) -> bool:
    user = await services.db.get_user(update.from_user.id)
    if user and user.get("banned"):
        answer = getattr(update, "answer", None)
        if answer is not None:
            await answer(sc("❌ You are banned from this bot."), show_alert=True)
        else:
            await update.reply_text(sc("❌ You are banned from this bot."))
        return False
    return True


def own_action(query: Any) -> str | None:
    return action_for(query.from_user.id, query.data)


async def reject_foreign_callback(query: Any) -> None:
    await query.answer(sc("This button belongs to another user."), show_alert=True)


async def edit(query: Any, text: str, reply_markup: Any = None) -> None:
    """Edit in place; Telegram rejects no-op edits, which are harmless."""
    try:
        await query.message.edit_text(text, reply_markup=reply_markup)
    except RPCError as exc:
        if "MESSAGE_NOT_MODIFIED" not in str(exc).upper():
            raise
    await query.answer()


async def safe_delete(message: Any) -> None:
    try:
        await message.delete()
    except RPCError:
        pass


async def animated_edit(message: Any, base: str, delay: float = 0.45) -> None:
    """One short status animation used only around userbot code delivery."""
    for dots in (".", "..", "..."):
        try:
            await message.edit_text(sc(base + dots))
        except RPCError:
            return
        await asyncio.sleep(delay)


def owner_only(user_id: int, services: Any) -> bool:
    return user_id in services.config.owner_ids
