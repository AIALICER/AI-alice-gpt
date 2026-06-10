"""
Gemini API キーを .env から読み込む（Character Creator / Bot Manager 共通）。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "YOUR_GEMINI_API_KEY",
        "YOUR_TOKEN",
        "your_gemini_api_key",
    }
)


class GeminiKeyError(Exception):
    """Gemini API キーが使えない場合。"""


def load_gemini_api_keys(project_root: Path) -> list[str]:
    """
    GEN_API_KEY / GEN_API_KEY_2 をプロジェクトルートの .env から読み込む。

    override=True で exe 起動時もルートの .env を優先する。
    """
    env_path = project_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)

    keys: list[str] = []
    for name in ("GEN_API_KEY", "GEN_API_KEY_2"):
        raw = os.getenv(name, "").strip().strip("\"'")
        if not raw or raw in PLACEHOLDER_VALUES:
            continue
        if raw not in keys:
            keys.append(raw)

    if not keys:
        hint = f"（{env_path}）" if env_path.is_file() else "（.env が見つかりません）"
        raise GeminiKeyError(
            "GEN_API_KEY が .env に設定されていません。"
            f"{hint}\n"
            "AI-Alice ルートの .env に GEN_API_KEY=... を設定してください。"
            "（.env.example の YOUR_GEMINI_API_KEY のままでは使えません）"
        )

    return keys
