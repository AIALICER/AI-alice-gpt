#!/usr/bin/env python3
"""
AIモモイ Discord Bot 起動スクリプト

Usage:
    python characters/momoi/momoi.py
    python characters/momoi/momoi.py -gpt-fallback

Environment Variables:
    MOMOI_DISCORD_TOKEN: Discord Bot Token
    OPENAI_API_KEY: OpenAI API Key
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from characters import momoi
from common.bot_base import CharacterBot
from common.bot_model_cli import parse_bot_run_args

if __name__ == "__main__":
    args = parse_bot_run_args()

    bot = CharacterBot(
        character_name=momoi.config.CHARACTER_NAME,
        display_name=momoi.config.DISPLAY_NAME,
        command_pattern=momoi.config.COMMAND_PATTERN,
        history_clear_command=momoi.config.HISTORY_CLEAR_COMMAND,
        discord_token_env=momoi.config.DISCORD_TOKEN_ENV,
        system_instruction_path=momoi.config.SYSTEM_INSTRUCTION_PATH,
        messages=momoi.messages,
        special_commands=momoi.config.SPECIAL_COMMANDS,
    )
    bot.run(local=args.local, message=args.message, model_name=args.model_name)
