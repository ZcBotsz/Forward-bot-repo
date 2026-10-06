"""Settings, identities, captions, filters, databases, and custom buttons."""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from ..services import Services
from ..ui import back, button, markup, onoff, sc
from .common import edit, is_allowed, own_action


async def show_settings(query: CallbackQuery, services: Services) -> None:
    text = sc("⚙️ Settings Hub\n\nConfigure your bots, forwarding content, filters and ZC Manager modes.")
    await edit(
        query,
        text,
        markup(
            [
                [
                    button(query.from_user.id, "🤖 Bots", "settings:bots"),
                    button(query.from_user.id, "📝 Caption", "settings:caption"),
                ],
                [
                    button(query.from_user.id, "🗃️ Database", "settings:database"),
                    button(query.from_user.id, "💠 Filters", "settings:filters"),
                ],
                [
                    button(query.from_user.id, "🔘 Button", "settings:button"),
                    button(query.from_user.id, "🧰 ZC Manager", "manager:home"),
                ],
                [
                    button(query.from_user.id, "⏭️ Skip Rules", "settings:rules"),
                    button(query.from_user.id, "📦 My Jobs", "settings:jobs"),
                ],
                [button(query.from_user.id, "🔴 Reset", "settings:reset")],
                [button(query.from_user.id, "🔵 Back", "home")],
            ]
        ),
    )


async def show_bots(query: CallbackQuery, services: Services) -> None:
    identities = await services.db.list_identities(query.from_user.id)
    lines = ["🤖 My Bots", "", "You can manage your bots in here."]
    rows = []
    for identity in identities:
        label = f"{'🤖' if identity['kind'] == 'bot' else '👤'} {identity.get('name', 'Unnamed')}"
        username = identity.get("username")
        lines.append(f"• {label} {('@' + username) if username else ''}")
        rows.append(
            [
                button(
                    query.from_user.id,
                    f"🔴 Remove {identity.get('name', 'identity')[:20]}",
                    f"bot:remove:{identity['ref']}",
                )
            ]
        )
    rows.extend(
        [
            [
                button(query.from_user.id, "🟢 Add Bot", "bot:add"),
                button(query.from_user.id, "🟢 Add User Bot", "bot:adduser"),
            ],
            [button(query.from_user.id, "🔵 Back", "settings:home")],
        ]
    )
    await edit(query, sc("\n".join(lines)), markup(rows))


async def show_caption(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    current = str(settings.get("caption", "") or "")
    text = sc(
        "📝 Custom Caption\n\n"
        "Variables: {filename}, {size}, {caption}, {year}, {language}, {quality}, {type}.\n"
        "Variables work on videos, audio and documents; photos retain their original caption.\n"
        "HTML allowed: <b> <i> <u> <s> <code> <spoiler> <a href>.\n\n"
        "Example:\n<b>{filename}</b>\n📊 Size: {size}\n🎬 Quality: {quality}\n📅 Year: {year}\n🗣️ Language: {language}\n\n"
        f"Current: {'set' if current else 'not set'}"
    )
    rows = [[button(query.from_user.id, "🟢 Add Caption", "caption:add")]]
    if current:
        rows.append(
            [
                button(query.from_user.id, "🔵 View Caption", "caption:view"),
                button(query.from_user.id, "🔴 Delete Caption", "caption:delete"),
            ]
        )
    rows.append([button(query.from_user.id, "🔵 Back", "settings:home")])
    await edit(query, text, markup(rows))


async def show_database(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    text = sc(
        "🗃️ Duplicate Database\n\n"
        "Database is required to store your duplicate messages permanently. Otherwise stored duplicate media may disappear after a bot restart.\n\n"
        f"Personal database: {'connected' if settings.get('db_uri_enc') else 'using the bot database'}"
    )
    rows = [[button(query.from_user.id, "🟢 Add URL", "database:add")]]
    if settings.get("db_uri_enc"):
        rows[0].append(button(query.from_user.id, "🔴 Remove URL", "database:delete"))
    rows.append([button(query.from_user.id, "🔵 Back", "settings:home")])
    await edit(query, text, markup(rows))


async def show_filters(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    values = settings["filters"]
    keys = [
        ("text", "Text"),
        ("photo", "Photo"),
        ("video", "Video"),
        ("document", "Document"),
        ("audio", "Audio"),
        ("voice", "Voice"),
        ("animation", "Animation/GIF"),
        ("sticker", "Sticker"),
        ("poll", "Poll"),
        ("video_note", "Video Note"),
    ]
    rows = [
        [button(query.from_user.id, f"{onoff(bool(values.get(key)))} {label}", f"filters:toggle:{key}")]
        for key, label in keys
    ]
    rows.extend(
        [
            [button(query.from_user.id, "⏭️ Skip Rules", "settings:rules")],
            [button(query.from_user.id, "🔵 Back", "settings:home")],
        ]
    )
    await edit(query, sc("💠 Custom Filters 💠\n\nConfigure the types of messages you want to forward."), markup(rows))


async def show_rules(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    values = settings["filters"]
    text = sc(
        "⏭️ Skip Rules\n\n"
        f"Extensions: {', '.join(values.get('skip_extensions', [])) or 'none'}\n"
        f"Keywords: {', '.join(values.get('skip_keywords', [])) or 'none'}\n"
        f"Maximum file size: {values.get('max_size_mb', 0) or 'disabled'} MB"
    )
    await edit(
        query,
        text,
        markup(
            [
                [
                    button(query.from_user.id, "🟢 Set Extensions", "rules:extensions"),
                    button(query.from_user.id, "🟢 Set Keywords", "rules:keywords"),
                ],
                [button(query.from_user.id, "🟢 Set Max Size", "rules:size")],
                [button(query.from_user.id, "🔵 Back", "settings:filters")],
            ]
        ),
    )


async def show_custom_button(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    has_button = bool(settings.get("buttons"))
    text = sc(
        "🔘 Custom Button\n\n"
        "You can set inline buttons on forwarded messages.\n"
        "Format: [ZC Channel][buttonurl:https://t.me/ZCYT_2026]\n"
        "Add :same after a line to keep its buttons on the previous row.\n\n"
        f"Current button: {'set' if has_button else 'not set'}"
    )
    rows = [[button(query.from_user.id, "🟢 Add Button", "custombutton:add")]]
    if has_button:
        rows.append(
            [
                button(query.from_user.id, "🔵 View Button", "custombutton:view"),
                button(query.from_user.id, "🔴 Delete Button", "custombutton:delete"),
            ]
        )
    rows.append([button(query.from_user.id, "🔵 Back", "settings:home")])
    await edit(query, text, markup(rows))


async def show_jobs(query: CallbackQuery, services: Services) -> None:
    job = await services.db.get_active_job(query.from_user.id)
    if not job:
        text = sc("📦 My Jobs\n\nNo active forwarding job.")
        keys = back(query.from_user.id, "settings:home")
    else:
        stats = job.get("stats", {})
        text = sc(
            "📦 My Active Job\n\n"
            f"State: {job.get('state')}\n"
            f"Source: {job['source'].get('title')}\n"
            f"Target count: {len(job.get('targets', []))}\n"
            f"Forwarded: {stats.get('forwarded', 0)}\n"
            f"Last checkpoint: {job.get('last_id', 0)}"
        )
        keys = markup(
            [
                [button(query.from_user.id, "🔴 Cancel Job", f"fw:cancel:{job['_id']}")],
                [button(query.from_user.id, "🔵 Back", "settings:home")],
            ]
        )
    await edit(query, text, keys)


def register(app: Client, services: Services) -> None:
    @app.on_message(filters.private & filters.command("settings", prefixes="/"), group=1)
    async def settings_command(_: Client, message: Message) -> None:
        await services.db.ensure_user(message.from_user.id, message.from_user.first_name or "User")
        if not await is_allowed(message, services):
            return
        await message.reply_text(
            sc("⚙️ Opening Settings…"),
            reply_markup=markup([[button(message.from_user.id, "🔵 Open Settings", "settings:home")]]),
        )

    @app.on_callback_query(group=2)
    async def settings_callbacks(_: Client, query: CallbackQuery) -> None:
        action = own_action(query)
        if not action or not await is_allowed(query, services):
            return
        if action == "settings:home":
            await show_settings(query, services)
        elif action == "settings:bots":
            await show_bots(query, services)
        elif action == "settings:caption":
            await show_caption(query, services)
        elif action == "settings:database":
            await show_database(query, services)
        elif action == "settings:filters":
            await show_filters(query, services)
        elif action == "settings:rules":
            await show_rules(query, services)
        elif action == "settings:button":
            await show_custom_button(query, services)
        elif action == "settings:jobs":
            await show_jobs(query, services)
        elif action == "settings:reset":
            await edit(
                query,
                sc("⚠️ This removes saved bots, userbots, settings, duplicate records and active jobs. Continue?"),
                markup(
                    [
                        [
                            button(query.from_user.id, "🔴 Yes, Reset", "reset:yes"),
                            button(query.from_user.id, "🔵 No", "settings:home"),
                        ]
                    ]
                ),
            )
        elif action == "bot:add":
            await services.db.set_flow(query.from_user.id, "BOT_TOKEN")
            await edit(
                query,
                sc(
                    "Send your bot token from @BotFather. Example: <code>1234567890:ABCdef…</code>\n/cancel — cancel this process"
                ),
            )
        elif action == "bot:adduser":
            await edit(
                query,
                sc(
                    "⚠️ Use your Telegram account at your own risk. Userbot logins may be restricted or banned by Telegram; the developer is not responsible.\n\nChoose a secure login method."
                ),
                markup(
                    [
                        [button(query.from_user.id, "🟢 Login using phone number", "userbot:phone")],
                        [button(query.from_user.id, "🟢 Login using string session", "userbot:session")],
                        [button(query.from_user.id, "🔵 Back", "settings:bots")],
                    ]
                ),
            )
        elif action == "userbot:phone":
            await services.db.set_flow(query.from_user.id, "USERBOT_PHONE")
            await edit(
                query, sc("Send your phone number with country code. Example: <code>+1234567890</code>\n/cancel")
            )
        elif action == "userbot:session":
            await services.db.set_flow(query.from_user.id, "USERBOT_SESSION")
            await edit(query, sc("Send your Pyrogram/Kurigram string session from a trusted source. /cancel"))
        elif action.startswith("bot:remove:"):
            ref = action[len("bot:remove:") :]
            if await services.db.delete_identity(query.from_user.id, ref):
                await edit(
                    query,
                    sc("✅ Identity removed."),
                    markup([[button(query.from_user.id, "🔵 Back to Bots", "settings:bots")]]),
                )
            else:
                await query.answer(sc("Identity not found."), show_alert=True)
        elif action == "caption:add":
            await services.db.set_flow(query.from_user.id, "CAPTION")
            await edit(
                query,
                sc(
                    "Send your custom caption template. Variables: {filename}, {size}, {caption}, {year}, {language}, {quality}, {type}. /cancel"
                ),
            )
        elif action == "caption:view":
            settings = await services.db.get_settings(query.from_user.id)
            await edit(
                query,
                sc("📝 Saved Caption\n\n") + str(settings.get("caption", "")),
                back(query.from_user.id, "settings:caption"),
            )
        elif action == "caption:delete":
            await services.db.set_setting(query.from_user.id, "caption", "")
            await edit(
                query, sc("✅ Caption deleted."), markup([[button(query.from_user.id, "🔵 Back", "settings:caption")]])
            )
        elif action == "database:add":
            await services.db.set_flow(query.from_user.id, "DATABASE_URI")
            await edit(query, sc("Send your MongoDB URI. It will be tested and encrypted before saving. /cancel"))
        elif action == "database:delete":
            await services.db.set_setting(query.from_user.id, "db_uri_enc", "")
            await edit(
                query,
                sc("✅ Personal duplicate database removed; the bot database will be used."),
                back(query.from_user.id, "settings:database"),
            )
        elif action.startswith("filters:toggle:"):
            key = action.rsplit(":", 1)[1]
            settings = await services.db.get_settings(query.from_user.id)
            values = dict(settings["filters"])
            if key in values and isinstance(values[key], bool):
                values[key] = not values[key]
                await services.db.set_setting(query.from_user.id, "filters", values)
            await show_filters(query, services)
        elif action == "rules:extensions":
            await services.db.set_flow(query.from_user.id, "SKIP_EXTENSIONS")
            await edit(
                query,
                sc(
                    "Send extensions to skip, separated by commas. Example: <code>zip, exe, apk</code>. Send <code>clear</code> to remove them. /cancel"
                ),
            )
        elif action == "rules:keywords":
            await services.db.set_flow(query.from_user.id, "SKIP_KEYWORDS")
            await edit(
                query, sc("Send keywords to skip, separated by commas. Send <code>clear</code> to remove them. /cancel")
            )
        elif action == "rules:size":
            await services.db.set_flow(query.from_user.id, "MAX_SIZE")
            await edit(
                query,
                sc(
                    "Send the maximum permitted file size in MB (for example <code>1500</code>). Send <code>0</code> to disable. /cancel"
                ),
            )
        elif action == "custombutton:add":
            await services.db.set_flow(query.from_user.id, "CUSTOM_BUTTON")
            await edit(
                query,
                sc(
                    "Send your custom button. Format: <code>[ZC Channel][buttonurl:https://t.me/ZCYT_2026]</code> /cancel"
                ),
            )
        elif action == "custombutton:view":
            settings = await services.db.get_settings(query.from_user.id)
            lines = [f"[{label}][buttonurl:{url}]" for row in settings.get("buttons", []) for label, url in row]
            await edit(
                query, sc("🔘 Saved Buttons\n\n") + "\n".join(lines), back(query.from_user.id, "settings:button")
            )
        elif action == "custombutton:delete":
            await services.db.set_setting(query.from_user.id, "buttons", [])
            await edit(query, sc("✅ Custom button deleted."), back(query.from_user.id, "settings:button"))
