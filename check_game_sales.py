#!/usr/bin/env python3
"""ゲームセールチェックスクリプト"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# .env から環境変数を読み込む（スタンドアロン実行時用）
from dotenv import load_dotenv
load_dotenv()

from common.game_sale_handler import check_game_sales, create_sale_message


def main():
    print("Twitch 人気ゲームの Steam セールをチェックします...\n")
    
    db_path = "data/game_sales.db"
    
    new_sales = check_game_sales(db_path)
    
    if new_sales:
        print("\n=== 新規セール ===")
        for sale in new_sales:
            print(f"  #{sale['twitch_rank']} {sale['game_name']}")
            print(f"     割引率：{sale['discount_percent']}% OFF")
            print(f"     価格：¥{sale['original_price'] // 100:,} → ¥{sale['final_price'] // 100:,}")
            print(f"     URL: {sale['sale_url']}\n")
        
        message = create_sale_message(new_sales)
        print("\n=== Discord 通知メッセージ ===")
        print(message)
    else:
        print("\n新規セールはありませんでした")


if __name__ == "__main__":
    main()
