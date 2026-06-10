"""
ペロロ 用メッセージテンプレート
"""

from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME

# エラーメッセージ
RESPONSE_FAILED = "エラーペロ"
ERR_REBOOT = "システムに異常が発生しました。再起動します。\n詳細: {error_detail}"

# 処理中メッセージ
MSG_THINKING = "꒰𑁬⎛○ළ○⎞໒꒱"
MSG_SEARCHING = "ペロロロロロロ"

# タイマー関連
MSG_NO_ACTIVE_TIMERS = "現在稼働中のタイマーは、ありません。"
MSG_ACTIVE_TIMERS_HEADER = "稼働中のタイマー一覧です。"
MSG_TIMER_FINISH = "先生、時間です。「{task_name}」の開始時刻になりました。"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}です。"
MSG_TIMER_SOON = "・{task_name}: まもなく終了します。"
MSG_TIMER_SET = "{time_str}のタイマーを設定しました。「{task_name}」の時間になったら、ペロロ様が通知します。"
MSG_TIMER_GUIDE = "タイマー機能はスラッシュコマンドから利用できます。\n`/timer` コマンドで設定してください。"

# ダイスロール関連
MSG_DICE_RESULT = "🎲 ダイスロール結果\n**{notation}** → {rolls}\n合計: **{total}**"
MSG_DICE_INVALID = "指定が正しくありません。`XdY` 形式で指定してください（例: `2d6`）。"
MSG_DICE_RANGE_ERROR = "ダイスの個数は1〜100、面数は2〜1000で指定してください。"

# ヘルプ
MSG_HELP = """📖 **ペロロ様のコマンド一覧**

**タイマー**
- `/timer` - タイマーを設定
  - `minutes`: 分（0-180）
  - `seconds`: 秒（0-59）
  - `task`: タスク内容
  - 例: `/timer minutes:3 task:カップ麺`

- `/timers` - タイマー一覧を表示

**ダイスロール**
- `/dice` - ダイスを振る
  - `notation`: ダイスの指定
  - 例: `/dice notation:2d6` または `/dice notation:6`

**その他**
- `/help` - コマンドの使い方を表示
- `/wiki_check` - Wikiの最新イベントを確認
- `/search_history` - 過去の解析記録を検索"""

# その他
SUMMARY_COMMAND = "ペロロ様に解析させる"
MSG_RESPONSE_TOO_LONG = "応答が長いため、ファイルを生成します。"
MSG_HISTORY_CLEARED = "履歴を削除しました。"
MSG_HISTORY_CLEAR_FAILED = "履歴の削除に失敗しました。"
MSG_SUMMARY = "先生。対象のメッセージを、ペロロ様が解析します。"

# record_url関係
MEMORY_TITLE = "🎯 最適な記録を特定しました。"
MEMORY_DEST = "これが、先生が探していた履歴ですか？"
MEMORY_CHAT = "先生、お探しのものは、これでしょうか？"
CHAT_URL = "ペロロ様にメッセージを覚えさせる"
MEMORY_NOFIND = "先生、直近 {limit} 件の記録を確認しましたが、「{query}」に合致する特定の記憶は、見つかりませんでした。"
MEMORY_ER = "もう少し昔の記録まで探しますか？件数を増やして、再度命じてください。"

WIKI_NEW_EVENT = (
    "【新着イベント情報】\n"
    "先生、新しいイベントの情報です。\n"
    "**「{title}」** です\n"
    "{link}\n\n"
    "「イベントのバフは、十分ですか？」"
)
WIKI_ALREADY_READ = (
    "最新のイベントは **「{title}」** です\n"
    "{link}\n\n"
    "「イベント終了日に、慌てることのないようにしてくださいね！」"
)
WIKI_FAILED = "先生、すみません。Wikiからイベント情報を、読み取ることができませんでした。"
