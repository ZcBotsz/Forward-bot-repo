"""Forward wizard, job controls, and duplicate-removal entry point."""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from ..plans import require_feature
from ..services import Services
from ..ui import back, button, markup, sc
from .common import edit, is_allowed, own_action


async def show_identity_picker(query: CallbackQuery, services: Services, purpose: str = "forward") -> None:
    identities = await services.db.list_identities(query.from_user.id)
    if not identities:
        await edit(
            query,
            sc("No bot or userbot has been added yet. Add one in Settings first."),
            markup(
                [
                    [button(query.from_user.id, "🟢 Add Identity", "settings:bots")],
                    [button(query.from_user.id, "🔵 Back", "home")],
                ]
            ),
        )
        return
    rows = []
    for identity in identities:
        icon = "🤖" if identity["kind"] == "bot" else "👤"
        rows.append(
            [
                button(
                    query.from_user.id,
                    f"{icon} {identity.get('name', 'Unnamed')}",
                    f"{purpose}:client:{identity['ref']}",
                )
            ]
        )
    rows.append([button(query.from_user.id, "🔵 Back", "home")])
    title = (
        "Choose which bot / userbot will forward messages."
        if purpose == "fw"
        else "Choose the identity that can delete messages."
    )
    await edit(query, sc(title), markup(rows))


async def begin_forward_from_command(message: Message, services: Services) -> None:
    user = await services.db.get_user(message.from_user.id)
    if not user or user.get("plan") == "free":
        await message.reply_text(
            sc("🔒 This feature needs the Plus plan. Tap Plans to upgrade."),
            reply_markup=markup([[button(message.from_user.id, "💳 Plans", "plans:home")]]),
        )
        return
    identities = await services.db.list_identities(message.from_user.id)
    if not identities:
        await message.reply_text(
            sc("No bot or userbot has been added yet."),
            reply_markup=markup([[button(message.from_user.id, "🟢 Add Identity", "settings:bots")]]),
        )
        return
    rows = [
        [
            button(
                message.from_user.id,
                f"{'🤖' if item['kind'] == 'bot' else '👤'} {item.get('name', 'Unnamed')}",
                f"fw:client:{item['ref']}",
            )
        ]
        for item in identities
    ]
    rows.append([button(message.from_user.id, "🔵 Back", "home")])
    await message.reply_text(sc("Choose which bot / userbot will forward messages."), reply_markup=markup(rows))


async def confirm_forward(query: CallbackQuery, services: Services) -> None:
    flow = await services.db.get_flow(query.from_user.id)
    if not flow or flow.get("kind") != "FW_CONFIRM":
        await query.answer(sc("This setup expired. Run /forward again."), show_alert=True)
        return
    data = flow["data"]
    try:
        settings = await services.db.get_settings(query.from_user.id)
        # Fill a pleasant seller default at job creation without silently changing user configuration.
        if settings.get("modes", {}).get("course_seller") and not settings.get("seller", {}).get("name"):
            settings["seller"] = {
                **settings["seller"],
                "name": f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name,
            }
        targets = [data["target"]]
        if settings.get("modes", {}).get("pi"):
            for raw in settings.get("pi_targets", []):
                extra = await services.engine.resolve_target(query.from_user.id, data["ref"], str(raw))
                if all(int(item["id"]) != int(extra["id"]) for item in targets):
                    targets.append(extra)
        job_id = await services.engine.create_job(
            query.from_user.id,
            data["ref"],
            data["source"],
            targets,
            int(data["skip"]),
            int(data["end_id"]),
            settings,
            progress_chat_id=query.message.chat.id,
            progress_message_id=query.message.id,
        )
        await services.db.clear_flow(query.from_user.id)
        await edit(
            query,
            sc(f"🔄 Job started. Preparing range and live listener…\n\nJob ID: {job_id}"),
            markup(
                [
                    [
                        button(query.from_user.id, "🔴 Cancel", f"fw:cancel:{job_id}"),
                        button(query.from_user.id, "🔵 Refresh", f"fw:refresh:{job_id}"),
                    ]
                ]
            ),
        )
    except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
        await edit(
            query,
            sc(f"❌ Could not start forwarding: {services.engine.clean_error(exc)}"),
            back(query.from_user.id, "home"),
        )


def confirmation_text(data: dict) -> str:
    active_modes = [name.replace("_", " ").title() for name, enabled in data.get("modes", {}).items() if enabled]
    return sc(
        "✅ Confirm Forwarding\n\n"
        f"Identity: {data.get('identity_name')}\n"
        f"From: {data['source'].get('title')}\n"
        f"To: {data['target'].get('title')}\n"
        f"Skip from start: {data['skip']}\n"
        f"Last message: {data['end_id']}\n"
        f"Total range: {max(0, int(data['end_id']) - int(data['skip']))}\n"
        f"Active modes: {', '.join(active_modes) if active_modes else 'none'}\n\n"
        "Start this job?"
    )


def register(app: Client, services: Services) -> None:
    @app.on_message(filters.private & filters.command(["forward", "unequify"], prefixes="/"), group=1)
    async def forward_commands(_: Client, message: Message) -> None:
        await services.db.ensure_user(message.from_user.id, message.from_user.first_name or "User")
        if not await is_allowed(message, services):
            return
        command = (message.command or ["forward"])[0].lower()
        if command == "forward":
            await begin_forward_from_command(message, services)
        else:
            if not await require_feature(message, services, "unequify"):
                return
            identities = await services.db.list_identities(message.from_user.id)
            if not identities:
                await message.reply_text(
                    sc("Add a bot or userbot first."),
                    reply_markup=markup([[button(message.from_user.id, "🟢 Add Identity", "settings:bots")]]),
                )
                return
            rows = [
                [
                    button(
                        message.from_user.id,
                        f"{'🤖' if item['kind'] == 'bot' else '👤'} {item.get('name')}",
                        f"uneq:client:{item['ref']}",
                    )
                ]
                for item in identities
            ]
            await message.reply_text(
                sc("Choose the identity that has delete rights in the channel."),
                reply_markup=markup(rows + [[button(message.from_user.id, "🔵 Back", "home")]]),
            )

    @app.on_callback_query(group=4)
    async def forward_callbacks(_: Client, query: CallbackQuery) -> None:
        action = own_action(query)
        if not action or not await is_allowed(query, services):
            return
        if action.startswith("fw:client:"):
            if not await require_feature(query, services, "forward"):
                return
            ref = action[len("fw:client:") :]
            identity = await services.db.get_identity(query.from_user.id, ref)
            if not identity:
                await query.answer(sc("Identity not found."), show_alert=True)
                return
            await services.db.set_flow(
                query.from_user.id, "FW_SOURCE", {"ref": ref, "identity_name": identity.get("name", "Identity")}
            )
            await edit(query, sc("Send the FROM channel ID, @username, or any message link from it. /cancel"))
        elif action == "fw:confirm":
            await confirm_forward(query, services)
        elif action == "fw:no":
            await services.db.clear_flow(query.from_user.id)
            await edit(query, sc("❌ Forwarding setup cancelled."), back(query.from_user.id, "home"))
        elif action.startswith("fw:cancel:"):
            job_id = action[len("fw:cancel:") :]
            if await services.engine.cancel_job(query.from_user.id, job_id):
                await edit(
                    query,
                    sc("❌ Job cancelled. Its last checkpoint was kept for your records."),
                    back(query.from_user.id, "settings:jobs"),
                )
            else:
                await query.answer(sc("This job is already stopped."), show_alert=True)
        elif action.startswith("fw:refresh:"):
            job_id = action[len("fw:refresh:") :]
            await services.engine._update_progress(job_id)  # refresh invokes the same guarded view renderer
            await query.answer(sc("Progress refreshed."))
        elif action.startswith("uneq:client:"):
            if not await require_feature(query, services, "unequify"):
                return
            await services.db.set_flow(
                query.from_user.id,
                "UNEQUIFY_CHANNEL",
                {
                    "ref": action[len("uneq:client:") :],
                    "progress_chat": query.message.chat.id,
                    "progress_message": query.message.id,
                },
            )
            await edit(
                query,
                sc("Send the channel ID, @username, or link to scan. The identity must have delete rights. /cancel"),
            )
