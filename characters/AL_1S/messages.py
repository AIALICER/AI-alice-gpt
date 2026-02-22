"""
アリス用メッセージテンプレート
"""

# 相方Bot情報（configからインポート）
from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME

# エラーメッセージ
RESPONSE_FAILED = "アリス,メッセージ出力に失敗しました...デバッグ作業が必要かもしれません！"
ERR_REBOOT = "エラーが発生しました…アリス、リブートします。\n詳細: {error_detail}"

# 処理中メッセージ
MSG_THINKING = "少し待ってください！アリスは思考中です…！"
MSG_SEARCHING = "アリス、検索中です！"

# タイマー関連
MSG_NO_ACTIVE_TIMERS = "現在動いているタイマーはありません!"
MSG_ACTIVE_TIMERS_HEADER = "現在稼働中のタイマーはこちらです！"
MSG_TIMER_FINISH = "（パンパカパーン！）先生、お時間です！「{task_name}」のクエストの開始時刻ですよ！"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}秒です！"
MSG_TIMER_SOON = "・{task_name}: まもなく終了です！"
MSG_TIMER_SET = "了解です！{time_str}のタイマーを設定しました！「{task_name}」のクエスト開始時刻になったらお知らせしますよ！"
MSG_TIMER_GUIDE = "タイマー機能はスラッシュコマンドから利用できますよ！\\n`/timer` コマンドでクエストの準備時間を設定しましょう！"

# ダイスロール関連
MSG_DICE_RESULT = "🎲 ダイスロール結果です！\n**{notation}** → {rolls}\n合計: **{total}**"
MSG_DICE_INVALID = "指定が正しくありません...！`XdY` 形式で指定してください（例: `2d6`）"
MSG_DICE_RANGE_ERROR = "ダイスの個数は1〜100、面数は2〜1000で指定してください！"

# ヘルプ
MSG_HELP = """📖 **アリスのコマンド一覧**

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
SUMMARY_COMMAND = "アリスに解析させる"
MSG_RESPONSE_TOO_LONG = "応答が長すぎるため，ファイルの生成を行います！"
MSG_HISTORY_CLEARED = "了解です！このチャンネルの記憶をリセットしました！"
MSG_HISTORY_CLEAR_FAILED = "ごめんなさい、履歴の消去に失敗しました…"
MSG_SUMMARY = "先生。対象のメッセージをこちらで解析します!"

# record_url関係
MEMORY_TITLE = "🎯 最適な記録を特定しました!"
MEMORY_DEST = "これが先生の望む履歴です！"
MEMORY_CHAT = "先生、お探しのものはこれですか?"
MEMORY_NOFIND = "すいません...{limit} 件の記録の中に「{query}」に合致する特定の記憶は見つけられませんでした...\n"
MEMORY_ER = "もう少し昔の記録まで探しますか？件数を増やしてリトライしましょう！"
CHAT_URL = "アリスにメッセージを覚えさせる"

WIKI_NEW_EVENT = (
    "【新着イベント情報】\n"
    "先生、新しいイベントの情報です！\n"
    "**「{title}」** です！\n"
    "{link}\n\n"
    "「アリス、準備万端です！先生、クエストの攻略、頑張りましょうね！」"
)
WIKI_ALREADY_READ = (
    "最新のイベントは **「{title}」** ですね！\n"
    "{link}\n\n"
    "「イベントミッションは終わりましたか？先生！」"
)
WIKI_FAILED = "先生、すみません。Wikiからイベント情報を読み取ることができませんでした。"