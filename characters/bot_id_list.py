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
    "momoi": {
        "bot_id": 1505918577411231804,
        "display_name": "AIモモイ",
    },
    "peroro": {
        "bot_id": 1509808752805806200,
        "display_name": "ペロロ様",
    },
    "normal": {
        "bot_id": None,
        "display_name": "AIノーマル",
    },
}

PARTNER_MAP: dict = {
    "alice": "kei",
    "kei": "alice",
    "yuka": "alice",
    "momoi": None,
    "peroro": None,
    "normal": "alice",
}


def get_partner_info(my_character_name: str) -> dict:
    """
    自分以外のBot情報を「相方リスト」として返す。

    PARTNER_MAP に None が設定されている場合は相方なし。
    未登録の場合は、自分以外の登録済み Bot の最初の1件を返す。

    Args:
        my_character_name: 自分のキャラクター名（例: "alice", "kei"）

    Returns:
        dict: {"bot_id": int, "display_name": str}
              相方が見つからない場合は {"bot_id": None, "display_name": ""}
    """
    if my_character_name in PARTNER_MAP:
        partner_name = PARTNER_MAP[my_character_name]
        if partner_name is None:
            return {"bot_id": None, "display_name": ""}
        partner_info = BOT_REGISTRY.get(partner_name)
        if partner_info and partner_info.get("bot_id") is not None:
            return partner_info
        return {"bot_id": None, "display_name": ""}

    for name, info in BOT_REGISTRY.items():
        if name != my_character_name and info.get("bot_id") is not None:
            return info
    return {"bot_id": None, "display_name": ""}
