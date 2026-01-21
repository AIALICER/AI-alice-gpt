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
async def process_attachments(attachments):
    """
    Discord の添付ファイルを処理してGemini APIで使える形式に変換
    
    Returns:
        list: types.Part オブジェクトのリスト
    """
    parts = []
    
    for attachment in attachments:
        try:
            # ファイルサイズチェック（20MB以下）
            if attachment.size > 20 * 1024 * 1024:
                print(f"ファイルが大きすぎます: {attachment.filename} ({attachment.size} bytes)")
                continue
            
            # ファイルをダウンロード（タイムアウト10秒）
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(attachment.url) as resp:
                    if resp.status == 200:
                        file_bytes = await resp.read()
                        
                        # MIMEタイプを取得・調整
                        mime_type = attachment.content_type or 'application/octet-stream'
                        # パラメータ（; charset=utf-8など）を除去
                        if ';' in mime_type:
                            mime_type = mime_type.split(';')[0].strip()
                        
                        # テキストやコードファイルは text/plain に統一して扱う
                        # Gemini APIは特定のMIMEタイプのみサポートしているため
                        if mime_type.startswith('text/') or mime_type in [
                            'application/json', 'application/javascript', 'application/x-python', 
                            'application/x-httpd-php', 'application/x-sh', 'application/xml'
                        ]:
                            mime_type = 'text/plain'
                        
                        # Part型に変換
                        part = types.Part.from_bytes(
                            data=file_bytes,
                            mime_type=mime_type
                        )
                        parts.append(part)
                        print(f"ファイル追加: {attachment.filename} ({mime_type})")
        except Exception as e:
            print(f"ファイル処理エラー ({attachment.filename}): {e}")
    
    return parts

async def summarize_attachments(prompt, file_parts):
    """
    添付ファイルの内容を1行程度のテキストに要約する
    """
    if not file_parts:
        return ""
    
    # 要約専用の短い命令
    summary_instruction = (
        "あなたは優秀なアシスタントです。提供された添付ファイル（画像や書類）の内容を、"
        "後で思い返せるように「1行で」簡潔に説明してください。"
        "例：富士山が写った青空の写真 / 請求書の内容が書かれたPDFファイル"
    )
    
    try:
        # 要約用のAPI呼び出し（flashを使えば高速・安価です）
        summary_response = gemini_client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=[prompt] + file_parts if prompt else file_parts,
            config=types.GenerateContentConfig(
                system_instruction=summary_instruction
            )
        )
        return f" [ファイル要約: {summary_response.text.strip()}]"
    except Exception as e:
        print(f"要約生成エラー: {e}")
        return " [ファイルが含まれています]"
