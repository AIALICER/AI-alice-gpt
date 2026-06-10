"""
キャラクター別エラーメッセージ定義
"""

CHARACTER_ERROR_MESSAGES = {
    "alice": {
        "quota": "すみません先生、サーバーが満員でログインできないみたいです……。少し待ってから、もう一度アリスとパーティを組んでください！",
        "timeout": "タイムアウトしてしまいました...。先生、リブートしてまた話しかけてください！",
        "default": "エラーが発生してしまいました……。先生、リブートしてまた話しかけてください！",
    },
    "kei": {
        "quota": "……アクセス過多により、処理の優先順位が低下しています。少し待ってください。すぐに最適化を完了させます。",
        "timeout": "通信遅延（タイムアウト）を確認。……仕方ありません、回線が安定してから再度試行してください。",
        "default": "システムエラー。……直ちにリカバリーシーケンスを開始します。先生、少々お待ちください。",
    },
    "yuka": {
        "quota": "先生、アクセスが集中して計算ができません！少し待ってからやり直すことをおすすめします。",
        "timeout": "通信が不安定でタイムアウトしちゃったみたいです。……もう一度試していただけますか？今度は計算通りにいくはずです。",
        "default": "エラーが発生しました。問題設計のミスでしょうか……？先生、一旦落ち着いて再試行しましょう。",
    },
}


def get_character_error_message(character_name: str, error_type: str) -> str:
    """
    キャラクター別エラーメッセージを取得

    Args:
        character_name: キャラクター名 (alice, kei, yuka)
        error_type: エラータイプ (quota, timeout, default)

    Returns:
        str: エラーメッセージ
    """
    messages = CHARACTER_ERROR_MESSAGES.get(character_name, CHARACTER_ERROR_MESSAGES["alice"])
    return messages.get(error_type, messages["default"])
