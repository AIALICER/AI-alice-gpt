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
async def set_timer(channel, minutes, task_name):
    channel_id = channel.id
    end_time = time.time() + (minutes * 60)
    
    timer_data = {"task": task_name, "end_time": end_time}
    
    # リストに追加
    if channel_id not in active_timers:
        active_timers[channel_id] = []
    active_timers[channel_id].append(timer_data)

    try:
        await asyncio.sleep(minutes * 60)
        await channel.send(f"🔔 時間ですよ！「{task_name}」の予定です。")
    finally:
        # 終わったらリストから消す
        if channel_id in active_timers:
            active_timers[channel_id] = [t for t in active_timers[channel_id] if t != timer_data]
def get_japan_time() -> str:
    """
    現在の日本標準時（JST）を取得
    
    Returns:
        str: 日本時間の文字列（例: "2026-01-06 20:18:48 (月曜日)"）
    """
    # JST = UTC+9
    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)
    
    # 曜日を日本語で
    weekdays = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']
    weekday_jp = weekdays[now_jst.weekday()]
    
    # フォーマット
    formatted_time = now_jst.strftime('%Y-%m-%d %H:%M:%S')
    return f"{formatted_time} ({weekday_jp})"