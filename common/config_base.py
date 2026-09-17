"""
共通設定管理モジュール

- 環境変数の読み込み
- データベースパスの動的設定
- GPTクライアントの初期化（デフォルト: gpt-6-astra）
- データベース初期化
"""

import os
import sqlite3
from pathlib import Path

import httpx
from dotenv import dotenv_values, load_dotenv
from openai import AsyncOpenAI, OpenAI

# プロジェクト直下の .env を読む
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(_ENV_PATH)

# OpenAI API キーは .env を優先（古い OS 環境変数で上書きされないようにする）
_env_file_values = dotenv_values(_ENV_PATH) if _ENV_PATH.is_file() else {}
for _key in ("OPENAI_API_KEY", "OPENAI_API_KEY_2", "OPENAI_MODEL", "OPENAI_FALLBACK_MODEL"):
    _val = (_env_file_values.get(_key) or "").strip().strip("\"'")
    if _val and not _val.upper().startswith("YOUR_"):
        os.environ[_key] = _val

# === データベース設定 ===
DB_DIR = "data"
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
USER_BIRTHDAY_CHANNEL_ID: int | None = _read_channel_id("USER_BIRTHDAY_CHANNEL_ID")
BLUEARCHIVE_BIRTHDAY_CHANNEL_ID: int = _read_channel_id(
    "BLUEARCHIVE_BIRTHDAY_CHANNEL_ID", 1051173133228462220
)

# === Discord履歴設定 ===
DISCORD_HISTORY_LIMIT = 5
ENABLE_DISCORD_HISTORY = True
DISCORD_HISTORY_MAX_CHARS = 500

# === OpenAI API設定（Astra 既定） ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY_2 = os.getenv("OPENAI_API_KEY_2")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-astra")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# タイムアウト（長時間ブロック防止）
httpx_timeout = httpx.Timeout(60.0, connect=10.0, read=60.0, write=30.0, pool=10.0)

gpt_client = OpenAI(api_key=OPENAI_API_KEY, timeout=httpx_timeout, max_retries=2)
gpt_async_client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=httpx_timeout, max_retries=2)

gpt_client_fallback = None
gpt_async_client_fallback = None
if OPENAI_API_KEY_2:
    gpt_client_fallback = OpenAI(
        api_key=OPENAI_API_KEY_2,
        timeout=httpx_timeout,
        max_retries=2,
    )
    gpt_async_client_fallback = AsyncOpenAI(
        api_key=OPENAI_API_KEY_2,
        timeout=httpx_timeout,
        max_retries=2,
    )


def get_db_path(character_name: str) -> str:
    """キャラクター別のDBパスを取得。"""
    db_name = f"{character_name.lower()}_bot.db"
    return os.path.join(DB_DIR, db_name)


def init_database(db_path: str) -> None:
    """必要なテーブルを作成する。"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER,
        role TEXT,
        content TEXT,
        author_name TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    for col_sql in (
        "ALTER TABLE chat_history ADD COLUMN author_name TEXT",
        "ALTER TABLE chat_history ADD COLUMN user_id INTEGER",
    ):
        try:
            cursor.execute(col_sql)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS chat_memories (
        channel_id INTEGER PRIMARY KEY,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS url_memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER,
        user_id INTEGER,
        summary TEXT,
        message_link TEXT,
        timestamp DATETIME DEFAULT (datetime('now', 'localtime'))
    )
    """
    )
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS wiki_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT UNIQUE,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        display_name TEXT,
        account_name TEXT,
        birthday TEXT,
        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN birthday TEXT")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS feedback_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK(kind IN ('good', 'bad')),
        user_message TEXT,
        bot_message TEXT NOT NULL,
        user_label TEXT NOT NULL DEFAULT '先生',
        bot_label TEXT NOT NULL DEFAULT 'アリス',
        discord_message_id INTEGER,
        created_at DATETIME DEFAULT (datetime('now', 'localtime'))
    )
    """
    )
    cursor.execute(
        """
    CREATE INDEX IF NOT EXISTS idx_feedback_examples_kind_created
    ON feedback_examples(kind, created_at DESC)
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS user_memories (
        user_id INTEGER PRIMARY KEY,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS chat_embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        history_id INTEGER UNIQUE,
        channel_id INTEGER NOT NULL,
        user_id INTEGER,
        role TEXT,
        author_name TEXT,
        content TEXT NOT NULL,
        embedding BLOB NOT NULL,
        model TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    cursor.execute(
        """
    CREATE INDEX IF NOT EXISTS idx_chat_embeddings_channel
    ON chat_embeddings(channel_id)
    """
    )
    cursor.execute(
        """
    CREATE INDEX IF NOT EXISTS idx_chat_embeddings_user
    ON chat_embeddings(user_id)
    """
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    print("=== 環境変数デバッグ ===")
    print(f"OPENAI_API_KEY: {'設定済み' if OPENAI_API_KEY else '未設定'}")
    print(f"OPENAI_MODEL: {OPENAI_MODEL}")
    print(f"OPENAI_FALLBACK_MODEL: {OPENAI_FALLBACK_MODEL}")
    print(f"DB_DIR: {DB_DIR}")
    print("=======================")
