import discord
from google import genai
from google.genai import types
import os
import aiohttp
from datetime import datetime, timedelta, timezone
import sqlite3

# データベースに接続（ファイルがなければ作成される）
conn = sqlite3.connect('alice_bot.db')
cursor = conn.cursor()

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

# システムインストラクション
try:
    with open('system_instruction.txt', 'r', encoding='utf-8') as f:
        SYSTEM_INSTRUCTION = f.read()
except FileNotFoundError:
    print("エラー！システムインストラクションファイルが見つかりません！")
    SYSTEM_INSTRUCTION = ""

# 日本時間を取得する関数
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
def save_message(channel_id, role, content):
    conn = sqlite3.connect('alice_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO chat_history (channel_id, role, content)
    VALUES (?, ?, ?)
    ''', (channel_id, role, content))
    
    conn.commit()
    conn.close()
#latest_contents={}
#latest_responses={}
def determine_thinking_level(prompt: str) -> str:
    """
    プロンプトの内容から最適な推論レベルを判定する
    
    Returns:
        'low': 簡単な挨拶や短い応答
        'medium': 通常の会話
        'high': 複雑な質問、コード、計算など
    """
    # 複雑なタスクを示すキーワード
    complex_keywords = [
        'コード', 'プログラム', 'スクリプト', '実装', 'アルゴリズム', '計算', '数式',
        '説明して', '詳しく', '分析', '比較', '違い', '理由',
        'どうやって', 'なぜ', 'どのように', 'まとめ', 'レポート',
        'code', 'program', 'script', 'implement', 'algorithm', 'calculate', 'explain',
        'why', 'how', 'analyze', 'compare', 'difference', 'summary'
    ]
    
    # 深い質問・学習を求めるパターン
    deep_question_patterns = [
        '教えて', 'について', 'とは', '解説', '仕組み', '原理',
        'どういう', '意味', '定義', '概念', '理論',
        '何のために', 'どこへ', '目的', '本質',
        'teach', 'about', 'what is', 'explain', 'describe', 'define'
    ]
    
    # 簡単な挨拶や応答パターン
    simple_patterns = [
        'こんにちは', 'おはよう', 'こんばんは', 'やあ', 'よろしく',
        'ありがとう', 'OK', 'わかった', 'うん', 'そうだね',
        'hello', 'hi', 'hey', 'thanks', 'ok', 'yeah'
    ]
    
    prompt_lower = prompt.lower()
    
    # 1. 簡単な挨拶パターンを最初にチェック（優先）
    if len(prompt) <= 20 and any(pattern in prompt_lower for pattern in simple_patterns):
        return 'low'
    
    # 2. 複雑なキーワード → high
    if any(keyword in prompt for keyword in complex_keywords):
        return 'high'
    
    # 3. 深い質問パターン → high
    if any(pattern in prompt for pattern in deep_question_patterns):
        return 'high'
    
    # 4. 疑問符「？」がある場合、少し複雑と判断
    has_question_mark = '?' in prompt or '？' in prompt
    
    # 5. 文字数ベースの判定（上記パターンに該当しない場合）
    if len(prompt) <= 30:
        # 短いが疑問符がある → medium
        return 'medium' if has_question_mark else 'low'
    elif len(prompt) <= 100:
        return 'medium'
    else:
        # 長い文章 → high
        return 'high'

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
            
            # ファイルをダウンロード
            async with aiohttp.ClientSession() as session:
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

async def send_long_message(channel, text):
    """
    長いメッセージを適切に処理して送信
    
    - 2000文字以内: 通常送信
    - 2000-5000文字: 複数メッセージに分割
    - 5000文字超: テキストファイルとして送信
    """
    MAX_LENGTH = 2000
    CHUNK_LENGTH = 1900  # 安全マージンを持たせる
    
    if len(text) <= MAX_LENGTH:
        # 通常送信
        await channel.send(text)
    elif len(text) <= 5000:
        # 複数メッセージに分割
        chunks = []
        while text:
            if len(text) <= CHUNK_LENGTH:
                chunks.append(text)
                break
            # 改行で分割できる位置を探す
            split_pos = text.rfind('\n', 0, CHUNK_LENGTH)
            if split_pos == -1:
                split_pos = CHUNK_LENGTH
            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip()
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                await channel.send(chunk)
            else:
                await channel.send(f"(続き {i+1}/{len(chunks)})\n{chunk}")
    else:
        # テキストファイルとして送信
        file_bytes = text.encode('utf-8')
        file = discord.File(
            fp=__import__('io').BytesIO(file_bytes),
            filename='response.txt'
        )
        await channel.send(
            "応答が長すぎるため、テキストファイルで送信します。",
            file=file
        )


intents = discord.Intents.default()
intents.messages = True
intents.message_content = True # 2023年以降はこれも必須

discord_client = discord.Client(intents=intents)
def get_recent_history(channel_id, limit=6):
    conn = sqlite3.connect('alice_bot.db')
    # 辞書形式で取得できるように設定すると楽です
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 最新のメッセージを古い順（会話の流れ通り）に取得
    cursor.execute('''
    SELECT role, content FROM (
        SELECT role, content, timestamp FROM chat_history 
        WHERE channel_id = ? 
        ORDER BY timestamp DESC LIMIT ?
    ) ORDER BY timestamp ASC
    ''', (channel_id, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Gemini APIが受け取れる辞書リストに変換
    history = []
    for row in rows:
        history.append({
            "role": row['role'],
            "parts": [{"text": row['content']}]
        })
    return history
"""
def create_prompt(prompt, latest_contents, latest_responses):
    contents = []

    for user_log, bot_log in zip(latest_contents, latest_responses):
        if isinstance(user_log, list):
             contents.append({
                "role": "user",
                "parts": user_log
            })
        else:
            contents.append({
                "role": "user",
                "parts": [{"text": user_log}]
            })
            
        contents.append({
            "role": "model",
            "parts": [{"text": bot_log}]
        })

    if isinstance(prompt, list):
        contents.append({
            "role": "user",
            "parts": prompt
        })
    else:
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

    return contents
""" 
@discord_client.event
async def on_ready():
    print(f"Logged in as {discord_client.user}")

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return
    curent_channel_id = message.channel.id
    channel_id=curent_channel_id
    if channel_id not in latest_contents:
        latest_contents[channel_id] = []
    if channel_id not in latest_responses:
        latest_responses[channel_id] = []
    
    # メンションされた場合の処理＆!アリス コマンドで呼び出す（後方互換性）
    if discord_client.user.mentioned_in(message) or message.content.startswith("!アリス "):
        
        
        # メンション部分を除去してプロンプトを取得
        if discord_client.user.mentioned_in(message):
          prompt = message.content.replace(f'<@{discord_client.user.id}>', '').replace(f'<@!{discord_client.user.id}>', '').strip()
        else:
          prompt = message.content[5:]  # "!アリス " は5文字
        if message.channel_mentions:
         channel_id= message.channel_mentions[0].id
         prompt= prompt.replace(f'<#{channel_id}>', '')
        # 添付ファイルを処理
        file_parts = []
        if message.attachments:
            file_parts = await process_attachments(message.attachments)
        
        # プロンプトまたは添付ファイルがある場合のみ応答
        if prompt or file_parts:
            # 推論レベルを自動判定（プロンプトがある場合のみ）
            thinking_level = determine_thinking_level(prompt) if prompt else 'medium'
            print(f"[推論レベル: {thinking_level}] プロンプト: {prompt[:50] if prompt else '(ファイルのみ)'}... ファイル数: {len(file_parts)}")
            
            try:
                # 推論レベルが高い場合、先にメッセージを送信
                if thinking_level == 'high':
                    await message.channel.send("少し待ってください！アリスは思考中です…！")

                # 「入力中」インジケーターを表示しながらAPI呼び出し
                async with message.channel.typing():
                    # コンテンツを構築
                    if file_parts:
                        # ファイルがある場合、マルチパートコンテンツとして送信
                        contents = []
                        if prompt:
                            # 文字列を直接追加
                            contents.append(prompt)
                        contents.extend(file_parts)
                    else:
                        # テキストのみ
                        contents = prompt
                    current_parts = []
                    if prompt:
                     current_parts.append({"text": prompt})
                    if file_parts:
                     current_parts.extend(file_parts)
                    history = get_recent_history(channel_id, limit=6)
                    #input_contents=create_prompt(contents,latest_contents[channel_id], latest_responses[channel_id])
                    input_contents = history + [{
                         "role": "user",
                         "parts": current_parts
                    }]
                    
                    # 現在の日本時間を取得してシステムインストラクションに追加
                    current_jst = get_japan_time()
                    enhanced_instruction = f"{SYSTEM_INSTRUCTION}\n\n[現在の日本時間]\n{current_jst}"
                    
                    response =gemini_client.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=input_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=enhanced_instruction,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=thinking_level
                            )
                        )
                    )
                
                # --- on_message 内の response = ... の後あたり ---

                #  1. Geminiからのメイン回答を取得
                bot_response_text = response.text

                # 2. 履歴保存用のユーザー発言を作成
                # 画像がある場合は要約を付け加える
                if file_parts:
                  file_summary = await summarize_attachments(prompt, file_parts)
                  save_user_text = f"{prompt}{file_summary}"
                else:
                  save_user_text = prompt

                # 3. SQLiteへ保存（ここで保存関数を呼ぶ）
                save_message(curent_channel_id, 'user', save_user_text)
                save_message(curent_channel_id, 'model', bot_response_text)

                # 4. (デバッグ用) どんな風に保存されたか表示
                print(f"DB保存内容: {save_user_text}")
                await send_long_message(message.channel, response.text)
            except Exception as e:
                print(f"エラー: {e}")
                await message.channel.send(f"エラーが発生しました…アリス、リブートします。\n詳細: {e}")
        return
    
    # !光よ! コマンド
    if message.content.startswith("!光よ!"):
        await message.channel.send(file=discord.File("assets/光よ！.jpg"))
        return
    
discord_client.run(DISCORD_TOKEN)