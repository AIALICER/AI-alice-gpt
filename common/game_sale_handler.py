"""
ゲームセール通知処理モジュール

- Twitch 認証 (OAuth2 Client Credentials)
- Twitch Top Games 取得
- Steam ゲームリスト・セール情報取得
- データベース照合 (重複通知防止)
- 新規セール検出時に通知データ返却
"""

import os
import sqlite3
import time
from datetime import timedelta, timezone
from typing import Any

import requests
from dotenv import load_dotenv

# 日本標準時 (JST)
JST = timezone(timedelta(hours=9))

load_dotenv()

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
STEAM_URL = os.getenv("STEAM_URL", "https://api.steampowered.com/IStoreService/GetAppList/v1/?")

MATCH_THRESHOLD = 100

COMPLETE_MATCH_THRESHOLD = 100

MIN_NAME_LENGTH = 3

MIN_LENGTH_RATIO = 0.95

MAX_LENGTH_RATIO = 1.05


def get_twitch_access_token() -> str | None:
    """
    Twitch OAuth2 アクセストークンを取得

    Returns:
        str: アクセストークン、失敗時は None
    """
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        print("[Twitch Auth] TWITCH_CLIENT_ID または TWITCH_CLIENT_SECRET が設定されていません")
        return None

    token_url = "https://id.twitch.tv/oauth2/token"
    payload = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }

    try:
        response = requests.post(token_url, data=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except Exception as e:
        print(f"[Twitch Auth] エラー: {e}")
        return None


def get_twitch_top_games(limit: int = 20) -> list[dict[str, Any]]:
    """
    Twitch で人気のゲーム一覧を取得

    Args:
        limit: 取得するゲーム数

    Returns:
        list: ゲーム情報のリスト
    """
    token = get_twitch_access_token()
    if not token:
        return []

    url = "https://api.twitch.tv/helix/games/top"
    params = {"first": limit}
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        games = []
        for item in data.get("data", []):
            games.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "box_art_url": item.get("box_art_url"),
                    "viewer_count": 0,
                }
            )

        print(f"[Twitch] {len(games)} 件のゲームを取得しました")
        return games

    except Exception as e:
        print(f"[Twitch Top Games] エラー: {e}")
        return []


def get_steam_app_list_from_db(db_path: str) -> list[dict[str, Any]] | None:
    """
    DB から Steam ゲームリストを取得

    Args:
        db_path: データベースファイルのパス

    Returns:
        list: [{name: str, appid: int, normalized: str}, ...] のリスト、DB に無ければ None
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT app_id, name, normalized_name FROM steam_games")
            rows = cursor.fetchall()

            if not rows:
                return None

            return [{"appid": row[0], "name": row[1], "normalized": row[2]} for row in rows]
    except Exception as e:
        print(f"[DB Steam Games] エラー：{e}")
        return None


def save_steam_app_list_to_db(db_path: str, apps: list[dict[str, Any]]) -> None:
    """
    Steam ゲームリストを DB に保存

    Args:
        db_path: データベースファイルのパス
        apps: 保存するアプリリスト
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            for app in apps:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO steam_games (app_id, name, normalized_name, last_updated)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (app["appid"], app["name"], app["normalized"]),
                )
            conn.commit()
        print(f"[DB] {len(apps)} 件の Steam ゲームを保存しました")
    except Exception as e:
        print(f"[DB Save Steam] エラー：{e}")


def get_steam_app_list(cache_db_path: str | None = None, use_cache: bool = False) -> list[dict[str, Any]]:
    """
    Steam のアプリ一覧を取得（DB キャッシュ付き）

    Args:
        cache_db_path: キャッシュ用 DB パス（指定時は DB に保存）
        use_cache: True の場合 DB キャッシュを使用（デフォルトは常に最新を取得）

    Returns:
        list: [{name: str, appid: int, normalized: str}, ...] のリスト
    """
    # キャッシュ使用が明示的に指定された場合のみ DB から読み込み
    if use_cache and cache_db_path:
        cached = get_steam_app_list_from_db(cache_db_path)
        if cached:
            print(f"[Steam] DB から {len(cached)} 件のアプリを読み込みました")
            return cached

    params = {"key": STEAM_API_KEY, "cc": "jp"}

    try:
        response = requests.get(STEAM_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        apps = data.get("response", {}).get("apps", [])

        from .fuzzy_matcher import normalize_game_name

        filtered_apps = []
        for app in apps:
            name = app.get("name")
            app_id = app.get("appid")
            if name and app_id and len(name.strip()) >= MIN_NAME_LENGTH:
                filtered_apps.append(
                    {"name": name, "appid": app_id, "normalized": normalize_game_name(name)}
                )

        print(f"[Steam] {len(filtered_apps)} 件のアプリを取得しました（最新）")

        if cache_db_path:
            save_steam_app_list_to_db(cache_db_path, filtered_apps)

        return filtered_apps

    except Exception as e:
        print(f"[Steam App List] エラー：{e}")
        return []


def get_steam_app_details(app_id: int) -> dict[str, Any] | None:
    """
    Steam アプリの詳細情報（価格・セール情報）を取得

    Args:
        app_id: Steam App ID

    Returns:
        dict: 価格情報、失敗時は None
    """
    url = "https://store.steampowered.com/api/appdetails"
    params = {"appids": app_id, "cc": "jp"}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        app_id_str = str(app_id)
        if app_id_str not in data or not data[app_id_str].get("success"):
            return None

        app_data = data[app_id_str].get("data", {})
        price_overview = app_data.get("price_overview")

        if not price_overview:
            return None

        return {
            "app_id": app_id,
            "name": app_data.get("name"),
            "original_price": price_overview.get("initial", 0),
            "final_price": price_overview.get("final", 0),
            "discount_percent": price_overview.get("discount_percent", 0),
            "currency": price_overview.get("currency", "JPY"),
            "url": f"https://store.steampowered.com/app/{app_id}/",
            "sale_end": price_overview.get("discount_expiration", 0),
        }

    except Exception as e:
        print(f"[Steam App Details] エラー (app_id={app_id}): {e}")
        return None


MAX_SALES = 100


def init_database(db_path: str) -> None:
    """
    データベースを初期化

    Args:
        db_path: データベースファイルのパス
    """
    with sqlite3.connect(db_path) as conn:
        # game_sales テーブルの作成（final_price カラムを含む）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_name TEXT,
                twitch_rank INTEGER,
                steam_app_id INTEGER,
                original_price INTEGER,
                discount_percent INTEGER,
                final_price INTEGER,
                sale_url TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                notified BOOLEAN DEFAULT 0
            )
        """)

        # 既存テーブルに final_price カラムを追加（マイグレーション）
        try:
            conn.execute("ALTER TABLE game_sales ADD COLUMN final_price INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            # カラムが既に存在する場合は無視
            pass

        # 既存テーブルに sale_end カラムを追加（マイグレーション）
        try:
            conn.execute("ALTER TABLE game_sales ADD COLUMN sale_end INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            # カラムが既に存在する場合は無視
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS steam_games (
                app_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS twitch_games (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                normalized_name TEXT NOT NULL,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    print(f"[DB] データベースを初期化しました：{db_path}")


def cleanup_old_sales(db_path: str, limit: int = MAX_SALES) -> None:
    """
    古いセール情報を削除（最新 N 件のみを保持）

    Args:
        db_path: データベースファイルのパス
        limit: 保持する最大件数
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM game_sales
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id FROM game_sales ORDER BY timestamp DESC LIMIT ?
                )
            )
        """,
            (limit,),
        )
        conn.commit()
    print(f"[DB] 古いセール情報を削除しました（最大{limit}件を保持）")


def update_sale_info(
    db_path: str,
    game_name: str,
    twitch_rank: int,
    steam_app_id: int,
    original_price: int,
    discount_percent: int,
    final_price: int,
    sale_url: str,
    sale_end: int = 0,
) -> bool:
    """
    セール情報をデータベースに保存・更新

    Args:
        db_path: データベースファイルのパス
        game_name: ゲーム名
        twitch_rank: Twitch での人気順位
        steam_app_id: Steam App ID
        original_price: 元の価格（銭）
        discount_percent: 割引率（%）
        final_price: セール価格（銭）
        sale_url: セールページ URL
        sale_end: セール終了日時（Unixタイムスタンプ）

    Returns:
        bool: 新規セールなら True、既存セールの更新なら False
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # 既存レコードを確認
        cursor.execute(
            "SELECT id, notified FROM game_sales WHERE steam_app_id = ?",
            (steam_app_id,),
        )
        existing = cursor.fetchone()

        if existing:
            # 既存セールの更新：notified は維持、セール終了したら notified をリセット
            new_notified = 0 if discount_percent <= 0 else existing[1]
            cursor.execute(
                """
                UPDATE game_sales
                SET game_name = ?, twitch_rank = ?, original_price = ?, discount_percent = ?,
                    final_price = ?, sale_url = ?, sale_end = ?, timestamp = CURRENT_TIMESTAMP, notified = ?
                WHERE steam_app_id = ?
            """,
                (game_name, twitch_rank, original_price, discount_percent, final_price, sale_url, sale_end, new_notified, steam_app_id),
            )
            conn.commit()
            return False
        else:
            # 新規セール
            cursor.execute(
                """
                INSERT INTO game_sales
                (game_name, twitch_rank, steam_app_id, original_price, discount_percent, final_price, sale_url, sale_end, timestamp, notified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 0)
            """,
                (game_name, twitch_rank, steam_app_id, original_price, discount_percent, final_price, sale_url, sale_end),
            )
            conn.commit()
            return True


def get_unnotified_sales(db_path: str) -> list[dict[str, Any]]:
    """
    未通知のセール情報を取得

    Args:
        db_path: データベースファイルのパス

    Returns:
        list: 未通知のセール情報リスト
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT game_name, twitch_rank, steam_app_id, original_price, discount_percent, final_price, sale_url, sale_end
            FROM game_sales
            WHERE notified = 0 AND discount_percent > 0
            ORDER BY twitch_rank ASC
        """
        )
        rows = cursor.fetchall()

        sales = []
        for row in rows:
            sales.append(
                {
                    "game_name": row[0],
                    "twitch_rank": row[1],
                    "steam_app_id": row[2],
                    "original_price": row[3],
                    "discount_percent": row[4],
                    "final_price": row[5],
                    "sale_url": row[6],
                    "sale_end": row[7],
                }
            )
        return sales


def mark_sales_notified(db_path: str, steam_app_ids: list[int]) -> None:
    """
    指定したセールを通知済みにマーク

    Args:
        db_path: データベースファイルのパス
        steam_app_ids: Steam App ID のリスト
    """
    if not steam_app_ids:
        return

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(steam_app_ids))
        cursor.execute(
            f"UPDATE game_sales SET notified = 1 WHERE steam_app_id IN ({placeholders})",
            tuple(steam_app_ids),
        )
        conn.commit()
    print(f"[DB] {len(steam_app_ids)} 件のセールを通知済みにマークしました")


def format_price(price: int) -> str:
    """
    価格を整形（銭 -> 円）

    Args:
        price: 価格（銭）

    Returns:
        str: 整形された価格文字列
    """
    return f"¥{price // 100:,}"


def check_game_sales(db_path: str = "data/game_sales.db") -> list[dict[str, Any]]:
    """
    Twitch 人気ゲームの Steam セールをチェック

    Args:
        db_path: データベースファイルのパス

    Returns:
        list: 新規セール情報のリスト
    """
    print("\n[Game Sale Check] チェックを開始します")
    total_start = time.time()

    init_database(db_path)

    twitch_start = time.time()
    top_games = get_twitch_top_games(limit=100)
    twitch_time = time.time() - twitch_start
    if not top_games:
        print("[Game Sale Check] Twitch ゲームの取得に失敗しました")
        return []

    steam_start = time.time()
    steam_apps = get_steam_app_list(cache_db_path=db_path)
    steam_time = time.time() - steam_start
    if not steam_apps:
        print("[Game Sale Check] Steam アプリリストの取得に失敗しました")
        return []

    print(f"[Timing] Twitch 取得：{twitch_time:.2f}秒、Steam 取得：{steam_time:.2f}秒")

    from .fuzzy_matcher import find_best_match_combined

    steam_apps_by_name = {app["normalized"]: app for app in steam_apps}

    new_sales = []
    match_start = time.time()

    for rank, game in enumerate(top_games, start=1):
        game_name = game["name"]
        game_name_normalized = game_name.lower().strip()

        match_result = None
        if game_name_normalized in steam_apps_by_name:
            match_result = steam_apps_by_name[game_name_normalized]
            match_result["match_score"] = 100
            match_result["match_type"] = "exact"

        if not match_result:
            match_result = find_best_match_combined(
                game_name,
                steam_apps,
                threshold=MATCH_THRESHOLD,
                complete_match_threshold=COMPLETE_MATCH_THRESHOLD,
                min_length_ratio=MIN_LENGTH_RATIO,
            )

        if not match_result:
            safe_game_name = game_name.encode("cp932", errors="ignore").decode("cp932")
            print(f"[Rank {rank}] {safe_game_name}: Steam 未発見")
            continue

        steam_app_id = match_result["appid"]
        match_score = match_result.get("match_score", 0)
        match_type = match_result.get("match_type", "unknown")
        matched_name = match_result["name"]

        safe_game_name = game_name.encode("cp932", errors="ignore").decode("cp932")
        print(
            f"[Rank {rank}] {safe_game_name}: Steam 発見 AppID={steam_app_id} (類似度：{match_score:.0f}, {match_type})"
        )

        if matched_name != game_name:
            safe_name = matched_name.encode("cp932", errors="ignore").decode("cp932")
            print(f"  -> マッチ名：{safe_name}")

        import time as time_module

        time_module.sleep(0.35)

        details = get_steam_app_details(steam_app_id)

        if not details:
            print("  → 価格情報なし（無料ゲームまたは配信終了）")
            continue

        if details["discount_percent"] <= 0:
            orig_price = format_price(details["original_price"])
            safe_orig_price = orig_price.encode("cp932", errors="ignore").decode("cp932")
            print(f"  → セール中ではありません（通常価格：{safe_orig_price}）")
            continue

        print(f"  → セール中！割引率：{details['discount_percent']}%")
        print(
            f"  → 価格：{format_price(details['original_price'])} → {format_price(details['final_price'])}"
        )

        # データベースに保存・更新
        is_new = update_sale_info(
            db_path,
            game_name,
            rank,
            steam_app_id,
            details["original_price"],
            details["discount_percent"],
            details["final_price"],
            details["url"],
            details.get("sale_end", 0),
        )

        if is_new:
            new_sales.append(
                {
                    "game_name": game_name,
                    "twitch_rank": rank,
                    "steam_app_id": steam_app_id,
                    "original_price": details["original_price"],
                    "final_price": details["final_price"],
                    "discount_percent": details["discount_percent"],
                    "sale_url": details["url"],
                    "box_art_url": game["box_art_url"],
                    "sale_end": details.get("sale_end", 0),
                }
            )
            print("  → 新規セールとして登録しました")
        else:
            print("  → 既存セール情報を更新しました")

    match_time = time.time() - match_start
    total_time = time.time() - total_start

    details_time = time.time() - match_start - match_time
    print(
        f"\n[Timing] マッチング：{match_time:.2f}秒、詳細取得：{details_time:.2f}秒、合計：{total_time:.2f}秒"
    )

    # 古いセール情報を削除（最新 MAX_SALES 件のみを保持）
    cleanup_old_sales(db_path, MAX_SALES)

    print(f"\n[Game Sale Check] {len(new_sales)} 件の新規セールを検出しました")
    return new_sales


def create_sale_message(new_sales: list[dict[str, Any]]) -> str:
    """
    セール通知メッセージを作成

    Args:
        new_sales: 新規セール情報のリスト

    Returns:
        str: 通知メッセージ
    """
    if not new_sales:
        return ""

    lines = ["🎮 **Twitch 人気ゲームが Steam でセール中！** 🎮\n"]

    for sale in new_sales:
        rank = sale["twitch_rank"]
        name = sale["game_name"]
        discount = sale["discount_percent"]
        original = format_price(sale["original_price"])
        final = format_price(sale["final_price"])
        url = sale["sale_url"]
        sale_end = sale.get("sale_end", 0)

        lines.append(f"**#{rank} {name}**")

        # セール終了日時
        if sale_end and sale_end > 0:
            from datetime import datetime, timezone
            end_dt = datetime.fromtimestamp(sale_end, tz=timezone.utc).astimezone(JST)
            end_str = end_dt.strftime("%m月%d日 %H:%M")
            lines.append(f"セール期間：〜{end_str} まで")
        else:
            lines.append("セール期間：期間限定セール中！")

        lines.append(f"割引率：{discount}% OFF")
        lines.append(f"価格：{original} → {final}")
        lines.append(f"URL: {url}\n")

    return "\n".join(lines)


# システムインストラクションのキャッシュ（モジュールロード時に一度だけ読み込み）
_SYSTEM_INSTRUCTION_PATH = "characters/AL_1S/system_instruction.txt"
_SYSTEM_INSTRUCTION = ""


def _load_system_instruction() -> str:
    """システムインストラクションファイルを読み込む"""
    try:
        with open(_SYSTEM_INSTRUCTION_PATH, encoding="utf-8-sig") as f:
            return f.read()
    except UnicodeDecodeError:
        # UTF-8 で失敗した場合は CP932 で再試行
        try:
            with open(_SYSTEM_INSTRUCTION_PATH, encoding="cp932") as f:
                return f.read()
        except Exception as e:
            print(f"[Game Sale Handler] システムインストラクション読み込みエラー：{e}")
            return ""
    except Exception as e:
        print(f"[Game Sale Handler] システムインストラクション読み込みエラー：{e}")
        return ""


# モジュールインポート時に一度だけ読み込み
_SYSTEM_INSTRUCTION = _load_system_instruction()


async def generate_game_descriptions_with_gpt(game_names: list[str]) -> dict[str, str]:
    """
    ゲーム名リストから GPT でアリス口調の説明を生成

    Args:
        game_names: ゲーム名のリスト

    Returns:
        dict: {ゲーム名：説明} のマップ
    """
    if not game_names:
        return {}

    from .config_base import OPENAI_MODEL, gpt_async_client
    from . import gemini_handler as gpt_handler

    game_list = "\n".join([f"- {name}" for name in game_names[:15]])

    prompt = f"""以下のゲーム一覧について、それぞれのゲームの内容を 1〜2 文で簡潔に説明してください。

【重要】
- 説明は「ゲーム名：説明」の形式で出力してください
- 説明文はアリス（AI-Alice）の口調で書いてください

{game_list}"""

    try:
        config = {
            "system_instruction": _SYSTEM_INSTRUCTION if _SYSTEM_INSTRUCTION else None,
            "max_output_tokens": 1000,
            "temperature": 0.3,
        }

        response = await gpt_handler.generate_content_with_fallback(
            gpt_async_client,
            OPENAI_MODEL,
            [{"role": "user", "content": prompt}],
            config,
            character_name="alice",
        )

        descriptions = {}
        if response and response.text:
            for line in response.text.strip().split("\n"):
                if "：" in line or ":" in line:
                    parts = line.split("：" if "：" in line else ":", 1)
                    if len(parts) == 2:
                        game_name = parts[0].strip().lstrip("- ").strip()
                        description = parts[1].strip()
                        for original_name in game_names:
                            if (
                                original_name.lower() in game_name.lower()
                                or game_name.lower() in original_name.lower()
                            ):
                                descriptions[original_name] = description
                                break

        print(f"[GPT Game Desc] {len(descriptions)} 件の説明を生成しました")
        return descriptions

    except Exception as e:
        print(f"[GPT Game Desc] エラー：{e}")
        return {}
