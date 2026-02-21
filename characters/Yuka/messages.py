"""
ユウカ用メッセージテンプレート
"""

# 相方Bot情報（configからインポート）
from .config import PARTNER_BOT_NAME

# エラーメッセージ
RESPONSE_FAILED = "計算機が...故障していたとは..."
ERR_REBOOT = "悲しみも怒りも すべて因数分解してやるわ。\n詳細: {error_detail}"

# 処理中メッセージ
MSG_THINKING = "今日も全力であなたをアシストしますね。少しお待ちください..."
MSG_SEARCHING = "現在の状況と条件……"

# タイマー関連
MSG_NO_ACTIVE_TIMERS = "現在動いているタイマーはありません!"
MSG_ACTIVE_TIMERS_HEADER = "現在稼働中のタイマーはこちらです！"
MSG_TIMER_FINISH = "先生、お時間です！「{task_name}」はこれにて完了になります。"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}秒です！"
MSG_TIMER_SOON = "・{task_name}: まもなく終了です！ま、ここまでは計算通りね。"
MSG_TIMER_SET = "了解！{time_str}のタイマーを設定しました！「{task_name}」、時間になったらお知らせしますね♪"
MSG_TIMER_GUIDE = "タイマー機能はスラッシュコマンドから利用できます！\\n`/timer` コマンドで簡単に設定できますよ♪"

# その他
SUMMARY_COMMAND = "ユウカに解析させる"
MSG_RESPONSE_TOO_LONG = "変数が……多すぎる……，ファイルの生成を行います！"
MSG_HISTORY_CLEARED = "了解！このチャンネルの記憶をリセットしますね！"
MSG_HISTORY_CLEAR_FAILED = "ごめんなさい、履歴の消去に失敗しました…"
MSG_SUMMARY = "先生。対象のメッセージはこちらで解析します!"

# record_url関係
MEMORY_TITLE = "記録を特定しました"
MEMORY_DEST = "これが該当する記録です"
MEMORY_CHAT = "先生、お探しのものはこれですか?"
MEMORY_NOFIND = "{limit} 件の記録の中に「{query}」に合致する記憶は見つけられませんでした…"
MEMORY_ER = "より古い記録を検索しますか？"
CHAT_URL = "ユウカにメッセージを覚えさせる"

WIKI_NEW_EVENT = (
    "【新着イベント情報】\n"
    "先生、新しいイベント情報が入りました。\n"
    "**「{title}」** です。\n"
    "{link}\n\n"
    "「予算配分、先に計算しておきますね。」"
)
WIKI_ALREADY_READ = (
    "最新のイベントは **「{title}」** ですね。\n"
    "{link}\n\n"
    "「報酬の回収漏れがないか、確認しておいてくださいね。」"
)
WIKI_FAILED = "先生、すみません。Wikiからイベント情報を読み取ることができませんでした。"