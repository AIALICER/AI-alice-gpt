import discord
from google import genai
from google.genai import types
import os
import aiohttp
from datetime import datetime, timedelta, timezone
import sqlite3
import asyncio
import look_db
import time
active_timers = {}

# === 過去チャット履歴読み込み設定 ===
DISCORD_HISTORY_LIMIT = 15  # Discordから取得するメッセージ数
ENABLE_DISCORD_HISTORY = True  # Discord履歴読み込み機能の有効/無効
DISCORD_HISTORY_MAX_CHARS = 500  # 1メッセージあたりの最大文字数（長すぎるメッセージは切り詰め）
# データベースの保存ディレクトリを確認・作成
DB_DIR = 'data'
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

DB_PATH = os.path.join(DB_DIR, 'alice_bot.db')

# データベースに接続（ファイルがなければ作成される）
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
summary_tasks = {}
# チャンネルごとに履歴を保存するテーブルを作成
cursor.execute('''
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER,
    role TEXT,       -- 'user' か 'model'
    content TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
# channel_id に UNIQUE を付けることで、上書き（ON CONFLICT）が可能になります
cursor.execute('''
CREATE TABLE IF NOT EXISTS chat_memories (
    channel_id INTEGER PRIMARY KEY,  -- PRIMARY KEYにすると自動でUNIQUEになります
    content TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
# 変更を確定して閉じる
conn.commit()
conn.close()
# 環境変数から取得
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEN_API_KEY = os.getenv("GEN_API_KEY")
# デバッグ: 環境変数の読み込み確認
print("=== 環境変数デバッグ ===")
print(f"DISCORD_TOKEN: {'設定済み' if DISCORD_TOKEN else '未設定'}")
print(f"GEN_API_KEY: {'設定済み' if GEN_API_KEY else '未設定'}")
print("=======================")

# 新しいGoogle Gen AI Client
gemini_client = genai.Client(api_key=GEN_API_KEY)