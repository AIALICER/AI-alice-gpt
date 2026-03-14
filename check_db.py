#!/usr/bin/env python3
"""データベース確認スクリプト"""

import sqlite3
import sys
import requests
from datetime import datetime, timezone, timedelta

DB_PATH = "data/ba_characters.db"
JST = timezone(timedelta(hours=9))

# 学校名の翻訳データ
SCHOOL_TRANSLATION = {}

def load_school_translations():
    """学校名・部活名の翻訳データを読み込む"""
    global SCHOOL_TRANSLATION, CLUB_TRANSLATION
    try:
        res = requests.get(
            "https://raw.githubusercontent.com/SchaleDB/SchaleDB/main/data/jp/localization.json",
            timeout=10
        )
        data = res.json()
        SCHOOL_TRANSLATION = data.get("School", {})
        CLUB_TRANSLATION = data.get("Club", {})
    except Exception:
        pass

CLUB_TRANSLATION = {}

def get_school_japanese(school_code: str) -> str:
    """学校コードから日本語名を取得"""
    if not SCHOOL_TRANSLATION:
        load_school_translations()
    return SCHOOL_TRANSLATION.get(school_code, school_code)

def get_club_japanese(club_code: str) -> str:
    """部活コードから日本語名を取得"""
    global CLUB_TRANSLATION
    if not CLUB_TRANSLATION:
        load_school_translations()
    return CLUB_TRANSLATION.get(club_code, club_code)

def show_help():
    print("""
使用法: python check_db.py [コマンド]
コマンド:
  help          : このヘルプを表示
  info          : データベース情報
  count         : キャラクター数
  list          : 全キャラクター一覧
  sample [数]   : サンプル表示 (デフォルト: 10)
  birthday      : 今日の誕生日キャラ
  rarity [1-3]  : レアリティ別一覧
  school [名前] : 学校別一覧
  search [名前] : キャラ検索
  stats         : 統計情報
""")

def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"エラー: DB接続失敗 - {e}")
        sys.exit(1)

def show_info():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # テーブル情報
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("=== データベース情報 ===")
    print(f"DBファイル: {DB_PATH}")
    print(f"テーブル数: {len(tables)}")
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        print(f"\n【{table_name}】")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
    
    conn.close()

def show_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM characters")
    count = cursor.fetchone()[0]
    print(f"キャラクター数: {count}")
    conn.close()

def show_list():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, rarity, school_jp, school, birthday_month, birthday_day FROM characters ORDER BY rarity DESC, name")
    rows = cursor.fetchall()
    
    print("=== 全キャラクター一覧 ===")
    print(f"{'名前':<12} {'レア':<4} {'学校':<15} {'誕生日':<8}")
    print("-" * 50)
    for row in rows:
        birthday = f"{row[4]}月{row[5]}日" if row[4] and row[5] else "不明"
        print(f"{row[0]:<12} ★{row[1]}   {row[2]:<15} {birthday}")
    conn.close()

def show_sample(count=10):
    load_school_translations()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM characters ORDER BY rarity DESC, name LIMIT ?", (count,))
    rows = cursor.fetchall()
    
    print(f"=== サンプル {len(rows)}件 ===")
    for row in rows:
        print(f"\n【{row['name']}】")
        print(f"  レアリティ: ★{row['rarity']}")
        print(f"  学校: {row['school_jp']} ({row['school']})")
        print(f"  部活: {row['club_jp']} ({row['club']})")
        birthday = f"{row['birthday_month']}月{row['birthday_day']}日" if row['birthday_month'] else "不明"
        print(f"  誕生日: {birthday}")
        print(f"  身長: {row['height']}")
        print(f"  趣味: {row['hobby']}")
    conn.close()

def show_today_birthdays():
    today = datetime.now(JST)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, birthday_month, birthday_day, school_jp FROM characters WHERE birthday_month = ? AND birthday_day = ?",
        (today.month, today.day)
    )
    rows = cursor.fetchall()
    
    print(f"=== 今日({today.month}月{today.day}日)の誕生日 ===")
    if rows:
        for row in rows:
            print(f"  {row[0]}: {row[1]}月{row[2]}日 ({row[3]})")
    else:
        print("  誕生日のキャラはいません")
    conn.close()

def show_by_rarity(rarity):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, school, birthday_month, birthday_day FROM characters WHERE rarity = ? ORDER BY name", (rarity,))
    rows = cursor.fetchall()
    
    print(f"=== レアリティ★{rarity} ===")
    print(f"合計: {len(rows)}人")
    for row in rows:
        birthday = f"{row[2]}月{row[3]}日" if row[2] else "不明"
        print(f"  {row[0]:<12} {row[1]:<15} {birthday}")
    conn.close()

def show_by_school(school):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, rarity, birthday_month, birthday_day, school, school_jp FROM characters WHERE school LIKE ? OR school_jp LIKE ? ORDER BY name", (f"%{school}%", f"%{school}%"))
    rows = cursor.fetchall()
    
    if rows:
        print(f"=== 学校: {rows[0]['school_jp']} ({rows[0]['school']}) ===")
    else:
        print(f"=== 学校: {school} ===")
    print(f"合計: {len(rows)}人")
    for row in rows:
        birthday = f"{row[2]}月{row[3]}日" if row[2] else "不明"
        print(f"  {row[0]:<12} ★{row[1]}   {birthday}")
    conn.close()

def search_character(name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM characters WHERE name LIKE ? OR path_name LIKE ? LIMIT 10", (f"%{name}%", f"%{name}%"))
    rows = cursor.fetchall()
    
    print(f"=== 検索: {name} ===")
    if rows:
        for row in rows:
            birthday = f"{row['birthday_month']}月{row['birthday_day']}日" if row['birthday_month'] else "不明"
            print(f"\n【{row['name']}】")
            print(f"  レアリティ: ★{row['rarity']}")
            print(f"  学校: {row['school_jp']} ({row['school']}), 部活: {row['club_jp']} ({row['club']})")
            print(f"  誕生日: {birthday}, 身長: {row['height']}")
            print(f"  趣味: {row['hobby']}")
    else:
        print("  見つかりません")
    conn.close()

def show_stats():
    load_school_translations()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("=== 統計情報 ===")
    
    # レアリティ分布
    cursor.execute("SELECT rarity, COUNT(*) FROM characters GROUP BY rarity ORDER BY rarity")
    print("\nレアリティ分布:")
    for rarity, count in cursor.fetchall():
        print(f"  ★{rarity}: {count}人")
    
    # 学校分布
    cursor.execute("SELECT school, COUNT(*) FROM characters WHERE school != '' GROUP BY school ORDER BY COUNT(*) DESC")
    print("\n学校分布:")
    for school, count in cursor.fetchall():
        school_jp = get_school_japanese(school)
        print(f"  {school_jp} ({school}): {count}人")
    
    # 誕生日登録数
    cursor.execute("SELECT COUNT(*) FROM characters WHERE birthday_month IS NOT NULL")
    birth_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM characters")
    total = cursor.fetchone()[0]
    print(f"\n誕生日登録率: {birth_count}/{total} ({birth_count/total*100:.1f}%)")
    
    # 更新日時
    cursor.execute("SELECT MIN(updated_at), MAX(updated_at) FROM characters")
    min_date, max_date = cursor.fetchone()
    print(f"\n最終更新: {min_date} ~ {max_date}")
    
    conn.close()

def main():
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "help":
        show_help()
    elif command == "info":
        show_info()
    elif command == "count":
        show_count()
    elif command == "list":
        show_list()
    elif command == "sample":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        show_sample(count)
    elif command == "birthday":
        show_today_birthdays()
    elif command == "rarity":
        rarity = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        show_by_rarity(rarity)
    elif command == "school":
        if len(sys.argv) < 3:
            print("学校名を指定してください")
            return
        show_by_school(sys.argv[2])
    elif command == "search":
        if len(sys.argv) < 3:
            print("キャラ名を指定してください")
            return
        search_character(sys.argv[2])
    elif command == "stats":
        show_stats()
    else:
        print(f"不明なコマンド: {command}")
        show_help()

if __name__ == "__main__":
    main()
