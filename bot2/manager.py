"""ZC Manager mode menus and mode-specific configuration workflows."""

from __future__ import annotations

from pyrogram import Client
from pyrogram.types import CallbackQuery

from ..plans import require_feature
from ..services import Services
from ..ui import back, button, markup, onoff, sc
from .common import edit, is_allowed, own_action

_MODE_LABELS = {
    "delta": "ZC Delta Mode",
    "alpha": "ZC Alpha Mode",
    "gamma": "ZC Gamma Mode",
    "theta": "ZC Theta Mode",
    "watermark": "ZC Watermark",
    "pi": "ZC Pi Mode",
    "replacer": "ZC Replacer",
    "remover": "ZC Remover",
    "link_remover": "ZC Link Remover",
    "numbering": "ZC Auto Numbering",
    "bullets": "ZC Bullets",
    "course_seller": "ZC Course Seller Mode",
    "text_only": "ZC Text Only Mode",
}


async def show_manager(query: CallbackQuery, services: Services, page: int = 1) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    modes = settings["modes"]
    first = ["delta", "alpha", "gamma", "theta", "watermark", "pi", "text_only"]
    second = ["replacer", "remover", "link_remover", "numbering", "bullets", "course_seller"]
    chosen = first if page == 1 else second
    rows = [
        [button(query.from_user.id, f"{onoff(bool(modes.get(key)))} {_MODE_LABELS[key]}", f"manager:toggle:{key}")]
        for key in chosen
    ]
    if page == 1:
        rows += [
            [
                button(query.from_user.id, "⚙️ Watermark Options", "manager:watermark"),
                button(query.from_user.id, "🎯 Pi Targets", "manager:pi"),
            ],
            [button(query.from_user.id, "⚙️ Delta Setup", "manager:delta")],
            [button(query.from_user.id, "➡️ More Modes", "manager:page:2")],
        ]
    else:
        rows += [
            [
                button(query.from_user.id, "⚙️ Replacer Options", "manager:replacer"),
                button(query.from_user.id, "🔢 Numbering", "manager:numbering"),
            ],
            [
                button(query.from_user.id, "• Bullet Options", "manager:bullets"),
                button(query.from_user.id, "👤 Seller Options", "manager:seller"),
            ],
            [button(query.from_user.id, "⬅️ Back Modes", "manager:page:1")],
        ]
    rows.append([button(query.from_user.id, "🔵 Back", "settings:home")])
    await edit(
        query,
        sc(
            "🧰 ZC Manager\n\n"
            "Enable only modes included in your plan. Modes are snapshotted when a forwarding job begins.\n"
            "⚠️ Remover takes priority: when it is ON, Replacer is disabled."
        ),
        markup(rows),
    )


async def show_watermark(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    values = settings["watermark"]
    await edit(
        query,
        sc(
            "💧 ZC Watermark\n\n"
            f"Prefix: {'set' if values.get('prefix') else 'not set'}\n"
            f"Suffix: {'set' if values.get('suffix') else 'not set'}\n\n"
            "Prefix is placed at the start and suffix at the end of transformed captions. HTML is allowed."
        ),
        markup(
            [
                [
                    button(query.from_user.id, "🟢 Add Prefix", "watermark:prefix"),
                    button(query.from_user.id, "🟢 Add Suffix", "watermark:suffix"),
                ],
                [
                    button(query.from_user.id, "🔵 View Prefix", "watermark:viewprefix"),
                    button(query.from_user.id, "🔵 View Suffix", "watermark:viewsuffix"),
                ],
                [
                    button(query.from_user.id, "🔴 Delete Prefix", "watermark:deleteprefix"),
                    button(query.from_user.id, "🔴 Delete Suffix", "watermark:deletesuffix"),
                ],
                [button(query.from_user.id, "🔵 Back", "manager:home")],
            ]
        ),
    )


async def show_replacer(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    values = settings["replacer"]
    await edit(
        query,
        sc(
            "🔁 ZC Replacer\n\n"
            f"Replacement link: {'set' if values.get('link') else 'not set'}\n"
            f"Replacement username: {'set' if values.get('username') else 'not set'}\n"
            f"Word pairs: {len(values.get('pairs', []))}\n\n"
            "Links include hidden links. Replacer works only while Remover is OFF."
        ),
        markup(
            [
                [
                    button(query.from_user.id, "🟢 Set Link", "replacer:link"),
                    button(query.from_user.id, "🟢 Set Username", "replacer:username"),
                ],
                [
                    button(query.from_user.id, "🟢 Add Word Pair", "replacer:pair"),
                    button(query.from_user.id, "🔴 Clear Pairs", "replacer:clearpairs"),
                ],
                [button(query.from_user.id, "🔵 Back", "manager:page:2")],
            ]
        ),
    )


async def show_numbering(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    values = settings["numbering"]
    await edit(
        query,
        sc(f"🔢 ZC Auto Numbering\n\nStyle: {values.get('style')}\nStart number: {values.get('start')}"),
        markup(
            [
                [
                    button(query.from_user.id, "1. Style", "numbering:style:{n}."),
                    button(query.from_user.id, "1) Style", "numbering:style:{n})"),
                ],
                [
                    button(query.from_user.id, "-1 Style", "numbering:style:-{n}"),
                    button(query.from_user.id, "1️⃣ Style", "numbering:style:emoji"),
                ],
                [button(query.from_user.id, "🟢 Set Start", "numbering:start")],
                [button(query.from_user.id, "🔵 Back", "manager:page:2")],
            ]
        ),
    )


async def show_bullets(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    values = settings["bullets"]
    await edit(
        query,
        sc(
            f"• ZC Bullets\n\nBullets: {' '.join(values.get('items', []))}\nRandom: {onoff(bool(values.get('random')))}"
        ),
        markup(
            [
                [
                    button(query.from_user.id, "🟢 Set Emoji / List", "bullets:set"),
                    button(query.from_user.id, "🔄 Toggle Random", "bullets:random"),
                ],
                [button(query.from_user.id, "🔵 Back", "manager:page:2")],
            ]
        ),
    )


async def show_seller(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    values = settings["seller"]
    await edit(
        query,
        sc(
            "👤 ZC Course Seller Mode\n\n"
            f"Seller: {values.get('name') or 'your own username at job creation'}\n"
            f"Placement: {values.get('placement', 'after')}\n\n"
            "Appends: Extracted by: seller name"
        ),
        markup(
            [
                [
                    button(query.from_user.id, "🟢 Set Seller", "seller:set"),
                    button(query.from_user.id, "🔄 Toggle Placement", "seller:placement"),
                ],
                [button(query.from_user.id, "🔵 Back", "manager:page:2")],
            ]
        ),
    )


async def show_pi(query: CallbackQuery, services: Services) -> None:
    settings = await services.db.get_settings(query.from_user.id)
    targets = list(settings.get("pi_targets", []))
    rows = [[button(query.from_user.id, "🟢 Add Target", "pi:add")]]
    for index, target in enumerate(targets):
        rows.append([button(query.from_user.id, f"🔴 Remove {str(target)[:25]}", f"pi:remove:{index}")])
    rows.append([button(query.from_user.id, "🔵 Back", "manager:home")])
    await edit(
        query,
        sc(
            "🎯 ZC Pi Mode\n\nExtra targets are validated when you start a forwarding job.\n"
            + ("\n".join(f"• {item}" for item in targets) if targets else "No extra targets configured.")
        ),
        markup(rows),
    )


async def show_delta_picker(query: CallbackQuery, services: Services, source_raw: str, target_raw: str) -> None:
    identities = await services.db.list_identities(query.from_user.id)
    if not identities:
        await edit(query, sc("Add a bot or userbot first."), back(query.from_user.id, "settings:bots"))
        return
    rows = [
        [
            button(
                query.from_user.id,
                f"{'🤖' if row['kind'] == 'bot' else '👤'} {row.get('name')}",
                f"delta:client:{row['ref']}",
            )
        ]
        for row in identities
    ]
    rows.append([button(query.from_user.id, "🔵 Back", "manager:home")])
    await edit(
        query,
        sc("⚙️ Delta Setup\n\nChoose the identity that will read the source and post to the target."),
        markup(rows),
    )


def register(app: Client, services: Services) -> None:
    @app.on_callback_query(group=3)
    async def manager_callbacks(_: Client, query: CallbackQuery) -> None:
        action = own_action(query)
        if not action or not await is_allowed(query, services):
            return
        if action == "manager:home":
            await show_manager(query, services)
        elif action.startswith("manager:page:"):
            await show_manager(query, services, int(action.rsplit(":", 1)[1]))
        elif action.startswith("manager:toggle:"):
            mode = action.rsplit(":", 1)[1]
            if mode not in _MODE_LABELS or not await require_feature(query, services, mode):
                return
            settings = await services.db.get_settings(query.from_user.id)
            modes = dict(settings["modes"])
            enabled = not bool(modes.get(mode))
            modes[mode] = enabled
            # Mutually exclusive by policy, not merely a UI warning.
            if mode == "remover" and enabled:
                modes["replacer"] = False
            if mode == "replacer" and enabled:
                modes["remover"] = False
            # The two content gates cannot both forward anything useful.
            if mode == "gamma" and enabled:
                modes["text_only"] = False
            if mode == "text_only" and enabled:
                modes["gamma"] = False
            await services.db.set_setting(query.from_user.id, "modes", modes)
            await show_manager(
                query,
                services,
                1 if mode in {"delta", "alpha", "gamma", "theta", "watermark", "pi", "text_only"} else 2,
            )
        elif action == "manager:watermark":
            if await require_feature(query, services, "watermark"):
                await show_watermark(query, services)
        elif action == "manager:replacer":
            if await require_feature(query, services, "replacer"):
                await show_replacer(query, services)
        elif action == "manager:numbering":
            if await require_feature(query, services, "numbering"):
                await show_numbering(query, services)
        elif action == "manager:bullets":
            if await require_feature(query, services, "bullets"):
                await show_bullets(query, services)
        elif action == "manager:seller":
            if await require_feature(query, services, "course_seller"):
                await show_seller(query, services)
        elif action == "manager:pi":
            if await require_feature(query, services, "pi"):
                await show_pi(query, services)
        elif action == "manager:delta":
            if await require_feature(query, services, "delta"):
                await services.db.set_flow(query.from_user.id, "DELTA_SOURCE")
                await edit(query, sc("Send the Delta source channel ID, @username, or message link. /cancel"))
        elif action.startswith("watermark:"):
            if not await require_feature(query, services, "watermark"):
                return
            item = action.split(":", 1)[1]
            if item in {"prefix", "suffix"}:
                await services.db.set_flow(query.from_user.id, f"WATERMARK_{item.upper()}")
                await edit(query, sc(f"Send the watermark {item}. HTML is allowed. /cancel"))
            elif item.startswith("view"):
                value = (await services.db.get_settings(query.from_user.id))["watermark"].get(item[4:], "")
                await edit(
                    query,
                    sc(f"💧 Saved {item[4:]}\n\n") + (value or sc("Not set.")),
                    back(query.from_user.id, "manager:watermark"),
                )
            elif item.startswith("delete"):
                key = item[6:]
                settings = await services.db.get_settings(query.from_user.id)
                values = dict(settings["watermark"])
                values[key] = ""
                await services.db.set_setting(query.from_user.id, "watermark", values)
                await show_watermark(query, services)
        elif action.startswith("replacer:"):
            if not await require_feature(query, services, "replacer"):
                return
            item = action.split(":", 1)[1]
            if item == "link":
                await services.db.set_flow(query.from_user.id, "REPLACER_LINK")
                await edit(query, sc("Send the replacement https:// link, or <code>clear</code>. /cancel"))
            elif item == "username":
                await services.db.set_flow(query.from_user.id, "REPLACER_USERNAME")
                await edit(query, sc("Send the replacement @username, or <code>clear</code>. /cancel"))
            elif item == "pair":
                await services.db.set_flow(query.from_user.id, "REPLACER_PAIR_OLD")
                await edit(query, sc("Send the old word/text to replace. /cancel"))
            elif item == "clearpairs":
                settings = await services.db.get_settings(query.from_user.id)
                values = dict(settings["replacer"])
                values["pairs"] = []
                await services.db.set_setting(query.from_user.id, "replacer", values)
                await show_replacer(query, services)
        elif action.startswith("numbering:"):
            if not await require_feature(query, services, "numbering"):
                return
            item = action.split(":", 1)[1]
            if item.startswith("style:"):
                settings = await services.db.get_settings(query.from_user.id)
                values = dict(settings["numbering"])
                values["style"] = item[6:]
                await services.db.set_setting(query.from_user.id, "numbering", values)
                await show_numbering(query, services)
            elif item == "start":
                await services.db.set_flow(query.from_user.id, "NUMBERING_START")
                await edit(query, sc("Send the start number. /cancel"))
        elif action.startswith("bullets:"):
            if not await require_feature(query, services, "bullets"):
                return
            item = action.split(":", 1)[1]
            if item == "set":
                await services.db.set_flow(query.from_user.id, "BULLETS")
                await edit(query, sc("Send one emoji or a comma-separated emoji list. /cancel"))
            elif item == "random":
                settings = await services.db.get_settings(query.from_user.id)
                values = dict(settings["bullets"])
                values["random"] = not bool(values.get("random"))
                await services.db.set_setting(query.from_user.id, "bullets", values)
                await show_bullets(query, services)
        elif action.startswith("seller:"):
            if not await require_feature(query, services, "course_seller"):
                return
            item = action.split(":", 1)[1]
            if item == "set":
                await services.db.set_flow(query.from_user.id, "SELLER")
                await edit(query, sc("Send the seller name or @username. /cancel"))
            elif item == "placement":
                settings = await services.db.get_settings(query.from_user.id)
                values = dict(settings["seller"])
                values["placement"] = "before" if values.get("placement") == "after" else "after"
                await services.db.set_setting(query.from_user.id, "seller", values)
                await show_seller(query, services)
        elif action == "pi:add":
            await services.db.set_flow(query.from_user.id, "PI_TARGET")
            await edit(
                query,
                sc("Send an extra Pi target channel ID or @username. It will be validated when a job starts. /cancel"),
            )
        elif action.startswith("pi:remove:"):
            settings = await services.db.get_settings(query.from_user.id)
            pi_targets = list(settings.get("pi_targets", []))
            try:
                pi_targets.pop(int(action.rsplit(":", 1)[1]))
            except (ValueError, IndexError):
                pass
            await services.db.set_setting(query.from_user.id, "pi_targets", pi_targets)
            await show_pi(query, services)
        elif action.startswith("delta:client:"):
            if not await require_feature(query, services, "delta"):
                return
            flow = await services.db.get_flow(query.from_user.id)
            data = (flow or {}).get("data", {})
            if (flow or {}).get("kind") != "DELTA_CLIENT":
                await query.answer(sc("Delta setup expired. Start it again."), show_alert=True)
                return
            try:
                source, _linked_message_id = await services.engine.resolve_source(
                    query.from_user.id, action[len("delta:client:") :], data["source"]
                )
                delta_target = await services.engine.resolve_target(
                    query.from_user.id, action[len("delta:client:") :], data["target"]
                )
                settings = await services.db.get_settings(query.from_user.id)
                job_id = await services.engine.create_delta_job(
                    query.from_user.id, action[len("delta:client:") :], source, delta_target, settings
                )
                await services.db.clear_flow(query.from_user.id)
                await edit(
                    query,
                    sc(f"✅ Delta job started from message 1. Job ID: {job_id}"),
                    back(query.from_user.id, "settings:jobs"),
                )
            except Exception as exc:  # noqa: BLE001 - user-facing boundary normalizes backend errors
                await edit(
                    query,
                    sc(f"❌ Delta setup failed: {services.engine.clean_error(exc)}"),
                    back(query.from_user.id, "manager:home"),
                )
