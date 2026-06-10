#!/usr/bin/env python3
"""
normal Discord Bot 起動スクリプト

Usage:
    python Normal.py

Environment Variables:
    NORMAL_DISCORD_TOKEN: normal用 Discord Bot Token
    OPENAI_API_KEY: OpenAI API Key
"""

import os
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from characters import normal
from common.bot_base import CharacterBot

if __name__ == "__main__":
    from common.bot_model_cli import parse_bot_run_args

    args = parse_bot_run_args()

    bot = CharacterBot(
        character_name=normal.config.CHARACTER_NAME,
        display_name=normal.config.DISPLAY_NAME,
        command_pattern=normal.config.COMMAND_PATTERN,
        history_clear_command=normal.config.HISTORY_CLEAR_COMMAND,
        discord_token_env=normal.config.DISCORD_TOKEN_ENV,
        system_instruction_path=normal.config.SYSTEM_INSTRUCTION_PATH,
        messages=normal.messages,
        special_commands=normal.config.SPECIAL_COMMANDS,
    )
    bot.run(local=args.local, message=args.message, model_name=args.model_name)
