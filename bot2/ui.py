"""UI rendering helpers. Telegram has no reliable inline-button colours, so emoji convey intent."""

from __future__ import annotations

import html
import platform
import re
from collections.abc import Iterable
from datetime import UTC, datetime

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import PLAN_LABELS, PLAN_PRICES, Settings, plan_at_least

_SMALL_CAPS = str.maketrans(
    {
        **{letter: cap for letter, cap in zip("abcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ", strict=True)},
        **{letter: cap for letter, cap in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ", strict=True)},
    }
)
# Protect things that should stay readable/clickable exactly as supplied.
_PROTECTED = re.compile(r"<[^>]*>|https?://[^\s<>]+|@[A-Za-z0-9_]{4,}|/[A-Za-z0-9_]+|\{[A-Za-z_]+\}")


def sc(text: str) -> str:
    """Convert ordinary UI copy to small caps while preserving tags, URLs and placeholders."""
    pieces: list[str] = []
    cursor = 0
    for match in _PROTECTED.finditer(text):
        pieces.append(text[cursor : match.start()].translate(_SMALL_CAPS))
        pieces.append(match.group(0))
        cursor = match.end()
    pieces.append(text[cursor:].translate(_SMALL_CAPS))
    return "".join(pieces)


def e(value: object) -> str:
    return html.escape(str(value), quote=False)


def cb(user_id: int, action: str) -> str:
    """Compact callback form with server-side ownership binding."""
    return f"u{user_id}|{action}"


def action_for(user_id: int, callback_data: str | None) -> str | None:
    prefix = f"u{user_id}|"
    if callback_data and callback_data.startswith(prefix):
        return callback_data[len(prefix) :]
    return None


def button(user_id: int, label: str, action: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(sc(label), callback_data=cb(user_id, action))


def url_button(label: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(sc(label), url=url)


def markup(rows: Iterable[Iterable[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(row) for row in rows])


def back(user_id: int, action: str = "home") -> InlineKeyboardMarkup:
    return markup([[button(user_id, "🔵 Back", action)]])


def home_keyboard(user_id: int, config: Settings, is_owner: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [button(user_id, "🔵 Help", "home:help"), button(user_id, "🔵 About", "home:about")],
        [button(user_id, "🔵 Settings", "settings:home"), button(user_id, "💳 Plans", "plans:home")],
        [button(user_id, "🔵 Referral", "home:referral"), url_button("📚 How To Use Me", config.tutorial_url)],
        [url_button("📣 Main Channel", config.main_channel_url), url_button("🛟 Support", config.support_url)],
        [url_button("🔔 Updates", config.updates_url), url_button("👨‍💻 Contact Admin", config.admin_url)],
    ]
    if is_owner:
        rows.append([button(user_id, "🛠️ Admin Panel", "admin:home")])
    return markup(rows)


def welcome_text(name: str) -> str:
    return sc(
        f"Hello {e(name)}\n\n"
        "I'm a powerful auto forward bot.\n\n"
        "I can forward all messages from one channel to another channel ➜ with more features.\n"
        "Click Help button to know more about me."
    )


def help_text() -> str:
    return sc(
        "📚 Available commands\n\n"
        "/start — open the welcome menu\n"
        "/forward — start forwarding messages\n"
        "/settings — open settings\n"
        "/unequify — remove duplicate media\n"
        "/myplan — view your subscription\n"
        "/transfer — transfer your active plan\n"
        "/cancel — cancel the current setup\n"
        "/reset — reset your settings\n\n"
        "💢 Features\n"
        "Forward public-channel content you are allowed to access, use a userbot for private chats where your own account is a member, set captions and buttons, skip duplicates, filter message types, and skip extensions, keywords or file sizes.\n\n"
        "Protected-content restrictions are respected; this bot does not bypass them."
    )


def how_to_text() -> str:
    return sc(
        "⚠️ Before forwarding:\n"
        "► Add a bot or userbot\n"
        "► Add at least one to your target channel as an admin\n"
        "► You can add bots using /settings\n"
        "► If the From channel is private, your userbot must be a member there, or your bot needs permission there\n"
        "► Then use /forward to forward messages"
    )


def status_text(users: int, bots: int, channels: int) -> str:
    return sc(
        "╭──────❪ 🤖 Bot Status ❫─────⍟\n│\n"
        f"├👨 Users : {users}\n│\n"
        f"├🤖 Bots : {bots}\n│\n"
        f"├📣 Channels : {channels}\n"
        "╰───────────────────⍟"
    )


def plan_text(user: dict) -> str:
    registered = user.get("registered_at") or datetime.now(UTC)
    if registered.tzinfo is None:
        registered = registered.replace(tzinfo=UTC)
    plan = user.get("plan", "free")
    expires = user.get("plan_expires_at")
    if plan == "free" or not expires:
        time_left = "N/A"
    else:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        seconds = max(0, int((expires - datetime.now(UTC)).total_seconds()))
        time_left = f"{seconds // 86400}d {(seconds % 86400) // 3600}h"
    features = [
        ("Forwarding", "forward"),
        ("ZC Delta Mode", "delta"),
        ("ZC Watermark", "watermark"),
        ("ZC Replacer & Remover", "replacer"),
        ("ZC Link Remover", "link_remover"),
        ("ZC Gamma Mode", "gamma"),
        ("Unequify", "unequify"),
    ]
    unlocked = "\n".join(
        f"{'✅' if plan_at_least(plan, feature_minimum(feature)) else '❌'} {label}" for label, feature in features
    )
    return sc(
        "⚜️💎 My Plan 💎⚜️\n\n"
        f"👤 User : {e(user.get('name', 'User'))}\n"
        f"⚡ User ID : {user.get('_id')}\n"
        f"💎 Plan : {PLAN_LABELS.get(plan, PLAN_LABELS['free'])}\n"
        f"📊 Plan Type : {plan.title()}\n"
        f"📅 Registration Date : {registered.astimezone().strftime('%d-%m-%Y')}\n"
        f"🕐 Registration Time : {registered.astimezone().strftime('%I:%M:%S %p')}\n"
        f"⏰ Time Left : {time_left}\n\n"
        f"✨ Features Unlocked :\n{unlocked}\n\n"
        "💡 Tip: Upgrade to unlock premium features!"
    )


def feature_minimum(feature: str) -> str:
    from .config import FEATURE_PLANS

    return FEATURE_PLANS[feature]


def plans_overview(current: str) -> str:
    def current_text(name: str) -> str:
        return " (Current)" if name == current else ""

    return sc(
        "💳 Subscription Plans 💳\n\nChoose the perfect plan for your needs.\n\n"
        f"🆓 Free{current_text('free')} — configuration options only — Free\n\n"
        f"⭐ Plus{current_text('plus')} — forwarding, no ZC Manager features — {PLAN_PRICES['plus']}\n\n"
        f"💎 Pro{current_text('pro')} — Gamma, Watermark, Text Only plus Plus — {PLAN_PRICES['pro']}\n\n"
        f"♾️ Infinity{current_text('infinity')} — Pro plus all Manager features except Delta, Theta and Pi — {PLAN_PRICES['infinity']}\n\n"
        f"🚀 Ultra{current_text('ultra')} — Infinity plus exclusive Delta, Theta and Pi — {PLAN_PRICES['ultra']}\n\n"
        "Use the buttons below to view details or contact admin to upgrade."
    )


def plan_detail(plan: str) -> str:
    details = {
        "plus": ["Forwarding one job at a time"],
        "pro": ["Forwarding one job at a time", "ZC Gamma Mode", "ZC Watermark", "ZC Text Only Mode"],
        "infinity": [
            "Everything in Pro",
            "ZC Replacer & Remover",
            "ZC Link Remover",
            "ZC Alpha Mode",
            "ZC Course Seller Mode",
            "Auto Numbering and Bullets",
            "Unequify",
        ],
        "ultra": ["Everything in Infinity", "ZC Delta Mode", "ZC Theta Mode", "ZC Pi Mode"],
        "free": ["Configuration options"],
    }
    items = "\n".join(f"✅ {item}" for item in details[plan])
    return sc(
        f"{PLAN_LABELS[plan]} Plan\n\n"
        f"Price: {PLAN_PRICES[plan]}\n\n"
        f"Features included:\n{items}\n\n"
        "💡 Want to upgrade? Contact admin to purchase this plan."
    )


def about_text(kurigram_version: str, mongo_version: str, support: str, updates: str, admin: str) -> str:
    return sc(
        "╭──────❪ 🤖 Bot Details ❫─────〄\n"
        "│ 🤖 Name : ZC Forward Bot\n"
        f"│ 👨‍💻 Support Group : {support}\n"
        f"│ 🛰️ Updates : {updates}\n"
        f"│ 🧠 Language : Python {platform.python_version()}\n"
        f"│ ⚙️ Library : Kurigram {kurigram_version}\n"
        f"│ 🗃️ Database : MongoDB {mongo_version}\n"
        f"│ 🌐 Owner : Contact {admin}\n"
        "│ 💎 Powered by : ZC Developers ⚡\n"
        "╰───────────────────⍟\n"
        "✨ Thank you for using ZC Forward Bot ✨"
    )


def onoff(value: bool) -> str:
    return "✅ ON" if value else "❌ OFF"
