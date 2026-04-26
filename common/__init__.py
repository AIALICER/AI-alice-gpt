"""
common - Discord Bot共通モジュール

このパッケージには、複数のキャラクターBotで共有される
基盤機能が含まれています。

モジュール:
- config_base: 共通設定管理、DB初期化、GPTクライアント
- gemini_handler: GPT API処理（フォールバック、推論レベル判定）
- db_handler: データベース処理（履歴、記憶管理）
- file_handler: ファイル処理（添付ファイル処理）
- timer_handler: タイマー処理
- message_sender: メッセージ送信処理
- url_handler: URL処理（URL抽出、コンテンツ取得）
- bot_base: Discord Bot基盤クラス
"""

from .config_base import (
    DB_DIR,
    DISCORD_HISTORY_LIMIT,
    ENABLE_DISCORD_HISTORY,
    DISCORD_HISTORY_MAX_CHARS,
    OPENAI_API_KEY,
    gpt_async_client,
    get_db_path,
    init_database,
)

__all__ = [
    'DB_DIR',
    'DISCORD_HISTORY_LIMIT',
    'ENABLE_DISCORD_HISTORY',
    'DISCORD_HISTORY_MAX_CHARS',
    'OPENAI_API_KEY',
    'gpt_async_client',
    'get_db_path',
    'init_database',
]
