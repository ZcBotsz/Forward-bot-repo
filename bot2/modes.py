"""Pure forwarding pipeline helpers.

The engine converts incoming Telegram entities to Telegram's HTML representation first, then
these functions transform HTML. This preserves hidden-link entity semantics while avoiding
unsafe offset arithmetic on UTF-16 entity offsets.
"""

from __future__ import annotations

import html
import re
import secrets
from dataclasses import dataclass
from typing import Any

_URL = re.compile(r"(?<![\w\"'=])(https?://[^\s<]+|(?:t\.me|telegram\.me)/[^\s<]+)", re.IGNORECASE)
_USERNAME = re.compile(r"(?<![\w@])@[A-Za-z0-9_]{4,}")
_ANCHOR = re.compile(r"<a\s+([^>]*?)href\s*=\s*([\"'])(.*?)\2([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_QUALITY = re.compile(r"\b((?:2160|1440|1080|720|480|360)p|4k)\b", re.IGNORECASE)
_BUTTON = re.compile(r"\[([^\[\]\n]{1,64})\]\[buttonurl:(https?://[^\s\]]+)\]", re.IGNORECASE)


@dataclass(slots=True)
class MediaInfo:
    kind: str
    filename: str = ""
    size: int = 0
    unique_id: str = ""
    original_html: str = ""
    is_text: bool = False
    source_link: str = ""


@dataclass(slots=True)
class PipelineResult:
    accepted: bool
    reason: str = ""
    text: str = ""
    signature: str = ""


def media_info(message: Any) -> MediaInfo:
    """Extract the small, library-neutral subset of a Pyrogram message used by the pipeline."""
    kind = "text" if getattr(message, "text", None) and not getattr(message, "media", None) else "unknown"
    for candidate in ("photo", "video", "document", "audio", "voice", "animation", "sticker", "poll", "video_note"):
        if getattr(message, candidate, None) is not None:
            kind = candidate
            break
    media = getattr(message, kind, None)
    filename = getattr(media, "file_name", "") if media else ""
    size = int(getattr(media, "file_size", 0) or 0) if media else 0
    unique_id = str(getattr(media, "file_unique_id", "") or "") if media else ""
    # Pyrogram offers .html for text/caption; fall back safely for test doubles / old builds.
    if kind == "text":
        raw = getattr(getattr(message, "text", None), "html", None)
        original = raw or getattr(message, "text", "") or ""
    else:
        raw = getattr(getattr(message, "caption", None), "html", None)
        original = raw or getattr(message, "caption", "") or ""
    return MediaInfo(kind, filename, size, unique_id, str(original), kind == "text")


def file_signature(info: MediaInfo) -> str:
    """Only media has a stable Telegram unique ID. Text is intentionally not de-duped."""
    if not info.unique_id:
        return ""
    return f"{info.unique_id}:{info.size}:{info.filename.lower()}"


def accepts_filters(info: MediaInfo, settings: dict[str, Any]) -> tuple[bool, str]:
    filters = settings.get("filters", {})
    if not bool(filters.get(info.kind, True)):
        return False, "filtered"
    lower_name = info.filename.lower()
    extensions = [str(value).lower().lstrip(".") for value in filters.get("skip_extensions", [])]
    if any(lower_name.endswith(f".{ext}") for ext in extensions if ext):
        return False, "filtered"
    plain_text = strip_html(info.original_html).lower()
    keywords = [str(value).lower() for value in filters.get("skip_keywords", [])]
    if any(word and word in plain_text for word in keywords):
        return False, "filtered"
    max_size_mb = float(filters.get("max_size_mb", 0) or 0)
    if max_size_mb and info.size > max_size_mb * 1024 * 1024:
        return False, "filtered"
    return True, ""


def accepts_modes(info: MediaInfo, modes: dict[str, Any]) -> tuple[bool, str]:
    if modes.get("gamma") and info.kind != "photo":
        return False, "mode"
    if modes.get("text_only") and not info.is_text:
        return False, "mode"
    return True, ""


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)


def remove_links_and_usernames(value: str, remove_usernames: bool = True) -> str:
    """Remove visible URLs and unwrap HTML anchors without removing their visible label."""
    value = _ANCHOR.sub(lambda match: match.group(5), value)
    value = _URL.sub("", value)
    if remove_usernames:
        value = _USERNAME.sub("", value)
    return cleanup_text(value)


def remove_links_only(value: str) -> str:
    return cleanup_text(_URL.sub("", _ANCHOR.sub(lambda match: match.group(5), value)))


def replace_links_and_usernames(value: str, link: str, username: str, pairs: list[dict[str, str]]) -> str:
    """Replace href targets, visible links, usernames and configured word pairs in HTML safely."""

    def anchor_replacement(match: re.Match[str]) -> str:
        target = link or match.group(3)
        visible = match.group(5)
        # Deliberately do not alter visible anchor text unless a word pair says so below.
        return f'<a {match.group(1)}href="{html.escape(target, quote=True)}"{match.group(4)}>{visible}</a>'

    value = _ANCHOR.sub(anchor_replacement, value)
    if link:
        value = _URL.sub(link, value)
    if username:
        clean = username if username.startswith("@") else f"@{username}"
        value = _USERNAME.sub(clean, value)
    # Longest entries first makes overlapping pairs predictable.
    for pair in sorted(pairs, key=lambda item: len(str(item.get("old", ""))), reverse=True):
        old, new = str(pair.get("old", "")), str(pair.get("new", ""))
        if old:
            value = value.replace(old, new)
    return value


def cleanup_text(value: str) -> str:
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def human_size(size: int) -> str:
    if not size:
        return ""
    units = ("B", "KB", "MB", "GB", "TB")
    number = float(size)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            return f"{number:.1f} {unit}" if unit != "B" else f"{int(number)} B"
        number /= 1024
    return ""


def detect_language(filename: str) -> str:
    tokens = {
        "hindi": "Hindi",
        "english": "English",
        "tamil": "Tamil",
        "telugu": "Telugu",
        "malayalam": "Malayalam",
        "kannada": "Kannada",
        "marathi": "Marathi",
        "bengali": "Bengali",
        "punjabi": "Punjabi",
        "korean": "Korean",
        "japanese": "Japanese",
    }
    lower = filename.lower().replace(".", " ").replace("-", " ").replace("_", " ")
    found = [label for token, label in tokens.items() if re.search(rf"\b{re.escape(token)}\b", lower)]
    return ", ".join(found)


def render_caption_template(template: str, info: MediaInfo, transformed_caption: str) -> str:
    """Render supported variables and discard lines with a missing variable value."""
    year_match = _YEAR.search(info.filename)
    quality_match = _QUALITY.search(info.filename)
    values = {
        "filename": info.filename,
        "size": human_size(info.size),
        "caption": transformed_caption,
        "year": year_match.group(1) if year_match else "",
        "language": detect_language(info.filename),
        "quality": quality_match.group(1) if quality_match else "",
        "type": info.kind,
    }
    output_lines: list[str] = []
    for line in template.splitlines():
        rendered = line
        missing = False
        for key, value in values.items():
            marker = "{" + key + "}"
            if marker in rendered:
                rendered = rendered.replace(marker, value)
                missing = missing or not bool(value)
        if not missing and rendered.strip():
            output_lines.append(rendered)
    return "\n".join(output_lines).strip()


def numbered_prefix(numbering: dict[str, Any], sequence: int) -> str:
    style = str(numbering.get("style", "{n}."))
    number = int(numbering.get("start", 1) or 1) + sequence
    emoji_digits = {0: "0️⃣", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣"}
    if style == "emoji":
        return "".join(emoji_digits[int(digit)] for digit in str(number))
    return style.replace("{n}", str(number))


def source_post_link(chat_id: int | str, username: str | None, message_id: int) -> str:
    if username:
        return f"https://t.me/{username.lstrip('@')}/{message_id}"
    raw = str(chat_id)
    raw = raw.removeprefix("-100")
    return f"https://t.me/c/{raw}/{message_id}"


def apply_pipeline(info: MediaInfo, settings: dict[str, Any], sequence: int = 0) -> PipelineResult:
    """Transform an accepted message's text/caption; dedupe is claimed by the engine."""
    accepted, reason = accepts_filters(info, settings)
    if not accepted:
        return PipelineResult(False, reason)
    modes = settings.get("modes", {})
    accepted, reason = accepts_modes(info, modes)
    if not accepted:
        return PipelineResult(False, reason)

    text = info.original_html
    # Remover is authoritative and intentionally prevents Replacer from running.
    if modes.get("remover"):
        text = remove_links_and_usernames(text)
    elif modes.get("replacer"):
        replacement = settings.get("replacer", {})
        text = replace_links_and_usernames(
            text,
            str(replacement.get("link", "")),
            str(replacement.get("username", "")),
            list(replacement.get("pairs", [])),
        )
    if modes.get("link_remover"):
        text = remove_links_only(text)

    # Caption templates apply to video/audio/documents only; photos retain their source caption.
    template = str(settings.get("caption", "") or "")
    if template and info.kind in {"video", "audio", "document"}:
        text = render_caption_template(template, info, text)

    if modes.get("numbering"):
        prefix = numbered_prefix(dict(settings.get("numbering", {})), sequence)
        text = f"{prefix} {text}".strip()
    if modes.get("bullets"):
        bullets = list(dict(settings.get("bullets", {})).get("items", [])) or ["📌"]
        random_mode = bool(dict(settings.get("bullets", {})).get("random", False))
        bullet = secrets.choice(bullets) if random_mode else bullets[sequence % len(bullets)]
        text = f"{bullet} {text}".strip()
    if modes.get("watermark"):
        watermark = dict(settings.get("watermark", {}))
        prefix, suffix = str(watermark.get("prefix", "")), str(watermark.get("suffix", ""))
        text = "\n".join(part for part in (prefix, text, suffix) if part).strip()
    if modes.get("course_seller"):
        seller = dict(settings.get("seller", {}))
        name = str(seller.get("name", "") or "")
        if name:
            line = f"Extracted by: {name}"
            text = f"{line}\n{text}" if seller.get("placement") == "before" else f"{text}\n{line}"
    if modes.get("theta") and info.source_link:
        text = f'{text}\n\n<a href="{html.escape(info.source_link, quote=True)}">Source post</a>'.strip()

    return PipelineResult(True, text=text, signature=file_signature(info))


def parse_buttons(value: str) -> list[list[tuple[str, str]]]:
    """Parse [Label][buttonurl:https://...] entries. ':same' joins the prior row."""
    rows: list[list[tuple[str, str]]] = []
    for line in value.splitlines():
        same = line.strip().endswith(":same")
        line = line.strip()[:-5].rstrip() if same else line.strip()
        matches = _BUTTON.findall(line)
        if not matches:
            if line:
                raise ValueError("Each button must use [Label][buttonurl:https://example.com].")
            continue
        row = [(label.strip(), url.strip()) for label, url in matches]
        if same and rows:
            rows[-1].extend(row)
        else:
            rows.append(row)
    if not rows:
        raise ValueError("No valid button was found.")
    if any(len(row) > 8 for row in rows):
        raise ValueError("A button row can contain at most 8 buttons.")
    return rows


def safe_buttons(value: Any) -> list[list[tuple[str, str]]]:
    if isinstance(value, list):
        try:
            return [[(str(label), str(url)) for label, url in row] for row in value]
        except (TypeError, ValueError):
            return []
    return []
