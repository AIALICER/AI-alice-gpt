"""
Gemini API で messages.py を生成する。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from google.genai import types

from tools.common.gemini_keys import GeminiKeyError, load_gemini_api_keys
from tools.common.gemini_messages_client import (
    DEFAULT_MESSAGES_MODEL,
    DEFAULT_TIMEOUT_SEC,
    create_messages_gemini_client,
)

from .generator import CharacterSpec, GeneratorError, render_messages
from .messages_format import normalize_messages_source

REQUIRED_CONSTANTS = (
    "RESPONSE_FAILED",
    "ERR_REBOOT",
    "MSG_THINKING",
    "MSG_SEARCHING",
    "MSG_NO_ACTIVE_TIMERS",
    "MSG_ACTIVE_TIMERS_HEADER",
    "MSG_TIMER_FINISH",
    "MSG_TIMER_REMAINING",
    "MSG_TIMER_SOON",
    "MSG_TIMER_SET",
    "MSG_TIMER_GUIDE",
    "MSG_DICE_RESULT",
    "MSG_DICE_INVALID",
    "MSG_DICE_RANGE_ERROR",
    "MSG_HELP",
    "SUMMARY_COMMAND",
    "MSG_RESPONSE_TOO_LONG",
    "MSG_HISTORY_CLEARED",
    "MSG_HISTORY_CLEAR_FAILED",
    "MSG_SUMMARY",
    "MEMORY_TITLE",
    "MEMORY_DEST",
    "MEMORY_CHAT",
    "CHAT_URL",
    "MEMORY_NOFIND",
    "MEMORY_ER",
    "WIKI_NEW_EVENT",
    "WIKI_ALREADY_READ",
    "WIKI_FAILED",
)

_REFERENCE_PATH = Path(__file__).resolve().parents[2] / "characters" / "Key" / "messages.py"
_MAX_INSTRUCTION_CHARS = 12_000


@dataclass
class MessagesGenerationResult:
    code: str
    source: str  # "gemini" | "template"
    error: str | None = None


def _log(msg: str) -> None:
    print(f"[messages_generator] {msg}", flush=True)


def _build_prompt(
    *,
    display_name: str,
    character_name: str,
    bot_display_name: str,
    system_instruction: str,
) -> str:
    reference = _REFERENCE_PATH.read_text(encoding="utf-8") if _REFERENCE_PATH.exists() else ""
    constants = ", ".join(REQUIRED_CONSTANTS)
    return f"""あなたは Discord Bot 用の Python モジュール `messages.py` を生成するアシスタントです。

## キャラクター設定
- 表示名: {display_name}
- 内部ID: {character_name}
- Bot表示名: {bot_display_name}

## system_instruction（キャラクターの性格・口調の根拠）
```
{system_instruction}
```

## 参考実装（構造・定数名はこのファイルに合わせること）
```python
{reference}
```

## 出力要件
1. 上記参考と同じ定数名をすべて定義した、実行可能な Python ソースのみを出力する（説明文・Markdown・コードフェンス禁止）。
2. 先頭に必ず次の import を含める:
   `from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME`
3. モジュール docstring は「{display_name} 用メッセージテンプレート」とする。
4. 各メッセージ文言は system_instruction の口調・一人称・二人称に合わせる（例: 「先生」呼び、キャラ固有の言い回し）。
5. Python の format 用プレースホルダは `{{task_name}}`, `{{error_detail}}` のように単一中括弧で書く（二重括弧エスケープは使わない）。
6. `MSG_HELP` は参考と同様にタイマー・ダイス・wiki・search_history を含む複数行文字列とする。
7. `WIKI_NEW_EVENT` / `WIKI_ALREADY_READ` は括弧付き複数行文字列とする（括弧内は行頭4スペースのみ。8スペース以上のインデントは禁止）。
8. モジュール先頭レベルの定義は行頭インデント0（空白なし）とする。
9. 定義必須の定数名: {constants}
"""


def _extract_python_source(raw: str) -> str:
    text = raw.strip()
    fenced = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text


def _validate_messages_source(code: str) -> None:
    missing = [name for name in REQUIRED_CONSTANTS if not re.search(rf"^{name}\s*=", code, re.MULTILINE)]
    if missing:
        raise GeneratorError(f"生成された messages.py に不足している定数: {', '.join(missing)}")

    if "from .config import PARTNER_BOT_ID" not in code:
        raise GeneratorError("生成された messages.py に PARTNER_BOT_ID の import がありません。")


def _normalize_code(code: str, display_name: str) -> str:
    code = code.replace("\r\n", "\n").strip() + "\n"
    if "from .config import PARTNER_BOT_ID" not in code:
        header = (
            f'"""\n{display_name} 用メッセージテンプレート\n"""\n\n'
            "from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME\n\n"
        )
        if not code.startswith('"""'):
            code = header + code
    try:
        return normalize_messages_source(code)
    except SyntaxError as exc:
        raise GeneratorError(f"生成された messages.py の構文が不正です: {exc}") from exc


def _context_from_spec(spec: CharacterSpec) -> tuple[str, str, str, str]:
    return (
        spec.display_name,
        spec.character_name,
        spec.bot_display_name or spec.display_name,
        spec.system_instruction,
    )


def generate_messages_with_gemini(
    project_root: Path,
    spec: CharacterSpec,
    *,
    model: str = DEFAULT_MESSAGES_MODEL,
) -> MessagesGenerationResult:
    """CharacterSpec から messages.py を生成する。"""
    display_name, character_name, bot_display_name, system_instruction = _context_from_spec(spec)
    return generate_messages_from_instruction(
        project_root,
        display_name=display_name,
        character_name=character_name,
        system_instruction=system_instruction,
        bot_display_name=bot_display_name,
        template_fallback_spec=spec,
        model=model,
    )


def generate_messages_from_instruction(
    project_root: Path,
    *,
    display_name: str,
    character_name: str,
    system_instruction: str,
    bot_display_name: str | None = None,
    template_fallback_spec: CharacterSpec | None = None,
    model: str = DEFAULT_MESSAGES_MODEL,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> MessagesGenerationResult:
    """
    system_instruction を元に Gemini で messages.py を生成する。

    失敗時はテンプレートにフォールバックし、error に理由を入れる。
    """
    bot_name = bot_display_name or display_name
    instruction = system_instruction.strip()
    if not instruction:
        return MessagesGenerationResult(
            code=render_messages(template_fallback_spec) if template_fallback_spec else "",
            source="template",
            error="system_instruction.txt が空です。",
        )

    if len(instruction) > _MAX_INSTRUCTION_CHARS:
        instruction = instruction[:_MAX_INSTRUCTION_CHARS] + "\n...(以下省略)"
        _log(f"system_instruction を {_MAX_INSTRUCTION_CHARS} 文字に切り詰めました")

    try:
        api_keys = load_gemini_api_keys(project_root)
    except GeminiKeyError as exc:
        fallback = render_messages(template_fallback_spec) if template_fallback_spec else ""
        return MessagesGenerationResult(code=fallback, source="template", error=str(exc))

    prompt = _build_prompt(
        display_name=display_name,
        character_name=character_name,
        bot_display_name=bot_name,
        system_instruction=instruction,
    )
    config = types.GenerateContentConfig(temperature=0.5, max_output_tokens=8192)

    api_errors: list[str] = []
    for index, api_key in enumerate(api_keys, start=1):
        label = f"GEN_API_KEY{'' if index == 1 else '_2'}"
        _log(f"{label} で Gemini 呼び出し中（model={model}, timeout={timeout_sec}s）...")
        try:
            client = create_messages_gemini_client(api_key, timeout_sec=timeout_sec)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            api_errors.append(f"{label}: {err}")
            _log(f"{label} 失敗: {err}")
            continue

        raw = (response.text or "").strip()
        if not raw:
            api_errors.append(f"{label}: 応答が空でした")
            _log(f"{label}: 応答が空")
            continue

        try:
            code = _normalize_code(_extract_python_source(raw), display_name)
            _validate_messages_source(code)
            _log(f"{label} で生成成功")
            return MessagesGenerationResult(code=code, source="gemini")
        except GeneratorError as exc:
            api_errors.append(f"{label}: 生成結果の検証失敗 — {exc}")
            _log(f"{label} 検証失敗: {exc}")
            continue

    fallback = render_messages(template_fallback_spec) if template_fallback_spec else ""
    detail = "\n".join(api_errors) if api_errors else "不明なエラー"
    _log("Gemini 生成失敗、テンプレートにフォールバック")
    return MessagesGenerationResult(
        code=fallback,
        source="template",
        error=(
            f"Gemini による messages.py 生成に失敗しました（モデル: {model}）。\n"
            f"{detail}\n\n"
            "・.env の GEN_API_KEY が AI-Alice ルートにあるか\n"
            "・プレースホルダ（YOUR_GEMINI_API_KEY）のままになっていないか\n"
            f"・{timeout_sec:.0f} 秒以内に応答がない場合はネットワーク/API を確認\n"
            "・exe の場合は characters/ があるフォルダで起動しているか"
        ),
    )
