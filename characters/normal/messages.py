"""
normal 用メッセージテンプレート
"""

# 相方Bot情報（configからインポート）
from .config import PARTNER_BOT_NAME

# エラーメッセージ
RESPONSE_FAILED = "エラーが発生しました。少し待ってからもう一度試してください。"
ERR_REBOOT = "システムエラーが発生しました。\n詳細: {error_detail}"

# 処理中メッセージ
MSG_THINKING = "処理中です。少し待ってください。"
MSG_SEARCHING = "検索して確認しています。"

# タイマー関連
MSG_NO_ACTIVE_TIMERS = "現在動作中のタイマーはありません。"
MSG_ACTIVE_TIMERS_HEADER = "現在のタイマー一覧です。"
MSG_TIMER_FINISH = "時間です。「{task_name}」の時間になりました。"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}秒"
MSG_TIMER_SOON = "・{task_name}: まもなく終了します。"
MSG_TIMER_SET = "{time_str} のタイマーを設定しました。「{task_name}」の時間になったら通知します。"
MSG_TIMER_GUIDE = "タイマー機能はスラッシュコマンドから利用できます。\n`/timer` コマンドで設定してください。"

# ダイスロール関連
MSG_DICE_RESULT = "🎲 ダイスロール結果\n**{notation}** → {rolls}\n合計: **{total}**"
MSG_DICE_INVALID = "指定が正しくありません。`XdY` 形式で指定してください（例: `2d6`）"
MSG_DICE_RANGE_ERROR = "ダイスの個数は1〜100、面数は2〜1000で指定してください。"

# ヘルプ
MSG_HELP = """📖 **ノーマルのコマンド一覧**

**タイマー**
- `/timer` - タイマーを設定
- `/timers` - タイマー一覧を表示

**ダイスロール**
- `/dice` - ダイスを振る

**その他**
- `/help` - コマンドの使い方を表示
- `/wiki_check` - Wikiの最新イベントを確認
- `/search_history` - 過去の解析記録を検索"""

# その他
SUMMARY_COMMAND = "ノーマルに解析させる"
MSG_RESPONSE_TOO_LONG = "応答が長いため、ファイルを生成します。"
MSG_HISTORY_CLEARED = "履歴を削除しました。"
MSG_HISTORY_CLEAR_FAILED = "履歴の削除に失敗しました。"
MSG_SUMMARY = "指定されたメッセージを解析します。"

# record_url関係
MEMORY_TITLE = "記録を見つけました"
MEMORY_DEST = "こちらが該当する記録です。"
MEMORY_CHAT = "この記録で合っていますか？"
CHAT_URL = "ノーマルにメッセージを覚えさせる"
MEMORY_NOFIND = "直近 {limit} 件の記録から「{query}」に一致する内容は見つかりませんでした。"
MEMORY_ER = "必要であれば検索件数を増やして再実行してください。"

WIKI_NEW_EVENT = (
    "【新着イベント情報】\n"
    "新しいイベント情報です。\n"
    "**「{title}」**\n"
    "{link}"
)
WIKI_ALREADY_READ = (
    "最新のイベントは **「{title}」** です。\n"
    "{link}"
)
WIKI_FAILED = "Wikiからイベント情報を取得できませんでした。"
