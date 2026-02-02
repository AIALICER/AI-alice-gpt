"""
アリス固有の設定
"""

import re

# キャラクター名
CHARACTER_NAME = "alice"  # DB名に使用
DISPLAY_NAME = "アリス"

# コマンドパターン（全角/半角の!、全角/半角スペース、改行に対応）
COMMAND_PATTERN = re.compile(r'^[!！]アリス[ 　\n]')
HISTORY_CLEAR_COMMAND = "!アリス 履歴消去"
# 環境変数キー
DISCORD_TOKEN_ENV = "DISCORD_TOKEN"

# 特殊コマンド
SPECIAL_COMMANDS = {
    "!光よ!": {
        "message": "ターゲット確認！出力臨界点突破！光よ！",
        "file": "characters/AL_1S/assets/光よ！.jpg"
    }
}

# システムインストラクションパス
SYSTEM_INSTRUCTION_PATH = "characters/AL_1S/system_instruction.txt"

# 相方Bot情報（相互会話用）
PARTNER_BOT_ID = 1338274620373676082  # ケイのBot ID
PARTNER_BOT_NAME = "ケイ"
