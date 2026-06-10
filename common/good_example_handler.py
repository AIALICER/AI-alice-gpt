"""
✅ / ❌ リアクションで会話例を system_instruction に追記する。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import discord

GOOD_EXAMPLES_MARKER = "[GOOD_EXAMPLES_FROM_FEEDBACK]"
BAD_EXAMPLES_MARKER = "[BAD_EXAMPLES_FROM_FEEDBACK]"
MAX_EXAMPLE_BLOCKS = 40

JST = ZoneInfo("Asia/Tokyo")
FeedbackKind = Literal["good", "bad"]

_CHECK_MARK_CHARS = frozenset({"✅", "☑", "✔", "✔️", "\N{WHITE HEAVY CHECK MARK}"})
_CHECK_MARK_NAMES = frozenset(
    {"white_check_mark", "check_mark", "ballot_box_with_check", "\N{WHITE HEAVY CHECK MARK}"}
)

_X_MARK_CHARS = frozenset({"❌", "✖", "✖️", "×", "\N{CROSS MARK}"})
_X_MARK_NAMES = frozenset(
    {"x", "X", "negative_squared_cross_mark", "cross_mark", "no_entry", "\N{CROSS MARK}"}
)

_MARKER_BY_KIND: dict[FeedbackKind, str] = {
    "good": GOOD_EXAMPLES_MARKER,
    "bad": BAD_EXAMPLES_MARKER,
}

_INTRO_BY_KIND: dict[FeedbackKind, str] = {
    "good": (
        f"\n\n{GOOD_EXAMPLES_MARKER}\n"
        "以下は先生が ✅ で評価した会話例です。"
        "文体・トーン・応答の質を参考にしてください。\n"
    ),
    "bad": (
        f"\n\n{BAD_EXAMPLES_MARKER}\n"
        "以下は先生が ❌ / :X: で評価した会話例です。"
        "このような応答は避けてください。\n"
    ),
}

_LABEL_BY_KIND: dict[FeedbackKind, str] = {
    "good": "良い例",
    "bad": "悪い例",
}


def classify_feedback_emoji(emoji: discord.PartialEmoji | str) -> FeedbackKind | None:
    if _is_check_mark(emoji):
        return "good"
    if _is_x_mark(emoji):
        return "bad"
    return None


def _is_check_mark(emoji: discord.PartialEmoji | str) -> bool:
    if isinstance(emoji, str):
        return emoji in _CHECK_MARK_CHARS
    name = getattr(emoji, "name", None) or ""
    if name in _CHECK_MARK_CHARS or name in _CHECK_MARK_NAMES:
        return True
    if len(name) == 1 and ord(name) in {0x2705, 0x2611, 0x2714}:
        return True
    return str(emoji) in _CHECK_MARK_CHARS


def _is_x_mark(emoji: discord.PartialEmoji | str) -> bool:
    if isinstance(emoji, str):
        return emoji in _X_MARK_CHARS
    name = getattr(emoji, "name", None) or ""
    if name in _X_MARK_CHARS or name in _X_MARK_NAMES:
        return True
    if len(name) == 1 and ord(name) in {0x274C, 0x2716, 0x00D7}:
        return True
    return str(emoji) in _X_MARK_CHARS


def is_white_check_mark(emoji: discord.PartialEmoji | str) -> bool:
    """後方互換。"""
    return _is_check_mark(emoji)


def resolve_instruction_path(path: str | Path) -> Path:
    """system_instruction.txt を絶対パスに解決する。"""
    p = Path(path)
    if p.is_file():
        return p.resolve()
    if p.is_absolute():
        return p
    cwd_candidate = (Path.cwd() / p).resolve()
    if cwd_candidate.is_file():
        return cwd_candidate
    root = Path(__file__).resolve().parents[1]
    root_candidate = (root / p).resolve()
    if root_candidate.is_file():
        return root_candidate
    return cwd_candidate


def load_system_instruction(path: str | Path) -> str:
    return resolve_instruction_path(path).read_text(encoding="utf-8")


def _normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


async def collect_user_prompt_and_response(
    channel: discord.abc.Messageable,
    bot_response: discord.Message,
    *,
    bot_user_id: int,
    user_label: str = "先生",
    bot_label: str = "アリス",
) -> list[tuple[str, str]]:
    """直前のユーザー発言と、リアクション対象の Bot 応答だけを返す。"""
    user_message: discord.Message | None = None
    async for msg in channel.history(limit=30, before=bot_response):
        if msg.type not in (discord.MessageType.default, discord.MessageType.reply):
            continue
        content = (msg.content or "").strip()
        if not content:
            continue
        if msg.author.id == bot_user_id:
            continue
        user_message = msg
        break

    exchanges: list[tuple[str, str]] = []
    if user_message:
        exchanges.append((user_label, user_message.content.strip()))
    bot_text = (bot_response.content or "").strip()
    if bot_text:
        exchanges.append((bot_label, bot_text))
    return exchanges


def format_example_block(
    exchanges: list[tuple[str, str]],
    *,
    kind: FeedbackKind,
) -> str:
    if not exchanges:
        return ""
    timestamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    lines = [f"--- {_LABEL_BY_KIND[kind]} {timestamp} ---"]
    for label, text in exchanges:
        parts = text.splitlines() or [""]
        lines.append(f"{label}: {parts[0]}")
        for part in parts[1:]:
            lines.append(f"  {part}")
    return "\n".join(lines)


def _ensure_marker_section(content: str, kind: FeedbackKind) -> str:
    marker = _MARKER_BY_KIND[kind]
    if marker in content:
        return content
    return content.rstrip() + _INTRO_BY_KIND[kind]


def _trim_example_blocks(section_body: str, kind: FeedbackKind) -> str:
    label = _LABEL_BY_KIND[kind]
    parts = re.split(rf"(?=--- {label} \d{{4}}-\d{{2}}-\d{{2}})", section_body)
    header = parts[0]
    blocks = [p for p in parts[1:] if p.strip()]
    if len(blocks) <= MAX_EXAMPLE_BLOCKS:
        return header + "".join(blocks)
    return header + "".join(blocks[-MAX_EXAMPLE_BLOCKS:])


def append_feedback_example(
    system_instruction_path: str | Path,
    block: str,
    *,
    kind: FeedbackKind,
    bot_label: str = "アリス",
) -> tuple[bool, str]:
    """system_instruction.txt に良い例 / 悪い例を追記する。"""
    path = resolve_instruction_path(system_instruction_path)
    if not path.is_file():
        return False, f"system_instruction が見つかりません: {path}"

    block = block.strip()
    if not block:
        return False, "追記する会話が空です"

    prefix = f"{bot_label}:"
    bot_lines = [line for line in block.splitlines() if line.startswith(prefix)]
    if not bot_lines:
        return False, f"{bot_label} の応答行がありません"

    marker = _MARKER_BY_KIND[kind]
    content = path.read_text(encoding="utf-8")
    signature = _normalize_line(bot_lines[-1])
    if signature and signature in content:
        return False, f"同じ{_LABEL_BY_KIND[kind]}は既に保存済みです"

    content = _ensure_marker_section(content, kind)
    marker_index = content.index(marker)
    before = content[: marker_index + len(marker)]
    after = content[marker_index + len(marker) :]

    label = _LABEL_BY_KIND[kind]
    split_match = re.search(rf"(?=--- {label} \d{{4}}-\d{{2}}-\d{{2}})", after)
    if split_match:
        intro = after[: split_match.start()]
        body = after[split_match.start() :]
    else:
        intro = after
        body = ""

    new_body = _trim_example_blocks(body + block + "\n\n", kind)
    path.write_text(before + intro + new_body, encoding="utf-8")
    return True, f"{_LABEL_BY_KIND[kind]}を system_instruction に保存しました"


def append_good_example(system_instruction_path: str | Path, block: str) -> tuple[bool, str]:
    """後方互換。"""
    return append_feedback_example(system_instruction_path, block, kind="good")
