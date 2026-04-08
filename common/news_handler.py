import sqlite3
import urllib.parse

import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://bluearchive.wikiru.jp/?%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88"


def check_wiki_logic(db_path):
    print(f"\n[Debug] Wiki巡回を開始します: {TARGET_URL}")

    try:
        first_link = None
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(TARGET_URL, headers=headers, timeout=10)
        res.encoding = res.apparent_encoding

        print(f"[Debug] HTTPステータスコード: {res.status_code}")

        soup = BeautifulSoup(res.text, "html.parser")

        # 1. ボディ全体があるか確認
        content_body = soup.select_one("#body")
        if not content_body:
            print(
                "[Debug] エラー: #body 要素が見つかりませんでした。Wikiの構造が変わった可能性があります。"
            )
            # 念のためHTMLの冒頭100文字を表示
            print(f"[Debug] HTML冒頭: {res.text[:100]}")
            return None

        # 2. リンクを探す
        # イベント一覧の「開催中・開催予定」のテーブルなどから最初のリンクを狙う
        # Wikiruの構造に合わせて、少し柔軟に探すようにします
        # 候補1: 表の中のリンク
        tables = content_body.select("table")
        for table in tables:
            link = table.select_one("a")  # 表の中の最初のaタグ
            if link and link.get("href") and not link.get("href").startswith("http"):
                first_link = link
                print("[Debug] 表の中からリンクを発見しました。")
                break

        # 候補2: 表で見つからなければ、body内のWikiリンク
        if not first_link:
            first_link = content_body.find("a", href=lambda x: x and x.startswith("?"))
            if first_link:
                print("[Debug] Bodyから直接リンクを発見しました。")

        if not first_link:
            print("[Debug] エラー: a[href^='?'] （Wiki内リンク）が見つかりませんでした。")
            return None

        title = first_link.get_text().strip()
        href = first_link.get("href")

        link = "https://bluearchive.wikiru.jp/" + href
        # 3. 🌟 先生のアイデア：URLからタイトルを抽出
        # "?" を消してから、パーセントエンコーディング（%E3...）を日本語に直す
        decoded_name = urllib.parse.unquote(href.replace("?", ""))

        # 4. もし階層（スラッシュ）が含まれていたら、最後の名前だけをタイトルにする
        # 例: "イベント/お掃除大作戦" -> "お掃除大作戦"
        title = decoded_name.split("/")[-1]
        print(f"[Debug] 取得成功！ タイトル: {title}")
        print(f"[Debug] URL: {link}")

        # 3. DB照合
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wiki_news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    url TEXT UNIQUE,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("SELECT id FROM wiki_news WHERE url = ?", (link,))
            row = cursor.fetchone()

            if not row:
                print("[Debug] 結果: 新着情報です。DBに保存します。")
                cursor.execute("INSERT INTO wiki_news (title, url) VALUES (?, ?)", (title, link))
                conn.commit()
                return {"is_new": True, "title": title, "url": link}
            else:
                print("[Debug] 結果: 既にDBに存在する既読情報です。")
                return {"is_new": False, "title": title, "url": link}

    except Exception as e:
        print(f"[Debug] 致命的なエラーが発生しました: {e}")
        import traceback

        traceback.print_exc()  # どこでエラーが出たか詳細に表示
        return None
