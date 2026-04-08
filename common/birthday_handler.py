"""
ユーザー誕生日管理モジュール

- ユーザーの誕生日登録・取得
- 当日の誕生日チェック（ユーザー）
"""

import sqlite3
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


# =========================================================
# ユーザー誕生日の登録・取得
# =========================================================


def set_user_birthday(db_path: str, user_id: int, month: int, day: int) -> None:
    """
    ユーザーの誕生日をDBに登録（MM-DD形式）

    Args:
        db_path: データベースファイルのパス
        user_id: Discord ユーザーID
        month: 月（1〜12）
        day: 日（1〜31）
    """
    birthday_str = f"{month:02d}-{day:02d}"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
    UPDATE users SET birthday = ? WHERE user_id = ?
    """,
        (birthday_str, user_id),
    )
    conn.commit()
    conn.close()


def get_user_birthday(db_path: str, user_id: int) -> str | None:
    """
    指定ユーザーの誕生日文字列（MM-DD）を返す。未登録の場合はNone。
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT birthday FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row["birthday"]:
        return row["birthday"]
    return None


def get_today_user_birthdays(db_path: str) -> list[dict]:
    """
    今日が誕生日のユーザー一覧を返す。

    Returns:
        list[dict]: [{"user_id": int, "display_name": str}, ...]
    """
    today = datetime.now(JST)
    today_str = f"{today.month:02d}-{today.day:02d}"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT user_id, display_name FROM users
    WHERE birthday = ?
    """,
        (today_str,),
    )
    rows = cursor.fetchall()
    conn.close()

    return [{"user_id": row["user_id"], "display_name": row["display_name"]} for row in rows]


def get_all_user_birthdays(db_path: str) -> list[dict]:
    """
    DBに登録されている全ユーザーの誕生日を取得する。

    Args:
        db_path: ユーザーデータベースのパス

    Returns:
        list[dict]: [{"user_id": int, "display_name": str, "birthday": "MM-DD"}, ...]
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
    SELECT user_id, display_name, birthday FROM users
    WHERE birthday IS NOT NULL
    ORDER BY birthday
    """)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "user_id": row["user_id"],
            "display_name": row["display_name"],
            "birthday": row["birthday"],
        }
        for row in rows
    ]
