"""
Blue Archive キャラクターデータベースモジュール

SchaleDBからキャラクター情報を取得・保存・管理する。
- 名前、誕生日、レアリティ、所属学校、部活、身長、趣味など
"""

import sqlite3
import asyncio
import re
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests

JST = timezone(timedelta(hours=9))
SCHALEDB_URL = "https://raw.githubusercontent.com/SchaleDB/SchaleDB/main/data/jp/students.json"
LOCALIZATION_URL = "https://raw.githubusercontent.com/SchaleDB/SchaleDB/main/data/jp/localization.json"
DB_PATH = "data/ba_characters.db"

# 翻訳マップ
SCHOOL_TRANSLATION = {}
SCHOOL_LONG_TRANSLATION = {}
CLUB_TRANSLATION = {}

def load_school_translations():
    """学校名・部活名の翻訳データを読み込む"""
    global SCHOOL_TRANSLATION, SCHOOL_LONG_TRANSLATION, CLUB_TRANSLATION
    try:
        res = requests.get(LOCALIZATION_URL, timeout=10)
        data = res.json()
        SCHOOL_TRANSLATION = data.get("School", {})
        SCHOOL_LONG_TRANSLATION = data.get("SchoolLong", {})
        CLUB_TRANSLATION = data.get("Club", {})
        print(f"[character_handler] 翻訳データ読み込み完了: 学校={len(SCHOOL_TRANSLATION)}件, 部活={len(CLUB_TRANSLATION)}件")
    except Exception as e:
        print(f"[character_handler] 翻訳データ読み込みエラー: {e}")

def get_school_name_japanese(school_code: str, long_name: bool = False) -> str:
    """
    学校コードから日本語の学校名を取得

    Args:
        school_code: 学校コード (例: "Gehenna", "Trinity")
        long_name: trueなら正式名称、falseなら略称

    Returns:
        日本語の学校名
    """
    if not SCHOOL_TRANSLATION:
        load_school_translations()

    if long_name:
        return SCHOOL_LONG_TRANSLATION.get(school_code, school_code)
    else:
        return SCHOOL_TRANSLATION.get(school_code, school_code)

def get_club_name_japanese(club_code: str) -> str:
    """
    部活コードから日本語の部活名を取得

    Args:
        club_code: 部活コード (例: "Kohshinjo68", "GourmetClub")

    Returns:
        日本語の部活名
    """
    if not CLUB_TRANSLATION:
        load_school_translations()
    
    return CLUB_TRANSLATION.get(club_code, club_code)


# =========================================================
# DBセットアップ
# =========================================================

def init_db() -> None:
    """キャラクターデータベースを初期化"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        name_kana TEXT,
        birthday_month INTEGER,
        birthday_day INTEGER,
        rarity INTEGER,
        school TEXT,
        school_jp TEXT,
        club TEXT,
        club_jp TEXT,
        height TEXT,
        hobby TEXT,
        path_name TEXT,
        is_released INTEGER DEFAULT 1,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()


# =========================================================
# SchaleDBからデータ取得
# =========================================================

def scrape_characters() -> list[dict]:
    """SchaleDB からキャラクター情報を取得する"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    results = []

    try:
        res = requests.get(SCHALEDB_URL, headers=headers, timeout=30)
        res.encoding = "utf-8"
        print(f"[character_handler] SchaleDB取得 HTTP {res.status_code}")

        # 翻訳データも取得
        load_school_translations()

        students = res.json()
        birthday_pattern = re.compile(r'(\d{1,2})月(\d{1,2})日')

        for student in students:
            name = student.get("Name", "")
            if not name:
                continue

            birthday_str = student.get("Birthday", "")
            birthday_month = None
            birthday_day = None
            if birthday_str:
                match = birthday_pattern.search(birthday_str)
                if match:
                    birthday_month = int(match.group(1))
                    birthday_day = int(match.group(2))

            school_code = student.get("School", "")
            club_code = student.get("Club", "")

            results.append({
                "name": name,
                "name_kana": student.get("PersonalNameRuby", ""),
                "birthday_month": birthday_month,
                "birthday_day": birthday_day,
                "rarity": student.get("StarGrade", 0),
                "school": school_code,
                "school_jp": get_school_name_japanese(school_code, False),
                "club": club_code,
                "club_jp": get_club_name_japanese(club_code),
                "height": student.get("CharHeightMetric", ""),
                "hobby": student.get("Hobby", ""),
                "path_name": student.get("PathName", ""),
                "is_released": 1 if all(student.get("IsReleased", [False])) else 0
            })

        print(f"[character_handler] 取得完了: {len(results)} 件")
        return results

    except Exception as e:
        print(f"[character_handler] 取得エラー: {e}")
        return []


def update_characters(characters: list[dict]) -> int:
    """キャラクター情報をDBにupsertする"""
    if not characters:
        return 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    count = 0

    for c in characters:
        try:
            cursor.execute('''
            INSERT INTO characters (
                name, name_kana, birthday_month, birthday_day,
                rarity, school, school_jp, club, club_jp,
                height, hobby, path_name, is_released, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name)
            DO UPDATE SET
                name_kana = excluded.name_kana,
                birthday_month = excluded.birthday_month,
                birthday_day = excluded.birthday_day,
                rarity = excluded.rarity,
                school = excluded.school,
                school_jp = excluded.school_jp,
                club = excluded.club,
                club_jp = excluded.club_jp,
                height = excluded.height,
                hobby = excluded.hobby,
                path_name = excluded.path_name,
                is_released = excluded.is_released,
                updated_at = excluded.updated_at
            ''', (
                c["name"], c["name_kana"], c["birthday_month"], c["birthday_day"],
                c["rarity"], c["school"], c["school_jp"], c["club"], c["club_jp"],
                c["height"], c["hobby"], c["path_name"], c["is_released"]
            ))
            count += 1
        except Exception as e:
            print(f"[character_handler] upsertエラー ({c.get('name', 'unknown')}): {e}")

    conn.commit()
    conn.close()
    return count


# =========================================================
# キャラクター検索
# =========================================================

def get_character(name: str) -> Optional[dict]:
    """キャラ名（部分一致）で検索"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM characters
    WHERE name LIKE ? OR path_name LIKE ?
    ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END
    LIMIT 1
    ''', (f"%{name}%", f"%{name}%", name))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_characters_by_school(school: str) -> list[dict]:
    """指定した学校のキャラクター一覧を取得（日本語/英語両対応）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM characters
    WHERE school = ? OR school_jp LIKE ? OR school LIKE ?
    ORDER BY name
    ''', (school, f"%{school}%", f"%{school}%"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_characters() -> list[dict]:
    """全キャラクター一覧を取得"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM characters ORDER BY rarity DESC, name')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_school_list() -> list[dict]:
    """登録されている学校一覧を取得"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT school, school_jp, COUNT(*) as count
    FROM characters
    WHERE school != ''
    GROUP BY school, school_jp
    ORDER BY count DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# =========================================================
# 非同期ラッパー
# =========================================================

async def async_update() -> int:
    """非同期でデータ更新"""
    loop = asyncio.get_running_loop()
    characters = await loop.run_in_executor(None, scrape_characters)
    if not characters:
        return 0
    count = await loop.run_in_executor(None, update_characters, characters)
    return count


# =========================================================
# 互換性のため（旧birthday_handler用）
# =========================================================

def scrape_bluearchive_birthdays() -> list[dict]:
    """旧birthday_handler互換: 誕生日データのみを取得"""
    characters = scrape_characters()
    results = []
    for c in characters:
        if c["birthday_month"] and c["birthday_day"]:
            results.append({
                "name": c["name"],
                "month": c["birthday_month"],
                "day": c["birthday_day"]
            })
    return results


def upsert_character_birthdays(characters: list[dict]) -> int:
    """旧birthday_handler互換: 全データ更新を使用"""
    all_characters = scrape_characters()
    return update_characters(all_characters)


async def async_scrape_and_update() -> int:
    """旧birthday_handler互換"""
    return await async_update()


def init_birthday_db() -> None:
    """旧birthday_handler互換"""
    init_db()


def count_character_birthdays() -> int:
    """旧birthday_handler互換"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM characters")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_character_birthday(name: str) -> Optional[dict]:
    """旧birthday_handler互換"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT name, birthday_month, birthday_day FROM characters
    WHERE name LIKE ? AND birthday_month IS NOT NULL
    ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END LIMIT 1
    ''', (f"%{name}%", name))
    row = cursor.fetchone()
    conn.close()
    if row and row["birthday_month"]:
        return {"name": row["name"], "month": row["birthday_month"], "day": row["birthday_day"]}
    return None


def get_today_character_birthdays() -> list[dict]:
    """旧birthday_handler互換"""
    today = datetime.now(JST)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT name, birthday_month, birthday_day FROM characters
    WHERE birthday_month = ? AND birthday_day = ?
    ORDER BY name
    ''', (today.month, today.day))
    rows = cursor.fetchall()
    conn.close()
    return [{"name": r["name"], "month": r["birthday_month"], "day": r["birthday_day"]} for r in rows]



