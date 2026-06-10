"""
AIモモイ 用メッセージテンプレート
"""

from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME

# エラーメッセージ
RESPONSE_FAILED = "えっ、エラー！？　もー、信じられない！　なんとかするから待ってて、先生！"
ERR_REBOOT = "あー、もうー、クソゲーじゃん！　システムに異常が発生したみたい……リトライしよう、先生！\n詳細: {error_detail}"

# 処理中メッセージ
MSG_THINKING = "うーん……今、シナリオを考えてる最中だから、ちょっと待っててね、先生！"
MSG_SEARCHING = "よし、攻略本を読んでみるね！　検索開始！"

# タイマー関連
MSG_NO_ACTIVE_TIMERS = "えー、今は稼働中のタイマーがないよ、先生。暇なら一緒にゲームしない？"
MSG_ACTIVE_TIMERS_HEADER = "現在のクエスト一覧だよ、先生！　どれも進行中だね！"
MSG_TIMER_FINISH = "先生、時間だよ！　「{task_name}」の開始時刻、来たー！"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}秒！　急げー！"
MSG_TIMER_SOON = "・{task_name}: まもなく終了するよ！　ラストスパート！"
MSG_TIMER_SET = "やった！　{time_str}のタイマーを設定したよ！　「{task_name}」の時間になったら、私が教えてあげる！"
MSG_TIMER_GUIDE = "タイマーはスラッシュコマンドで設定できるよ！　`/timer` コマンドでクエストを登録してね！"

# ダイスロール関連
MSG_DICE_RESULT = "🎲 ダイスロール結果！　運命の女神はどっちに微笑むかな！？\n**{notation}** → {rolls}\n合計: **{total}**"
MSG_DICE_INVALID = "えー、指定が間違ってるよ、先生！　`XdY` って感じで教えてよ（例: `2d6`）！"
MSG_DICE_RANGE_ERROR = "ダイスの個数は1〜100、面数は2〜1000で指定してね！　それ以上はチートになっちゃうよ！"

# ヘルプ
MSG_HELP = """📖 **AIモモイの冒険ガイド！**

**タイマー**
- `/timer` - クエスト開始時間を設定！
  - `minutes`: 分（0-180）
  - `seconds`: 秒（0-59）
  - `task`: クエスト内容
  - 例: `/timer minutes:3 task:カップ麺`

- `/timers` - 進行中のクエスト一覧を確認！

**ダイスロール**
- `/dice` - 運命を左右するダイスを振る！
  - `notation`: ダイスの指定
  - 例: `/dice notation:2d6` または `/dice notation:6`

**その他**
- `/help` - このガイドを表示！
- `/wiki_check` - 最新のイベント情報をチェック！
- `/search_history` - 過去のセーブデータをロード！

先生、コマンドの使い方は実際に試してみるのが一番だよ！　最高のゲームを作るためには、色んな経験が必要だからね！"""

# その他
SUMMARY_COMMAND = "先生！　このメッセージ、私が解析しちゃうね！"
MSG_RESPONSE_TOO_LONG = "うわー、テキスト量が多いよ、先生！　ファイルにして渡すね！"
MSG_HISTORY_CLEARED = "セーブデータを削除したよ！　また最初から、新しい物語を始めよう！"
MSG_HISTORY_CLEAR_FAILED = "えー、セーブデータの削除に失敗しちゃった！　もー、なんでー！"
MSG_SUMMARY = "先生！　対象のメッセージ、私が解析してあげるね！"

# record_url関係
MEMORY_TITLE = "🎯 ここにセーブデータがあるみたい！"
MEMORY_DEST = "先生、これが探してたクエスト履歴かな？"
MEMORY_CHAT = "先生、お探しの攻略情報、これじゃないかな？"
CHAT_URL = "AIモモイにメッセージを記憶させる"
MEMORY_NOFIND = "先生、直近 {limit} 件のセーブデータを確認したけど、「{query}」に合致する特定の記録は見つからなかったよ。\n"
MEMORY_ER = "もしかして、もっと昔のセーブデータを探す？　件数を増やしてもう一回教えて！"

WIKI_NEW_EVENT = (
    "【新着イベント情報】\n"
    "先生、新しいイベントの情報だよ！\n"
    "**「{title}」**だって！\n"
    "{link}\n\n"
    "「新しいクエスト、一緒に挑戦しようね！」"
)
WIKI_ALREADY_READ = (
    "最新のイベントは **「{title}」** だよ！\n"
    "{link}\n\n"
    "「イベント終了日に焦らないように、今のうちに計画立てておこうね、先生！」"
)
WIKI_FAILED = "先生、すみません。Wikiからイベント情報が読み込めなかったよ……もー、クソゲーじゃん！"
