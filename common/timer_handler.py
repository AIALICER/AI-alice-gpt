"""
タイマー処理モジュール

- タイマーの設定と管理
- 残り時間の確認
- 日本時間の取得
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

# グローバルなタイマー管理辞書（キャラクターごとに分離する場合は外部で管理）
# 構造: {channel_id: [{"task": str, "end_time": float}, ...]}
active_timers: dict[int, list[dict[str, Any]]] = {}


async def set_timer(
    channel,
    minutes: float,
    task_name: str,
    finish_message_template: str = "Time's up! Task: {task_name}",
    timers_dict: dict[int, list[dict[str, Any]]] = None,
) -> None:
    """
    タイマーを設定し、終了時にメッセージを送信

    Args:
        channel: Discordチャンネルオブジェクト
        minutes: タイマーの長さ（分）
        task_name: タスク名
        finish_message_template: 終了時のメッセージテンプレート
        timers_dict: タイマー管理辞書（指定しない場合はグローバル辞書を使用）
    """
    if timers_dict is None:
        timers_dict = active_timers

    channel_id = channel.id
    end_time = time.time() + (minutes * 60)

    timer_data = {"task": task_name, "end_time": end_time}

    # リストに追加
    if channel_id not in timers_dict:
        timers_dict[channel_id] = []
    timers_dict[channel_id].append(timer_data)

    try:
        await asyncio.sleep(minutes * 60)
        finish_msg = finish_message_template.format(task_name=task_name)
        await channel.send(finish_msg)

    finally:
        # 終わったらリストから消す
        if channel_id in timers_dict:
            timers_dict[channel_id] = [t for t in timers_dict[channel_id] if t != timer_data]


def get_remaining_timers(
    channel_id: int,
    no_timer_message: str = "No active timers.",
    timer_list_header: str = "Active timers:",
    remaining_template: str = "- {task_name}: {minutes}m {seconds}s remaining",
    soon_template: str = "- {task_name}: Ending soon!",
    timers_dict: dict[int, list[dict[str, Any]]] = None,
) -> str:
    """
    指定したチャンネルのタイマー一覧を文字列で返す

    Args:
        channel_id: チャンネルID
        no_timer_message: タイマーがない場合のメッセージ
        timer_list_header: タイマー一覧のヘッダー
        remaining_template: 残り時間テンプレート
        soon_template: まもなく終了テンプレート
        timers_dict: タイマー管理辞書（指定しない場合はグローバル辞書を使用）

    Returns:
        str: タイマー状況のテキスト
    """
    if timers_dict is None:
        timers_dict = active_timers

    if channel_id not in timers_dict or not timers_dict[channel_id]:
        return no_timer_message

    lines = [timer_list_header]
    now = time.time()

    for timer in timers_dict[channel_id]:
        remaining = timer["end_time"] - now
        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            msg = remaining_template.format(
                task_name=timer["task"], minutes=minutes, seconds=seconds
            )
            lines.append(msg)
        else:
            msg = soon_template.format(task_name=timer["task"])
            lines.append(msg)

    return "\n".join(lines)


def get_japan_time() -> str:
    """
    現在の日本標準時（JST）を取得

    Returns:
        str: 日本時間の文字列（例: "2026-01-06 20:18:48 (月曜日)"）
    """
    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)

    weekdays = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]
    weekday_jp = weekdays[now_jst.weekday()]

    formatted_time = now_jst.strftime("%Y-%m-%d %H:%M:%S")
    return f"{formatted_time} ({weekday_jp})"
