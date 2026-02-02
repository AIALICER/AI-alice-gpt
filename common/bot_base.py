"""
Discord Bot基盤クラス

キャラクターごとの設定を受け取り、共通のメッセージ処理ロジックを提供する。
"""

import discord
from discord import app_commands
import re
import os
import asyncio
from typing import Dict, Any, Optional, List, Callable
from google.genai import types

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
        
        # イベントハンドラの設定
        self._setup_events()
    
    def _load_system_instruction(self) -> str:
        """システムインストラクションファイルを読み込む"""
        try:
            with open(self.system_instruction_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"[ERROR] System instruction file not found: {self.system_instruction_path}")
            return ""
    
    def _setup_events(self) -> None:
        """Discordイベントハンドラを設定"""
        
        @self.client.event
        async def on_ready():
            print(f"[{self.display_name}] Logged in as {self.client.user}")
            # テストするサーバーのID（数字）をここに入れる
            target_guild = discord.Object(id=751791380837171340) 
    
            # このサーバーにコマンドをコピーして同期
            self.client.tree.copy_global_to(guild=target_guild)
            await self.client.tree.sync(guild=target_guild)
    
            print(f"[{self.display_name}] {self.client.user} サーバー限定同期完了！")
        @self.client.event
        async def on_message(message):
            await self._handle_message(message)
        @self.client.tree.context_menu(name=self.messages.SUMMARY_COMAND)
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
            await self._handle_message(message, force_process=True, target_channel=thread)
    async def _handle_message(self, message: discord.Message, force_process: bool = False, 
                              interaction: discord.Interaction = None,target_channel: discord.Thread = None ) -> None:
        """メッセージハンドラ（メインロジック）"""
        # 自分自身のメッセージは無視
        if message.author == self.client.user:
            return
        
        current_channel_id = message.channel.id
        channel_id = current_channel_id
        
        # 履歴消去コマンド
        if message.content == self.history_clear_command:
            if db_handler.clear_db_history(self.db_path, channel_id):
                await message.channel.send(self.messages.DB_DEL_SUC)
            else:
                await message.channel.send(self.messages.DB_DEL_FIL)
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
            # タイマー状況確認
            if "タイマー" in message.content and ("残り" in message.content or "状況" in message.content):
                status_message = timer_handler.get_remaining_timers(
                    channel_id,
                    no_timer_message=self.messages.TIMER_NOT,
                    timer_list_header=self.messages.TIMER_ALL,
                    remaining_template=self.messages.MSG_TIMER_REMAINING,
                    soon_template=self.messages.MSG_TIMER_SOON,
                    timers_dict=self.active_timers
                )
                await message.channel.send(status_message)
                return
            
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
        timer_second = judgment['minutes']
        timer_name = judgment['task']
        
        prompt_display = '(empty mention)' if is_empty_mention else (prompt[:50] if prompt else '(file only)')
        print(f"[{self.display_name}] Level: {thinking_level}, Search: {needs_search}, Prompt: {prompt_display}...")
        
        try:
            # 推論レベルが高い場合、思考中メッセージを送信
            if thinking_level == 'high':
                if not interaction:
                    await message.channel.send(self.messages.ALI_THI)
            
            # 検索が必要な場合
            tools = []
            if needs_search:
                if not interaction:
                    await message.channel.send(self.messages.ALI_SUR)
                tools.append(types.Tool(google_search=types.GoogleSearch()))
            
            # タイマーの設定
            if timer_second != 0:
                t_name = str(timer_name) if timer_name else "Timer"
                asyncio.create_task(timer_handler.set_timer(
                    message.channel,
                    timer_second,
                    t_name,
                    finish_message_template=self.messages.MSG_TIMER_FINISH,
                    timers_dict=self.active_timers
                ))
            
            # コンテンツの構築
            current_parts = []
            syslog = ""
            if timer_second != 0:
                syslog = f"\n\n[System info: Timer accepted for {timer_second} minutes. Please only report 'Acknowledged' and do not respond as if time has passed. Also, do not reference past conversation for this message.]"
            
            if prompt:
                current_parts.append({"text": prompt + syslog})
            elif is_empty_mention:
                # 空メンション時は文脈理解用のメッセージを追加
                current_parts.append({"text": "(ユーザーのメンションのみ - 会話の文脈を理解して応答してください)" + syslog})
            if file_parts:
                current_parts.extend(file_parts)
            
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
            enhanced_instruction = f"{self.system_instruction}\n\n[Current Japan Time]\n{current_jst}"
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
            dest = target_channel if target_channel else message.channel

            if interaction and not target_channel:
            # 従来通り、自分だけにエフェメラルで返す場合
              await interaction.followup.send(bot_response_text, ephemeral=True)
            else:
    # スレッドが指定されている、または通常のチャットの場合
             await message_sender.send_long_message(
              dest, # ここを message.channel から dest に変更
              bot_response_text,
              long_message_notice=self.messages.ALI_LONG_MES
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
                bot_response_text = self.messages.ALICE_FILED
                
        except Exception as extract_error:
            print(f"[{self.display_name}] Extract error: {type(extract_error).__name__}: {extract_error}")
            bot_response_text = self.messages.ALICE_FILED
        
        return bot_response_text
    
    def run(self) -> None:
        """Botを起動"""
        token = os.getenv(self.discord_token_env)
        if not token:
            print(f"[ERROR] Discord token not found in environment variable: {self.discord_token_env}")
            return
        
        print(f"[{self.display_name}] Starting bot...")
        self.client.run(token)
