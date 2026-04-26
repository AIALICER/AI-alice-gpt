import asyncio
import time
from dataclasses import dataclass
from typing import Any

from .config_base import (
    OPENAI_FALLBACK_MODEL,
    OPENAI_MODEL,
    gpt_async_client,
    gpt_async_client_fallback,
)


@dataclass
class GPTResponse:
    text: str


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


async def _create_response_text(client: Any, model_name: str, contents: list, config: dict) -> str:
    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "input": contents,
    }
    if config.get("system_instruction"):
        request_kwargs["instructions"] = config["system_instruction"]
    if config.get("tools"):
        request_kwargs["tools"] = config["tools"]
    if config.get("temperature") is not None:
        request_kwargs["temperature"] = config["temperature"]
    if config.get("max_output_tokens") is not None:
        request_kwargs["max_output_tokens"] = config["max_output_tokens"]

    response = await client.responses.create(**request_kwargs)
    return (response.output_text or "").strip()


async def generate_content_with_fallback(client, primary_model: str, contents, config):
    """レート制限/タイムアウト時に自動フォールバックしてGPT応答を返す。"""
    execution_plan = [
        (gpt_async_client, OPENAI_MODEL),
        (gpt_async_client, OPENAI_FALLBACK_MODEL),
    ]
    if gpt_async_client_fallback:
        execution_plan.extend(
            [
                (gpt_async_client_fallback, OPENAI_MODEL),
                (gpt_async_client_fallback, OPENAI_FALLBACK_MODEL),
            ]
        )

    last_exception = None
    for target_client, model_name in execution_plan:
        try:
            client_label = "API_1" if target_client == gpt_async_client else "API_2"
            print(f"[GPT API] Trying {client_label} with model: {model_name}")
            text = await _create_response_text(target_client, model_name, contents, config)
            return GPTResponse(text=text)
        except Exception as e:
            error_str = str(e)
            print(f"[X] {model_name} ({client_label}) failed: {type(e).__name__}")
            last_exception = e
            is_retryable = (
                isinstance(e, TimeoutError)
                or "429" in error_str
                or "503" in error_str
                or "UNAVAILABLE" in error_str
                or "overloaded" in error_str.lower()
                or _is_timeout_error(error_str)
            )
            if is_retryable:
                if "503" in error_str or "UNAVAILABLE" in error_str:
                    await asyncio.sleep(2)
                else:
                    await asyncio.sleep(1)
                continue
            raise e
    raise last_exception or Exception("All models and keys failed.")


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
        print(f"[GPT] [TIMING] ルーター用履歴取得: {time.time() - step_start:.2f}秒")

    history_text = ""
    if history:
        history_lines = []
        for msg in history:
            role = "User" if msg["role"] == "user" else character_name
            text = msg.get("content", "")
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
        response = await generate_content_with_fallback(
            client=gpt_async_client,
            primary_model=OPENAI_MODEL,
            contents=[{"role": "user", "content": router_prompt}],
            config={"max_output_tokens": 60, "temperature": 0.1},
        )
        print(f"[GPT] [TIMING] ルーターAPI呼び出し: {time.time() - step_start:.2f}秒")

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
