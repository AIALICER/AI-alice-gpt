"""
アリス用メッセージテンプレート
"""

# 相方Bot情報（configからインポート）
from .config import PARTNER_BOT_ID, PARTNER_BOT_NAME

# エラーメッセージ
ALICE_FILED = "計算機が...故障していたとは..."
ERR_REBOOT = "悲しみも怒りも すべて因数分解してやるわ。\n詳細: {error_detail}"

# 処理中メッセージ
ALI_THI = "今日も全力であなたをアシストしますね。少しお待ちください..."
ALI_SUR = "現在の状況と条件……よし。これは勝ちね！"

# タイマー関連
TIMER_NOT = "現在動いているタイマーはありません!"
TIMER_ALL = "現在稼働中のタイマーはこちらです！"
MSG_TIMER_FINISH = "先生、お時間です！「{task_name}」計算通り。完璧～。"
MSG_TIMER_REMAINING = "・{task_name}: 残り {minutes}分{seconds}秒です！"
MSG_TIMER_SOON = "・{task_name}: まもなく終了です！ま、ここまでは計算通りね。"
MSG_TIMER_SET = "了解！{minutes}分のタイマーを設定しました！「{task_name}」、時間になったらお知らせしますね♪"

# その他
# SUMMARY_COMAND="アリスに解析させる"
ALI_LONG_MES = "変数が……多すぎる……，ファイルの生成を行います！"
DB_DEL_SUC = "了解！このチャンネルの記憶をリセットしますね！"
DB_DEL_FIL = "ごめんなさい、履歴の消去に失敗しました…"
MSG_SUMMARY="先生。対象のメッセージはこちらで解析します!"

# 特殊コマンド
