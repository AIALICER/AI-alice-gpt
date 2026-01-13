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
    return history
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
            # textがNoneの場合は空文字列に変換
            if text is None:
                text = ""
            if len(text) > 100:
                text = text[:100] + "..."
            history_lines.append(f"{role}: {text}")
        history_text = "\n".join(history_lines)
    
    # 推論レベルと検索要否を同時に判定するプロンプト
    router_prompt = f"""あなたはAIチャットボットの判定システムです。3つの項目を判定してください。

## 判定1: 推論レベル
- **low**: 簡単な挨拶、相槌、雑談
- **medium**: 一般的な質問、日常会話、意見
- **high**: コード、計算、分析、詳細解説、創作

## 判定2: 検索の必要性
- **true**: 最新情報、ニュース、天気、時事問題など外部情報が必要
- **false**: 一般知識、コード、挨拶など検索不要
## 判定3: タイマー・リマインダーの必要性
- **minutes**: ユーザーが時間の計測やリマインドを求めている場合は、その「分」の数値のみを返してください。
- 「1時間」なら **60** - 「30秒」なら **0.5** 
- 不要な場合や時間が不明な場合は **0**
- **task**: タイマーの内容（例：「カップ麺」「会議」）。不要な場合は **null**
## 会話履歴
{history_text if history_text else "（なし）"}

## ユーザー入力
{prompt if prompt else "（テキストなし、ファイル添付あり）"}
{"※添付ファイルがあります" if has_attachments else ""}

## 出力形式（厳守）
level:low/medium/high,search:true/false,minutes:int,task:str

例: level:high,search:false,minutes:10,task:会議,
例: level:medium,search:true,minutes:0,task:null"""

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
        minutes= 0
        task=""
        if 'level:' in result:
            level_part = result.split('level:')[1].split(',')[0].strip()
            if level_part in ['low', 'medium', 'high']:
                level = level_part
        
        if 'search:' in result:
            search_part = result.split('search:')[1].split(',')[0].strip()
            search = search_part == 'true'
        if 'minutes:' in result:
            minutes_part = result.split('minutes:')[1].split(',')[0].strip()
            if minutes_part.isdigit():
             minutes=int(minutes_part)
        if 'task' in result:
            task=result.split('task:')[1].split(',')[0].strip()
        print(f"[API統合判定] レベル: {level}, 検索: {search},時間{minutes},タイマーの要件{task}")
        return {'level': level, 'search': search,'minutes':minutes,'task':task}
            
    except Exception as e:
        print(f"[API統合判定スキップ] {e} -> デフォルト値を使用")
        # エラー時はデフォルト値（medium, 検索なし）
        return {'level': 'medium', 'search': False}
def save_message(channel_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO chat_history (channel_id, role, content)
    VALUES (?, ?, ?)
    ''', (channel_id, role, content))
    
    conn.commit()
    conn.close()
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

