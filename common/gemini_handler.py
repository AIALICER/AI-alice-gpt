import asyncio
import os
import re
import time
from datetime import datetime, timedelta, timezone

from google.genai import types

# 日本標準時 (JST) の定義
JST = timezone(timedelta(hours=9))
from .config_base import gemini_client, gemini_client_fallback


def _is_timeout_error(error_str: str) -> bool:
    """タイムアウト関連のエラーか判定"""
    return any(
        token in error_str.lower()
        for token in (
            "timeout",
            "timed out",
            "read timed out",
            "connect timeout",
            "read timeout",
            "deadline",
            "exceeded",
        )
    )


def _should_try_fallback_key(e: Exception, error_str: str) -> bool:
    """APIキーのフォールバックを試すべきエラーか判定"""
    return (
        isinstance(e, TimeoutError)
        or _is_timeout_error(error_str)
        or "RESOURCE_EXHAUSTED" in error_str
        or "429" in error_str
        or "quota" in error_str.lower()
    )


async def generate_content_with_fallback(client, primary_model: str, contents, config):
    """
    APIレートリミット/タイムアウト発生時に自動フォールバックするラッパー関数

    フォールバック順序:
    1. primary_model with client (gemini-3.1-flash-lite-preview等)
    2. primary_model with fallback_client (APIキー2)
    3. gemini-3-flash-preview (ThinkingConfig対応)
    4. gemini-2.0-flash (ThinkingConfig除外)
    5. gemini-2.0-flash-lite (ThinkingConfig除外)
    """
    fallback_chain = [
        ("gemini-3-flash-preview", True),
        ("gemini-2.0-flash", False),
        ("gemini-2.0-flash-lite", False),
    ]

    models_to_try = [(primary_model, True)] + fallback_chain
    used_fallback_key = False

    for model_name, can_thinking in models_to_try:
        try:
            print(f"[Gemini API] Using model: {model_name}")

            if not can_thinking:
                sys_instruct = None
                if hasattr(config, "system_instruction"):
                    sys_instruct = config.system_instruction
                current_tools = getattr(config, "tools", None)

                new_config = types.GenerateContentConfig(
                    tools=current_tools, system_instruction=sys_instruct
                )

                return await client.aio.models.generate_content(
                    model=model_name, contents=contents, config=new_config
                )
            else:
                return await client.aio.models.generate_content(
                    model=model_name, contents=contents, config=config
                )

        except Exception as e:
            error_str = str(e)
            err_type = type(e).__name__
            print(f"[X] {model_name}: {err_type}")

            if (
                gemini_client_fallback
                and _should_try_fallback_key(e, error_str)
                and not used_fallback_key
            ):
                print("[~] Trying KEY_2...")
                used_fallback_key = True
                try:
                    if not can_thinking:
                        sys_instruct = None
                        if hasattr(config, "system_instruction"):
                            sys_instruct = config.system_instruction
                        current_tools = getattr(config, "tools", None)
                        new_config = types.GenerateContentConfig(
                            tools=current_tools, system_instruction=sys_instruct
                        )
                        return await gemini_client_fallback.aio.models.generate_content(
                            model=model_name, contents=contents, config=new_config
                        )
                    else:
                        return await gemini_client_fallback.aio.models.generate_content(
                            model=model_name, contents=contents, config=config
                        )
                except Exception as e2:
                    print(f"[X] KEY_2 failed: {type(e2).__name__}")

            is_retryable = (
                isinstance(e, TimeoutError)
                or "429" in error_str
                or "RESOURCE_EXHAUSTED" in error_str
                or "503" in error_str
                or "UNAVAILABLE" in error_str
                or "overloaded" in error_str.lower()
                or _is_timeout_error(error_str)
            )

            if is_retryable:
                if isinstance(e, TimeoutError) or _is_timeout_error(error_str):
                    print("[~] Retry in 1s...")
                    await asyncio.sleep(1)
                elif "503" in error_str or "UNAVAILABLE" in error_str:
                    print("[~] Overloaded, wait 2s...")
                    await asyncio.sleep(2)

                if model_name == models_to_try[-1][0]:
                    raise e
                continue
            else:
                raise e


def generate_content_safe(
    client,
    primary_model: str,
    contents,
    config,
    fallback_model: str = "gemini-2.0-flash",
):
    try:
        return client.models.generate_content(model=primary_model, contents=contents, config=config)
    except Exception as e:
        error_str = str(e)
        if (
            isinstance(e, TimeoutError)
            or "429" in error_str
            or "RESOURCE_EXHAUSTED" in error_str
            or _is_timeout_error(error_str)
        ):
            print(f"[!] {primary_model} -> {fallback_model}")
            sys_instruct = None
            if hasattr(config, "system_instruction"):
                sys_instruct = config.system_instruction
            new_config = types.GenerateContentConfig(system_instruction=sys_instruct)
            return client.models.generate_content(
                model=fallback_model, contents=contents, config=new_config
            )
        else:
            raise e


def determine_level_and_search_rule_based(prompt: str):
    prompt_lower = prompt.lower()
    search_required_keywords = [
        "今日",
        "最新",
        "ニュース",
        "天気",
        "現在",
        "株価",
        "リアルタイム",
        "速報",
        "今週",
        "今月",
        "昨日",
        "トレンド",
        "為替",
        "レート",
        "today",
        "latest",
        "news",
        "weather",
        "current",
        "now",
        "trending",
    ]
    simple_greetings = [
        "こんにちは",
        "おはよう",
        "こんばんは",
        "やあ",
        "よろしく",
        "ありがとう",
        "おやすみ",
        "バイバイ",
        "さようなら",
        "hello",
        "hi",
        "hey",
        "thanks",
        "good morning",
        "good night",
        "bye",
    ]
    code_keywords = [
        "コード",
        "プログラム",
        "スクリプト",
        "実装",
        "アルゴリズム",
        "関数",
        "クラス",
        "バグ",
        "エラー",
        "デバッグ",
        "リファクタ",
        "code",
        "program",
        "script",
        "implement",
        "algorithm",
        "function",
        "class",
        "bug",
        "error",
        "debug",
        "refactor",
        "python",
        "javascript",
    ]
    simple_responses = [
        "ok",
        "わかった",
        "うん",
        "そうだね",
        "なるほど",
        "いいね",
        "yes",
        "no",
        "yeah",
        "sure",
        "got it",
    ]
    time_responses = ["計って", "計測して", "タイマー", "測って", "たったら", "終わったら"]

    if any(kw in prompt_lower for kw in time_responses):
        return None
    if len(prompt) <= 20 and any(p in prompt_lower for p in simple_greetings):
        return {"level": "low", "search": False, "minutes": 0, "task": "null"}
    if len(prompt) <= 15 and any(p in prompt_lower for p in simple_responses):
        return {"level": "low", "search": False, "minutes": 0, "task": "null"}
    if any(kw in prompt_lower for kw in code_keywords):
        return {"level": "high", "search": False, "minutes": 0, "task": "null"}
    if any(kw in prompt_lower for kw in search_required_keywords):
        return {"level": "high", "search": True, "minutes": 0, "task": "null"}
    return None


async def determine_level_and_search(
    prompt: str,
    channel_id: int,
    has_attachments: bool = False,
    get_recent_history_func=None,
    character_name: str = "Bot",
) -> dict:
    rule_result = determine_level_and_search_rule_based(prompt)
    if rule_result is not None:
        return {**rule_result, "reference": False}

    step_start = time.time()
    history = []
    if get_recent_history_func:
        history = get_recent_history_func(channel_id, limit=4)
    print(f"[GEMINI] [TIMING] ルーター用履歴取得: {time.time() - step_start:.2f}秒")

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
## Judgment 4: Reference Necessity
- **true**: The message refers to previous turns using pronouns or implicit references. (e.g., "Why?", "Explain it more", "Fix that code", "What about him?", "I see")
- **false**: The message is self-contained and can be understood without any history. (e.g., "Hello", "How is the weather?", "Write a Python code for a calculator")
## Conversation History
{history_text if history_text else "(None)"}

## User Input
{prompt if prompt else "(No text, file attached)"}
{"*File attached" if has_attachments else ""}

## Output Format (strict)
level:low/medium/high,search:true/false,minutes:int,task:str,reference:true/false

Example: level:high,search:false,minutes:10,task:meeting,reference:true
Example: level:medium,search:true,minutes:0,task:null,reference:false"""

    try:
        step_start = time.time()
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model="gemini-3.1-flash-lite-preview",
            contents=router_prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                max_output_tokens=30,
                temperature=0.1,
            ),
        )
        print(f"[GEMINI] [TIMING] ルーターAPI呼び出し: {time.time() - step_start:.2f}秒")

        result = response.text.strip().lower()
        level, search, minutes, task, reference = "medium", False, 0, "null", False

        if "level:" in result:
            level = result.split("level:")[1].split(",")[0].strip()
        if "search:" in result:
            search = result.split("search:")[1].split(",")[0].strip() == "true"
        if "minutes:" in result:
            try:
                minutes = float(result.split("minutes:")[1].split(",")[0].strip())
            except:
                minutes = 0
        if "task:" in result:
            task = result.split("task:")[1].split(",")[0].strip()
        if "reference:" in result:
            reference = result.split("reference:")[1].split(",")[0].strip() == "true"

        return {
            "level": level,
            "search": search,
            "minutes": minutes,
            "task": task,
            "reference": reference,
        }
    except Exception as e:
        print(f"[API] Err: {type(e).__name__}")
        return {
            "level": "medium",
            "search": False,
            "minutes": 0,
            "task": "null",
            "reference": False,
        }
