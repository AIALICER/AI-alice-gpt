"""
Gemini API処理モジュール

- フォールバック付きAPI呼び出し
- 推論レベルと検索要否の判定
- ルールベース判定とAPI統合判定
"""

import asyncio
from google.genai import types
from .config_base import gemini_client, gemini_client_fallback


def _is_timeout_error(error_str: str) -> bool:
    return any(token in error_str.lower() for token in (
        "timeout",
        "timed out",
        "read timed out",
        "connect timeout",
        "read timeout"
    ))


def _should_try_fallback_key(e: Exception, error_str: str) -> bool:
    """APIキーのフォールバックが必要か判定"""
    return (
        isinstance(e, TimeoutError) or
        _is_timeout_error(error_str) or
        "RESOURCE_EXHAUSTED" in error_str or
        "429" in error_str or
        "quota" in error_str.lower()
    )


async def generate_content_with_fallback(client, primary_model: str, contents, config):
    """
    APIレートリミット/タイムアウト発生時に自動フォールバックするラッパー関数
    
    フォールバック順序:
    1. primary_model with client (gemini-3-flash-preview等)
    2. primary_model with fallback_client (APIキー2)
    3. gemini-2.5-flash (ThinkingConfig除外)
    4. gemini-2.5-flash-lite (ThinkingConfig除外)
    
    Args:
        client: Geminiクライアント
        primary_model: 優先使用するモデル名
        contents: API入力コンテンツ
        config: GenerateContentConfig
    
    Returns:
        GenerateContentResponse
    """
    fallback_chain = [
        ('gemini-2.5-flash', False),
        ('gemini-2.5-flash-lite', False)
    ]
    
    models_to_try = [(primary_model, True)] + fallback_chain
    used_fallback_key = False
    
    for model_name, is_primary in models_to_try:
        try:
            # Gemini 2.5系の場合、ThinkingConfigを除外
            if model_name.startswith('gemini-2.5'):
                sys_instruct = None
                if hasattr(config, 'system_instruction'):
                    sys_instruct = config.system_instruction
                current_tools = getattr(config, 'tools', None)
                
                new_config = types.GenerateContentConfig(
                    tools=current_tools,
                    system_instruction=sys_instruct
                )
                
                if not is_primary:
                    print(f"[WARNING] Rate limit reached. Falling back to {model_name} (Thinking OFF)")
                
                return await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=new_config
                )
            else:
                # Gemini 3系はそのままThinkingConfigを使用
                if not is_primary:
                    print(f"[WARNING] Rate limit reached. Falling back to {model_name}")
                
                return await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                
        except Exception as e:
            error_str = str(e)
            print(f"[ERROR] Model {model_name} failed: {error_str}")
            
            # APIキーフォールバックを試すべきか判定
            if gemini_client_fallback and _should_try_fallback_key(e, error_str) and not used_fallback_key:
                print("[INFO] Primary API key failed. Trying fallback API key (KEY_2)...")
                used_fallback_key = True
                # 同じモデルでフォールバックキーを試す
                try:
                    if model_name.startswith('gemini-2.5'):
                        sys_instruct = None
                        if hasattr(config, 'system_instruction'):
                            sys_instruct = config.system_instruction
                        current_tools = getattr(config, 'tools', None)
                        new_config = types.GenerateContentConfig(
                            tools=current_tools,
                            system_instruction=sys_instruct
                        )
                        return await gemini_client_fallback.aio.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=new_config
                        )
                    else:
                        return await gemini_client_fallback.aio.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=config
                        )
                except Exception as e2:
                    error_str2 = str(e2)
                    print(f"[ERROR] Fallback API key also failed: {error_str2}")
                    # フォールバックキーでも失敗したので次のモデルへ
            
            # リトライ対象のエラー判定
            is_retryable = (
                isinstance(e, TimeoutError) or
                "429" in error_str or 
                "RESOURCE_EXHAUSTED" in error_str or
                "503" in error_str or 
                "UNAVAILABLE" in error_str or
                "overloaded" in error_str.lower() or
                _is_timeout_error(error_str)
            )
            
            if is_retryable:
                if isinstance(e, TimeoutError) or _is_timeout_error(error_str):
                    print("[INFO] Timeout detected. Waiting 1 second before retry...")
                    await asyncio.sleep(1)
                elif "503" in error_str or "UNAVAILABLE" in error_str:
                    print("[INFO] Server overload detected. Waiting 2 seconds...")
                    await asyncio.sleep(2)
                
                if model_name == models_to_try[-1][0]:
                    raise Exception(f"All models failed (retry limit): {e}")
                continue
            else:
                print(f"[ERROR] Non-retryable error: {type(e).__name__}: {error_str}")
                raise e
    
    raise Exception("Unexpected error: Fallback chain did not complete")


def generate_content_safe(client, primary_model: str, contents, config, fallback_model: str = 'gemini-2.5-flash'):
    """
    同期版のレートリミット対応API呼び出し
    
    Args:
        client: Geminiクライアント
        primary_model: 優先使用するモデル名
        contents: API入力コンテンツ
        config: GenerateContentConfig
        fallback_model: フォールバック先モデル
    
    Returns:
        GenerateContentResponse
    """
    try:
        return client.models.generate_content(
            model=primary_model,
            contents=contents,
            config=config
        )
    except Exception as e:
        if isinstance(e, TimeoutError) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or _is_timeout_error(str(e)):
            print(f"[WARNING] {primary_model} rate limit/timeout. Falling back to {fallback_model}.")
            
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


def determine_level_and_search_rule_based(prompt: str) -> dict | None:
    """
    ルールベースで推論レベルと検索要否を判定する
    
    明らかなケースのみ判定し、それ以外はNoneを返してAPI判定に委ねる
    
    Args:
        prompt: ユーザーの入力テキスト
    
    Returns:
        dict: {'level': 'low/medium/high', 'search': True/False, 'minutes': int, 'task': str}
        または None（API判定が必要）
    """
    prompt_lower = prompt.lower()
    
    # 検索が必要なキーワード
    search_required_keywords = [
        '今日', '最新', 'ニュース', '天気', '現在', '株価', 'リアルタイム',
        '速報', '今週', '今月', '昨日', 'トレンド', '為替', 'レート',
        'today', 'latest', 'news', 'weather', 'current', 'now', 'trending'
    ]
    
    # 簡単な挨拶パターン
    simple_greetings = [
        'こんにちは', 'おはよう', 'こんばんは', 'やあ', 'よろしく',
        'ありがとう', 'おやすみ', 'バイバイ', 'さようなら',
        'hello', 'hi', 'hey', 'thanks', 'good morning', 'good night', 'bye'
    ]
    
    # コード・技術系キーワード
    code_keywords = [
        'コード', 'プログラム', 'スクリプト', '実装', 'アルゴリズム', '関数',
        'クラス', 'バグ', 'エラー', 'デバッグ', 'リファクタ',
        'code', 'program', 'script', 'implement', 'algorithm', 'function',
        'class', 'bug', 'error', 'debug', 'refactor', 'python', 'javascript'
    ]
    
    # 相槌・短い返答
    simple_responses = [
        'OK', 'ok', 'わかった', 'うん', 'そうだね', 'なるほど', 'いいね',
        'yes', 'no', 'yeah', 'sure', 'got it'
    ]
    
    # タイマー関連
    time_responses = [
        '計って', '計測して', 'タイマー', '測って', 'たったら', '経ったら'
    ]
    
    if any(kw in prompt_lower for kw in time_responses):
        print("[Rule-based] Timer detection required, need API judgment")
        return None
    
    if len(prompt) <= 20 and any(p in prompt_lower for p in simple_greetings):
        print("[Rule-based] Greeting pattern -> low, no search, no timer")
        return {'level': 'low', 'search': False, 'minutes': 0, 'task': "null"}
    
    if len(prompt) <= 15 and any(p in prompt_lower for p in simple_responses):
        print("[Rule-based] Response pattern -> low, no search, no timer")
        return {'level': 'low', 'search': False, 'minutes': 0, 'task': "null"}
    
    if any(kw in prompt_lower for kw in code_keywords):
        print("[Rule-based] Code pattern -> high, no search, no timer")
        return {'level': 'high', 'search': False, 'minutes': 0, 'task': "null"}
    
    if any(kw in prompt_lower for kw in search_required_keywords):
        print("[Rule-based] Search required pattern -> high, search needed, no timer")
        return {'level': 'high', 'search': True, 'minutes': 0, 'task': "null"}
    
    return None


async def determine_level_and_search(
    prompt: str, 
    channel_id: int, 
    has_attachments: bool = False,
    get_recent_history_func=None,
    character_name: str = "Bot"
) -> dict:
    """
    推論レベルと検索要否を統合判定する
    
    1. まずルールベースで判定（API呼び出しなし）
    2. 判定できない場合のみGemini APIで判定
    
    Args:
        prompt: ユーザーの入力テキスト
        channel_id: チャンネルID
        has_attachments: 添付ファイルの有無
        get_recent_history_func: 履歴取得関数
        character_name: キャラクター名（ログ用）
    
    Returns:
        dict: {'level': 'low/medium/high', 'search': True/False, 'minutes': float, 'task': str}
    """
    # ルールベースで事前判定
    rule_result = determine_level_and_search_rule_based(prompt)
    if rule_result is not None:
        return rule_result
    
    # API統合判定
    history = []
    if get_recent_history_func:
        history = get_recent_history_func(channel_id, limit=4)
    
    # 会話履歴をテキスト形式に変換
    history_text = ""
    if history:
        history_lines = []
        for msg in history:
            role = "User" if msg["role"] == "user" else character_name
            text = msg["parts"][0]["text"] if msg["parts"] else ""
            if text is None:
                text = ""
            if len(text) > 100:
                text = text[:100] + "..."
            history_lines.append(f"{role}: {text}")
        history_text = "\n".join(history_lines)
    
    router_prompt = f"""You are an AI chatbot judgment system. Please judge 3 items.

## Judgment 1: Inference Level
- **low**: Simple greetings, responses, casual chat
- **medium**: General questions, daily conversation, opinions
- **high**: Code, calculations, analysis, detailed explanations, creative writing

## Judgment 2: Search Necessity
- **true**: Latest information, news, weather, current events (external info needed)
- **false**: General knowledge, code, greetings (no search needed)

## Judgment 3: Timer/Reminder Necessity
- **minutes**: If user requests time measurement or reminder, return the number of minutes only.
- "1 hour" = **60**, "30 seconds" = **0.5**
- If not needed or time is unclear = **0**
- **task**: Timer description (e.g., "cup noodles", "meeting"). If not needed = **null**

## Conversation History
{history_text if history_text else "(None)"}

## User Input
{prompt if prompt else "(No text, file attached)"}
{"*File attached" if has_attachments else ""}

## Output Format (strict)
level:low/medium/high,search:true/false,minutes:int,task:str

Example: level:high,search:false,minutes:10,task:meeting
Example: level:medium,search:true,minutes:0,task:null"""

    try:
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
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
        print(f"[API Judgment] Result: {result}")
        
        level = 'medium'
        search = False
        minutes = 0
        task = ""
        
        if 'level:' in result:
            level_part = result.split('level:')[1].split(',')[0].strip()
            if level_part in ['low', 'medium', 'high']:
                level = level_part
        
        if 'search:' in result:
            search_part = result.split('search:')[1].split(',')[0].strip()
            search = search_part == 'true'
        
        if 'minutes:' in result:
            minutes_part = result.split('minutes:')[1].split(',')[0].strip()
            try:
                minutes = float(minutes_part)
            except ValueError:
                minutes = 0
        
        if 'task' in result:
            task = result.split('task:')[1].split(',')[0].strip()
        
        print(f"[API Judgment] Level: {level}, Search: {search}, Minutes: {minutes}, Task: {task}")
        return {'level': level, 'search': search, 'minutes': minutes, 'task': task}
            
    except Exception as e:
        print(f"[API Judgment Skip] {e} -> Using default values")
        return {'level': 'medium', 'search': False, 'minutes': 0, 'task': "null"}
