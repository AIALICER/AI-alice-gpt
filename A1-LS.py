import discord
from google import genai
from google.genai import types
import os
import aiohttp

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
latest_contents={}
latest_responses={}
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
 
@discord_client.event
async def on_ready():
    print(f"Logged in as {discord_client.user}")

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return
    channel_id = message.channel.id
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
                    input_contents=create_prompt(contents,latest_contents[channel_id], latest_responses[channel_id])
                    response =gemini_client.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=input_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=thinking_level
                            )
                        )
                    )
                
                latest_contents[channel_id].append(contents)
                latest_responses[channel_id].append(contents)
                if len(latest_contents[channel_id]) >6:
                 latest_contents[channel_id].pop(0)
                if len(latest_responses[channel_id]) >6:
                 latest_responses[channel_id].pop(0)
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