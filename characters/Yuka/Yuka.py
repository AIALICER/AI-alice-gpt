#!/usr/bin/env python3
"""
Yuka (早瀬ユウカ) Discord Bot 起動スクリプト

Usage:
    python Yuka.py
    python Yuka.py -gpt-fallback

Environment Variables:
    YUKA_DISCORD_TOKEN: ユウカ用Discord Bot Token
    OPENAI_API_KEY: OpenAI API Key
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from characters import Yuka
from common.bot_base import CharacterBot
from common.bot_model_cli import parse_bot_run_args

if __name__ == "__main__":
    args = parse_bot_run_args()

    bot = CharacterBot(
        character_name=Yuka.config.CHARACTER_NAME,
        display_name=Yuka.config.DISPLAY_NAME,
        command_pattern=Yuka.config.COMMAND_PATTERN,
        history_clear_command=Yuka.config.HISTORY_CLEAR_COMMAND,
        discord_token_env=Yuka.config.DISCORD_TOKEN_ENV,
        system_instruction_path=Yuka.config.SYSTEM_INSTRUCTION_PATH,
        messages=Yuka.messages,
        special_commands=Yuka.config.SPECIAL_COMMANDS,
    )
    bot.run(local=args.local, message=args.message, model_name=args.model_name)
