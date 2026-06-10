"""
Discord Bot 起動時の GPT モデル指定（全キャラ共通）。

既定: config_base.OPENAI_MODEL（オプション未指定時）
オプション: --gpt-fallback でフォールバックモデルを使用
任意指定: --model <モデル名>
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from .config_base import OPENAI_FALLBACK_MODEL, OPENAI_MODEL


class BotModelOptionError(ValueError):
    """起動オプションが不正な場合。"""


@dataclass
class BotRunArgs:
    local: bool
    message: str | None
    model_name: str | None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI-Alice Discord Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "モデル例:\n"
            f"  （未指定）       → {OPENAI_MODEL}\n"
            f"  --gpt-fallback   → {OPENAI_FALLBACK_MODEL}\n"
            f"  --model gpt-4o   → 任意のモデル名"
        ),
    )
    parser.add_argument("--local", action="store_true", help="ローカルテストモード")
    parser.add_argument("-m", "--message", help="ローカルモードで送る1件のメッセージ")
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help=f"GPT モデル名を直接指定。未指定時は {OPENAI_MODEL}",
    )
    parser.add_argument(
        "--gpt-fallback",
        action="store_const",
        const=OPENAI_FALLBACK_MODEL,
        dest="gpt_preset",
        default=None,
        help=f"会話に {OPENAI_FALLBACK_MODEL} を使う",
    )
    return parser


def parse_bot_run_args(argv: list[str] | None = None) -> BotRunArgs:
    """Bot 起動用の共通引数を解析する。"""
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    ns = parser.parse_args(raw)

    if ns.gpt_preset and ns.model:
        parser.error("--model と --gpt-fallback は同時に指定できません。")

    return BotRunArgs(
        local=ns.local,
        message=ns.message,
        model_name=ns.model or ns.gpt_preset,
    )
