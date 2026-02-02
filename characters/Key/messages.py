"""
ケイ用メッセージテンプレート
"""

# 相方Bot情報（configからインポート）
from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME

# エラーメッセージ
ALICE_FILED = "……エラーが発生しました。修復を試みます。"
ERR_REBOOT = "システムに異常が発生しました。再起動します。\n詳細: {error_detail}"

# 処理中メッセージ
ALI_THI = "……………………処理中です。"
ALI_SUR = "検索を実行します。"

# タイマー関連
TIMER_NOT = "現在稼働中のタイマーはありません。"
TIMER_ALL = "稼働中のタイマー一覧です。"
MSG_TIMER_FINISH = "先生、時間です。「{task_name}」の開始時刻になりました。"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}秒です。"
MSG_TIMER_SOON = "・{task_name}: まもなく終了します。"

# その他
SUMMARY_COMAND="ケイに解析させる"
ALI_LONG_MES = "応答が長いため、ファイルを生成します。"
DB_DEL_SUC = "履歴を削除しました。"
DB_DEL_FIL = "履歴の削除に失敗しました。"
MSG_SUMMARY="先生。対象のメッセージをこちらで解析します．"