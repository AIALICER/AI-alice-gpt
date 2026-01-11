import discord
from google import genai
from google.genai import types
import os
import aiohttp
from datetime import datetime, timedelta, timezone
import sqlite3
import asyncio
import look_db
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
    
def save_message(channel_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO chat_history (channel_id, role, content)
    VALUES (?, ?, ?)
    ''', (channel_id, role, content))
    
    conn.commit()
    conn.close()
def determine_level_and_search_rule_based(prompt: str) -> dict | None:
    """
    ルールベースで推論レベルと検索要否を判定する（案2）
    明らかなケースのみ判定し、それ以外はNoneを返してAPI判定に委ねる
    
    Returns:
        dict: {'level': 'low/medium/high', 'search': True/False} または None（API判定が必要）
    """
    prompt_lower = prompt.lower()
    
    # === 検索が必要なキーワード ===
    search_required_keywords = [
        '今日', '最新', 'ニュース', '天気', '現在', '株価', 'リアルタイム',
        '速報', '今週', '今月', '昨日', 'トレンド', '為替', 'レート',
        'today', 'latest', 'news', 'weather', 'current', 'now', 'trending'
    ]
    
    # === 簡単な挨拶パターン（検索不要・low） ===
    simple_greetings = [
        'こんにちは', 'おはよう', 'こんばんは', 'やあ', 'よろしく',
        'ありがとう', 'おやすみ', 'バイバイ', 'さようなら',
        'hello', 'hi', 'hey', 'thanks', 'good morning', 'good night', 'bye'
    ]
    
    # === コード・技術系キーワード（検索不要・high） ===
    code_keywords = [
        'コード', 'プログラム', 'スクリプト', '実装', 'アルゴリズム', '関数',
        'クラス', 'バグ', 'エラー', 'デバッグ', 'リファクタ',
        'code', 'program', 'script', 'implement', 'algorithm', 'function',
        'class', 'bug', 'error', 'debug', 'refactor', 'python', 'javascript'
    ]
    
    # === 相槌・短い返答（検索不要・low） ===
    simple_responses = [
        'OK', 'ok', 'わかった', 'うん', 'そうだね', 'なるほど', 'いいね',
        'yes', 'no', 'yeah', 'sure', 'got it'
    ]
    
    # 1. 短い挨拶 → low, 検索不要
    if len(prompt) <= 20 and any(p in prompt_lower for p in simple_greetings):
        print("[ルールベース判定] 挨拶パターン → low, 検索不要")
        return {'level': 'low', 'search': False}
    
    # 2. 相槌・短い返答 → low, 検索不要
    if len(prompt) <= 15 and any(p in prompt_lower for p in simple_responses):
        print("[ルールベース判定] 相槌パターン → low, 検索不要")
        return {'level': 'low', 'search': False}
    
    # 3. コード・技術系 → high, 検索不要
    if any(kw in prompt_lower for kw in code_keywords):
        print("[ルールベース判定] コード系パターン → high, 検索不要")
        return {'level': 'high', 'search': False}
    
    # 4. 検索必須キーワード → high, 検索必要
    if any(kw in prompt_lower for kw in search_required_keywords):
        print("[ルールベース判定] 検索必須パターン → high, 検索必要")
        return {'level': 'high', 'search': True}
    
    # 上記に該当しない場合はAPI判定が必要
    return None


async def generate_content_safe(client, primary_model, contents, config, fallback_model='gemini-2.5-flash'):
    """
    APIレートリミット(429)発生時にフォールバックモデルで再試行するラッパー関数
    """
    try:
        return client.models.generate_content(
            model=primary_model,
            contents=contents,
            config=config
        )
    except Exception as e:
        # 429 RESOURCE_EXHAUSTED の場合
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print(f"⚠️ {primary_model} のレートリミット到達。{fallback_model} にフォールバックします。")
            
            # フォールバック時はThinkingConfigなど特有の設定を除外して再構築
            sys_instruct = None
            if hasattr(config, 'system_instruction'):
                sys_instruct = config.system_instruction
            
            new_config = types.GenerateContentConfig(
                system_instruction=sys_instruct
            )
            
            return client.models.generate_content(
                model=fallback_model,
                contents=contents,
                config=new_config
            )
        else:
            raise e


async def determine_level_and_search(prompt: str, channel_id: int, has_attachments: bool = False) -> dict:
    """
    推論レベルと検索要否を統合判定する（案1 + 案2）
    
    1. まずルールベースで判定（API呼び出しなし）
    2. 判定できない場合のみGemini APIで判定
    
    Returns:
        dict: {'level': 'low/medium/high', 'search': True/False}
    """
    # === 案2: ルールベースで事前判定 ===
    rule_result = determine_level_and_search_rule_based(prompt)
    if rule_result is not None:
        return rule_result
    
    # === 案1: API統合判定（ルールベースで判定できなかった場合） ===
    # 会話履歴を取得（直近4件まで）
    history = get_recent_history(channel_id, limit=4)
    
    # 会話履歴をテキスト形式に変換
    history_text = ""
    if history:
        history_lines = []
        for msg in history:
            role = "ユーザー" if msg["role"] == "user" else "アリス"
            text = msg["parts"][0]["text"] if msg["parts"] else ""
            if len(text) > 100:
                text = text[:100] + "..."
            history_lines.append(f"{role}: {text}")
        history_text = "\n".join(history_lines)
    
    # 推論レベルと検索要否を同時に判定するプロンプト
    router_prompt = f"""あなたはAIチャットボットの判定システムです。2つの項目を判定してください。

## 判定1: 推論レベル
- **low**: 簡単な挨拶、相槌、雑談
- **medium**: 一般的な質問、日常会話、意見
- **high**: コード、計算、分析、詳細解説、創作

## 判定2: 検索の必要性
- **true**: 最新情報、ニュース、天気、時事問題など外部情報が必要
- **false**: 一般知識、コード、挨拶など検索不要

## 会話履歴
{history_text if history_text else "（なし）"}

## ユーザー入力
{prompt if prompt else "（テキストなし、ファイル添付あり）"}
{"※添付ファイルがあります" if has_attachments else ""}

## 出力形式（厳守）
level:low/medium/high,search:true/false

例: level:high,search:false
例: level:medium,search:true"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=router_prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level='minimal'
                ),
                max_output_tokens=30,
                temperature=0.1
            )
        )
        
        result = response.text.strip().lower()
        print(f"[API統合判定] 結果: {result}")
        
        # パース: "level:high,search:false" 形式
        level = 'medium'  # デフォルト
        search = False    # デフォルト
        
        if 'level:' in result:
            level_part = result.split('level:')[1].split(',')[0].strip()
            if level_part in ['low', 'medium', 'high']:
                level = level_part
        
        if 'search:' in result:
            search_part = result.split('search:')[1].split(',')[0].strip()
            search = search_part == 'true'
        
        print(f"[API統合判定] レベル: {level}, 検索: {search}")
        return {'level': level, 'search': search}
            
    except Exception as e:
        print(f"[API統合判定スキップ] {e} -> デフォルト値を使用")
        # エラー時はデフォルト値（medium, 検索なし）
        return {'level': 'medium', 'search': False}


async def generate_content_with_fallback(client, primary_model, contents, config):
    """
    APIレートリミット(429)発生時に自動フォールバックするラッパー関数
    
    フォールバック順序:
    1. gemini-3-flash-preview
    2. gemini-2.5-flash (ThinkingConfig → thinking_budget変換)
    3. gemini-2.5-flash-lite (ThinkingConfig → thinking_budget変換)
    """
    # thinking_levelからthinking_budgetへの変換マップ
    thinking_level_to_budget = {
        'minimal': 512,
        'low': 2048,
        'medium': 8192,
        'high': 24576
    }
    
    fallback_chain = [
        ('gemini-2.5-flash', False),      # 2段目: Gemini 2.5 Flash
        ('gemini-2.5-flash-lite', False)  # 3段目: Gemini 2.5 Flash-Lite
    ]
    
    models_to_try = [(primary_model, True)] + fallback_chain
    
    for model_name, is_primary in models_to_try:
        try:
            # Gemini 2.5系の場合、ThinkingConfigを除外（SDKエラー回避のため基本設定のみ）
            if model_name.startswith('gemini-2.5'):
                # system_instructionを取得
                sys_instruct = None
                if hasattr(config, 'system_instruction'):
                    sys_instruct = config.system_instruction
                current_tools = getattr(config, 'tools', None)
                # 新しいconfigを構築（thinking_budgetはSDK未対応の可能性があるため除外）
                new_config = types.GenerateContentConfig(
                    tools=current_tools,
                    system_instruction=sys_instruct
                )
                
                if not is_primary:
                    print(f"⚠️ レートリミット到達。{model_name} にフォールバックします（Thinking機能OFF）")
                
                return await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=new_config
                )
            else:
                # Gemini 3系はそのままThinkingConfigを使用
                if not is_primary:
                    print(f"⚠️ レートリミット到達。{model_name} にフォールバックします")
                
                return await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                # 次のモデルへフォールバック
                if model_name == models_to_try[-1][0]:
                    # 全てのモデルで失敗した場合
                    raise Exception(f"全てのモデルでレートリミット到達: {e}")
                continue
            else:
                # 429以外のエラーはそのまま送出
                raise e
    
    # ここには到達しないはずだが、念のため
    raise Exception("予期しないエラー: フォールバックチェーンが完了しませんでした")


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
    print("b")
    conn.close()
    return memory
def get_recent_history(channel_id, limit=6):
    conn = sqlite3.connect(DB_PATH)
    # 辞書形式で取得できるように設定すると楽です
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 最新のメッセージを古い順（会話の流れ通り）に取得
    cursor.execute('''
    SELECT role, content FROM (
        SELECT role, content, timestamp FROM chat_history 
        WHERE channel_id = ? 
        ORDER BY timestamp ASC
    ) ''', (channel_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Gemini APIが受け取れる辞書リストに変換
    history = []
    for row in rows:
        history.append({
            "role": row['role'],
            "parts": [{"text": row['content']}]
        })
    print("a")
    return history

@discord_client.event
async def on_ready():
    print(f"Logged in as {discord_client.user}")

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return
    curent_channel_id = message.channel.id
    channel_id=curent_channel_id
    if message.content == "!アリス 履歴消去":
        if clear_db_history(channel_id):       
            await message.channel.send("了解です！このチャンネルの記憶をリセットしました！")
        else:
            await message.channel.send("ごめんなさい、履歴の消去に失敗しました…")
        return
    if message.content == "!ログ確認":
        look_db.check_database()
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
        if channel_id in summary_tasks:
          summary_tasks[channel_id].cancel()
        summary_tasks[channel_id] = asyncio.create_task(summarize_and_cleanup(channel_id))
        # 添付ファイルを処理
        file_parts = []
        if message.attachments:
            file_parts = await process_attachments(message.attachments)
        
        # プロンプトまたは添付ファイルがある場合のみ応答
        if prompt or file_parts:
            # 即座に「入力中...」インジケーターを表示
            async with message.channel.typing():
                # 統合判定: 推論レベルと検索要否を同時に判定（案1 + 案2）
                judgment = await determine_level_and_search(
                    prompt=prompt if prompt else "",
                    channel_id=channel_id,
                    has_attachments=bool(file_parts)
                )
                thinking_level = judgment['level']
                needs_search = judgment['search']
                print(f"[統合判定] レベル: {thinking_level}, 検索: {needs_search}, プロンプト: {prompt[:50] if prompt else '(ファイルのみ)'}...")
                
                try:
                    # 推論レベルが高い場合、追加の思考中メッセージを送信
                    if thinking_level == 'high':
                        await message.channel.send("少し待ってください！アリスは思考中です…！")
                    
                    # 検索が必要な場合、ツールを設定
                    alice_tools = []
                    if needs_search:
                        await message.channel.send("アリス、検索中です！")
                        alice_tools.append(
                            types.Tool(google_search=types.GoogleSearch())
                        )
                     
                    # コンテンツを構築
                    current_parts = []
                    if prompt:
                        current_parts.append({"text": prompt})
                    if file_parts:
                        current_parts.extend(file_parts)
                    
                    history = get_recent_history(channel_id, limit=6)
                    input_contents = history + [{
                         "role": "user",
                         "parts": current_parts
                    }]
                    memories=""
                    memories=get_memories(channel_id)
                    # 現在の日本時間を取得
                    current_jst = get_japan_time()
                    enhanced_instruction = f"{SYSTEM_INSTRUCTION}\n\n[現在の日本時間]\n{current_jst}"
                    if alice_tools:
                        current_config = types.GenerateContentConfig(
                            system_instruction=enhanced_instruction + "\n\n【重要】最新情報のためにGoogle検索を使ってください。"+ "\n\n以下はログより以前の会話履歴の要約です必要に応じて確認してください"+memories,
                            tools=alice_tools,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=thinking_level
                            )
                        )
                        print("検索を実行\n")
                    else:
                        current_config = types.GenerateContentConfig(
                            system_instruction=enhanced_instruction+ "\n\n以下はログより以前の会話履歴の要約です必要に応じて確認してください"+memories,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=thinking_level
                            )
                        )
                    # レートリミット対応の呼び出し（3段階フォールバック）
                    response = await generate_content_with_fallback(
                        client=gemini_client,
                        primary_model='gemini-3-flash-preview',
                        contents=input_contents,
                        config=current_config
                    )
                
                    # 応答の取得と保存
                    bot_response_text = response.text

                    if file_parts:
                        file_summary = await summarize_attachments(prompt, file_parts)
                        save_user_text = f"{prompt}{file_summary}"
                    else:
                        save_user_text = prompt

                    save_message(curent_channel_id, 'user', save_user_text)
                    save_message(curent_channel_id, 'model', bot_response_text)

                    print(f"DB保存内容: {save_user_text}")
                    await send_long_message(message.channel, bot_response_text)

                except Exception as e:
                    print(f"エラー: {e}")
                    await message.channel.send(f"エラーが発生しました…アリス、リブートします。\n詳細: {e}")
        return
    
    # !光よ! コマンド
    if message.content.startswith("!光よ!"):
        await message.channel.send(file=discord.File("assets/光よ！.jpg"))
        return
    
discord_client.run(DISCORD_TOKEN)