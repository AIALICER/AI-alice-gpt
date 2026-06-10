#!/usr/bin/env python3
"""
ペロロ Discord Bot 起動スクリプト

Usage:
    python characters/peroro/peroro.py

Environment Variables:
    PERORO_DISCORD_TOKEN: Discord Bot Token
    OPENAI_API_KEY: OpenAI API Key
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from characters import peroro
from common.bot_base import CharacterBot

if __name__ == "__main__":
    from common.bot_model_cli import parse_bot_run_args

    args = parse_bot_run_args()

    bot = CharacterBot(
        character_name=peroro.config.CHARACTER_NAME,
        display_name=peroro.config.DISPLAY_NAME,
        command_pattern=peroro.config.COMMAND_PATTERN,
        history_clear_command=peroro.config.HISTORY_CLEAR_COMMAND,
        discord_token_env=peroro.config.DISCORD_TOKEN_ENV,
        system_instruction_path=peroro.config.SYSTEM_INSTRUCTION_PATH,
        messages=peroro.messages,
        special_commands=peroro.config.SPECIAL_COMMANDS,
    )
    bot.run(local=args.local, message=args.message, model_name=args.model_name)
