"""
既存プロジェクトファイルへの安全な追記。
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field

from .generator import (
    CharacterSpec,
    GeneratorError,
    compose_service_name,
    format_compose_service_block,
    render_env_snippet,
)

PARTNER_NONE_LABEL = "なし（相方なし）"


def is_no_partner(partner_name: str) -> bool:
    return partner_name.strip() in ("", PARTNER_NONE_LABEL, "なし", "none")


@dataclass
class PatchOptions:
    """追記オプション（安全な項目は既定で自動）。"""

    auto_partner_map: bool = False
    partner_name: str = "alice"
    auto_compose: bool = False


@dataclass
class PatchResult:
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = self.messages + [f"⚠ {w}" for w in self.warnings]
        return "\n".join(lines) if lines else "追記なし"


def _escape_py_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _read_text(path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _backup(path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def append_env(project_root, spec: CharacterSpec) -> PatchResult:
    """新規環境変数キーのみ .env に追記（既存キーは上書きしない）。"""
    result = PatchResult()
    env_path = project_root / ".env"
    key = spec.discord_token_env
    line = f"{key}={spec.discord_token}"

    if not env_path.exists():
        example = project_root / ".env.example"
        if example.exists():
            shutil.copy2(example, env_path)
            result.messages.append(".env を .env.example から作成しました。")
        else:
            env_path.write_text("", encoding="utf-8")
            result.messages.append(".env を新規作成しました。")

    content = _read_text(env_path)
    pattern = re.compile(rf"^{re.escape(key)}\s*=", re.MULTILINE)
    if pattern.search(content):
        result.warnings.append(f".env: {key} は既に存在するためスキップしました（上書きしません）。")
        return result

    snippet = render_env_snippet(spec)
    if content and not content.endswith("\n"):
        content += "\n"
    content += "\n" + snippet
    _backup(env_path)
    _write_text(env_path, content)
    result.messages.append(f".env: {key} を追記しました。")
    return result


def _registry_has_key(content: str, character_name: str) -> bool:
    return bool(re.search(rf'"{re.escape(character_name)}"\s*:', content))


def append_bot_registry(project_root, spec: CharacterSpec) -> PatchResult:
    """bot_id_list.py の BOT_REGISTRY に追記。"""
    result = PatchResult()
    path = project_root / "characters" / "bot_id_list.py"
    if not path.exists():
        raise GeneratorError(f"見つかりません: {path}")

    content = _read_text(path)
    if _registry_has_key(content, spec.character_name):
        result.warnings.append(
            f"bot_id_list.py: BOT_REGISTRY に '{spec.character_name}' が既にあるためスキップしました。"
        )
        return result

    marker = "PARTNER_MAP:"
    idx = content.find(marker)
    if idx < 0:
        raise GeneratorError("bot_id_list.py に PARTNER_MAP: が見つかりません。")

    entry = (
        f'    "{spec.character_name}": {{\n'
        f'        "bot_id": {spec.bot_id},\n'
        f'        "display_name": {_escape_py_string(spec.bot_display_name)},\n'
        f"    }},\n"
    )
    registry_section = content[:idx]
    last_brace = registry_section.rfind("}")
    if last_brace < 0:
        raise GeneratorError("BOT_REGISTRY の終端を特定できません。")

    content = content[:last_brace] + entry + content[last_brace:]
    _backup(path)
    _write_text(path, content)
    result.messages.append(f"bot_id_list.py: BOT_REGISTRY に '{spec.character_name}' を追記しました。")
    return result


def append_partner_map(
    project_root, spec: CharacterSpec, partner_name: str
) -> PatchResult:
    """bot_id_list.py の PARTNER_MAP に追記。"""
    result = PatchResult()
    path = project_root / "characters" / "bot_id_list.py"
    content = _read_text(path)

    if not is_no_partner(partner_name):
        if partner_name not in list_registry_keys(content) and partner_name != spec.character_name:
            result.warnings.append(
                f"bot_id_list.py: 相方 '{partner_name}' は BOT_REGISTRY に未登録ですが追記します。"
            )

    partner_pattern = re.compile(
        rf'^\s*"{re.escape(spec.character_name)}"\s*:', re.MULTILINE
    )
    if partner_pattern.search(content[content.find("PARTNER_MAP:") :]):
        result.warnings.append(
            f"bot_id_list.py: PARTNER_MAP に '{spec.character_name}' が既にあるためスキップしました。"
        )
        return result

    marker = "def get_partner_info"
    idx = content.find(marker)
    if idx < 0:
        raise GeneratorError("bot_id_list.py に def get_partner_info が見つかりません。")

    if is_no_partner(partner_name):
        entry = f'    "{spec.character_name}": None,\n'
        detail = "相方なし (None)"
    else:
        entry = f'    "{spec.character_name}": "{partner_name}",\n'
        detail = f"'{partner_name}'"
    section = content[:idx]
    last_brace = section.rfind("}")
    if last_brace < 0:
        raise GeneratorError("PARTNER_MAP の終端を特定できません。")

    content = content[:last_brace] + entry + content[last_brace:]
    _backup(path)
    _write_text(path, content)
    result.messages.append(
        f"bot_id_list.py: PARTNER_MAP に '{spec.character_name}' → {detail} を追記しました。"
    )
    return result


def list_registry_keys(content: str) -> list[str]:
    start = content.find("BOT_REGISTRY")
    end = content.find("PARTNER_MAP")
    if start < 0 or end < 0:
        return []
    block = content[start:end]
    return re.findall(r'"([a-z][a-z0-9_]*)"', block)


def _find_root_networks_index(content: str) -> int:
    """
    新サービスを挿入する位置（トップレベル networks: の直前）。

    サービス定義内の ``    networks:`` は対象外。
    ファイル内に複数ある場合は **最後** のトップレベル行を使う。
    """
    root_matches = [m.start() for m in re.finditer(r"^networks:\s*$", content, re.MULTILINE)]
    if root_matches:
        return root_matches[-1]

    # フォールバック: 行頭が networks: で始まる行のうち最後（インデント付きは除外）
    last = None
    for m in re.finditer(r"^networks:", content, re.MULTILINE):
        line_start = content.rfind("\n", 0, m.start()) + 1
        if m.start() == line_start:
            last = m.start()
    if last is not None:
        return last

    raise GeneratorError("compose.yaml にトップレベルの networks: が見つかりません。")


def append_compose(project_root, spec: CharacterSpec) -> PatchResult:
    """compose.yaml にサービス定義を追記。"""
    result = PatchResult()
    path = project_root / "compose.yaml"
    if not path.exists():
        raise GeneratorError(f"見つかりません: {path}")

    content = _read_text(path)
    service = compose_service_name(spec)
    if re.search(rf"^  {re.escape(service)}\s*:", content, re.MULTILINE) or re.search(
        rf"^{re.escape(service)}\s*:", content, re.MULTILINE
    ):
        result.warnings.append(f"compose.yaml: サービス '{service}' は既に存在するためスキップしました。")
        return result

    service_yaml = format_compose_service_block(spec)

    idx = _find_root_networks_index(content)
    insertion = service_yaml + "\n"
    content = content[:idx] + insertion + content[idx:]
    _backup(path)
    _write_text(path, content)
    result.messages.append(
        f"compose.yaml: サービス '{service}' "
        f"(python characters/{spec.folder_name}/{spec.script_name}.py) を追記しました。"
    )
    return result


def apply_project_patches(
    project_root,
    spec: CharacterSpec,
    options: PatchOptions,
) -> PatchResult:
    """安全な追記を実行し、オプションに応じて危険な追記も行う。"""
    combined = PatchResult()

    env_part = append_env(project_root, spec)
    combined.messages.extend(env_part.messages)
    combined.warnings.extend(env_part.warnings)

    registry_part = append_bot_registry(project_root, spec)
    combined.messages.extend(registry_part.messages)
    combined.warnings.extend(registry_part.warnings)

    if options.auto_partner_map:
        partner_part = append_partner_map(project_root, spec, options.partner_name.strip() or "alice")
        combined.messages.extend(partner_part.messages)
        combined.warnings.extend(partner_part.warnings)

    if options.auto_compose:
        compose_part = append_compose(project_root, spec)
        combined.messages.extend(compose_part.messages)
        combined.warnings.extend(compose_part.warnings)

    return combined
