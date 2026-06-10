"""
Character Creator / Bot Manager 用の Gemini クライアント（タイムアウト付き）。
"""

from __future__ import annotations

import httpx
from google import genai
from google.genai import types

# messages.py 生成は軽量・高速モデル（会話 Bot の MAIN とは別）
DEFAULT_MESSAGES_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT_SEC = 120.0


def create_messages_gemini_client(
    api_key: str,
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> genai.Client:
    """長時間ハングしないよう HTTP タイムアウトとリトライ上限を設定する。"""
    timeout = httpx.Timeout(
        timeout_sec,
        connect=min(30.0, timeout_sec),
        read=timeout_sec,
        write=60.0,
        pool=30.0,
    )
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            httpxClient=httpx.Client(timeout=timeout),
            retryOptions=types.HttpRetryOptions(
                attempts=1,
                initialDelay=1.0,
                maxDelay=5.0,
                expBase=2.0,
                jitter=0.1,
                httpStatusCodes=[429, 500, 503],
            ),
        ),
    )
