"""
ユウカ固有の設定
"""

import re
from characters.bot_id_list import get_partner_info

# キャラクター名
CHARACTER_NAME = "Yuka"  # DB名に使用
DISPLAY_NAME = "ユウカ"

# コマンドパターン（全角/半角の!、全角/半角スペース、改行に対応）
COMMAND_PATTERN = re.compile(r'^[!！]ユウカ[ 　\n]')
HISTORY_CLEAR_COMMAND = "!ユウカ 履歴消去"
# 環境変数キー
DISCORD_TOKEN_ENV = "YUKA_DISCORD_TOKEN"

# 特殊コマンド
SPECIAL_COMMANDS = {
    
}

# システムインストラクションパス
SYSTEM_INSTRUCTION_PATH = "characters/Yuka/system_instruction.txt"

# 相方Bot情報（相互会話用）
# PARTNER_BOT_ID = 1468944602370277472 
PARTNER_BOT_NAME = "AIユウカ"
