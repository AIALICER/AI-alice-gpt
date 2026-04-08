"""
ケイ固有の設定
"""

import re

from characters.bot_id_list import get_partner_info

# キャラクター名
CHARACTER_NAME = "kei"  # DB名に使用
DISPLAY_NAME = "ケイ"

# コマンドパターン（全角/半角の!、全角/半角スペース、改行に対応）
COMMAND_PATTERN = re.compile(r"^[!！]ケイ[ 　\n]")
HISTORY_CLEAR_COMMAND = "!ケイ 履歴消去"
# 環境変数キー
DISCORD_TOKEN_ENV = "KEI_DISCORD_TOKEN"

# 特殊コマンド（初期は空）
SPECIAL_COMMANDS = {}

# システムインストラクションパス
SYSTEM_INSTRUCTION_PATH = "characters/Key/system_instruction.txt"

# 相方Bot情報（bot_registry.py で一元管理）
_partner = get_partner_info(CHARACTER_NAME)
PARTNER_BOT_ID = _partner["bot_id"]
PARTNER_BOT_NAME = _partner["display_name"]
