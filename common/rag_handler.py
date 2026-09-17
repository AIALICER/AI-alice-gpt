"""
テキスト会話向け埋め込み RAG（OpenAI embeddings）

- chat_history のテキスト行を埋め込み保存（VC ログは除外）
- チャンネル / ユーザーを横断して類似検索し、プロンプトへ注入する
"""

from __future__ import annotations

import math
import re
import sqlite3
import struct
import threading
import time
from typing import Any

from .config_base import (
    OPENAI_EMBEDDING_MODEL,
    gpt_client,
    gpt_client_fallback,
)

EMBEDDING_DIM = 768
RAG_TOP_K = 5
RAG_MIN_SCORE = 0.45
RAG_MAX_CONTENT_CHARS = 500
BACKFILL_BATCH = 8

_MIN_EMBED_INTERVAL_SEC = 0.4
_EMBED_MAX_RETRIES = 4
_EMBED_BACKOFF_BASE_SEC = 5.0

_VC_PREFIX_RE = re.compile(r"^\[VC(音声|テキスト)")
_embed_lock = threading.Lock()
_last_embed_at = 0.0
_quota_cooldown_until = 0.0


def is_indexable_text(content: str | None) -> bool:
    """埋め込み対象のテキストか（VC・空・極短は除外）。"""
    if not content:
        return False
    text = content.strip()
    if len(text) < 4:
        return False
    if _VC_PREFIX_RE.match(text):
        return False
    return True


def pack_embedding(values: list[float]) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


def unpack_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _is_quota_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return (
        "429" in s
        or "resource_exhausted" in s
        or "quota exceeded" in s
        or "rate limit" in s
    )


def _wait_for_embed_slot() -> None:
    global _last_embed_at
    now = time.monotonic()
    if _quota_cooldown_until > now:
        wait = _quota_cooldown_until - now
        print(f"[RAG] embed cooldown {wait:.1f}s (quota)")
        time.sleep(wait)
        now = time.monotonic()
    elapsed = now - _last_embed_at
    if elapsed < _MIN_EMBED_INTERVAL_SEC:
        time.sleep(_MIN_EMBED_INTERVAL_SEC - elapsed)


def embed_text(text: str, *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """OpenAI embeddings で単一テキストを埋め込む。"""
    global _last_embed_at, _quota_cooldown_until
    _ = task_type  # OpenAI では task_type 不要（互換のため残す）

    clients = [c for c in (gpt_client, gpt_client_fallback) if c is not None]
    if not clients:
        raise RuntimeError("No OpenAI client configured for embeddings")

    last_error: Exception | None = None
    with _embed_lock:
        for client in clients:
            for attempt in range(_EMBED_MAX_RETRIES):
                try:
                    _wait_for_embed_slot()
                    response = client.embeddings.create(
                        model=OPENAI_EMBEDDING_MODEL,
                        input=text,
                        dimensions=EMBEDDING_DIM,
                    )
                    _last_embed_at = time.monotonic()
                    return list(response.data[0].embedding)
                except Exception as exc:
                    last_error = exc
                    _last_embed_at = time.monotonic()
                    if _is_quota_error(exc):
                        backoff = min(_EMBED_BACKOFF_BASE_SEC * (2**attempt), 60.0)
                        _quota_cooldown_until = time.monotonic() + backoff
                        print(
                            f"[RAG] embed 429/quota "
                            f"(attempt {attempt + 1}/{_EMBED_MAX_RETRIES}), "
                            f"wait {backoff:.0f}s"
                        )
                        if attempt + 1 < _EMBED_MAX_RETRIES:
                            time.sleep(backoff)
                            continue
                        break
                    break

    raise RuntimeError(f"embed_text failed: {last_error}")


def index_history_row(
    db_path: str,
    *,
    history_id: int,
    channel_id: int,
    role: str,
    content: str,
    author_name: str | None = None,
    user_id: int | None = None,
) -> bool:
    """1件の chat_history を埋め込み索引へ追加。成功で True。"""
    if not is_indexable_text(content):
        return False

    clipped = content.strip()
    if len(clipped) > RAG_MAX_CONTENT_CHARS:
        clipped = clipped[:RAG_MAX_CONTENT_CHARS]

    try:
        vector = embed_text(clipped, task_type="RETRIEVAL_DOCUMENT")
    except Exception as exc:
        if _is_quota_error(exc) or "embed_text failed" in str(exc):
            print(f"[RAG] index skip history_id={history_id}: {exc}")
            return False
        raise
    blob = pack_embedding(vector)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_embeddings (
                history_id, channel_id, user_id, role, author_name,
                content, embedding, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(history_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                user_id = excluded.user_id,
                role = excluded.role,
                author_name = excluded.author_name,
                content = excluded.content,
                embedding = excluded.embedding,
                model = excluded.model
            """,
            (
                history_id,
                channel_id,
                user_id,
                role,
                author_name,
                clipped,
                blob,
                OPENAI_EMBEDDING_MODEL,
            ),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def search_related(
    db_path: str,
    query: str,
    *,
    top_k: int = RAG_TOP_K,
    min_score: float = RAG_MIN_SCORE,
    exclude_history_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """チャンネル・ユーザー横断で類似ログを取得する。"""
    if not is_indexable_text(query):
        return []

    try:
        query_vec = embed_text(
            query.strip()[:RAG_MAX_CONTENT_CHARS], task_type="RETRIEVAL_QUERY"
        )
    except Exception as exc:
        print(f"[RAG] search skipped (embed failed): {exc}")
        return []
    exclude = exclude_history_ids or set()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT history_id, channel_id, user_id, role, author_name, content, embedding
            FROM chat_embeddings
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    scored: list[dict[str, Any]] = []
    for row in rows:
        hid = row["history_id"]
        if hid is not None and hid in exclude:
            continue
        content = row["content"] or ""
        if content.strip() == query.strip():
            continue
        score = cosine_similarity(query_vec, unpack_embedding(row["embedding"]))
        if score < min_score:
            continue
        scored.append(
            {
                "history_id": hid,
                "channel_id": row["channel_id"],
                "user_id": row["user_id"],
                "role": row["role"],
                "author_name": row["author_name"],
                "content": content,
                "score": score,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def format_rag_context(hits: list[dict[str, Any]]) -> str:
    """system_instruction に足す用の短いブロック。"""
    if not hits:
        return ""
    lines = [
        "[Related Past Logs — semantic search across channels/users]",
        "Use only if relevant. Do not invent details that are not here.",
    ]
    for hit in hits:
        who = hit.get("author_name") or hit.get("role") or "unknown"
        ch = hit.get("channel_id")
        score = hit.get("score", 0.0)
        text = (hit.get("content") or "").replace("\n", " ").strip()
        lines.append(f"- ch={ch} by={who} score={score:.2f}: {text}")
    return "\n".join(lines)


def backfill_missing_embeddings(db_path: str, *, limit: int = BACKFILL_BATCH) -> int:
    """未索引のテキスト履歴を最大 limit 件埋め込む。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT h.id, h.channel_id, h.role, h.content, h.author_name, h.user_id
            FROM chat_history h
            LEFT JOIN chat_embeddings e ON e.history_id = h.id
            WHERE e.id IS NULL
            ORDER BY h.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    indexed = 0
    for row in rows:
        content = row["content"] or ""
        if not is_indexable_text(content):
            continue
        try:
            ok = index_history_row(
                db_path,
                history_id=int(row["id"]),
                channel_id=int(row["channel_id"]),
                role=row["role"] or "user",
                content=content,
                author_name=row["author_name"],
                user_id=row["user_id"],
            )
            if ok:
                indexed += 1
            else:
                break
        except Exception as exc:
            print(f"[RAG] backfill skip id={row['id']}: {exc}")
            break
    return indexed
