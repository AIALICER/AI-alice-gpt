"""
新規キャラクター用ファイルを生成するモジュール。
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

import requests

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_USER_AGENT = "AI-Alice-CharacterCreator/1.0 (character setup tool)"


class GeneratorError(Exception):
    """生成処理のエラー。"""


@dataclass
class BotInfo:
    bot_id: int
    username: str
    display_name: str


@dataclass
class CharacterSpec:
    character_name: str
    display_name: str
    folder_name: str
    script_name: str
    discord_token_env: str
    bot_id: int
    bot_display_name: str
    system_instruction: str
    discord_token: str


def normalize_discord_token(raw: str) -> str:
    """
    貼り付け時の余計な文字を除去する。

    よくあるミス: 「Bot 」付きで貼る、改行・空白が混入、引用符で囲む。
    """
    token = raw.strip().strip("\"'")
    if token.lower().startswith("bot "):
        token = token[4:].strip()
    # コピペ時の改行・スペースを除去（トークン中に空白は通常ない）
    token = "".join(token.split())
    return token


def _discord_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bot {token}",
        "User-Agent": DISCORD_USER_AGENT,
    }


def _discord_response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = payload.get("message")
            code = payload.get("code")
            if message and code is not None:
                return f"{message} (code {code})"
            if message:
                return str(message)
    except json.JSONDecodeError:
        pass
    text = (response.text or "").strip()
    return text[:300] if text else response.reason or f"HTTP {response.status_code}"


def fetch_bot_info(token: str) -> BotInfo:
    """Discord API から Bot 情報を取得する。"""
    token = normalize_discord_token(token)
    if not token:
        raise GeneratorError("Discord Bot トークンを入力してください。")

    # Client Secret（ドットなし）や Application ID（数字のみ）の貼り間違いを検出
    if token.isdigit():
        raise GeneratorError(
            "Application ID が貼られています。Bot Token が必要です。\n"
            "Developer Portal → Bot → Reset Token の文字列をコピーしてください。"
        )
    if "." not in token:
        raise GeneratorError(
            "Client Secret の可能性があります。Bot Token が必要です。\n"
            "OAuth2 の Client Secret ではなく、Bot タブの Token をコピーしてください。"
        )

    try:
        response = requests.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers=_discord_headers(token),
            timeout=20,
        )
    except requests.RequestException as exc:
        raise GeneratorError(f"Discord API に接続できませんでした: {exc}") from exc

    if response.status_code == 200:
        payload = response.json()
    else:
        detail = _discord_response_detail(response)
        if response.status_code in (401, 403):
            raise GeneratorError(
                f"Discord API が拒否しました（HTTP {response.status_code}）。\n\n"
                "確認すること:\n"
                "・Developer Portal → Bot → Reset Token の「Bot Token」か\n"
                "・Client Secret / Application ID ではないか\n"
                "・Reset 後の新しいトークンか（古い値は無効）\n"
                "・先頭の「Bot 」は付けず MT... から貼る\n"
                "・VPN / プロキシ / ファイアウォールで discord.com が遮断されていないか\n\n"
                f"Discord API: {detail}"
            )
        if response.status_code == 429:
            raise GeneratorError(
                f"Discord API レート制限（429）です。しばらく待って再試行してください。\n{detail}"
            )
        raise GeneratorError(
            f"Discord API エラー (HTTP {response.status_code}): {detail}"
        )

    if not payload.get("bot"):
        raise GeneratorError(
            "このトークンは Bot 用ではありません。ユーザーアカウント用トークンは使えません。"
        )

    username = str(payload.get("username", "bot"))
    global_name = payload.get("global_name") or username
    bot_id = int(payload["id"])
    return BotInfo(bot_id=bot_id, username=username, display_name=str(global_name))


def slug_character_name(value: str) -> str:
    """DB用の内部キャラクター名（英小文字・数字・アンダースコア）。"""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "custom_bot"


def folder_name_from_username(username: str) -> str:
    """トークン確認時のフォルダ名候補（英数字のみ、先頭大文字）。"""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "", username)
    if not cleaned:
        return "CustomBot"
    return cleaned[0].upper() + cleaned[1:]


def validate_folder_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise GeneratorError("フォルダ名を入力してください。")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        raise GeneratorError(
            "フォルダ名は英字で始まり、英数字とアンダースコアのみ使用できます。"
        )
    return name


def validate_script_name(value: str) -> str:
    name = value.strip()
    if name.lower().endswith(".py"):
        name = name[:-3].strip()
    if not name:
        raise GeneratorError("起動スクリプト名（.py）を入力してください。")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise GeneratorError(
            "起動スクリプト名は英字またはアンダースコアで始まり、"
            "英数字とアンダースコアのみ使用できます（拡張子 .py は不要）。"
        )
    if name in {"config", "messages", "__init__"}:
        raise GeneratorError(f"「{name}」は予約名のため使用できません。")
    return name


def env_key_from_character_name(character_name: str) -> str:
    return f"{character_name.upper()}_DISCORD_TOKEN"


def compose_service_name(spec: CharacterSpec) -> str:
    """
    compose.yaml のサービスキー。

    起動パス（フォルダ名）と揃える。内部ID（character_name）とは別にできる。
    例: フォルダ momoi → サービス momoi（内部ID が ai でも momoi を使う）
    """
    slug = re.sub(r"[^a-z0-9]+", "-", spec.folder_name.lower()).strip("-")
    return slug or spec.character_name.replace("_", "-")


def build_spec(
    discord_token: str,
    system_instruction: str,
    folder_name: str,
    script_name: str,
    display_name: str | None = None,
    character_name: str | None = None,
) -> CharacterSpec:
    """入力から生成用スペックを組み立てる。"""
    instruction = system_instruction.strip()
    if not instruction:
        raise GeneratorError("system_instruction を入力してください。")

    resolved_folder = validate_folder_name(folder_name)
    resolved_script = validate_script_name(script_name)

    normalized_token = normalize_discord_token(discord_token)
    bot = fetch_bot_info(normalized_token)
    resolved_display = (display_name or bot.display_name).strip()
    if not resolved_display:
        raise GeneratorError("表示名（コマンド用）を特定できませんでした。")

    resolved_character = slug_character_name(character_name or bot.username)

    return CharacterSpec(
        character_name=resolved_character,
        display_name=resolved_display,
        folder_name=resolved_folder,
        script_name=resolved_script,
        discord_token_env=env_key_from_character_name(resolved_character),
        bot_id=bot.bot_id,
        bot_display_name=bot.display_name,
        system_instruction=instruction,
        discord_token=normalized_token,
    )


def _escape_regex(text: str) -> str:
    return re.escape(text)


def render_config(spec: CharacterSpec) -> str:
    pattern = _escape_regex(spec.display_name)
    return textwrap.dedent(
        f'''\
        """
        {spec.display_name} 固有の設定（character_creator により生成）
        """

        import re
        from characters.bot_id_list import get_partner_info

        CHARACTER_NAME = "{spec.character_name}"
        DISPLAY_NAME = "{spec.display_name}"

        COMMAND_PATTERN = re.compile(r'^[!！]{pattern}[ 　\\n]')
        HISTORY_CLEAR_COMMAND = "!{spec.display_name} 履歴消去"

        DISCORD_TOKEN_ENV = "{spec.discord_token_env}"

        SPECIAL_COMMANDS = {{}}

        SYSTEM_INSTRUCTION_PATH = "characters/{spec.folder_name}/system_instruction.txt"

        _partner = get_partner_info(CHARACTER_NAME)
        PARTNER_BOT_ID = _partner["bot_id"]
        PARTNER_BOT_NAME = _partner["display_name"]
        '''
    )


def render_messages(spec: CharacterSpec) -> str:
    from .messages_format import normalize_messages_source

    name = spec.display_name
    code = f'''"""
{name} 用メッセージテンプレート（character_creator により生成）
"""

from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME

RESPONSE_FAILED = "……エラーが発生しました。応答を生成できませんでした。"
ERR_REBOOT = "システムに異常が発生しました。再起動します。\\n詳細: {{error_detail}}"

MSG_THINKING = "……………………処理中です。"
MSG_SEARCHING = "検索を実行します。"

MSG_NO_ACTIVE_TIMERS = "現在稼働中のタイマーはありません。"
MSG_ACTIVE_TIMERS_HEADER = "稼働中のタイマー一覧です。"
MSG_TIMER_FINISH = "時間です。「{{task_name}}」の開始時刻になりました。"
MSG_TIMER_REMAINING = "・{{task_name}}: 残り {{minutes}}分{{seconds}}秒です。"
MSG_TIMER_SOON = "・{{task_name}}: まもなく終了します。"
MSG_TIMER_SET = "{{time_str}}のタイマーを設定しました。「{{task_name}}」の時間になったら通知します。"
MSG_TIMER_GUIDE = "タイマー機能は `/timer` から利用できます。"

MSG_DICE_RESULT = "🎲 ダイスロール結果\\n**{{notation}}** → {{rolls}}\\n合計: **{{total}}**"
MSG_DICE_INVALID = "指定が正しくありません。`XdY` 形式で指定してください（例: `2d6`）"
MSG_DICE_RANGE_ERROR = "ダイスの個数は1〜100、面数は2〜1000で指定してください。"

MSG_HELP = """📖 **{name} のコマンド一覧**

**タイマー**
- `/timer` - タイマーを設定
- `/timers` - タイマー一覧を表示

**その他**
- `/help` - コマンドの使い方を表示
- `/wiki_check` - Wikiの最新イベントを確認
- `/search_history` - 過去の解析記録を検索"""

SUMMARY_COMMAND = "{name}に解析させる"
MSG_RESPONSE_TOO_LONG = "応答が長いため、ファイルを生成します。"
MSG_HISTORY_CLEARED = "履歴を削除しました。"
MSG_HISTORY_CLEAR_FAILED = "履歴の削除に失敗しました。"
MSG_SUMMARY = "対象のメッセージを解析します。"

MEMORY_TITLE = "🎯 記録を特定しました。"
MEMORY_DEST = "お探しの履歴はこれでしょうか?"
MEMORY_CHAT = "お探しのものはこれでしょうか?"
CHAT_URL = "{name}にメッセージを覚えさせる"
MEMORY_NOFIND = "直近 {{limit}} 件を確認しましたが、「{{query}}」に合致する記憶は見つかりませんでした。\\n"
MEMORY_ER = "件数を増やして再度お試しください。"

WIKI_NEW_EVENT = (
    "【新着イベント情報】\\n"
    "**「{{title}}」** です\\n"
    "{{link}}"
)
WIKI_ALREADY_READ = (
    "最新のイベントは **「{{title}}」** です\\n"
    "{{link}}"
)
WIKI_FAILED = "Wikiからイベント情報を読み取ることができませんでした。"
'''
    return normalize_messages_source(code)


def render_init(spec: CharacterSpec) -> str:
    return textwrap.dedent(
        f'''\
        """
        {spec.display_name} キャラクターパッケージ
        """

        from . import config
        from . import messages
        '''
    )


def render_main_script(spec: CharacterSpec) -> str:
    module = spec.folder_name
    script = f"{spec.script_name}.py"
    return textwrap.dedent(
        f'''\
        #!/usr/bin/env python3
        """
        {spec.display_name} Discord Bot 起動スクリプト

        Usage:
            python characters/{module}/{script}

        Environment Variables:
            {spec.discord_token_env}: Discord Bot Token
            GEN_API_KEY: Google Gemini API Key
        """

        import os
        import sys

        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

        from characters import {module}
        from common.bot_base import CharacterBot

        if __name__ == "__main__":
            from common.bot_model_cli import parse_bot_run_args

            args = parse_bot_run_args()

            bot = CharacterBot(
                character_name={module}.config.CHARACTER_NAME,
                display_name={module}.config.DISPLAY_NAME,
                command_pattern={module}.config.COMMAND_PATTERN,
                history_clear_command={module}.config.HISTORY_CLEAR_COMMAND,
                discord_token_env={module}.config.DISCORD_TOKEN_ENV,
                system_instruction_path={module}.config.SYSTEM_INSTRUCTION_PATH,
                messages={module}.messages,
                special_commands={module}.config.SPECIAL_COMMANDS,
            )
            bot.run(local=args.local, message=args.message, model_name=args.model_name)
        '''
    )


def render_env_snippet(spec: CharacterSpec) -> str:
    return (
        f"# {spec.display_name} ({spec.bot_display_name})\n"
        f"{spec.discord_token_env}={spec.discord_token}\n"
    )


def format_compose_service_block(spec: CharacterSpec) -> str:
    """compose.yaml の services: 直下に置くブロック（インデント固定）。"""
    service = compose_service_name(spec)
    lines = [
        f"  # {spec.display_name} Discord Bot",
        f"  {service}:",
        "    build: .",
        f"    container_name: ai-{service}",
        f"    command: python characters/{spec.folder_name}/{spec.script_name}.py",
        "    restart: unless-stopped",
        "    env_file:",
        "      - .env",
        "    environment:",
        "      - PYTHONUNBUFFERED=1",
        "    networks:",
        "      - shared-network",
        "    volumes:",
        "      - ./data:/app/data",
        "    logging:",
        '      driver: "json-file"',
        "      options:",
        '        max-size: "10m"',
        '        max-file: "3"',
    ]
    return "\n".join(lines) + "\n"


@dataclass
class GenerationResult:
    spec: CharacterSpec
    created_files: list[Path]
    patch_summary: str = ""
    messages_source: str = "template"
    messages_error: str | None = None


def generate_character(
    project_root: Path,
    discord_token: str,
    system_instruction: str,
    folder_name: str,
    script_name: str,
    display_name: str | None = None,
    character_name: str | None = None,
    patch_options=None,
) -> GenerationResult:
    """キャラクターファイル一式を生成する。"""
    spec = build_spec(
        discord_token=discord_token,
        system_instruction=system_instruction,
        folder_name=folder_name,
        script_name=script_name,
        display_name=display_name,
        character_name=character_name,
    )

    char_dir = project_root / "characters" / spec.folder_name
    if char_dir.exists():
        raise GeneratorError(f"既に存在するフォルダです: characters/{spec.folder_name}")

    char_dir.mkdir(parents=True)
    (char_dir / "assets").mkdir(exist_ok=True)

    from .messages_generator import generate_messages_with_gemini

    gen_result = generate_messages_with_gemini(project_root, spec)
    messages_py = gen_result.code
    messages_source = gen_result.source

    files: dict[str, str] = {
        "config.py": render_config(spec),
        "messages.py": messages_py,
        "__init__.py": render_init(spec),
        "system_instruction.txt": spec.system_instruction + "\n",
        f"{spec.script_name}.py": render_main_script(spec),
    }

    created: list[Path] = []
    for filename, content in files.items():
        path = char_dir / filename
        path.write_text(content, encoding="utf-8")
        created.append(path)

    from .project_patcher import PatchOptions, apply_project_patches

    options = patch_options if patch_options is not None else PatchOptions()
    patch_result = apply_project_patches(project_root, spec, options)

    patch_lines = [patch_result.summary()]
    if messages_source == "gemini":
        patch_lines.append("messages.py: Gemini により口調を反映して生成しました。")
    elif gen_result.error:
        patch_lines.append(f"messages.py: テンプレートで生成（Gemini 失敗）\n{gen_result.error}")
    else:
        patch_lines.append("messages.py: 汎用テンプレートで生成しました。")

    return GenerationResult(
        spec=spec,
        created_files=created,
        patch_summary="\n".join(line for line in patch_lines if line),
        messages_source=messages_source,
        messages_error=gen_result.error,
    )
