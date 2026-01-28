"""
共通設定管理モジュール

- 環境変数の読み込み
- データベースパスの動的設定
- Geminiクライアントの初期化
- データベース初期化
"""

import os
import sqlite3
from google import genai
from google.genai import types
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# === データベース設定 ===
DB_DIR = 'data'
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

# === Discord履歴設定 ===
DISCORD_HISTORY_LIMIT = 5  # Discordから取得するメッセージ数
ENABLE_DISCORD_HISTORY = True  # Discord履歴読み込み機能の有効/無効
DISCORD_HISTORY_MAX_CHARS = 500  # 1メッセージあたりの最大文字数

# === Gemini API設定 ===
GEN_API_KEY = os.getenv("GEN_API_KEY")

gemini_http_options = types.HttpOptions(
    timeout=10,
    retryOptions=types.HttpRetryOptions(
        attempts=2,
        initialDelay=0.5,
        maxDelay=2.0,
        expBase=2.0,
        jitter=0.1,
        httpStatusCodes=[429, 503]
    )
)

gemini_client = genai.Client(
    api_key=GEN_API_KEY,
    http_options=gemini_http_options
)


def get_db_path(character_name: str) -> str:
    """
    キャラクター別のDBパスを取得
    
    Args:
        character_name: キャラクター名（例: "alice", "kei"）
    
    Returns:
        str: データベースファイルのパス
    """
    db_name = f"{character_name.lower()}_bot.db"
    return os.path.join(DB_DIR, db_name)


def init_database(db_path: str) -> None:
    """
    データベースの初期化
    
    必要なテーブル（chat_history, chat_memories）を作成する
    
    Args:
        db_path: データベースファイルのパス
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # チャンネルごとに履歴を保存するテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # チャンネルごとの記憶（要約）を保存するテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_memories (
        channel_id INTEGER PRIMARY KEY,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()


# デバッグ: 環境変数の読み込み確認
if __name__ == "__main__":
    print("=== 環境変数デバッグ ===")
    print(f"GEN_API_KEY: {'設定済み' if GEN_API_KEY else '未設定'}")
    print(f"DB_DIR: {DB_DIR}")
    print("=======================")
