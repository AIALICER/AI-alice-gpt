"""
共通設定管理モジュール

- 環境変数の読み込み
- データベースパスの動的設定
- Geminiクライアントの初期化
- データベース初期化
"""

import os
import sqlite3
import httpx
from google import genai
from google.genai import types
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# === データベース設定 ===
DB_DIR = 'data'
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)


def _read_channel_id(env_name: str, default: int | None = None) -> int | None:
    """環境変数からチャンネルIDを安全に読み込む。"""
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default

    raw_value = raw_value.strip()
    if not raw_value:
        return default

    try:
        return int(raw_value)
    except ValueError:
        print(f"[config_base] Invalid channel id for {env_name}: {raw_value!r}. Fallback={default}")
        return default

# === 誕生日通知チャンネル設定 ===
# ユーザー誕生日: None の場合はBotが参加している最初に見つかったテキストチャンネルに送信
USER_BIRTHDAY_CHANNEL_ID: int | None = _read_channel_id("USER_BIRTHDAY_CHANNEL_ID")
# ブルアカキャラ誕生日: お遊戯会チャンネル固定
BLUEARCHIVE_BIRTHDAY_CHANNEL_ID: int = _read_channel_id("BLUEARCHIVE_BIRTHDAY_CHANNEL_ID", 1051173133228462220)

# === Discord履歴設定 ===
DISCORD_HISTORY_LIMIT = 5  # Discordから取得するメッセージ数
ENABLE_DISCORD_HISTORY = True  # Discord履歴読み込み機能の有効/無効
DISCORD_HISTORY_MAX_CHARS = 500  # 1メッセージあたりの最大文字数

# === Gemini API設定 ===
GEN_API_KEY = os.getenv("GEN_API_KEY")
GEN_API_KEY_2 = os.getenv("GEN_API_KEY_2")

# httpxクライアントを作成（60秒のタイムアウト）
httpx_timeout = httpx.Timeout(60.0, connect=60.0, read=60.0, write=60.0, pool=60.0)
httpx_client_main = httpx.Client(timeout=httpx_timeout)
httpx_client_fallback = httpx.Client(timeout=httpx_timeout)

gemini_http_options = types.HttpOptions(
    httpxClient=httpx_client_main,
    retryOptions=types.HttpRetryOptions(
        attempts=2,
        initialDelay=0.5,
        maxDelay=2.0,
        expBase=2.0,
        jitter=0.1,
        httpStatusCodes=[429, 503]
    )
)

gemini_http_options_fallback = types.HttpOptions(
    httpxClient=httpx_client_fallback,
    retryOptions=types.HttpRetryOptions(
        attempts=2,
        initialDelay=0.5,
        maxDelay=2.0,
        expBase=2.0,
        jitter=0.1,
        httpStatusCodes=[429, 503]
    )
)

# メインクライアント（APIキー1）
gemini_client = genai.Client(
    api_key=GEN_API_KEY,
    http_options=gemini_http_options
)

# フォールバッククライアント（APIキー2）
gemini_client_fallback = None
if GEN_API_KEY_2:
    gemini_client_fallback = genai.Client(
        api_key=GEN_API_KEY_2,
        http_options=gemini_http_options_fallback
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
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS url_memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自動で増える通し番号
        channel_id INTEGER,                   -- チャンネルID
        user_id INTEGER,                      -- ユーザーID
        summary TEXT,                         -- メッセージの要約（Geminiが作成）
        message_link TEXT,                    -- Discordのメッセージリンク
        timestamp DATETIME DEFAULT (datetime('now', 'localtime')) -- 実行時の時刻
    )
    ''')
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS wiki_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT UNIQUE,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
    ''')
    # ユーザー情報テーブル（メンション時に自動登録）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        display_name TEXT,
        account_name TEXT,
        birthday TEXT,
        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    # birthday列が存在しない旧DBのマイグレーション
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN birthday TEXT")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise
    conn.commit()
    conn.close()


# デバッグ: 環境変数の読み込み確認
if __name__ == "__main__":
    print("=== 環境変数デバッグ ===")
    print(f"GEN_API_KEY: {'設定済み' if GEN_API_KEY else '未設定'}")
    print(f"DB_DIR: {DB_DIR}")
    print("=======================")
