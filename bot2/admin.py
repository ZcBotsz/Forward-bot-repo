"""Owner-only operations. Every callback performs its own owner check."""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from ..services import Services
from ..ui import button, markup, sc, url_button
from .common import edit, own_action, owner_only


async def show_admin(query: CallbackQuery, services: Services) -> None:
    if not owner_only(query.from_user.id, services):
        await query.answer(sc("Owner only."), show_alert=True)
        return
    await edit(
        query,
        sc("🛠️ ZC Admin Panel\n\nManage plans, users and announcements."),
        markup(
            [
                [button(query.from_user.id, "📊 Stats", "admin:stats")],
                [
                    button(query.from_user.id, "🟢 Grant Plan", "admin:grant"),
                    button(query.from_user.id, "🔴 Revoke Plan", "admin:revoke"),
                ],
                [button(query.from_user.id, "📢 Broadcast", "admin:broadcast")],
                [
                    button(query.from_user.id, "🔴 Ban User", "admin:ban"),
                    button(query.from_user.id, "🟢 Unban User", "admin:unban"),
                ],
                [
                    url_button("📣 Main Channel", services.config.main_channel_url),
                    url_button("🛟 Support", services.config.support_url),
                ],
                [
                    url_button("🔔 Updates", services.config.updates_url),
                    url_button("👨‍💻 Contact Admin", services.config.admin_url),
                ],
                [button(query.from_user.id, "🔵 Back", "home")],
            ]
        ),
    )


def register(app: Client, services: Services) -> None:
    @app.on_message(filters.private & filters.command("admin", prefixes="/"), group=1)
    async def admin_command(_: Client, message: Message) -> None:
        await services.db.ensure_user(message.from_user.id, message.from_user.first_name or "User")
        if not owner_only(message.from_user.id, services):
            await message.reply_text(sc("❌ This command is owner-only."))
            return
        await message.reply_text(
            sc("🛠️ Open the admin panel."),
            reply_markup=markup([[button(message.from_user.id, "🛠️ Admin Panel", "admin:home")]]),
        )

    @app.on_callback_query(group=5)
    async def admin_callbacks(_: Client, query: CallbackQuery) -> None:
        action = own_action(query)
        if not action or not action.startswith("admin:"):
            return
        if not owner_only(query.from_user.id, services):
            await query.answer(sc("Owner only."), show_alert=True)
            return
        if action == "admin:home":
            await show_admin(query, services)
        elif action == "admin:stats":
            stats = await services.db.stats()
            await edit(
                query,
                sc(
                    "📊 ZC Admin Stats\n\n"
                    f"Users: {stats['users']}\nPaid users: {stats['paid_users']}\n"
                    f"Managed bots: {stats['bots']}\nUserbots: {stats['userbots']}\nChannels: {stats['channels']}"
                ),
                markup([[button(query.from_user.id, "🔵 Back", "admin:home")]]),
            )
        elif action == "admin:grant":
            await services.db.set_flow(query.from_user.id, "ADMIN_GRANT_ID")
            await edit(query, sc("Send the recipient's numeric Telegram user ID. /cancel"))
        elif action == "admin:revoke":
            await services.db.set_flow(query.from_user.id, "ADMIN_REVOKE_ID")
            await edit(query, sc("Send the user's numeric Telegram user ID to revoke. /cancel"))
        elif action == "admin:broadcast":
            await services.db.set_flow(query.from_user.id, "ADMIN_BROADCAST")
            await edit(query, sc("Send the broadcast message. It will be sent as HTML text. /cancel"))
        elif action == "admin:ban":
            await services.db.set_flow(query.from_user.id, "ADMIN_BAN_ID")
            await edit(query, sc("Send the numeric Telegram user ID to ban. /cancel"))
        elif action == "admin:unban":
            await services.db.set_flow(query.from_user.id, "ADMIN_UNBAN_ID")
            await edit(query, sc("Send the numeric Telegram user ID to unban. /cancel"))
        elif action.startswith("admin:grantplan:"):
            plan = action.rsplit(":", 1)[1]
            flow = await services.db.get_flow(query.from_user.id)
            if not flow or flow.get("kind") != "ADMIN_GRANT_PLAN":
                await query.answer(sc("Grant flow expired."), show_alert=True)
                return
            data = dict(flow.get("data", {}))
            data["plan"] = plan
            await services.db.set_flow(query.from_user.id, "ADMIN_GRANT_DAYS", data)
            await edit(query, sc("Send number of days (default is 30). /cancel"))
