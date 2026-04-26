import csv

def get_gacha_names(r="★3",m="○"):
    filename = "blue_archive_chars.csv"
    star3_names = []

    try:
        # encoding="utf_8_sig" は保存時と同じものを使います
        with open(filename, "r", encoding="utf_8_sig") as f:
            # DictReaderを使うと、列名（ヘッダー）でデータにアクセスできて便利です
            reader = csv.DictReader(f)
            
            for row in reader:
                # 条件: 「レアリティ」が ★3 かつ 「ステータス」が ○
                # ※Wikiの表記に合わせて ★ か ☆ かをチェックしてください
                if "★3" in row["レアリティ"] and row["ステータス"] == "○":
                    star3_names.append(row["名前"])
        
        return star3_names

    except FileNotFoundError:
        print("CSVファイルが見つかりません。先にスクレイピングを実行してください。")
        return []
