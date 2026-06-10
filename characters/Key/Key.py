#!/usr/bin/env python3
"""
Key (ケイ) Discord Bot 起動スクリプト

Usage:
    python Key.py
    python Key.py -gpt-fallback

Environment Variables:
    KEI_DISCORD_TOKEN: ケイ用Discord Bot Token
    OPENAI_API_KEY: OpenAI API Key
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from characters import Key
from common.bot_base import CharacterBot
from common.bot_model_cli import parse_bot_run_args

if __name__ == "__main__":
    args = parse_bot_run_args()

    bot = CharacterBot(
        character_name=Key.config.CHARACTER_NAME,
        display_name=Key.config.DISPLAY_NAME,
        command_pattern=Key.config.COMMAND_PATTERN,
        history_clear_command=Key.config.HISTORY_CLEAR_COMMAND,
        discord_token_env=Key.config.DISCORD_TOKEN_ENV,
        system_instruction_path=Key.config.SYSTEM_INSTRUCTION_PATH,
        messages=Key.messages,
        special_commands=Key.config.SPECIAL_COMMANDS,
    )
    bot.run(local=args.local, message=args.message, model_name=args.model_name)
