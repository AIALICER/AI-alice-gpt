"""
データベース処理モジュール

- 履歴の取得・保存
- 記憶（要約）の管理
- 履歴の要約・クリーンアップ
"""

import asyncio
import sqlite3

from .config_base import gemini_client


def get_recent_history(db_path: str, channel_id: int, limit: int = 6) -> list:
    """
    指定チャンネルの直近の履歴を取得

    Args:
        db_path: データベースファイルのパス
        channel_id: チャンネルID
        limit: 取得する履歴の件数

    Returns:
        list: Gemini API形式の履歴リスト
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 最新のメッセージを古い順（会話の流れ通り）に取得
    cursor.execute(
        """
    SELECT role, content FROM (
        SELECT role, content, timestamp FROM chat_history
        WHERE channel_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ) ORDER BY timestamp ASC
    """,
        (channel_id, limit),
    )

    rows = cursor.fetchall()
    conn.close()

    # Gemini APIが受け取れる辞書リストに変換
    history = []
    for row in rows:
        history.append({"role": row["role"], "parts": [{"text": row["content"]}]})
    return history


def save_message(db_path: str, channel_id: int, role: str, content: str) -> None:
    """
    メッセージを履歴に保存

    Args:
        db_path: データベースファイルのパス
        channel_id: チャンネルID
        role: 'user' または 'model'
        content: メッセージ内容
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
    INSERT INTO chat_history (channel_id, role, content)
    VALUES (?, ?, ?)
    """,
        (channel_id, role, content),
    )

    conn.commit()
    conn.close()


def get_memories(db_path: str, channel_id: int) -> str:
    """
    指定チャンネルの記憶（要約）を取得

    Args:
        db_path: データベースファイルのパス
        channel_id: チャンネルID

    Returns:
        str: 記憶の内容（なければデフォルトメッセージ）
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT content
    FROM chat_memories
    WHERE channel_id = ?
    ORDER BY timestamp ASC
    """,
        (channel_id,),
    )

    old_memory_row = cursor.fetchone()
    memory = old_memory_row[0] if old_memory_row else "No memories yet."
    conn.close()
    return memory


def clear_db_history(db_path: str, channel_id: int) -> bool:
    """
    指定チャンネルの履歴をデータベースから削除

    Args:
        db_path: データベースファイルのパス
        channel_id: チャンネルID

    Returns:
        bool: 成功した場合True
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_history WHERE channel_id = ?", (channel_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"History delete error: {e}")
        return False


async def generate_summary(old_memory: str, new_chat: list) -> str:
    """
    会話履歴を要約して記憶を更新

    Args:
        old_memory: 既存の記憶
        new_chat: 新しい会話履歴

    Returns:
        str: 要約されたテキスト
    """
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
        summary_response = await gemini_client.aio.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        return f" [Log summary: {summary_response.text.strip()}]"
    except Exception as e:
        print(f"Summary generation error: {e}")
        return " [Summary failed]"


async def summarize_and_cleanup(db_path: str, channel_id: int) -> None:
    """
    10分放置されたら履歴を要約してクリーンアップ

    Args:
        db_path: データベースファイルのパス
        channel_id: チャンネルID
    """
    await asyncio.sleep(600)  # 10分待機

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()

    try:
        # そのチャンネルのログを一括取得
        cursor.execute(
            """
        SELECT role, content
        FROM chat_history
        WHERE channel_id = ?
        ORDER BY timestamp ASC
        """,
            (channel_id,),
        )
        rows = cursor.fetchall()

        if not rows:
            return

        history = []
        for row in rows:
            history.append({"role": row["role"], "parts": [{"text": row["content"]}]})

        # 現在の「記憶」を取得
        cursor.execute(
            """
        SELECT content
        FROM chat_memories
        WHERE channel_id = ?
        ORDER BY timestamp DESC LIMIT 1
        """,
            (channel_id,),
        )
        old_memory_row = cursor.fetchone()
        old_memory = old_memory_row["content"] if old_memory_row else "No memories yet."

        # Geminiで要約
        new_summary = await generate_summary(old_memory, history)

        # 記憶テーブルを更新
        cursor.execute(
            """
        INSERT INTO chat_memories (channel_id, content, timestamp)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(channel_id)
        DO UPDATE SET
            content = excluded.content,
            timestamp = excluded.timestamp
        """,
            (channel_id, new_summary),
        )

        cursor.execute("DELETE FROM chat_history WHERE channel_id = ?", (channel_id,))

        db.commit()
        print(f"Channel {channel_id}: Summarized logs and cleaned up database.")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()


def upsert_user(db_path: str, user_id: int, display_name: str, account_name: str) -> None:
    """
    ユーザー情報を登録または更新（upsert）する

    ボットがメンションされた際に呼び出し、ユーザーIDをキーとして
    表示名・アカウント名・最終アクセス日時を最新状態に保つ。

    Args:
        db_path: データベースファイルのパス
        user_id: Discord ユーザーID（整数）
        display_name: サーバー上の表示名（ニックネーム等）
        account_name: Discord アカウント名
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
    INSERT INTO users (user_id, display_name, account_name, last_seen)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(user_id)
    DO UPDATE SET
        display_name = excluded.display_name,
        account_name = excluded.account_name,
        last_seen    = excluded.last_seen
    """,
        (user_id, display_name, account_name),
    )
    conn.commit()
    conn.close()


def get_user_mention(db_path: str, display_name: str) -> str | None:
    """
    表示名（display_name）からDiscordメンション文字列を返す

    一致するユーザーが見つかった場合は '<@ユーザーID>' 形式の文字列を返す。
    見つからない場合は None を返す。

    Args:
        db_path: データベースファイルのパス
        display_name: 検索する表示名（部分一致）

    Returns:
        Optional[str]: '<@ユーザーID>' 形式、または None
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT user_id FROM users
    WHERE display_name LIKE ?
    ORDER BY last_seen DESC
    LIMIT 1
    """,
        (f"%{display_name}%",),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return f"<@{row['user_id']}>"
    return None


def get_all_users_info(db_path: str) -> str:
    """
    登録済み全ユーザーの情報をシステムインストラクション用テキストで返す

    Gemini に「誰をどうメンションするか」を伝えるために使用する。
    ユーザーが一人も登録されていない場合は空文字列を返す。

    Args:
        db_path: データベースファイルのパス

    Returns:
        str: '[Known Users]\\nDisplay Name: 〇〇 | Mention: <@ID>\\n...' 形式のテキスト
             登録ユーザーがいない場合は空文字列
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
    SELECT user_id, display_name, account_name
    FROM users
    ORDER BY last_seen DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return ""

    lines = [
        "[Known Users]",
        "# 以下のユーザーをメンションする際は Mention 列の文字列をそのまま使用すること",
    ]
    for row in rows:
        lines.append(
            f"Display Name: {row['display_name']} | "
            f"Account Name: {row['account_name']} | "
            f"Mention: <@{row['user_id']}>"
        )
    return "\n".join(lines)
