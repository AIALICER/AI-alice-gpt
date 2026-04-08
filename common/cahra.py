import csv  # 🌟 CSVライブラリをインポート

import requests
from bs4 import BeautifulSoup


def scrape_and_save_csv():
    url = "https://bluearchive.wikiru.jp/?%E3%82%AD%E3%83%A3%E3%83%A9%E3%82%AF%E3%82%BF%E3%83%BC%E4%B8%80%E8%A6%A7"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    characters_list = []
    rows = soup.select("tr")

    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 19:
            rarity = cols[0].get_text(strip=True)
            if "★" in rarity:
                name = cols[2].get_text(strip=True)
                status = cols[18].get_text(strip=True)

                # リスト形式で保存（CSVの1行分になる）
                characters_list.append([name, rarity, status])

    # 🌟 CSVファイルに書き込み
    filename = "blue_archive_chars.csv"
    header = ["名前", "レアリティ", "ステータス"]  # 見出し行

    # newline='' を指定しないと、Windowsなどで1行ごとに空行が入るのを防げます
    with open(filename, "w", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)  # ヘッダー（見出し）を書き込む
        writer.writerows(characters_list)  # データをまとめて書き込む

    print(f"保存完了: {filename} ({len(characters_list)}件)")


# 実行
scrape_and_save_csv()
