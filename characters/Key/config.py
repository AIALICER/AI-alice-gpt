"""
ケイ固有の設定
"""

import re

# キャラクター名
CHARACTER_NAME = "kei"  # DB名に使用
DISPLAY_NAME = "ケイ"

# コマンドパターン（全角/半角の!、全角/半角スペース、改行に対応）
COMMAND_PATTERN = re.compile(r'^[!！]ケイ[ 　\n]')
HISTORY_CLEAR_COMMAND = "!ケイ 履歴消去"

# 環境変数キー
DISCORD_TOKEN_ENV = "KEI_DISCORD_TOKEN"

# 特殊コマンド（初期は空）
SPECIAL_COMMANDS = {}

# システムインストラクションパス
SYSTEM_INSTRUCTION_PATH = "characters/Key/system_instruction.txt"
