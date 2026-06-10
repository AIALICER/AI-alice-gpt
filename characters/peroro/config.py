"""
ペロロ 固有の設定（character_creator により生成）
"""

import re
from characters.bot_id_list import get_partner_info

CHARACTER_NAME = "peroro"
DISPLAY_NAME = "ペロロ"

COMMAND_PATTERN = re.compile(r'^[!！]ペロロ[ 　\n]')
HISTORY_CLEAR_COMMAND = "!ペロロ 履歴消去"

DISCORD_TOKEN_ENV = "PERORO_DISCORD_TOKEN"

SPECIAL_COMMANDS = {}

SYSTEM_INSTRUCTION_PATH = "characters/peroro/system_instruction.txt"

_partner = get_partner_info(CHARACTER_NAME)
PARTNER_BOT_ID = _partner["bot_id"]
PARTNER_BOT_NAME = _partner["display_name"]
