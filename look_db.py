import sqlite3
import os
DB_DIR = 'data'
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

DB_PATH = os.path.join(DB_DIR, 'alice_bot.db')
def check_database(db_name=DB_PATH ):
    try:
        # データベースに接続
        conn = sqlite3.connect(db_name)
        conn.row_factory = sqlite3.Row  # カラム名でアクセスできるようにする
        cursor = conn.cursor()

        print(f"--- データベース確認: {db_name} ---")

        # 1. 存在するテーブル一覧を取得
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"\n[テーブル一覧]: {[t['name'] for t in tables]}")

        for table_info in tables:
            table_name = table_info['name']
            if table_name == 'sqlite_sequence': continue # 自動連番管理用はスキップ

            print(f"\n--- テーブル: {table_name} ---")
            
            # 2. カラム（列）情報を表示
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            col_names = [c['name'] for c in columns]
            print(f"カラム: {col_names}")

            # 3. 中身を最新5件だけ表示
            cursor.execute(f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT 5;")
            rows = cursor.fetchall()
            
            if not rows:
                print("（データは空です）")
            else:
                for row in rows:
                    # 辞書形式で見やすく出力
                    print(dict(row))

    except Exception as e:
        print(f"エラーが発生しました: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_database()