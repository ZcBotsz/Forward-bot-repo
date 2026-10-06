"""Welcome, help, plan, and common command handlers."""

from __future__ import annotations

import pyrogram
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from ..services import Services
from ..ui import (
    about_text,
    back,
    button,
    home_keyboard,
    how_to_text,
    markup,
    plan_detail,
    plan_text,
    plans_overview,
    sc,
    status_text,
    url_button,
    welcome_text,
)
from .common import edit, is_allowed, own_action


async def show_home(message_or_query: Message | CallbackQuery, services: Services, edit_existing: bool = False) -> None:
    user = message_or_query.from_user
    record = await services.db.ensure_user(user.id, user.first_name or "User")
    keyboard = home_keyboard(user.id, services.config, user.id in services.config.owner_ids)
    if edit_existing:
        await edit(message_or_query, welcome_text(record["name"]), keyboard)
    else:
        await message_or_query.reply_text(welcome_text(record["name"]), reply_markup=keyboard)


async def show_plans(query: CallbackQuery, services: Services) -> None:
    user = await services.db.get_user(query.from_user.id)
    plan = (user or {}).get("plan", "free")
    await edit(
        query,
        plans_overview(plan),
        markup(
            [
                [
                    button(query.from_user.id, "⚜️ My Plan", "plans:my"),
                    button(query.from_user.id, "⭐ Plus", "plans:plus"),
                ],
                [
                    button(query.from_user.id, "💎 Pro", "plans:pro"),
                    button(query.from_user.id, "♾️ Infinity", "plans:infinity"),
                ],
                [button(query.from_user.id, "🚀 Ultra", "plans:ultra")],
                [button(query.from_user.id, "🔵 Back", "home")],
            ]
        ),
    )


async def show_my_plan(query: CallbackQuery, services: Services) -> None:
    user = await services.db.get_user(query.from_user.id)
    await edit(query, plan_text(user or {}), back(query.from_user.id, "plans:home"))


def register(app: Client, services: Services) -> None:
    @app.on_message(
        filters.private & filters.command(["start", "help", "myplan", "reset", "transfer", "cancel"], prefixes="/"),
        group=1,
    )
    async def common_commands(_: Client, message: Message) -> None:
        await services.db.ensure_user(message.from_user.id, message.from_user.first_name or "User")
        if not await is_allowed(message, services):
            return
        command = (message.command or ["start"])[0].lower()
        if command == "start":
            await show_home(message, services)
        elif command == "help":
            await message.reply_text(
                help_text_for(message.from_user.id, services), reply_markup=help_keyboard(message.from_user.id)
            )
        elif command == "myplan":
            user = await services.db.get_user(message.from_user.id)
            await message.reply_text(plan_text(user or {}), reply_markup=back(message.from_user.id))
        elif command == "cancel":
            await services.db.clear_flow(message.from_user.id)
            # Phone-login client state is intentionally memory-only; release it on cancel as well.
            from .input import _stop_login

            await _stop_login(message.from_user.id)
            await message.reply_text(sc("❌ Process Cancelled !"), reply_markup=back(message.from_user.id))
        elif command == "reset":
            await message.reply_text(
                sc("⚠️ This removes your saved bots, userbots, settings, duplicate records and active jobs. Continue?"),
                reply_markup=markup(
                    [
                        [
                            button(message.from_user.id, "🔴 Yes, Reset", "reset:yes"),
                            button(message.from_user.id, "🔵 No", "home"),
                        ]
                    ]
                ),
            )
        elif command == "transfer":
            user = await services.db.get_user(message.from_user.id)
            if (user or {}).get("plan", "free") == "free":
                await message.reply_text(
                    sc("🔒 You need an active paid plan to transfer."), reply_markup=back(message.from_user.id)
                )
            else:
                await services.db.set_flow(message.from_user.id, "TRANSFER")
                await message.reply_text(
                    sc(
                        "Send the recipient's numeric Telegram user ID. Both users must have started this bot first. /cancel"
                    )
                )

    @app.on_callback_query(group=1)
    async def home_callbacks(_: Client, query: CallbackQuery) -> None:
        action = own_action(query)
        if not action:
            return
        if not await is_allowed(query, services):
            return
        if action == "home":
            await show_home(query, services, edit_existing=True)
        elif action == "home:help":
            await edit(query, help_text_for(query.from_user.id, services), help_keyboard(query.from_user.id))
        elif action == "home:how":
            await edit(query, how_to_text(), back(query.from_user.id, "home:help"))
        elif action == "home:about":
            await edit(
                query,
                about_text(
                    pyrogram.__version__,
                    await services.db.mongo_version(),
                    services.config.support_channel,
                    services.config.updates_channel,
                    services.config.admin_username,
                ),
                back(query.from_user.id),
            )
        elif action == "home:status":
            stats = await services.db.stats()
            await edit(
                query,
                status_text(stats["users"], stats["bots"] + stats["userbots"], stats["channels"]),
                back(query.from_user.id, "home:help"),
            )
        elif action == "home:referral":
            await edit(query, sc("🚧 Under maintenance. Coming soon."), back(query.from_user.id))
        elif action == "plans:home":
            await show_plans(query, services)
        elif action == "plans:my":
            await show_my_plan(query, services)
        elif action.startswith("plans:") and action.split(":", 1)[1] in {"free", "plus", "pro", "infinity", "ultra"}:
            plan = action.split(":", 1)[1]
            await edit(
                query,
                plan_detail(plan),
                markup(
                    [
                        [url_button("👨‍💻 Contact Admin", services.config.admin_url)],
                        [button(query.from_user.id, "🔵 Back", "plans:home")],
                    ]
                ),
            )
        elif action == "reset:yes":
            await services.engine.cancel_job(
                query.from_user.id, str((await services.db.get_active_job(query.from_user.id) or {}).get("_id", ""))
            )
            await services.db.reset_settings(query.from_user.id)
            await edit(query, sc("✅ Your settings and managed identities were reset."), back(query.from_user.id))


def help_text_for(_: int, __: object) -> str:
    from ..ui import help_text

    return help_text()


def help_keyboard(user_id: int):
    return markup(
        [
            [button(user_id, "📚 How To Use Me", "home:how"), button(user_id, "🔵 Settings", "settings:home")],
            [button(user_id, "📊 Status", "home:status")],
            [button(user_id, "🔵 Back", "home")],
        ]
    )
