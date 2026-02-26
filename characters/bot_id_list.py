"""
Bot レジストリ

全キャラクターBotのDiscord IDと表示名を一元管理する。
新しいキャラクターを追加する場合は、このファイルにのみ追記すればよい。

登録形式:
    BOT_REGISTRY = {
        "内部キャラクター名": {
            "bot_id": DiscordのユーザーID（int）,
            "display_name": 表示名（str）,
        },
        ...
    }
"""

BOT_REGISTRY: dict = {
    "alice": {
        "bot_id": 1455928987984592988,
        "display_name": "AIアリス",
    },
    "kei": {
        "bot_id": 1465400600878645352,
        "display_name": "AIケイ",
    },
    "yuka": {
        "bot_id": 1468944602370277472,
        "display_name": "AIユウカ",
    },
}

PARTNER_MAP: dict = {
    "alice": "kei",
    "kei": "alice",
    "yuka": "alice",
}


def get_partner_info(my_character_name: str) -> dict:
    """
    自分以外のBot情報を「相方リスト」として返す。

    現在のシステムでは相方は1体を想定しているため、
    自分以外の登録済みBot（bot_id が None でないもの）の中から
    最初の1件を返す。

    Args:
        my_character_name: 自分のキャラクター名（例: "alice", "kei"）

    Returns:
        dict: {"bot_id": int, "display_name": str}
              相方が見つからない場合は {"bot_id": None, "display_name": ""}
    """
    partner_name = PARTNER_MAP.get(my_character_name)
    if partner_name:
        partner_info = BOT_REGISTRY.get(partner_name)
        if partner_info and partner_info.get("bot_id") is not None:
            return partner_info

    for name, info in BOT_REGISTRY.items():
        if name != my_character_name and info.get("bot_id") is not None:
            return info
    return {"bot_id": None, "display_name": ""}
