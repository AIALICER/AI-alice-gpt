"""
normal 固有の設定
"""

import re
from characters.bot_id_list import get_partner_info

# キャラクター名
CHARACTER_NAME = "normal"  # DB名に使用
DISPLAY_NAME = "ノーマル"

# コマンドパターン（全角/半角の!、全角/半角スペース、改行に対応）
COMMAND_PATTERN = re.compile(r"^[!！]ノーマル[ 　\n]")
HISTORY_CLEAR_COMMAND = "!ノーマル 履歴消去"

# 環境変数キー
DISCORD_TOKEN_ENV = "NORMAL_DISCORD_TOKEN"

# 特殊コマンド
SPECIAL_COMMANDS = {}

# システムインストラクションパス
SYSTEM_INSTRUCTION_PATH = "characters/normal/system_instruction.txt"

# 相方Bot情報
_partner = get_partner_info(CHARACTER_NAME)
PARTNER_BOT_ID = _partner["bot_id"]
PARTNER_BOT_NAME = _partner["display_name"]
