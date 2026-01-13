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
from config import *
def get_memories(channel_id):
    conn = sqlite3.connect(DB_PATH)
    # 辞書形式で取得できるように設定すると楽です
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
            SELECT content 
            FROM chat_memories 
            WHERE channel_id = ? 
            ORDER BY timestamp ASC
        ''', (channel_id,)) # 引数の末尾にカンマを忘れずに（タプル形式にするため）
    old_memory_row = cursor.fetchone()
    memory = old_memory_row[0] if old_memory_row else "まだ記憶はありません。"
    conn.close()
    return memory
async def summarize_and_cleanup(channel_id):
    """10分放置されたら実行される処理"""

    await asyncio.sleep(600) # 10分待機
    
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()
    try:
        # 1. そのユーザーのログを一括取得
        
        cursor.execute('''
            SELECT role, content 
            FROM chat_history 
            WHERE channel_id = ? 
            ORDER BY timestamp ASC
        ''', (channel_id,)) # 引数の末尾にカンマを忘れずに（タプル形式にするため）
        rows = cursor.fetchall()
        
        if not rows:
            return
        history = []
        for row in rows:
         history.append({
            "role": row['role'],
            "parts": [{"text": row['content']}]
        })
        # 2. 現在の「記憶」を取得（以前の記憶に追記するため）
        cursor.execute('''
            SELECT content 
            FROM chat_memories 
            WHERE channel_id = ? 
            ORDER BY timestamp DESC LIMIT 1
        ''', (channel_id,))
        old_memory_row = cursor.fetchone()
        old_memory = old_memory_row['content'] if old_memory_row else "まだ記憶はありません。"

        # 3. Geminiで要約（gemini_logicの関数を呼ぶ）
        # ※新旧の情報を混ぜてアップデートさせるプロンプトを投げる
        new_summary = await generate_summary(old_memory, history)

        # 4. 記憶テーブルを更新し、古いログを消す（一括処理）
       # 4. 記憶テーブルを更新
        cursor.execute("""
            INSERT INTO chat_memories (channel_id, content, timestamp)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(channel_id) 
            DO UPDATE SET 
                content = excluded.content, 
                timestamp = excluded.timestamp
        """, (channel_id, new_summary))

        cursor.execute("DELETE FROM chat_history WHERE channel_id = ?", (channel_id,))
        
        db.commit()
        print(f"User {channel_id}: ログを要約してデータベースを清掃しました。")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()
async def generate_summary(old_memory, new_chat):
    prompt = f"""
    あなたは記憶を整理するアシスタントです。
    ユーザーに関する【これまでの記憶】を【新しい会話】に基づいて更新してください。
    
    【これまでの記憶】
    {old_memory}
    
    【新しい会話】
    {new_chat}
    
    【指示】
    - 重要な変更点や新しい情報（趣味、呼び名、約束など）があれば追記してください。
    - 古くなった情報や矛盾する情報は削除または修正してください。
    - 3行程度の短い文章にまとめてください。
    """
    try:
        # 要約用のAPI呼び出し（flashを使えば高速・安価です）
        summary_response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return f" [ログ要約: {summary_response.text.strip()}]"
    except Exception as e:
        print(f"要約生成エラー: {e}")
        return " [要約失敗]"
def clear_db_history(channel_id):
    """
    指定されたチャンネルの履歴をデータベースから削除する
    """
    try:
        conn = sqlite3.connect('alice_bot.db')
        cursor = conn.cursor()
        # そのチャンネルのレコードをすべて削除
        cursor.execute('DELETE FROM chat_history WHERE channel_id = ?', (channel_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"履歴削除エラー: {e}")
        return False