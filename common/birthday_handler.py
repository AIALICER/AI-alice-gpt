"""
誕生日機能モジュール

- ユーザーの誕生日登録・取得
- ブルアカキャラクターの誕生日スクレイピング・取得
- 当日の誕生日チェック（ユーザー / キャラ）
"""

import sqlite3
import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))

# ブルアカキャラ誕生日スクレイピング対象
BIRTHDAY_LIST_URL = "https://bluearchive.wikiru.jp/?誕生日一覧"
# ブルアカキャラ誕生日用DBパス（全Bot共有）
BA_BIRTHDAY_DB_PATH = "data/bluearchive_birthdays.db"


# =========================================================
# DBセットアップ
# =========================================================

def init_birthday_db() -> None:
    """ブルアカ誕生日専用DBを初期化"""
    conn = sqlite3.connect(BA_BIRTHDAY_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bluearchive_birthdays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        birthday_month INTEGER,
        birthday_day INTEGER,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()


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
    cursor.execute('''
    UPDATE users SET birthday = ? WHERE user_id = ?
    ''', (birthday_str, user_id))
    conn.commit()
    conn.close()


def get_user_birthday(db_path: str, user_id: int) -> Optional[str]:
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
    cursor.execute('''
    SELECT user_id, display_name FROM users
    WHERE birthday = ?
    ''', (today_str,))
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
    cursor.execute('''
    SELECT user_id, display_name, birthday FROM users
    WHERE birthday IS NOT NULL
    ORDER BY birthday
    ''')
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "user_id": row["user_id"],
            "display_name": row["display_name"],
            "birthday": row["birthday"]
        }
        for row in rows
    ]


# =========================================================
# ブルアカキャラ誕生日の管理
# =========================================================

def scrape_bluearchive_birthdays() -> list[dict]:
    """
    bluearchive.wikiru.jp の誕生日一覧ページをスクレイピングする。

    Returns:
        list[dict]: [{"name": str, "month": int, "day": int}, ...]
        失敗時は空リスト
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    results = []

    try:
        res = requests.get(BIRTHDAY_LIST_URL, headers=headers, timeout=15)
        res.encoding = res.apparent_encoding
        print(f"[birthday_handler] スクレイピング HTTP {res.status_code}: {BIRTHDAY_LIST_URL}")

        soup = BeautifulSoup(res.text, "html.parser")

        # wikiru.jp のページ構造: テーブルの各行に「キャラ名」「誕生日」が含まれる
        # 誕生日は「○月○日」形式
        birthday_pattern = re.compile(r'(\d{1,2})月(\d{1,2})日')

        tables = soup.select("table")
        for table in tables:
            rows = table.select("tr")
            for row in rows:
                cells = row.select("td, th")
                if len(cells) < 2:
                    continue
                for i, cell in enumerate(cells):
                    match = birthday_pattern.search(cell.get_text())
                    if match:
                        month = int(match.group(1))
                        day = int(match.group(2))
                        # 名前は前後のセル（通常は前のセル）から探す
                        # 名前セルを探す（リンクあり優先）
                        name = None
                        # 同じ行の他のセルからキャラ名を取得
                        for j, other_cell in enumerate(cells):
                            if j == i:
                                continue
                            link = other_cell.find("a")
                            if link:
                                candidate = link.get_text(strip=True)
                            else:
                                candidate = other_cell.get_text(strip=True)
                            # 数字のみや空は除外
                            if candidate and not re.fullmatch(r'[\d\s月日★☆:：/\-]+', candidate):
                                name = candidate
                                break
                        if name and 1 <= month <= 12 and 1 <= day <= 31:
                            results.append({"name": name, "month": month, "day": day})
                        break  # 1行に誕生日は1つ

        print(f"[birthday_handler] スクレイピング完了: {len(results)} 件取得")
        return results

    except Exception as e:
        print(f"[birthday_handler] スクレイピングエラー: {e}")
        return []


def upsert_character_birthdays(characters: list[dict]) -> int:
    """
    スクレイピングしたキャラ誕生日データを一括でDBにupsertする。

    Args:
        characters: [{"name": str, "month": int, "day": int}, ...]

    Returns:
        int: upsertした件数
    """
    conn = sqlite3.connect(BA_BIRTHDAY_DB_PATH)
    cursor = conn.cursor()
    count = 0
    for c in characters:
        try:
            cursor.execute('''
            INSERT INTO bluearchive_birthdays (name, birthday_month, birthday_day, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name)
            DO UPDATE SET
                birthday_month = excluded.birthday_month,
                birthday_day   = excluded.birthday_day,
                updated_at     = excluded.updated_at
            ''', (c["name"], c["month"], c["day"]))
            count += 1
        except Exception as e:
            print(f"[birthday_handler] upsertエラー ({c['name']}): {e}")
    conn.commit()
    conn.close()
    return count


def get_character_birthday(name: str) -> Optional[dict]:
    """
    キャラ名（部分一致）で誕生日を検索する。

    Args:
        name: 検索するキャラ名

    Returns:
        dict: {"name": str, "month": int, "day": int} or None
    """
    conn = sqlite3.connect(BA_BIRTHDAY_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT name, birthday_month, birthday_day
    FROM bluearchive_birthdays
    WHERE name LIKE ?
    ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END
    LIMIT 1
    ''', (f"%{name}%", name))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"name": row["name"], "month": row["birthday_month"], "day": row["birthday_day"]}
    return None


def get_today_character_birthdays() -> list[dict]:
    """
    今日が誕生日のブルアカキャラ一覧を返す。

    Returns:
        list[dict]: [{"name": str, "month": int, "day": int}, ...]
    """
    today = datetime.now(JST)

    conn = sqlite3.connect(BA_BIRTHDAY_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT name, birthday_month, birthday_day
    FROM bluearchive_birthdays
    WHERE birthday_month = ? AND birthday_day = ?
    ORDER BY name
    ''', (today.month, today.day))
    rows = cursor.fetchall()
    conn.close()

    return [{"name": row["name"], "month": row["birthday_month"], "day": row["birthday_day"]} for row in rows]


def get_all_character_birthdays() -> list[dict]:
    """
    全ブルアカキャラの誕生日一覧を返す（月日順）

    Returns:
        list[dict]: [{"name": str, "month": int, "day": int}, ...]
    """
    conn = sqlite3.connect(BA_BIRTHDAY_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT name, birthday_month, birthday_day
    FROM bluearchive_birthdays
    ORDER BY birthday_month, birthday_day, name
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [{"name": row["name"], "month": row["birthday_month"], "day": row["birthday_day"]} for row in rows]


def count_character_birthdays() -> int:
    """登録済みブルアカキャラ誕生日の件数を返す"""
    conn = sqlite3.connect(BA_BIRTHDAY_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bluearchive_birthdays")
    count = cursor.fetchone()[0]
    conn.close()
    return count


# =========================================================
# 非同期ラッパー（bot_base.pyから呼び出し用）
# =========================================================

async def async_scrape_and_update() -> int:
    """
    非同期でスクレイピング → DB更新を実行する。
    ブロッキング処理をスレッドプールで実行。

    Returns:
        int: 更新したキャラ数
    """
    loop = asyncio.get_running_loop()
    characters = await loop.run_in_executor(None, scrape_bluearchive_birthdays)
    if not characters:
        return 0
    count = await loop.run_in_executor(None, upsert_character_birthdays, characters)
    return count
