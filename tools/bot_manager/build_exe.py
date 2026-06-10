#!/usr/bin/env python3
"""Bot 設定マネージャの Windows 実行ファイルをビルドする。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY = Path(__file__).resolve().parent / "entry.py"
DIST_DIR = Path(__file__).resolve().parent / "dist"
STAGING_DIR = Path(__file__).resolve().parent / "dist_staging"
BUILD_DIR = Path(__file__).resolve().parent / "build"
EXE_NAME = "AI-Alice-BotManager"


def main() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        f"--name={EXE_NAME}",
        f"--paths={ROOT}",
        f"--distpath={STAGING_DIR}",
        f"--workpath={BUILD_DIR}",
        f"--specpath={Path(__file__).resolve().parent}",
        "--hidden-import=tools.bot_manager.app",
        "--hidden-import=tools.bot_manager.scanner",
        "--hidden-import=tools.bot_manager.slash_catalog",
        "--hidden-import=tools.character_creator.messages_generator",
        "--hidden-import=tools.character_creator.messages_format",
        "--hidden-import=tools.character_creator.generator",
        "--hidden-import=tools.common.project_root",
        "--hidden-import=tools.common.gemini_keys",
        "--hidden-import=tools.common.gemini_messages_client",
        "--hidden-import=httpx",
        "--hidden-import=google.genai",
        "--hidden-import=dotenv",
        str(ENTRY),
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    import shutil

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    built = STAGING_DIR / f"{EXE_NAME}.exe"
    exe_path = DIST_DIR / f"{EXE_NAME}.exe"
    try:
        shutil.copy2(built, exe_path)
    except PermissionError:
        fallback = DIST_DIR / f"{EXE_NAME}-new.exe"
        shutil.copy2(built, fallback)
        print(
            f"\n警告: {exe_path} が使用中のため上書きできませんでした。\n"
            f"代替: {fallback}"
        )
        exe_path = fallback
    print(f"\n完了: {exe_path}")


if __name__ == "__main__":
    main()
