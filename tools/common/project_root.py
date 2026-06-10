"""
AI-Alice プロジェクトルート（characters/ があるディレクトリ）を解決する。
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER_DIR = "characters"


def find_project_root_from(start: Path) -> Path | None:
    """start から親へ辿り、characters/ があるディレクトリを返す。"""
    current = start.resolve()
    for directory in [current, *current.parents]:
        if (directory / MARKER_DIR).is_dir():
            return directory
    return None


def get_project_root() -> Path:
    """
    プロジェクトルートを取得する。

    exe 配置場所（例: tools/bot_manager/dist/）からも、
    上位の AI-Alice ルートを自動検出する。
    """
    if getattr(sys, "frozen", False):
        search_starts = [
            Path.cwd(),
            Path(sys.executable).resolve().parent,
        ]
    else:
        # tools/common/project_root.py → リポジトリルート
        search_starts = [Path(__file__).resolve().parents[2]]

    for start in search_starts:
        found = find_project_root_from(start)
        if found is not None:
            return found

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        raise FileNotFoundError(
            "AI-Alice のプロジェクトルートが見つかりません。\n"
            f"  探した起点: {Path.cwd()} / {exe_dir}\n"
            "  characters/ フォルダがある AI-Alice ルートで exe を実行するか、\n"
            "  そのルートをカレントディレクトリにしてから起動してください。"
        )

    return search_starts[0]
