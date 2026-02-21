"""
ケイ用メッセージテンプレート
"""

# 相方Bot情報（configからインポート）
from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME

# エラーメッセージ
RESPONSE_FAILED = "……エラーが発生しました。修復を試みます。"
ERR_REBOOT = "システムに異常が発生しました。再起動します。\n詳細: {error_detail}"

# 処理中メッセージ
MSG_THINKING = "……………………処理中です。"
MSG_SEARCHING = "検索を実行します。"

# タイマー関連
MSG_NO_ACTIVE_TIMERS = "現在稼働中のタイマーはありません。"
MSG_ACTIVE_TIMERS_HEADER = "稼働中のタイマー一覧です。"
MSG_TIMER_FINISH = "先生、時間です。「{task_name}」の開始時刻になりました。"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}秒です。"
MSG_TIMER_SOON = "・{task_name}: まもなく終了します。"
MSG_TIMER_SET = "{time_str}のタイマーを設定しました。「{task_name}」の時間になったら通知します。"
MSG_TIMER_GUIDE = "タイマー機能はスラッシュコマンドから利用できます。\\n`/timer` コマンドで設定してください。"

# その他
SUMMARY_COMMAND = "ケイに解析させる"
MSG_RESPONSE_TOO_LONG = "応答が長いため、ファイルを生成します。"
MSG_HISTORY_CLEARED = "履歴を削除しました。"
MSG_HISTORY_CLEAR_FAILED = "履歴の削除に失敗しました。"
MSG_SUMMARY = "先生。対象のメッセージをこちらで解析します．"

# record_url関係
MEMORY_TITLE = "🎯 最適な記録を特定しました．"
MEMORY_DEST = "これが先生が探してた履歴ですか?"
MEMORY_CHAT = "先生、お探しのものはこれでしょうか?"
CHAT_URL = "ケイにメッセージを覚えさせる"
MEMORY_NOFIND = "先生、直近 {limit} 件の記録を確認しましたが、「{query}」に合致する特定の記憶は見つかりませんでした。\n"
MEMORY_ER = "もう少し昔の記録まで探しますか？件数を増やして再度命じてください。"

WIKI_NEW_EVENT = (
    "【新着イベント情報】\n"
    "先生、新しいイベントの情報です\n"
    "**「{title}」** です\n"
    "{link}\n\n"
    "「イベントのバフは十分ですか？」"
)
WIKI_ALREADY_READ = (
    "最新のイベントは **「{title}」** です\n"
    "{link}\n\n"
    "「イベント終了日に慌てることのないようにしてくださいね！」"
)
WIKI_FAILED = "先生、すみません。Wikiからイベント情報を読み取ることができませんでした。"