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

# その他
SUMMARY_COMAND="アリスに解析させる"
ALI_LONG_MES = "応答が長すぎるため，ファイルの生成を行います！"
DB_DEL_SUC = "了解です！このチャンネルの記憶をリセットしました！"
DB_DEL_FIL = "ごめんなさい、履歴の消去に失敗しました…"
MSG_SUMMARY="先生。対象のメッセージをこちらで解析します!"

# 特殊コマンド
HIKARI_KEN = "ターゲット確認！出力臨界点突破！光よ！"
