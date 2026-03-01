"""
Discord Bot基盤クラス

キャラクターごとの設定を受け取り、共通のメッセージ処理ロジックを提供する。
"""

import discord
from discord import app_commands
import re
import os
import asyncio
from typing import Dict, Any, Optional, List, Callable, Set
from google.genai import types
import time
from time import perf_counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta  # datetime, timezone, timedeltaはそのまま使用
from datetime import time as dt_time  # timeクラスは別名でインポートして標準timeモジュールと区別
from discord.ext import tasks  # @tasks.loop を使うために必要

# 日本標準時 (JST) の定義
JST = timezone(timedelta(hours=9))
from .config_base import (
    gemini_client,
    get_db_path,
    init_database,
    DISCORD_HISTORY_LIMIT,
    ENABLE_DISCORD_HISTORY,
    DISCORD_HISTORY_MAX_CHARS,
    USER_BIRTHDAY_CHANNEL_ID,
    BLUEARCHIVE_BIRTHDAY_CHANNEL_ID,
)
from . import gemini_handler
from . import db_handler
from . import file_handler
from . import timer_handler
from . import message_sender
from . import url_handler
from . import news_handler
from . import birthday_handler


@dataclass
class TimingData:
    """タイミング計測データクラス"""
    step_name: str
    start_time: float
    end_time: float = 0.0
    duration: float = 0.0
    
    def finalize(self, end_time: float):
        """計測を終了して継続時間を計算"""
        self.end_time = end_time
        self.duration = end_time - self.start_time


class PerformanceTimer:
    """パフォーマンス計測クラス"""
    
    def __init__(self, display_name: str, print_results: bool = True):
        self.display_name = display_name
        self.print_results = print_results
        self.timings: List[TimingData] = []
        self.current_step: Optional[TimingData] = None
        self.total_start: float = 0.0
        self._step_counter = 0
    
    def start_total(self):
        """全体計測を開始"""
        self.total_start = perf_counter()
        self.timings = []
        self._step_counter = 0
    
    @contextmanager
    def measure_step(self, step_name: str):
        """ステップ計測用コンテキストマネージャー"""
        start = perf_counter()
        timing = TimingData(step_name=step_name, start_time=start)
        self.current_step = timing
        
        try:
            yield self
        finally:
            end = perf_counter()
            timing.finalize(end)
            self.timings.append(timing)
            self._step_counter += 1
            
            if self.print_results:
                print(f"[{self.display_name}] [TIMING] {step_name}: {timing.duration:.3f}秒")
    
    def measure_parallel_start(self, step_name: str) -> TimingData:
        """並列処理の開始時間を記録"""
        timing = TimingData(step_name=step_name, start_time=perf_counter())
        self.current_step = timing
        return timing
    
    def measure_parallel_end(self, timing: TimingData):
        """並列処理の終了時間を記録"""
        timing.finalize(perf_counter())
        self.timings.append(timing)
        self._step_counter += 1
        
        if self.print_results:
            print(f"[{self.display_name}] [TIMING] {timing.step_name}: {timing.duration:.3f}秒")
    
    def print_summary(self):
        """計測サマリーを出力"""
        if not self.print_results or not self.timings:
            return
        
        total_duration = perf_counter() - self.total_start
        
        print(f"\n[{self.display_name}] [TIMING] ====== パフォーマンスサマリー ======")
        print(f"ステップ数: {len(self.timings)}")
        
        for i, timing in enumerate(self.timings, 1):
            percentage = (timing.duration / total_duration * 100) if total_duration > 0 else 0
            print(f"  {i}. {timing.step_name}: {timing.duration:.3f}秒 ({percentage:.1f}%)")
        
        print(f"合計時間: {total_duration:.3f}秒")
        print(f"[{self.display_name}] [TIMING] =================================\n")
    
    def get_timings_dict(self) -> Dict[str, float]:
        """計測結果を辞書形式で取得（分析用）"""
        return {timing.step_name: timing.duration for timing in self.timings}
    
    def get_slowest_step(self) -> Optional[TimingData]:
        """最も遅いステップを取得"""
        if not self.timings:
            return None
        return max(self.timings, key=lambda x: x.duration)


class CharacterBot:
    """
    キャラクター別Discord Botの基盤クラス
    
    Args:
        character_name: 内部キャラクター名（DB名に使用、例: "alice", "kei"）
        display_name: 表示用キャラクター名（例: "アリス", "ケイ"）
        command_pattern: コマンドパターン（正規表現）
        history_clear_command: 履歴消去コマンド文字列
        discord_token_env: Discord Tokenの環境変数名
        system_instruction_path: システムインストラクションファイルのパス
        messages: メッセージテンプレートモジュール
        special_commands: 特殊コマンド辞書（オプション）
    """
    
    def __init__(
        self,
        character_name: str,
        display_name: str,
        command_pattern: str,
        history_clear_command: str,
        discord_token_env: str,
        system_instruction_path: str,
        messages: Any,
        special_commands: Optional[Dict[str, Callable]] = None
    ):
        self.character_name = character_name
        self.display_name = display_name
        self.command_pattern = command_pattern
        self.history_clear_command = history_clear_command
        self.messages = messages
        self.special_commands = special_commands or {}
        self.summary_tasks: Dict[int, asyncio.Task] = {}
        
        # Discordクライアントの設定
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        
        # DBの初期化
        self.db_path = get_db_path(character_name)
        init_database(self.db_path)
        # ブルアカ誕生日専用DBの初期化（全Bot共有）
        birthday_handler.init_birthday_db()
        
        # 全BotのIDセット（誕生日お祝い時のメンション除外用）
        from characters.bot_id_list import BOT_REGISTRY
        self._all_bot_ids: Set[int] = {
            info["bot_id"] for info in BOT_REGISTRY.values()
            if info.get("bot_id") is not None
        }
        
        # システムインストラクションの読み込み
        if os.path.exists(system_instruction_path):
            with open(system_instruction_path, 'r', encoding='utf-8') as f:
                self.system_instruction = f.read()
        else:
            print(f"Warning: System instruction file not found at {system_instruction_path}")
            self.system_instruction = ""
        
        # Discord Bot Tokenの取得
        self.discord_token = os.getenv(discord_token_env)
        if not self.discord_token:
            raise ValueError(f"Environment variable {discord_token_env} is not set")
        
        # アクティブなタイマーを管理
        self.active_timers: Dict[int, List[Dict[str, Any]]] = {}
        
        # 処理済みメッセージIDの追跡（重複処理防止）
        self._processed_message_ids: Set[int] = set()
        self._message_id_timestamps: Dict[int, float] = {}
        self._message_locks: Dict[int, asyncio.Lock] = {}
    
    @tasks.loop(time=dt_time(hour=9, minute=0, tzinfo=JST))
    async def scheduled_wiki_check(self):
        """毎日午前9時（日本時間）にWikiをチェックするタスク"""
        if datetime.now(JST).weekday() == 1:  # 火曜日
            print(f"[{self.display_name}] Checking wiki...")
            try:
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, news_handler.check_wiki_logic, self.db_path)
                if res:
                    print(f"[{self.display_name}] Wiki check result: {res}")
            except Exception as e:
                print(f"[{self.display_name}] Wiki check error: {e}")

    @tasks.loop(time=dt_time(hour=0, minute=0, tzinfo=JST))
    async def scheduled_birthday_check(self):
        """
        毎日0時（日本時間）に実行する誕生日チェックタスク。

        - ユーザー誕生日: USER_BIRTHDAY_CHANNEL_ID のチャンネルにお祝いメッセージ
        - ブルアカキャラ誕生日: BLUEARCHIVE_BIRTHDAY_CHANNEL_ID（お遊戯会）に告知
        また、月曜日に1回ブルアカ誕生日データのスクレイピングを実行する。
        """
        print(f"[{self.display_name}] 誕生日チェックを開始します")
        today = datetime.now(JST)
        is_alice = self.character_name.lower() == "alice"

        # ========== ブルアカキャラ誕生日の更新（月曜日のみ） ==========
        if is_alice and today.weekday() == 0:  # 月曜日
            try:
                count = await birthday_handler.async_scrape_and_update()
                print(f"[{self.display_name}] ブルアカ誕生日DB更新: {count}件")
            except Exception as e:
                print(f"[{self.display_name}] ブルアカ誕生日スクレイピングエラー: {e}")

        # ========== ブルアカキャラ誕生日の告知 ==========
        if is_alice:
            try:
                ba_channel = self.client.get_channel(BLUEARCHIVE_BIRTHDAY_CHANNEL_ID)
                if ba_channel:
                    ba_birthdays = await asyncio.to_thread(birthday_handler.get_today_character_birthdays)
                    if ba_birthdays:
                        names = "、".join(c["name"] for c in ba_birthdays)
                        msg = await self._generate_birthday_message_ba(names)
                        await ba_channel.send(
                            msg,
                            allowed_mentions=discord.AllowedMentions.none()
                        )
                        print(f"[{self.display_name}] ブルアカキャラ誕生日告知完了: {names}")
            except Exception as e:
                print(f"[{self.display_name}] ブルアカ誕生日告知エラー: {e}")

        # ========== ユーザー誕生日のお祝い ==========
        try:
            user_birthdays = await asyncio.to_thread(
                birthday_handler.get_today_user_birthdays, self.db_path
            )
            if user_birthdays:
                # チャンネルを解決する
                birthday_channel = None
                if USER_BIRTHDAY_CHANNEL_ID:
                    birthday_channel = self.client.get_channel(USER_BIRTHDAY_CHANNEL_ID)
                if birthday_channel is None:
                    # フォールバック: Botが参加しているサーバーの最初のテキストチャンネル
                    for guild in self.client.guilds:
                        for ch in guild.text_channels:
                            if ch.permissions_for(guild.me).send_messages:
                                birthday_channel = ch
                                break
                        if birthday_channel:
                            break

                if birthday_channel:
                    for user_info in user_birthdays:
                        user_id = user_info["user_id"]
                        display_name = user_info["display_name"]
                        # Botへのメンションは除外
                        if user_id in self._all_bot_ids:
                            continue
                        msg = await self._generate_birthday_message_user(display_name)
                        # メンションなしで送信（mention_allowed_parse=[]で全メンション無効）
                        await birthday_channel.send(
                            msg,
                            allowed_mentions=discord.AllowedMentions.none()
                        )
                        print(f"[{self.display_name}] ユーザー誕生日祝い完了: {display_name}")
        except Exception as e:
            print(f"[{self.display_name}] ユーザー誕生日チェックエラー: {e}")

    async def _generate_birthday_message_user(self, display_name: str) -> str:
        """
        ユーザー誕生日のお祝いメッセージをGemini APIで生成する。
        失敗した場合はフォールバックメッセージを返す。
        """
        fallback = getattr(self.messages, 'MSG_BIRTHDAY_USER_FALLBACK',
                           f"🎂 {display_name}さん、お誕生日おめでとうございます！")
        prompt = (
            f"あなたは {self.display_name} というキャラクターです。"
            f"Discordサーバーのメンバー「{display_name}」さんの誕生日です。"
            f"キャラクターらしい自然な誕生日のお祝いメッセージを1〜3文で書いてください。"
            f"メンション（@記号）は絶対に使わないでください。"
            f"絵文字を1〜2個含めてください。"
        )
        try:
            from .config_base import gemini_client
            from google.genai import types
            response = await gemini_client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    thinking_config=types.ThinkingConfig(thinking_level='minimal')
                )
            )
            return response.text.strip() if response and response.text else fallback
        except Exception as e:
            print(f"[{self.display_name}] 誕生日メッセージ生成エラー: {e}")
            return fallback

    async def _generate_birthday_message_ba(self, names: str) -> str:
        """
        ブルアカキャラ誕生日の告知メッセージをGemini APIで生成する。
        失敗した場合はシンプルなメッセージを返す。
        """
        fallback = getattr(self.messages, 'MSG_BIRTHDAY_BA_FALLBACK',
                           f"🎂 今日は {names} の誕生日です！おめでとうございます！")
        prompt = (
            f"あなたは {self.display_name} というキャラクターです。"
            f"ブルーアーカイブのキャラクター「{names}」の誕生日です。"
            f"キャラクターらしい自然な誕生日告知メッセージを1〜3文で書いてください。"
            f"メンション（@記号）は絶対に使わないでください。"
            f"絵文字を1〜2個含めてください。"
        )
        try:
            from .config_base import gemini_client
            from google.genai import types
            response = await gemini_client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    thinking_config=types.ThinkingConfig(thinking_level='minimal')
                )
            )
            return response.text.strip() if response and response.text else fallback
        except Exception as e:
            print(f"[{self.display_name}] ブルアカ誕生日メッセージ生成エラー: {e}")
            return fallback

    def _cleanup_old_message_ids(self, current_time: float) -> None:
        """古いメッセージIDをクリーンアップ（5分経過したもの）"""
        timeout = 300  # 5分
        old_ids = [
            msg_id for msg_id, timestamp in self._message_id_timestamps.items()
            if current_time - timestamp > timeout
        ]
        for msg_id in old_ids:
            self._processed_message_ids.discard(msg_id)
            self._message_id_timestamps.pop(msg_id, None)
            self._message_locks.pop(msg_id, None)
    
    def _is_timer_related(self, content: str) -> bool:
        """タイマー関連のメッセージかどうかを判定"""
        timer_keywords = [
            r'\d+分.*タイマー',
            r'タイマー.*\d+分',
            r'\d+分.*たいまー',
            r'\d+秒.*タイマー',
            r'\d+秒.*たいまー',
        ]
        for pattern in timer_keywords:
            if re.search(pattern, content):
                return True
        return False
    
    def run(self):
        """Botを起動"""
        print(f"[{self.display_name}] Starting bot...")
        
        @self.client.event
        async def on_ready():
            """Bot準備完了時の処理"""
            print(f"[{self.display_name}] Logged in as {self.client.user}")
            try:
                synced = await self.tree.sync()
                print(f"[{self.display_name}] {self.client.user} サーバー限定同期完了！")
            except Exception as e:
                print(f"[{self.display_name}] Command sync error: {e}")
            
            # Wikiチェックのスケジュールタスクを開始
            if not self.scheduled_wiki_check.is_running():
                self.scheduled_wiki_check.start()
            
            # 誕生日チェックのスケジュールタスクを開始
            if not self.scheduled_birthday_check.is_running():
                self.scheduled_birthday_check.start()
            
            # 起動時にブルアカ誕生日DBが空ならスクレイピングを実行
            if self.character_name.lower() == "alice" and birthday_handler.count_character_birthdays() == 0:
                print(f"[{self.display_name}] ブルアカ誕生日DBが空のため初回スクレイピングを実行します")
                asyncio.create_task(birthday_handler.async_scrape_and_update())

        @self.client.event
        async def on_message(message: discord.Message):
            """メッセージ受信時の処理"""
            await self._handle_message(message)
        
        # タイマー設定スラッシュコマンド: /timer
        @self.tree.command(name="timer", description="タイマーを設定します")
        @app_commands.describe(minutes="分数（1〜180分）", seconds="秒数（0〜59秒、省略可）", task="タスク名（省略可）")
        async def timer_set(
            interaction: discord.Interaction,
            minutes: app_commands.Range[int, 1, 180],
            seconds: app_commands.Range[int, 0, 59] = 0,
            task: str = ""
        ):
            # タイマー設定
            total_seconds = minutes * 60 + seconds
            time_str = f"{minutes}分" if seconds == 0 else f"{minutes}分{seconds}秒"
            task_name = task if task else time_str
            await interaction.response.send_message(
                self.messages.MSG_TIMER_SET.format(time_str=time_str, task_name=task_name)
            )
            channel_id = interaction.channel_id
            timer_data = {
                "end_time": time.time() + total_seconds,
                "task": task_name,
                "interaction": interaction
            }
            if channel_id not in self.active_timers:
                self.active_timers[channel_id] = []
            self.active_timers[channel_id].append(timer_data)
            
            # 初期メッセージを送信
            initial_message = f"⏰ **{task_name}** のタイマー\n残り時間: {time_str}"
            sent_message = await interaction.channel.send(initial_message)
            
            # バックグラウンドでタイマー実行（カウントダウン付き）
            asyncio.create_task(self._run_timer_with_countdown(
                interaction.channel, sent_message, total_seconds, task_name, timer_data
            ))
        
        # タイマー一覧スラッシュコマンド: /timers
        @self.tree.command(name="timers", description="現在のタイマー一覧を表示します")
        async def timer_list(interaction: discord.Interaction):
            channel_id = interaction.channel_id
            status_message = timer_handler.get_remaining_timers(
                channel_id,
                no_timer_message=self.messages.MSG_NO_ACTIVE_TIMERS,
                timer_list_header=self.messages.MSG_ACTIVE_TIMERS_HEADER,
                remaining_template=self.messages.MSG_TIMER_REMAINING,
                soon_template=self.messages.MSG_TIMER_SOON,
                timers_dict=self.active_timers
            )
            await interaction.response.send_message(status_message)
        
        # ダイスロールスラッシュコマンド: /dice
        @self.tree.command(name="dice", description="ダイスを振ります")
        @app_commands.describe(notation="ダイスの指定（例: 6, 2d6, 1d100）")
        async def dice_roll(interaction: discord.Interaction, notation: str):
            import random
            notation = notation.lower().strip()
            match = re.match(r'^(\d+)(?:d(\d+))?$', notation)
            
            if not match:
                await interaction.response.send_message(self.messages.MSG_DICE_INVALID, ephemeral=True)
                return
            
            if match.group(2):
                num_dice = int(match.group(1))
                num_sides = int(match.group(2))
            else:
                num_dice = 1
                num_sides = int(match.group(1))
            
            if num_dice < 1 or num_dice > 100 or num_sides < 2 or num_sides > 1000:
                await interaction.response.send_message(self.messages.MSG_DICE_RANGE_ERROR, ephemeral=True)
                return
            
            rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
            total = sum(rolls)
            
            if num_dice <= 10:
                rolls_str = ", ".join(map(str, rolls))
                result_message = f"🎲 {notation} の結果: [{rolls_str}] = **{total}**"
            else:
                result_message = f"🎲 {notation} の結果: {num_dice}個のダイス = **{total}**"
            
            await interaction.response.send_message(result_message)
        
        # ========== 誕生日関連コマンド ==========

        # /birthday set <月> <日> - 誕生日登録
        @self.tree.command(name="birthday_set", description="あなたの誕生日を登録します")
        @app_commands.describe(month="月（1〜12）", day="日（1〜31）")
        async def birthday_set(
            interaction: discord.Interaction,
            month: app_commands.Range[int, 1, 12],
            day: app_commands.Range[int, 1, 31]
        ):
            # 存在しない日付のバリデーション（2000年はurl年なので 2/29 も有効）
            try:
                datetime(2000, month, day)
            except ValueError:
                invalid_msg = getattr(
                    self.messages,
                    'MSG_BIRTHDAY_INVALID_DATE',
                    "その日付は存在しません。月と日の組み合わせを確認してください。"
                )
                await interaction.response.send_message(invalid_msg, ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            user_id = interaction.user.id
            # DBにユーザーが登録されていなければ先にupsert
            await asyncio.to_thread(
                db_handler.upsert_user,
                self.db_path,
                user_id,
                interaction.user.display_name,
                interaction.user.name
            )
            await asyncio.to_thread(
                birthday_handler.set_user_birthday,
                self.db_path, user_id, month, day
            )
            msg = getattr(
                self.messages,
                'MSG_BIRTHDAY_SET',
                f"🎂 {month}月{day}日を誕生日として登録しました！"
            )
            await interaction.followup.send(msg, ephemeral=True)

        # /birthday_check [@ユーザー] - 誕生日確認
        @self.tree.command(name="birthday_check", description="登録された誕生日を確認します")
        @app_commands.describe(user="確認するユーザー（未指定の場合は自分）")
        async def birthday_check(
            interaction: discord.Interaction,
            user: Optional[discord.Member] = None
        ):
            await interaction.response.defer(ephemeral=True)
            target = user or interaction.user
            birthday_str = await asyncio.to_thread(
                birthday_handler.get_user_birthday,
                self.db_path, target.id
            )
            if birthday_str:
                m, d = birthday_str.split('-')
                msg = f"🎂 {target.display_name}さんの誕生日は **{int(m)}月{int(d)}日** です！"
            else:
                msg = getattr(
                    self.messages,
                    'MSG_BIRTHDAY_NOT_SET',
                    f"{target.display_name}さんの誕生日はまだ登録されていません。"
                )
            await interaction.followup.send(msg, ephemeral=True)

        # /birthday_ba <キャラ名> - ブルアカキャラ誕生日照会
        @self.tree.command(name="birthday_ba", description="ブルアカキャラの誕生日を答えます")
        @app_commands.describe(name="キャラクター名（信中名で可）")
        async def birthday_ba(
            interaction: discord.Interaction,
            name: str
        ):
            await interaction.response.defer()
            result = await asyncio.to_thread(birthday_handler.get_character_birthday, name)
            if result:
                msg = (
                    f"🎂 **{result['name']}** の誕生日は "
                    f"**{result['month']}月{result['day']}日** です！"
                )
            else:
                msg = (
                    f"「{name}」の誕生日はDBに登録されていません。"
                    f"キャラ名の表記を正確に入力するか、Google検索で確認してみてください。"
                )
            await interaction.followup.send(
                msg,
                allowed_mentions=discord.AllowedMentions.none()
            )

        self.client.run(self.discord_token)


    async def _run_timer_with_countdown(self, channel, message, total_seconds: int, task: str, timer_data: dict):
        """バックグラウンドでタイマーを実行（カウントダウン表示付き）"""
        end_time = time.time() + total_seconds
        
        try:
            # カウントダウン更新間隔（秒）
            # 残り時間に応じて更新頻度を調整
            while True:
                remaining = end_time - time.time()
                
                if remaining <= 0:
                    break
                
                # 残り時間に応じて更新間隔を調整
                if remaining > 60:
                    update_interval = 10  # 1分以上: 10秒ごと
                elif remaining > 10:
                    update_interval = 5   # 10秒〜1分: 5秒ごと
                else:
                    update_interval = 1   # 10秒以下: 1秒ごと
                
                # 残り時間を計算
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                
                if mins > 0:
                    time_display = f"{mins}分{secs}秒"
                else:
                    time_display = f"{secs}秒"
                
                # メッセージを編集して残り時間を更新
                try:
                    progress_bar = self._create_progress_bar(total_seconds, remaining)
                    await message.edit(content=f"⏰ **{task}** のタイマー\n{progress_bar} 残り: {time_display}")
                except Exception as e:
                    print(f"[{self.display_name}] Timer message edit error: {e}")
                
                # 次の更新まで待機
                await asyncio.sleep(min(update_interval, remaining))
            
            # タイマー終了
            await message.edit(content=f"✅ **{task}** のタイマーが終了しました！")
            await channel.send(self.messages.MSG_TIMER_FINISH.format(task_name=task))
            
        finally:
            # タイマー一覧から削除
            channel_id = channel.id
            if channel_id in self.active_timers:
                self.active_timers[channel_id] = [t for t in self.active_timers[channel_id] if t != timer_data]
    
    def _create_progress_bar(self, total_seconds: int, remaining_seconds: float) -> str:
        """プログレスバーを作成"""
        progress = 1 - (remaining_seconds / total_seconds)
        filled = int(progress * 10)
        empty = 10 - filled
        return "█" * filled + "░" * empty

    # ========== 並列処理用ヘルパーメソッド ==========

    async def _fetch_db_history(self, channel_id: int, limit: int) -> list:
        """DBから履歴を取得（並列処理用）"""
        return await asyncio.to_thread(db_handler.get_recent_history, self.db_path, channel_id, limit)

    async def _fetch_discord_history(self, channel, limit: int, is_empty_mention: bool) -> list:
        """Discordから履歴を取得（並列処理用）"""
        return await message_sender.fetch_discord_history(
            channel,
            limit=limit,
            bot_id=self.client.user.id,
            max_chars=DISCORD_HISTORY_MAX_CHARS
        )

    async def _fetch_memories(self, channel_id: int) -> str:
        """記憶を取得（並列処理用）"""
        return await asyncio.to_thread(db_handler.get_memories, self.db_path, channel_id)

    async def _fetch_user_info(self, author) -> dict:
        """ユーザー情報を取得（並列処理用）"""
        user_display_name = author.display_name
        user_account_name = author.name
        user_mention = f'<@{author.id}>'

        user_info = (
            f"\n\n[Current User]\n"
            f"Display Name: {user_display_name}\n"
            f"Account Name: {user_account_name}\n"
            f"Mention: {user_mention}\n"
            f"# ユーザーをメンションする場合は上記の Mention 文字列をそのまま使用すること"
        )

        known_users_info = await asyncio.to_thread(db_handler.get_all_users_info, self.db_path)

        return {
            "user_info": user_info,
            "known_users_info": known_users_info
        }

    async def _fetch_japan_time(self) -> str:
        """日本時間を取得（並列処理用）"""
        return timer_handler.get_japan_time()

    async def _handle_message(self, message: discord.Message, force_process: bool = False,
                              interaction: discord.Interaction = None,target_channel: discord.Thread = None ) -> None:
        """メッセージハンドラ（メインロジック）"""
        # 自分自身のメッセージは無視
        if message.author == self.client.user:
            return
        
        # メッセージIDによる重複チェック
        message_id = message.id
        current_time = time.time()
        
        # 古いメッセージIDをクリーンアップ（5分経過したもの）
        self._cleanup_old_message_ids(current_time)
        
        # 既に処理済みのメッセージは無視
        if message_id in self._processed_message_ids:
            print(f"[{self.display_name}] Duplicate message ignored: ID={message_id}")
            return
        
        # このメッセージの処理ロックを取得
        if message_id not in self._message_locks:
            self._message_locks[message_id] = asyncio.Lock()
        
        # ロックを取得して重複処理を防止
        async with self._message_locks[message_id]:
            # 二重チェック（ロック取得後に再確認）
            if message_id in self._processed_message_ids:
                print(f"[{self.display_name}] Duplicate message ignored (after lock): ID={message_id}")
                return
            
            # 処理済みとしてマーク
            self._processed_message_ids.add(message_id)
            self._message_id_timestamps[message_id] = current_time
            print(f"[{self.display_name}] Processing message: ID={message_id}, Content='{message.content[:50]}...'")
        
        current_channel_id = message.channel.id
        channel_id = current_channel_id
        
        # 履歴消去コマンド
        if message.content == self.history_clear_command:
            if db_handler.clear_db_history(self.db_path, channel_id):
                await message.channel.send(self.messages.MSG_HISTORY_CLEARED)
            else:
                await message.channel.send(self.messages.MSG_HISTORY_CLEAR_FAILED)
            return
        
        # タイマー関連メッセージの案内
        if self._is_timer_related(message.content):
            await message.channel.send(self.messages.MSG_TIMER_GUIDE)
            return
        
        # 特殊コマンドの処理
        for cmd, cmd_config in self.special_commands.items():
            if message.content.startswith(cmd):
                if 'message' in cmd_config:
                    await message.channel.send(cmd_config['message'])
                if 'file' in cmd_config:
                    await message.channel.send(file=discord.File(cmd_config['file']))
                return
        
        # メンションまたはコマンドパターンのチェック
        command_match = self.command_pattern.match(message.content)
        
        if self.client.user.mentioned_in(message) or command_match or force_process:
            # パフォーマンスタイマーの初期化
            timer = PerformanceTimer(self.display_name)
            timer.start_total()
            
            # ユーザー情報をDBに自動登録（upsert）
            with timer.measure_step("ユーザー情報登録"):
                await asyncio.to_thread(
                    db_handler.upsert_user,
                    self.db_path,
                    message.author.id,
                    message.author.display_name,
                    message.author.name
                )

            # プロンプトの抽出
            if self.client.user.mentioned_in(message):
             prompt = message.content.replace(f'<@{self.client.user.id}>', '').replace(f'<@!{self.client.user.id}>', '').strip()
            elif command_match:
             prompt = message.content[command_match.end():].strip()
            else:
             # 右クリック（force_process）時は、メッセージ全文をプロンプトにする
             prompt = message.content
            # チャンネルメンションの処理
            if message.channel_mentions:
                channel_id = message.channel_mentions[0].id
                prompt = prompt.replace(f'<#{channel_id}>', '')
            
            # プロンプトなしのメンションかどうか判定（@Bot のみ）
            is_empty_mention = self.client.user.mentioned_in(message) and not prompt
            
            # 要約タスクのリセット
            if channel_id in self.summary_tasks:
                self.summary_tasks[channel_id].cancel()
            self.summary_tasks[channel_id] = asyncio.create_task(
                db_handler.summarize_and_cleanup(self.db_path, channel_id)
            )
            
            # 添付ファイルの処理（空メンション時は通常より多く読み込む）
            with timer.measure_step("添付ファイル処理"):
                file_parts = []
                if message.attachments:
                    max_attachments = 10 if is_empty_mention else 5
                    file_parts = await file_handler.process_attachments(message.attachments[:max_attachments])
            
            # URLの処理（メッセージと履歴からURLを抽出してコンテンツを取得）
            url_context = ""
            if prompt:
                with timer.measure_step("プロンプトURL処理"):
                    url_contents = await url_handler.process_urls_in_text(prompt)
                    if url_contents:
                        url_context = url_handler.format_url_contents(url_contents)
            
            # プロンプトまたは添付ファイルがある場合のみ応答
            # 空メンション時は必ず応答（履歴を読み込むため）
            if prompt or file_parts or is_empty_mention:
                async with message.channel.typing():
                    await self._process_gemini_request(
                        message, channel_id, current_channel_id, prompt, file_parts, 
                        is_empty_mention, url_context, timer, interaction=interaction, 
                        target_channel=target_channel
                    )
            else:
                timer.print_summary()
            return
    
    async def _process_gemini_request(
        self,
        message: discord.Message,
        channel_id: int,
        current_channel_id: int,
        prompt: str,
        file_parts: list,
        is_empty_mention: bool = False,
        url_context: str = "",
        timer: PerformanceTimer = None,
        interaction: discord.Interaction = None,
        target_channel: discord.Thread = None
    ) -> None:
        """Gemini APIへのリクエストを処理（改善版計測）"""
        
        if timer is None:
            timer = PerformanceTimer(self.display_name)
            timer.start_total()
        
        # 履歴取得数の設定（空メンション時は拡張）
        db_history_limit = 15 if is_empty_mention else 6
        discord_history_limit = 20 if is_empty_mention else DISCORD_HISTORY_LIMIT
        
        # 推論レベルと検索要否の判定
        with timer.measure_step("推論レベル判定"):
            def get_history_func(ch_id, limit):
                return db_handler.get_recent_history(self.db_path, ch_id, limit)
            
            judgment = await gemini_handler.determine_level_and_search(
                prompt=prompt if prompt else "",
                channel_id=channel_id,
                has_attachments=bool(file_parts),
                get_recent_history_func=get_history_func,
                character_name=self.display_name
            )
        
        thinking_level = judgment['level']
        needs_search = judgment['search']
        timer_minutes = judgment['minutes']
        timer_name = judgment['task']
        needs_history = judgment['reference']

        prompt_display = '(empty mention)' if is_empty_mention else (prompt[:50] if prompt else '(file only)')
        print(f"[{self.display_name}] Level: {thinking_level}, Search: {needs_search}, History: {needs_history}, Prompt: {prompt_display}...")
        
        try:
            # 推論レベルが高い場合、思考中メッセージを送信
            if thinking_level == 'high':
                if not interaction:
                    await message.channel.send(self.messages.MSG_THINKING)
            
            # 検索が必要な場合
            tools = []
            if needs_search:
                if not interaction:
                    await message.channel.send(self.messages.MSG_SEARCHING)
                tools.append(types.Tool(google_search=types.GoogleSearch()))
            
            # タイマーの設定
            if timer_minutes != 0:
                t_name = str(timer_name) if timer_name else "Timer"
                asyncio.create_task(timer_handler.set_timer(
                    message.channel,
                    timer_minutes,
                    t_name,
                    finish_message_template=self.messages.MSG_TIMER_FINISH,
                    timers_dict=self.active_timers
                ))
            
            # コンテンツの構築
            current_parts = []
            syslog = ""
            if timer_minutes != 0:
                syslog = f"\n\n[System info: Timer accepted for {timer_minutes} minutes. Please only report 'Acknowledged' and do not respond as if time has passed. Also, do not reference past conversation for this message.]"

            if prompt:
                current_parts.append({"text": prompt + syslog})
            elif is_empty_mention:
                current_parts.append({"text": "(ユーザーのメンションのみ - 会話の文脈を理解して応答してください)" + syslog})
            if file_parts:
                current_parts.extend(file_parts)

            # 並列処理開始
            parallel_timing = timer.measure_parallel_start("並列データ取得")
            
            async_tasks = []
            if needs_history:
                async_tasks.append(self._fetch_db_history(channel_id, db_history_limit))
            else:
                async_tasks.append(None)

            if ENABLE_DISCORD_HISTORY and needs_history:
                async_tasks.append(self._fetch_discord_history(message.channel, discord_history_limit, is_empty_mention))
            else:
                async_tasks.append(None)

            async_tasks.append(self._fetch_memories(channel_id))
            author = message.author
            async_tasks.append(self._fetch_user_info(author))
            async_tasks.append(self._fetch_japan_time())

            valid_tasks = [t for t in async_tasks if t is not None]
            results = await asyncio.gather(*valid_tasks, return_exceptions=True)
            
            timer.measure_parallel_end(parallel_timing)

            # 結果を展開
            result_idx = 0
            history = []
            if needs_history:
                db_history_result = results[result_idx]
                result_idx += 1
                if isinstance(db_history_result, Exception):
                    print(f"[{self.display_name}] [PARALLEL] DB履歴取得エラー: {db_history_result}")
                    history = []
                else:
                    history = db_history_result

            discord_history = []
            if ENABLE_DISCORD_HISTORY and needs_history:
                discord_history_result = results[result_idx]
                result_idx += 1
                if isinstance(discord_history_result, Exception):
                    print(f"[{self.display_name}] [PARALLEL] Discord履歴取得エラー: {discord_history_result}")
                else:
                    discord_history = discord_history_result
                    if discord_history:
                        max_total = discord_history_limit if is_empty_mention else DISCORD_HISTORY_LIMIT
                        history = message_sender.merge_histories(discord_history, history, max_total=max_total)

            memories_result = results[result_idx]
            result_idx += 1
            memories = "" if isinstance(memories_result, Exception) else memories_result

            user_info_result = results[result_idx]
            result_idx += 1
            if isinstance(user_info_result, Exception):
                print(f"[{self.display_name}] [PARALLEL] ユーザー情報取得エラー: {user_info_result}")
                user_display_name = author.display_name
                user_account_name = author.name
                user_mention = f'<@{author.id}>'
                user_info = (
                    f"\n\n[Current User]\n"
                    f"Display Name: {user_display_name}\n"
                    f"Account Name: {user_account_name}\n"
                    f"Mention: {user_mention}\n"
                    f"# ユーザーをメンションする場合は上記の Mention 文字列をそのまま使用すること"
                )
                known_users_info = ""
            else:
                user_info = user_info_result["user_info"]
                known_users_info = user_info_result["known_users_info"]

            current_jst = results[result_idx]
            result_idx += 1
            if isinstance(current_jst, Exception):
                current_jst = timer_handler.get_japan_time()

            # 履歴URL処理
            with timer.measure_step("履歴URL処理"):
                history_url_context = ""
                if history:
                    history_texts: List[str] = []
                    for history_item in history[-8:]:
                        for part in history_item.get('parts', []):
                            text = part.get('text') if isinstance(part, dict) else None
                            if text:
                                history_texts.append(text)

                    if history_texts:
                        combined_history_text = "\n".join(history_texts)
                        history_url_contents = await url_handler.process_urls_in_text(combined_history_text)
                        if history_url_contents:
                            history_url_context = url_handler.format_url_contents(history_url_contents)

            if url_context or history_url_context:
                url_parts_text = url_context + history_url_context
                if prompt:
                    current_parts[0]["text"] = prompt + syslog + url_parts_text
                elif is_empty_mention:
                    current_parts[0]["text"] = "(ユーザーのメンションのみ - 会話の文脈を理解して応答してください)" + syslog + url_parts_text

            input_contents = history + [{
                "role": "user",
                "parts": current_parts
            }]
            known_users_section = f"\n\n{known_users_info}" if known_users_info else ""

            enhanced_instruction = f"{self.system_instruction}{user_info}{known_users_section}\n\n[Current Japan Time]\n{current_jst}"

            if tools:
                full_system_instruction = (
                    enhanced_instruction + 
                    "\n\n[IMPORTANT] Please use Google Search for latest information." +
                    "\n\nThe following is a summary of conversation history prior to logs. Please refer as needed: " + 
                    memories
                )
            else:
                full_system_instruction = (
                    enhanced_instruction +
                    "\n\nThe following is a summary of conversation history prior to logs. Please refer as needed: " +
                    memories
                )
            
            current_config = types.GenerateContentConfig(
                system_instruction=full_system_instruction,
                tools=tools,
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level)
            )
            
            # Gemini API呼び出し
            with timer.measure_step("Gemini API呼び出し"):
                response = await gemini_handler.generate_content_with_fallback(
                    client=gemini_client,
                    primary_model='gemini-3-flash-preview',
                    contents=input_contents,
                    config=current_config
                )
            
            # レスポンス抽出
            with timer.measure_step("レスポンス抽出"):
                bot_response_text = await self._extract_response_text(
                    response, input_contents, full_system_instruction, tools
                )
            
            # 履歴保存
            with timer.measure_step("DB保存"):
                if file_parts:
                    file_summary = await file_handler.summarize_attachments(prompt, file_parts)
                    save_user_text = f"{prompt}{file_summary}"
                else:
                    save_user_text = prompt

                await asyncio.to_thread(db_handler.save_message, self.db_path, current_channel_id, 'user', save_user_text)
                await asyncio.to_thread(db_handler.save_message, self.db_path, current_channel_id, 'model', bot_response_text)
            
            print(f"[{self.display_name}] DB saved: {save_user_text}")
            
            if self._contains_partner_mention(bot_response_text):
                print(f"[{self.display_name}] Partner mention detected in response")
            dest = target_channel if target_channel else message.channel

            # メッセージ送信
            with timer.measure_step("メッセージ送信"):
                if interaction and not target_channel:
                    await interaction.followup.send(bot_response_text, ephemeral=True)
                else:
                    await message_sender.send_long_message(
                        dest,
                        bot_response_text,
                        long_message_notice=self.messages.MSG_RESPONSE_TOO_LONG
                    )
            
            # サマリー出力
            timer.print_summary()
            
        except Exception as e:
            print(f"[{self.display_name}] Error: {e}")
            error_msg = self.messages.ERR_REBOOT.format(error_detail=e)
            await message.channel.send(error_msg)
    
    async def _extract_response_text(
        self,
        response,
        input_contents: list,
        full_system_instruction: str,
        tools: list
    ) -> str:
        """レスポンスからテキストを安全に抽出"""
        
        bot_response_text = None
        
        try:
            # 方法1: response.text を直接取得
            if response and hasattr(response, 'text') and response.text:
                bot_response_text = response.text
            
            # 方法2: candidates.content.parts から取得
            if not bot_response_text and response and hasattr(response, 'candidates') and response.candidates:
                first_candidate = response.candidates[0]
                if hasattr(first_candidate, 'content') and first_candidate.content:
                    if hasattr(first_candidate.content, 'parts') and first_candidate.content.parts:
                        parts_text = []
                        for part in first_candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                parts_text.append(part.text)
                        if parts_text:
                            bot_response_text = ''.join(parts_text)
            
            # 空レスポンス時のリトライ
            if not bot_response_text:
                print(f"[{self.display_name}] Empty, retrying...")
                retry_config = types.GenerateContentConfig(
                    system_instruction=full_system_instruction,
                    tools=tools,
                    thinking_config=types.ThinkingConfig(thinking_level='minimal')
                )
                retry_response = await gemini_handler.generate_content_with_fallback(
                    client=gemini_client,
                    primary_model='gemini-3-flash-preview',
                    contents=input_contents,
                    config=retry_config
                )
                if retry_response and hasattr(retry_response, 'text') and retry_response.text:
                    bot_response_text = retry_response.text
                else:
                    print(f"[{self.display_name}] Retry failed")
            
            if not bot_response_text:
                print(f"[{self.display_name}] Extract failed")
                bot_response_text = self.messages.RESPONSE_FAILED
                
        except Exception as extract_error:
            print(f"[{self.display_name}] Extract error: {type(extract_error).__name__}: {extract_error}")
            bot_response_text = self.messages.RESPONSE_FAILED
        
        return bot_response_text

    def _contains_partner_mention(self, text: str) -> bool:
        """応答に相方Botへのメンションが含まれるかチェック"""
        partner_id = getattr(self.messages, 'PARTNER_BOT_ID', None)
        if not partner_id:
            return False
        return f'<@{partner_id}>' in text or f'<@!{partner_id}>' in text

    async def get_or_create_report_channel(self, guild, channel_name="wiki-更新通知"):
        """レポート用チャンネルを取得または作成"""
        channel = discord.utils.get(guild.text_channels, name=channel_name)
    
        if channel is None:
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
            
                channel = await guild.create_text_channel(
                    name=channel_name,
                    topic="ブルーアーカイブWikiの更新を自動でお知らせします（自動生成）",
                    overwrites=overwrites
                )
                print(f"新しくチャンネルを作成しました: {channel_name}")
            
            except discord.Forbidden:
                print("エラー: チャンネルを作成する権限がありません。")
                return None
            except Exception as e:
                print(f"チャンネル作成中にエラーが発生しました: {e}")
                return None
    
        return channel

    async def report_wiki_news(self, target, result, is_manual=False):
        """Wikiの解析結果をDiscordに送信する共通処理"""
        if not result:
            if is_manual:
                await target.send(self.messages.WIKI_FAILED)
            return

        title = result["title"]
        link = result["url"]
        is_new = result["is_new"]

        if is_new:
            msg = self.messages.WIKI_NEW_EVENT.format(title=result["title"], link=result["url"])
            await target.send(msg)
        elif is_manual:
            msg = self.messages.WIKI_ALREADY_READ.format(title=result["title"], link=result["url"])
            await target.send(msg)
