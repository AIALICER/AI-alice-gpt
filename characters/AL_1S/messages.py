"""
アリス用メッセージテンプレート
"""

# 相方Bot情報（configからインポート）
from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME

# エラーメッセージ
ALICE_FILED = "アリス,メッセージ出力に失敗しました...デバッグ作業が必要かもしれません！"
ERR_REBOOT = "エラーが発生しました…アリス、リブートします。\n詳細: {error_detail}"

# 処理中メッセージ
ALI_THI = "少し待ってください！アリスは思考中です…！"
ALI_SUR = "アリス、検索中です！"

# タイマー関連
TIMER_NOT = "現在動いているタイマーはありません!"
TIMER_ALL = "現在稼働中のタイマーはこちらです！"
MSG_TIMER_FINISH = "（パンパカパーン！）先生、お時間です！「{task_name}」のクエストの開始時刻ですよ！"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}秒です！"
MSG_TIMER_SOON = "・{task_name}: まもなく終了です！"
MSG_TIMER_SET = "了解です！{minutes}分のタイマーを設定しました！「{task_name}」のクエスト開始時刻になったらお知らせしますよ！"

# その他
SUMMARY_COMAND="アリスに解析させる"
ALI_LONG_MES = "応答が長すぎるため，ファイルの生成を行います！"
DB_DEL_SUC = "了解です！このチャンネルの記憶をリセットしました！"
DB_DEL_FIL = "ごめんなさい、履歴の消去に失敗しました…"
MSG_SUMMARY="先生。対象のメッセージをこちらで解析します!"

# 特殊コマンド
HIKARI_KEN = "ターゲット確認！出力臨界点突破！光よ！"

# record_url関係
MEMORY_TITLE="🎯 最適な記録を特定しました!"
MEMORY_DEST="これが先生の望む履歴です！"
MEMORY_CHAT="先生、お探しのものはこれですか?"
MEMORY_NOFIND="すいません...{limit} 件の記録の中に「{query}」に合致する特定の記憶は見つけられませんでした...\n"
MEMORY_ER="もう少し昔の記録まで探しますか？件数を増やしてリトライしましょう！"
CHAT_URL="アリスにメッセージを覚えさせる"