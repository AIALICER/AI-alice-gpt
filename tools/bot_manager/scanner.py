"""
キャラクター一覧のスキャンと config / messages の読み書き。
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from tools.character_creator.messages_generator import REQUIRED_CONSTANTS


class BotManagerError(Exception):
    pass


@dataclass
class CharacterInfo:
    folder_name: str
    folder_path: Path
    config_path: Path
    messages_path: Path
    system_instruction_path: Path
    character_name: str
    display_name: str
    history_clear_command: str
    command_pattern: str
    special_commands: dict[str, dict[str, str]] = field(default_factory=dict)


def _read_config_field(tree: ast.Module, name: str) -> str | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
                    if isinstance(value, ast.Constant):
                        return str(value.value)
                    if name == "COMMAND_PATTERN" and isinstance(value, ast.Call):
                        if (
                            isinstance(value.func, ast.Attribute)
                            and value.func.attr == "compile"
                            and value.args
                            and isinstance(value.args[0], ast.Constant)
                        ):
                            return str(value.args[0].value)
    return None


def _read_special_commands(tree: ast.Module) -> dict[str, dict[str, str]]:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SPECIAL_COMMANDS":
                    value = ast.literal_eval(node.value)
                    if isinstance(value, dict):
                        return value
    return {}


def discover_characters(project_root: Path) -> list[CharacterInfo]:
    characters_dir = project_root / "characters"
    if not characters_dir.is_dir():
        raise BotManagerError(f"characters/ が見つかりません: {characters_dir}")

    result: list[CharacterInfo] = []
    for folder in sorted(characters_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        config_path = folder / "config.py"
        if not config_path.exists():
            continue

        source = config_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(config_path))
        character_name = _read_config_field(tree, "CHARACTER_NAME") or folder.name.lower()
        display_name = _read_config_field(tree, "DISPLAY_NAME") or folder.name
        history_clear = _read_config_field(tree, "HISTORY_CLEAR_COMMAND") or ""
        command_pattern = _read_config_field(tree, "COMMAND_PATTERN") or ""
        messages_path = folder / "messages.py"
        instruction_rel = _read_config_field(tree, "SYSTEM_INSTRUCTION_PATH")
        if instruction_rel:
            system_instruction_path = project_root / instruction_rel.replace("\\", "/")
        else:
            system_instruction_path = folder / "system_instruction.txt"

        result.append(
            CharacterInfo(
                folder_name=folder.name,
                folder_path=folder,
                config_path=config_path,
                messages_path=messages_path,
                system_instruction_path=system_instruction_path,
                character_name=character_name,
                display_name=display_name,
                history_clear_command=history_clear,
                command_pattern=command_pattern,
                special_commands=_read_special_commands(tree),
            )
        )
    return result


def _special_commands_source_span(source: str) -> tuple[int, int] | None:
    """SPECIAL_COMMANDS 代入式の source 内 [start, end) を返す。"""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SPECIAL_COMMANDS":
                    start_line = node.lineno - 1
                    end_line = (node.end_lineno or node.lineno) - 1
                    start = sum(len(lines[i]) for i in range(start_line))
                    end = sum(len(lines[i]) for i in range(end_line + 1))
                    return start, end
    return None


def format_special_commands_block(commands: dict[str, dict[str, str]]) -> str:
    if not commands:
        return "SPECIAL_COMMANDS = {}"
    lines = ["SPECIAL_COMMANDS = {"]
    for cmd, cfg in commands.items():
        lines.append(f'    {json.dumps(cmd, ensure_ascii=False)}: {{')
        if cfg.get("message"):
            lines.append(f'        "message": {json.dumps(cfg["message"], ensure_ascii=False)},')
        if cfg.get("file"):
            lines.append(f'        "file": {json.dumps(cfg["file"], ensure_ascii=False)},')
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def save_special_commands(config_path: Path, commands: dict[str, dict[str, str]]) -> None:
    content = config_path.read_text(encoding="utf-8")
    span = _special_commands_source_span(content)
    if span is None:
        raise BotManagerError("config.py に SPECIAL_COMMANDS が見つかりません。")
    start, end = span
    new_block = format_special_commands_block(commands)
    if not new_block.endswith("\n"):
        new_block += "\n"
    updated = content[:start] + new_block + content[end:]
    backup(config_path)
    config_path.write_text(updated, encoding="utf-8", newline="\n")


def backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def load_system_instruction(path: Path) -> str:
    if not path.exists():
        raise BotManagerError(f"system_instruction.txt がありません: {path}")
    return path.read_text(encoding="utf-8")


def load_messages(messages_path: Path) -> str:
    if not messages_path.exists():
        raise BotManagerError(f"messages.py がありません: {messages_path}")
    return messages_path.read_text(encoding="utf-8")


def save_messages(messages_path: Path, content: str) -> None:
    from tools.character_creator.messages_format import normalize_messages_source

    backup(messages_path)
    try:
        text = normalize_messages_source(content)
    except SyntaxError:
        # 手編集で直している最中はそのまま保存を許可
        text = content if content.endswith("\n") else content + "\n"
    messages_path.write_text(text, encoding="utf-8", newline="\n")


def validate_messages(content: str) -> tuple[list[str], list[str]]:
    """(errors, warnings)"""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        ast.parse(content)
    except SyntaxError as exc:
        errors.append(f"構文エラー: {exc}")
        return errors, warnings

    for name in REQUIRED_CONSTANTS:
        if not re.search(rf"^{re.escape(name)}\s*=", content, re.MULTILINE):
            errors.append(f"未定義の定数: {name}")

    if "from .config import PARTNER_BOT_ID" not in content:
        warnings.append("PARTNER_BOT_ID の import がありません。")

    help_match = re.search(r"MSG_HELP\s*=\s*\"\"\"(.*?)\"\"\"", content, re.DOTALL)
    if help_match:
        mentioned = set(re.findall(r"/([a-z_]+)", help_match.group(1)))
        warnings.append(f"MSG_HELP で言及されているスラッシュコマンド: {', '.join(sorted(mentioned)) or 'なし'}")
    else:
        warnings.append("MSG_HELP が見つかりません。")

    return errors, warnings


def extract_help_mentions(content: str) -> set[str]:
    help_match = re.search(r"MSG_HELP\s*=\s*\"\"\"(.*?)\"\"\"", content, re.DOTALL)
    if not help_match:
        return set()
    return set(re.findall(r"/([a-z_0-9]+)", help_match.group(1)))
