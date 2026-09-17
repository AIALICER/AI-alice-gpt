"""
👍 / 👎 リアクションで会話例を DB に保存し、system_instruction 生成時にマージする。
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import discord

GOOD_EXAMPLES_MARKER = "[GOOD_EXAMPLES_FROM_FEEDBACK]"
BAD_EXAMPLES_MARKER = "[BAD_EXAMPLES_FROM_FEEDBACK]"
MAX_LOAD_EXAMPLE_BLOCKS = 40  # Gemini に渡す際の読み込み上限（DB からは削除しない）

JST = ZoneInfo("Asia/Tokyo")
FeedbackKind = Literal["good", "bad"]

_THUMBSUP_CHARS = frozenset({"👍", "\N{THUMBS UP SIGN}"})
_THUMBSUP_NAMES = frozenset({"thumbsup", "+1", "thumbs_up"})

_THUMBSDOWN_CHARS = frozenset({"👎", "\N{THUMBS DOWN SIGN}"})
_THUMBSDOWN_NAMES = frozenset({"thumbsdown", "-1", "thumbs_down"})

_MARKER_BY_KIND: dict[FeedbackKind, str] = {
    "good": GOOD_EXAMPLES_MARKER,
    "bad": BAD_EXAMPLES_MARKER,
}

_INTRO_BY_KIND: dict[FeedbackKind, str] = {
    "good": (
        f"\n\n{GOOD_EXAMPLES_MARKER}\n"
        "以下は先生が 👍 で評価した会話例です。"
        "文体・トーン・応答の質を参考にしてください。\n"
    ),
    "bad": (
        f"\n\n{BAD_EXAMPLES_MARKER}\n"
        "以下は先生が 👎 で評価した会話例です。"
        "このような応答は避けてください。\n"
    ),
}

_LABEL_BY_KIND: dict[FeedbackKind, str] = {
    "good": "良い例",
    "bad": "悪い例",
}

_KIND_BY_LABEL: dict[str, FeedbackKind] = {v: k for k, v in _LABEL_BY_KIND.items()}


def classify_feedback_emoji(emoji: discord.PartialEmoji | str) -> FeedbackKind | None:
    if _is_thumbsup(emoji):
        return "good"
    if _is_thumbsdown(emoji):
        return "bad"
    return None


def _is_thumbsup(emoji: discord.PartialEmoji | str) -> bool:
    if isinstance(emoji, str):
        return emoji in _THUMBSUP_CHARS
    name = getattr(emoji, "name", None) or ""
    if name in _THUMBSUP_CHARS or name in _THUMBSUP_NAMES:
        return True
    if len(name) == 1 and ord(name) == 0x1F44D:
        return True
    return str(emoji) in _THUMBSUP_CHARS


def _is_thumbsdown(emoji: discord.PartialEmoji | str) -> bool:
    if isinstance(emoji, str):
        return emoji in _THUMBSDOWN_CHARS
    name = getattr(emoji, "name", None) or ""
    if name in _THUMBSDOWN_CHARS or name in _THUMBSDOWN_NAMES:
        return True
    if len(name) == 1 and ord(name) == 0x1F44E:
        return True
    return str(emoji) in _THUMBSDOWN_CHARS


def is_thumbsup(emoji: discord.PartialEmoji | str) -> bool:
    return _is_thumbsup(emoji)


def is_thumbsdown(emoji: discord.PartialEmoji | str) -> bool:
    return _is_thumbsdown(emoji)


def is_white_check_mark(emoji: discord.PartialEmoji | str) -> bool:
    """後方互換（👍 のみ）。"""
    return _is_thumbsup(emoji)


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


def strip_embedded_feedback_sections(content: str) -> str:
    """ファイル内の旧フィードバック追記セクションを除去する。"""
    cut_at: int | None = None
    for marker in (GOOD_EXAMPLES_MARKER, BAD_EXAMPLES_MARKER):
        idx = content.find(marker)
        if idx != -1 and (cut_at is None or idx < cut_at):
            cut_at = idx
    if cut_at is None:
        return content
    return content[:cut_at].rstrip()


def load_base_system_instruction(path: str | Path) -> str:
    """system_instruction.txt の本体のみ読み込む（フィードバックセクション除く）。"""
    instruction_path = resolve_instruction_path(path)
    if not instruction_path.is_file():
        return ""
    return strip_embedded_feedback_sections(
        instruction_path.read_text(encoding="utf-8")
    )


def load_system_instruction(path: str | Path) -> str:
    """後方互換: ファイル本体のみ（DB マージなし）。"""
    return load_base_system_instruction(path)


def build_system_instruction(path: str | Path, db_path: str) -> str:
    """ファイル本体 + DB 内の会話例を結合した system_instruction を返す。"""
    instruction_path = resolve_instruction_path(path)
    if instruction_path.is_file():
        raw_content = instruction_path.read_text(encoding="utf-8")
        _migrate_embedded_examples_if_needed(instruction_path, raw_content, db_path)
    base = load_base_system_instruction(instruction_path)
    examples = _format_examples_from_db(db_path)
    if not examples:
        return base
    if base:
        return base + examples
    return examples.lstrip("\n")


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
    created_at: datetime | None = None,
) -> str:
    if not exchanges:
        return ""
    timestamp = (created_at or datetime.now(JST)).strftime("%Y-%m-%d %H:%M")
    lines = [f"--- {_LABEL_BY_KIND[kind]} {timestamp} ---"]
    for label, text in exchanges:
        parts = text.splitlines() or [""]
        lines.append(f"{label}: {parts[0]}")
        for part in parts[1:]:
            lines.append(f"  {part}")
    return "\n".join(lines)


def save_feedback_example(
    db_path: str,
    exchanges: list[tuple[str, str]],
    *,
    kind: FeedbackKind,
    bot_label: str = "アリス",
    discord_message_id: int | None = None,
) -> tuple[bool, str]:
    """DB に良い例 / 悪い例を保存する。"""
    if not exchanges:
        return False, "追記する会話が空です"

    user_message: str | None = None
    user_label = "先生"
    bot_message: str | None = None
    for label, text in exchanges:
        if label == bot_label:
            bot_message = text.strip()
        else:
            user_label = label
            user_message = text.strip()

    if not bot_message:
        return False, f"{bot_label} の応答がありません"

    signature = _normalize_line(bot_message.splitlines()[-1] if bot_message else "")
    conn = sqlite3.connect(db_path)
    try:
        if signature:
            row = conn.execute(
                """
                SELECT 1 FROM feedback_examples
                WHERE kind = ? AND bot_message LIKE ?
                LIMIT 1
                """,
                (kind, f"%{signature}%"),
            ).fetchone()
            if row:
                return False, f"同じ{_LABEL_BY_KIND[kind]}は既に保存済みです"

        conn.execute(
            """
            INSERT INTO feedback_examples (
                kind, user_message, bot_message, user_label, bot_label, discord_message_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kind, user_message, bot_message, user_label, bot_label, discord_message_id),
        )
        conn.commit()
    finally:
        conn.close()

    return True, f"{_LABEL_BY_KIND[kind]}を DB に保存しました"


def append_feedback_example(
    system_instruction_path: str | Path,
    block: str,
    *,
    kind: FeedbackKind,
    bot_label: str = "アリス",
) -> tuple[bool, str]:
    """後方互換: block 文字列から exchanges を復元して DB 保存は行わない。"""
    exchanges = _parse_exchange_block(block)
    if not exchanges:
        return False, "会話ブロックの解析に失敗しました"
    return save_feedback_example(
        _legacy_db_path_from_instruction(system_instruction_path),
        exchanges,
        kind=kind,
        bot_label=bot_label,
    )


def append_good_example(system_instruction_path: str | Path, block: str) -> tuple[bool, str]:
    """後方互換。"""
    return append_feedback_example(system_instruction_path, block, kind="good")


def _legacy_db_path_from_instruction(path: str | Path) -> str:
    """instruction パスからキャラ名を推測して DB パスを返す（後方互換用）。"""
    from .config_base import get_db_path

    instruction_path = resolve_instruction_path(path)
    parts = instruction_path.parts
    if "characters" in parts:
        idx = parts.index("characters")
        if idx + 1 < len(parts):
            return get_db_path(parts[idx + 1])
    return get_db_path("alice")


def _normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _format_examples_from_db(db_path: str) -> str:
    sections: list[str] = []
    for kind in ("good", "bad"):
        blocks = _fetch_example_blocks(db_path, kind)
        if not blocks:
            continue
        sections.append(_INTRO_BY_KIND[kind] + "\n\n".join(blocks) + "\n")
    return "".join(sections)


def _fetch_example_blocks(db_path: str, kind: FeedbackKind) -> list[str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT user_label, user_message, bot_label, bot_message, created_at
            FROM feedback_examples
            WHERE kind = ?
            ORDER BY created_at ASC, id ASC
            """,
            (kind,),
        ).fetchall()
    finally:
        conn.close()

    if len(rows) > MAX_LOAD_EXAMPLE_BLOCKS:
        rows = rows[-MAX_LOAD_EXAMPLE_BLOCKS:]

    blocks: list[str] = []
    for row in rows:
        exchanges: list[tuple[str, str]] = []
        if row["user_message"]:
            exchanges.append((row["user_label"], row["user_message"]))
        exchanges.append((row["bot_label"], row["bot_message"]))
        created_at = datetime.fromisoformat(row["created_at"])
        blocks.append(
            format_example_block(exchanges, kind=kind, created_at=created_at)
        )
    return blocks


def _migrate_embedded_examples_if_needed(
    instruction_path: Path,
    raw_content: str,
    db_path: str,
) -> None:
    """旧 system_instruction.txt 内の会話例を DB へ一度だけ移行する。"""
    if not any(marker in raw_content for marker in _MARKER_BY_KIND.values()):
        return

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM feedback_examples").fetchone()[0]
        if count > 0:
            return

        migrated = 0
        for kind in ("good", "bad"):
            marker = _MARKER_BY_KIND[kind]
            marker_index = raw_content.find(marker)
            if marker_index == -1:
                continue
            section = raw_content[marker_index + len(marker) :]
            next_marker_index = len(section)
            for other_marker in _MARKER_BY_KIND.values():
                if other_marker == marker:
                    continue
                other_index = section.find(other_marker)
                if other_index != -1:
                    next_marker_index = min(next_marker_index, other_index)
            section = section[:next_marker_index]
            for block_text in _split_example_blocks(section):
                exchanges = _parse_exchange_block(block_text)
                if not exchanges:
                    continue
                bot_label, bot_message = exchanges[-1]
                bot_message = bot_message.strip()
                if not bot_message:
                    continue
                user_label = "先生"
                user_message: str | None = None
                if len(exchanges) > 1:
                    user_label, user_message = exchanges[0]
                    user_message = user_message.strip() or None
                conn.execute(
                    """
                    INSERT INTO feedback_examples (
                        kind, user_message, bot_message, user_label, bot_label
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (kind, user_message, bot_message, user_label, bot_label),
                )
                migrated += 1

        if migrated:
            conn.commit()
            stripped = strip_embedded_feedback_sections(raw_content)
            instruction_path.write_text(stripped + "\n", encoding="utf-8")
            print(
                f"[good_example_handler] {instruction_path.name} から "
                f"{migrated} 件の会話例を DB に移行しました"
            )
    finally:
        conn.close()


def _split_example_blocks(section: str) -> list[str]:
    label_pattern = "|".join(re.escape(label) for label in _LABEL_BY_KIND.values())
    matches = list(
        re.finditer(
            rf"--- ({label_pattern}) \d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}} ---",
            section,
        )
    )
    if not matches:
        return []
    blocks: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        blocks.append(section[start:end].strip())
    return blocks


def _parse_exchange_block(block_text: str) -> list[tuple[str, str]]:
    exchanges: list[tuple[str, str]] = []
    current_label: str | None = None
    current_lines: list[str] = []

    for line in block_text.splitlines():
        if line.startswith("--- "):
            continue
        speaker_match = re.match(r"^([^:]+): (.*)$", line)
        if speaker_match and not line.startswith("  "):
            if current_label is not None:
                exchanges.append((current_label, "\n".join(current_lines).strip()))
            current_label = speaker_match.group(1)
            first_line = speaker_match.group(2)
            current_lines = [first_line] if first_line else []
        elif line.startswith("  ") and current_label is not None:
            current_lines.append(line[2:])
        elif current_label is not None:
            current_lines.append(line)

    if current_label is not None:
        exchanges.append((current_label, "\n".join(current_lines).strip()))
    return exchanges
