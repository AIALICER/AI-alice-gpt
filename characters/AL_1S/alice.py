#!/usr/bin/env python3
"""
AL-1S (天童アリス) Discord Bot 起動スクリプト

Usage:
    python AL-1S.py

Environment Variables:
    DISCORD_TOKEN: アリス用Discord Bot Token
    GEN_API_KEY: Google Gemini API Key
"""

import os
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from characters import AL_1S
from common.bot_base import CharacterBot

if __name__ == "__main__":
    bot = CharacterBot(
        character_name=AL_1S.config.CHARACTER_NAME,
        display_name=AL_1S.config.DISPLAY_NAME,
        command_pattern=AL_1S.config.COMMAND_PATTERN,
        history_clear_command=AL_1S.config.HISTORY_CLEAR_COMMAND,
        discord_token_env=AL_1S.config.DISCORD_TOKEN_ENV,
        system_instruction_path=AL_1S.config.SYSTEM_INSTRUCTION_PATH,
        messages=AL_1S.messages,
        special_commands=AL_1S.config.SPECIAL_COMMANDS,
    )
    bot.run()
