"""
bot_base.py からスラッシュコマンド定義を解析する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SlashCommandInfo:
    name: str
    description: str
    scope: str  # "all" | "alice"


def _alice_only_ranges(lines: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.search(
            r'if self\.character_name(\.lower\(\))?\s*==\s*["\']alice["\']',
            line,
        ):
            base_indent = len(line) - len(line.lstrip())
            start = i
            i += 1
            while i < len(lines):
                current = lines[i]
                stripped = current.strip()
                if not stripped:
                    i += 1
                    continue
                indent = len(current) - len(current.lstrip())
                if indent <= base_indent:
                    if stripped.startswith("else"):
                        i += 1
                        continue
                    break
                i += 1
            ranges.append((start, i))
            continue
        i += 1
    return ranges


def _scope_for_line(line_no: int, alice_ranges: list[tuple[int, int]]) -> str:
    for start, end in alice_ranges:
        if start <= line_no < end:
            return "alice"
    return "all"


def parse_slash_commands(bot_base_path: Path) -> list[SlashCommandInfo]:
    text = bot_base_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    alice_ranges = _alice_only_ranges(lines)

    pattern = re.compile(
        r"@self\.tree\.command\(\s*name\s*=\s*[\"']([^\"']+)[\"']"
        r"(?:\s*,\s*|\s*\n\s*)description\s*=\s*[\"']([^\"']+)[\"']",
        re.DOTALL,
    )

    commands: list[SlashCommandInfo] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        name, description = match.group(1), match.group(2)
        if name in seen:
            continue
        seen.add(name)
        line_no = text[: match.start()].count("\n")
        scope = _scope_for_line(line_no, alice_ranges)
        commands.append(SlashCommandInfo(name=name, description=description, scope=scope))

    return sorted(commands, key=lambda c: (c.scope != "all", c.name))


def commands_for_character(
    character_name: str, all_commands: list[SlashCommandInfo]
) -> list[SlashCommandInfo]:
    is_alice = character_name.lower() == "alice"
    return [cmd for cmd in all_commands if cmd.scope == "all" or (cmd.scope == "alice" and is_alice)]


def compare_help_vs_implemented(
    help_mentions: set[str],
    available: list[SlashCommandInfo],
) -> tuple[list[str], list[str]]:
    """(help_only_not_implemented, implemented_not_in_help)"""
    available_names = {c.name for c in available}
    help_only = sorted(help_mentions - available_names)
    not_in_help = sorted(available_names - help_mentions)
    return help_only, not_in_help
