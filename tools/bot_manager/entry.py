#!/usr/bin/env python3
"""
PyInstaller 用エントリポイント。

exe は AI-Alice リポジトリ内のどこに置いても、
上位フォルダを辿って characters/ を探します。
"""

from __future__ import annotations

import sys
from pathlib import Path

_MARKER = "characters"


def _resolve_project_root() -> Path:
    if getattr(sys, "frozen", False):
        starts = [Path.cwd(), Path(sys.executable).resolve().parent]
    else:
        starts = [Path(__file__).resolve().parents[2]]

    for start in starts:
        current = start.resolve()
        for directory in [current, *current.parents]:
            if (directory / _MARKER).is_dir():
                return directory

    if getattr(sys, "frozen", False):
        raise FileNotFoundError(
            "AI-Alice のプロジェクトルートが見つかりません。\n"
            f"  探した起点: {Path.cwd()} / {Path(sys.executable).resolve().parent}\n"
            "  characters/ があるフォルダ（AI-Alice ルート）で exe を実行してください。"
        )
    return starts[0]


def main() -> None:
    root = _resolve_project_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from tools.bot_manager.app import run_app

    run_app(root)


if __name__ == "__main__":
    main()
