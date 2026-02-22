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
import discord
from discord.ext import tasks  # @tasks.loop を使うために必要
from datetime import datetime, timezone, timedelta  # datetime, timezone, timedeltaはそのまま使用
from datetime import time as dt_time  # timeクラスは別名でインポートして標準timeモジュールと区別

# 日本標準時 (JST) の定義
JST = timezone(timedelta(hours=9))
from .config_base import (
    gemini_client,
    get_db_path,
    init_database,
    DISCORD_HISTORY_LIMIT,
    ENABLE_DISCORD_HISTORY,
    DISCORD_HISTORY_MAX_CHARS,
)
from . import gemini_handler
from . import db_handler
from . import file_handler
from . import timer_handler
from . import message_sender
from . import url_handler
from . import record_url
from . import news_handler
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
        command_pattern: re.Pattern,
        history_clear_command: str,
        discord_token_env: str,
        system_instruction_path: str,
        messages,
        special_commands: Optional[Dict[str, Dict[str, str]]] = None
    ):
        self.character_name = character_name
        self.display_name = display_name
        self.command_pattern = command_pattern
        self.history_clear_command = history_clear_command
        self.discord_token_env = discord_token_env
        self.system_instruction_path = system_instruction_path
        self.messages = messages
        self.special_commands = special_commands or {}
        
        # データベースパスの設定と初期化
        self.db_path = get_db_path(character_name)
        init_database(self.db_path)
        
        # システムインストラクションの読み込み
        self.system_instruction = self._load_system_instruction()
        
        # Discord クライアントの初期化
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.client.tree = app_commands.CommandTree(self.client)
        # 状態管理
        self.summary_tasks: Dict[int, asyncio.Task] = {}
        self.active_timers: Dict[int, List[Dict[str, Any]]] = {}
        
        # メッセージ重複防止（メッセージIDとタイムスタンプの管理）
        self._processed_message_ids: Set[int] = set()
        self._message_id_timestamps: Dict[int, float] = {}
        self._message_locks: Dict[int, asyncio.Lock] = {}
        
        # イベントハンドラの設定
        self._setup_events()
    @tasks.loop(time=dt_time(hour=9, minute=0, tzinfo=JST))
    async def scheduled_wiki_check(self):
        if datetime.now(JST).weekday() == 1:  # 火曜日
            # ギルドを取得（IDは先生のものに書き換えてください）
            guild = self.client.get_guild(751791380837171340)
            if guild:
                from news_handler import check_wiki_logic
                res = check_wiki_logic(self.db_path)
                # report_channelを取得して報告
                channel = await self.get_or_create_report_channel(guild, "wiki-更新通知")
                await self.report_wiki_news(channel, res)
    def _load_system_instruction(self) -> str:
        """システムインストラクションファイルを読み込む"""
        try:
            with open(self.system_instruction_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"[ERROR] System instruction file not found: {self.system_instruction_path}")
            return ""
    
    def _cleanup_old_message_ids(self, current_time: float) -> None:
        """5分経過した古いメッセージIDをクリーンアップ"""
        timeout = 300  # 5分
        expired_ids = [
            msg_id for msg_id, timestamp in self._message_id_timestamps.items()
            if current_time - timestamp > timeout
        ]
        for msg_id in expired_ids:
            self._processed_message_ids.discard(msg_id)
            self._message_id_timestamps.pop(msg_id, None)
            if msg_id in self._message_locks:
                del self._message_locks[msg_id]
    
    def _contains_partner_mention(self, text: str) -> bool:
        """応答に相方Botへのメンションが含まれるかチェック"""
        partner_id = getattr(self.messages, 'PARTNER_BOT_ID', None)
        if not partner_id:
            return False
        return f'<@{partner_id}>' in text or f'<@!{partner_id}>' in text
    
    def _is_timer_related(self, content: str) -> bool:
        """タイマー関連のメッセージかどうかを判定（案内用）"""
        content = content.lower()
        timer_keywords = [
            r'\d+\s*分.*タイマー',
            r'タイマー.*\d+\s*分',
            r'\d+\s*分後',
            r'\d+\s*分.*たったら',
            r'\d+\s*分.*経ったら',
        ]
        for pattern in timer_keywords:
            if re.search(pattern, content):
                return True
        return False
    
    def _setup_events(self) -> None:
        """Discordイベントハンドラを設定"""
        
        @self.client.event
        async def on_ready():
            print(f"[{self.display_name}] Logged in as {self.client.user}")
            if not self.scheduled_wiki_check.is_running():
                self.scheduled_wiki_check.start()
            # テストするサーバーのID（数字）をここに入れる
            target_guild = discord.Object(id=751791380837171340) 
       
            # このサーバーにコマンドをコピーして同期
            self.client.tree.copy_global_to(guild=target_guild)
            await self.client.tree.sync(guild=target_guild)
    
            print(f"[{self.display_name}] {self.client.user} サーバー限定同期完了！")
        @self.client.event
        async def on_message(message):
            await self._handle_message(message)
        # スラッシュコマンド：記憶検索モードの開始
        # CharacterBotクラス内にて
        @self.client.tree.command(name="wiki_check", description="Wikiの最新イベントを確認します")
        async def wiki_check(interaction: discord.Interaction): # ここにselfはいらない（関数として定義）
         await interaction.response.defer()
        # 外部ファイルのロジックを呼び出す
         res = news_handler.check_wiki_logic(self.db_path) 
         await self.report_wiki_news(interaction.followup, res, is_manual=True)

        @self.client.tree.command(name="help", description="アリスのコマンド一覧を表示します")
        async def help_command(interaction: discord.Interaction):
            await interaction.response.send_message(self.messages.MSG_HELP)
        
        @self.client.tree.command(name="search_history", description="過去の解析記録を検索し、専用スレッドを作成します")
        @app_commands.describe(
          query="検索したいキーワードやURLの一部",
          limit="最新から何件の履歴を対象にするか（例：10）"
         )
        async def search_history(interaction: discord.Interaction, query: str, limit: int = 5):
          # 1. 応答を保留（検索とスレッド作成に時間がかかるため）
          await interaction.response.defer(ephemeral=True)
          try:
            # 2. record_url.py で定義した関数を呼び出す
            # 引数を明示的に渡すことで、関数側での self 混乱を防ぎます
            from . import record_url  # インポート場所は環境に合わせて調整
            
            await record_url.create_memory_thread(
                interaction=interaction,
                query=query,
                limit=limit,
                db_path=self.db_path,
                display_name=self.display_name,
                messages=self.messages
            )
            
          except Exception as e:
            print(f"[{self.display_name}] Search Command Error: {e}")
            await interaction.followup.send(self.messages.ERR_REBOOT.format(error_detail=e), ephemeral=True)
        @self.client.tree.context_menu(name=self.messages.CHAT_URL)
        async def record_chat_url(interaction: discord.Interaction, message: discord.Message):
            print(type(message))
            print(type(interaction))
            await interaction.response.send_message("メッセージを記録します！", ephemeral=True)
            await record_url.add_memory_with_context(message,interaction,self.db_path,self.display_name)
        @self.client.tree.context_menu(name=self.messages.SUMMARY_COMMAND)
        async def analyze_with_key(interaction: discord.Interaction, message: discord.Message):
            # 1. 応答を返す（ephemeral=True で自分だけに）
            await interaction.response.send_message("解析専用のプライベートスレッドを作成中...", ephemeral=True)
            
            # 2. プライベートスレッドの作成
            # ここでは引数の message を使うので self. は不要！
            thread = await message.channel.create_thread(
                name=f"解析：{message.author.display_name}の投稿",
                type=discord.ChannelType.private_thread,
                auto_archive_duration=60
            )
            
            # 3. ユーザーをスレッドに追加
            # ここでも引数の interaction を使うので self. は不要！
            await thread.add_user(interaction.user)
            
            # 4. スレッド開始の合図
            await thread.send(f"{interaction.user.mention} "+self.messages.MSG_SUMMARY)

            # 5. 解析実行（ここだけはクラスのメソッドを呼ぶので self. が必要！）
            await self._handle_message(message, force_process=True,interaction=True, target_channel=thread)
        
        # タイマースラッシュコマンド: /timer と /timers (アリスのみ)
        if self.character_name == "alice":
            @self.client.tree.command(name="timer", description="タイマーを設定します")
            @app_commands.describe(
                minutes="分（0-180）",
                seconds="秒（0-59）",
                task="タイマーの内容（例：カップ麺、会議）"
            )
            async def timer_set(
                interaction: discord.Interaction,
                minutes: app_commands.Range[int, 0, 180],
                seconds: app_commands.Range[int, 0, 59] = 0,
                task: str = "タイマー"
            ):
                total_seconds = minutes * 60 + seconds
                if total_seconds <= 0:
                    await interaction.response.send_message("時間を1秒以上設定してください。", ephemeral=True)
                    return
                
                # タイマーを設定
                channel_id = interaction.channel_id
                timer_data = {
                    "task": task,
                    "end_time": time.time() + total_seconds,
                    "user": interaction.user.name
                }
                
                if channel_id not in self.active_timers:
                    self.active_timers[channel_id] = []
                self.active_timers[channel_id].append(timer_data)
                
                # 時間表示の構築（秒が0の場合は省略）
                time_str = f"{minutes}分" if seconds == 0 else f"{minutes}分{seconds}秒"
                
                # 初期メッセージを送信（後で編集するため）
                initial_message = f"⏰ **{task}** のタイマー\n残り時間: {time_str}"
                await interaction.response.send_message(initial_message)
                
                # 送信したメッセージを取得
                sent_message = await interaction.original_response()
                
                # バックグラウンドでタイマー実行（カウントダウン付き）
                asyncio.create_task(self._run_timer_with_countdown(
                    interaction.channel, sent_message, total_seconds, task, timer_data
                ))
            
            # タイマー一覧スラッシュコマンド: /timers
            @self.client.tree.command(name="timers", description="現在のタイマー一覧を表示します")
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
            @self.client.tree.command(name="dice", description="ダイスを振ります")
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
                else:
                    rolls_str = ", ".join(map(str, rolls[:5])) + f"... (他{num_dice - 5}個)"
                
                result_msg = self.messages.MSG_DICE_RESULT.format(
                    notation=notation.upper(),
                    rolls=rolls_str,
                    total=total
                )
                await interaction.response.send_message(result_msg)

            @self.client.tree.command(name="help", description="コマンドの使い方を表示します")
            async def help_command(interaction: discord.Interaction):
                await interaction.response.send_message(self.messages.MSG_HELP)
    
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
            # ユーザー情報をDBに自動登録（upsert）
            db_handler.upsert_user(
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
            file_parts = []
            if message.attachments:
                max_attachments = 10 if is_empty_mention else 5
                file_parts = await file_handler.process_attachments(message.attachments[:max_attachments])
            
            # URLの処理（メッセージと履歴からURLを抽出してコンテンツを取得）
            url_context = ""
            if prompt:
                url_contents = await url_handler.process_urls_in_text(prompt)
                if url_contents:
                    url_context = url_handler.format_url_contents(url_contents)
            
            # プロンプトまたは添付ファイルがある場合のみ応答
            # 空メンション時は必ず応答（履歴を読み込むため）
            if prompt or file_parts or is_empty_mention:
                async with message.channel.typing():
                    await self._process_gemini_request(
                        message, channel_id, current_channel_id, prompt, file_parts, is_empty_mention, url_context,interaction=interaction,target_channel=target_channel 
                    )
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
        interaction: discord.Interaction = None,  # ← これを追加！
        target_channel: discord.Thread = None
    ) -> None:
        """Gemini APIへのリクエストを処理"""
        
        # 履歴取得数の設定（空メンション時は拡張）
        db_history_limit = 15 if is_empty_mention else 6
        discord_history_limit = 20 if is_empty_mention else DISCORD_HISTORY_LIMIT
        
        # 推論レベルと検索要否の判定
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
        needs_history=judgment['reference']

        prompt_display = '(empty mention)' if is_empty_mention else (prompt[:50] if prompt else '(file only)')
        print(f"[{self.display_name}] Level: {thinking_level}, Search: {needs_search}, History: {needs_history},Prompt: {prompt_display}...")
        
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
                # 空メンション時は文脈理解用のメッセージを追加
                current_parts.append({"text": "(ユーザーのメンションのみ - 会話の文脈を理解して応答してください)" + syslog})
            if file_parts:
                current_parts.extend(file_parts)
            if needs_history:
            # 履歴の取得（空メンション時は拡張）
             history = db_handler.get_recent_history(self.db_path, channel_id, limit=db_history_limit)
            
             # Discord履歴の取得とマージ（空メンション時は拡張）
             if ENABLE_DISCORD_HISTORY:
                discord_history = await message_sender.fetch_discord_history(
                    message.channel,
                    limit=discord_history_limit,
                    bot_id=self.client.user.id,
                    max_chars=DISCORD_HISTORY_MAX_CHARS
                )
                max_total = discord_history_limit if is_empty_mention else DISCORD_HISTORY_LIMIT
                history = message_sender.merge_histories(discord_history, history, max_total=max_total)
            else:
             history=[]
            # 履歴からURLを抽出してコンテンツを取得
            history_url_context = ""
            for history_item in history:
                if 'parts' in history_item:
                    for part in history_item['parts']:
                        if 'text' in part:
                            url_contents = await url_handler.process_urls_in_text(part['text'])
                            if url_contents:
                                history_url_context += url_handler.format_url_contents(url_contents)
            
            # URLコンテンツをプロンプトに追加
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
            # 記憶の取得
            memories = db_handler.get_memories(self.db_path, channel_id)
            
            # 現在の日本時間
            current_jst = timer_handler.get_japan_time()
            
            # システムインストラクションの構築
            # メンションしたユーザー情報を取得
            author = message.author
            user_display_name = author.display_name  # サーバー上の表示名（ニックネーム等）
            user_account_name = author.name           # Discordアカウント名
            user_mention = f'<@{author.id}>'         # Discordメンション形式
            user_info = (
                f"\n\n[Current User]\n"
                f"Display Name: {user_display_name}\n"
                f"Account Name: {user_account_name}\n"
                f"Mention: {user_mention}\n"
                f"# ユーザーをメンションする場合は上記の Mention 文字列をそのまま使用すること"
            )

            # 登録済み全ユーザー一覧を取得（他ユーザーへのメンション用）
            known_users_info = db_handler.get_all_users_info(self.db_path)
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
                thinking_config=types.ThinkingConfig(
                    thinking_level=thinking_level
                )
            )
            # Gemini API呼び出し
            response = await gemini_handler.generate_content_with_fallback(
                client=gemini_client,
                primary_model='gemini-3-flash-preview',
                contents=input_contents,
                config=current_config
            )
            
            # レスポンスからテキストを抽出
            bot_response_text = await self._extract_response_text(
                response, input_contents, full_system_instruction, tools
            )
            # 履歴の保存
            if file_parts:
                file_summary = await file_handler.summarize_attachments(prompt, file_parts)
                save_user_text = f"{prompt}{file_summary}"
            else:
                save_user_text = prompt
            
            db_handler.save_message(self.db_path, current_channel_id, 'user', save_user_text)
            db_handler.save_message(self.db_path, current_channel_id, 'model', bot_response_text)
            
            print(f"[{self.display_name}] DB saved: {save_user_text}")
            
            # 相方Botへのメンション検出とログ出力
            if self._contains_partner_mention(bot_response_text):
                print(f"[{self.display_name}] Partner mention detected in response")
            dest = target_channel if target_channel else message.channel

            if interaction and not target_channel:
            # 従来通り、自分だけにエフェメラルで返す場合
              await interaction.followup.send(bot_response_text, ephemeral=True)
            else:
    # スレッドが指定されている、または通常のチャットの場合
             await message_sender.send_long_message(
               dest, # ここを message.channel から dest に変更
               bot_response_text,
               long_message_notice=self.messages.MSG_RESPONSE_TOO_LONG
             )
            
            
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
                    thinking_config=types.ThinkingConfig(
                        thinking_level='minimal'
                    )
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
    async def get_or_create_report_channel(guild, channel_name="wiki-更新通知"):

    # 1. サーバー内のテキストチャンネルから、名前が一致するものを探す
     channel = discord.utils.get(guild.text_channels, name=channel_name)
    
    # 2. 見つからなかった場合、新しく作成する
     if channel is None:
        try:
            # 権限の設定（@everyoneは書き込み不可、Botは書き込み可能）
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
        """
        Wikiの解析結果をDiscordに送信する共通処理
        target: 送信先 (interaction.followup または discord.TextChannel)
        result: wiki_logic.check_wiki_logic の戻り値
        is_manual: 手動実行（スラッシュコマンド）かどうか
        """
        if not result:
            if is_manual:
                await target.send(self.messages.WIKI_FAILED)
            return

        title = result["title"]
        link = result["url"]
        is_new = result["is_new"]

        # 新着の場合、または手動で確認された場合
        if is_new:
            msg= self.messages.WIKI_NEW_EVENT.format(
                title=result["title"], 
                link=result["url"]
            )
            await target.send(msg)
        elif is_manual:
            # 既読だけど手動で聞かれた場合
            msg = self.messages.WIKI_ALREADY_READ.format(
                title=result["title"], 
                link=result["url"]
            )
            await target.send(msg)
    def run(self) -> None:
        """Botを起動"""
        token = os.getenv(self.discord_token_env)
        if not token:
            print(f"[ERROR] Discord token not found in environment variable: {self.discord_token_env}")
            return
        
        print(f"[{self.display_name}] Starting bot...")
        self.client.run(token)
