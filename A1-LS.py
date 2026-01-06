import discord
from google import genai
from google.genai import types
import os
import aiohttp
from datetime import datetime, timedelta, timezone
import sqlite3

# データベースの保存ディレクトリを確認・作成
DB_DIR = 'data'
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

DB_PATH = os.path.join(DB_DIR, 'alice_bot.db')

# データベースに接続（ファイルがなければ作成される）
conn = sqlite3.connect(DB_PATH)
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
def save_message(channel_id, role, content):
    conn = sqlite3.connect(DB_PATH)
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


async def determine_thinking_level_with_router(prompt: str, channel_id: int, has_attachments: bool = False) -> str:
    """
    Gemini 3 Flashを使用したRouter構成で推論レベルを判定する
    
    Args:
        prompt: ユーザーからのプロンプト
        channel_id: チャンネルID（会話履歴取得用）
        has_attachments: 添付ファイルがあるかどうか
    
    Returns:
        'low': 簡単な挨拶や短い応答（思考不要）
        'medium': 通常の会話（軽い思考）
        'high': 複雑な質問、コード、分析など（深い思考が必要）
    """
    
    # 会話履歴を取得（直近4件まで）
    history = get_recent_history(channel_id, limit=4)
    
    # 会話履歴をテキスト形式に変換
    history_text = ""
    if history:
        history_lines = []
        for msg in history:
            role = "ユーザー" if msg["role"] == "user" else "アリス"
            text = msg["parts"][0]["text"] if msg["parts"] else ""
            # 履歴は要約（長すぎる場合は切り詰め）
            if len(text) > 100:
                text = text[:100] + "..."
            history_lines.append(f"{role}: {text}")
        history_text = "\n".join(history_lines)
    
    # Router用の分類プロンプト
    router_prompt = f"""あなたはAIチャットボットの推論レベル分類器です。
ユーザーの質問に対して、どの程度の思考深度が必要かを判定してください。

## 分類基準

**low（思考不要）**:
- 簡単な挨拶（こんにちは、おはよう、ありがとう等）
- 短い相槌や確認（OK、わかった、そうだね等）
- 雑談的な軽いやり取り

**medium（軽い思考）**:
- 一般的な質問への回答
- 簡単な情報提供
- 日常会話の続き
- 意見や感想を求められた場合

**high（深い思考が必要）**:
- コードやプログラミングに関する質問
- 複雑な計算や分析
- 詳細な説明や解説を求められた場合
- 比較、理由の説明、仕組みの解説
- 長文での回答が必要な質問
- 創作やアイデア出し
- 問題解決やトラブルシューティング

## 会話履歴（参考）
{history_text if history_text else "（なし）"}

## 現在のユーザー入力
{prompt if prompt else "（テキストなし、ファイル添付あり）"}

{"※添付ファイルがあります" if has_attachments else ""}

## 出力
上記を踏まえ、推論レベルを low / medium / high のいずれか1単語のみで回答してください。"""

    try:
        # Gemini 3 Flashで高速分類
        response = gemini_client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=router_prompt,
            config=types.GenerateContentConfig(
                # 分類タスクなので最小限の思考で十分（'minimal'が最軽量）
                thinking_config=types.ThinkingConfig(
                    thinking_level='minimal'
                ),
                # 出力を短く制限
                max_output_tokens=10,
                temperature=0.1  # 一貫性のため低めに設定
            )
        )
        
        # 結果をパース
        result = response.text.strip().lower()
        
        # 有効な値かチェック
        if result in ['low', 'medium', 'high']:
            print(f"[Router分類] レベル: {result}")
            return result
        else:
            # パースできない場合はフォールバック
            print(f"[Router分類] 不明な結果: {result}、フォールバック実行")
            return determine_thinking_level(prompt)
            
    except Exception as e:
        # エラー時はルールベースにフォールバック
        print(f"[Router分類エラー] {e}、ルールベース判定にフォールバック")
        return determine_thinking_level(prompt)


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
            # Gemini 2.5系の場合、ThinkingConfigをthinking_budgetに変換
            if model_name.startswith('gemini-2.5'):
                # system_instructionを取得
                sys_instruct = None
                if hasattr(config, 'system_instruction'):
                    sys_instruct = config.system_instruction
                
                # thinking_budgetを決定
                thinking_budget = None
                if hasattr(config, 'thinking_config') and config.thinking_config:
                    thinking_level = getattr(config.thinking_config, 'thinking_level', 'medium')
                    thinking_budget = thinking_level_to_budget.get(thinking_level, 8192)
                
                # 新しいconfigを構築
                new_config = types.GenerateContentConfig(
                    system_instruction=sys_instruct,
                    thinking_budget=thinking_budget
                )
                
                if not is_primary:
                    print(f"⚠️ レートリミット到達。{model_name} にフォールバックします（thinking_budget={thinking_budget}）")
                
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=new_config
                )
            else:
                # Gemini 3系はそのままThinkingConfigを使用
                if not is_primary:
                    print(f"⚠️ レートリミット到達。{model_name} にフォールバックします")
                
                return client.models.generate_content(
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
    if message.content == "!アリス 履歴消去":
        if clear_db_history(channel_id):       
            await message.channel.send("了解です！このチャンネルの記憶をリセットしました！")
        else:
            await message.channel.send("ごめんなさい、履歴の消去に失敗しました…")
        return
    
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
            # 即座に「入力中...」インジケーターを表示
            async with message.channel.typing():
                # Router構成で推論レベルを自動判定（Gemini 3 Flash使用）
                thinking_level = await determine_thinking_level_with_router(
                    prompt=prompt if prompt else "",
                    channel_id=channel_id,
                    has_attachments=bool(file_parts)
                )
                print(f"[推論レベル: {thinking_level}] プロンプト: {prompt[:50] if prompt else '(ファイルのみ)'}... ファイル数: {len(file_parts)}")
                
                try:
                    # 推論レベルが高い場合、追加の思考中メッセージを送信
                    if thinking_level == 'high':
                        await message.channel.send("少し待ってください！アリスは思考中です…！")

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
                    
                    # 現在の日本時間を取得
                    current_jst = get_japan_time()
                    enhanced_instruction = f"{SYSTEM_INSTRUCTION}\n\n[現在の日本時間]\n{current_jst}"
                    
                    # レートリミット対応の呼び出し（3段階フォールバック）
                    response = await generate_content_with_fallback(
                        client=gemini_client,
                        primary_model='gemini-3-flash-preview',
                        contents=input_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=enhanced_instruction,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=thinking_level
                            )
                        )
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