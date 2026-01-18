import discord
import re
from google import genai
from google.genai import types
from datetime import datetime, timedelta, timezone
import asyncio
import look_db
import sendmessage
import timeee
from config import *
import db_func
import file_func
# システムインストラクション
try:
    with open('system_instruction.txt', 'r', encoding='utf-8') as f:
        SYSTEM_INSTRUCTION = f.read()
except FileNotFoundError:
    print("エラー！システムインストラクションファイルが見つかりません！")
    SYSTEM_INSTRUCTION = ""

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True # 2023年以降はこれも必須

discord_client = discord.Client(intents=intents)
@discord_client.event
async def on_ready():
    print(f"Logged in as {discord_client.user}")

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return
    curent_channel_id = message.channel.id
    channel_id=curent_channel_id
    
    if message.content == "!アリス 履歴消去":
        if db_func.clear_db_history(channel_id):       
            await message.channel.send("了解です！このチャンネルの記憶をリセットしました！")
        else:
            await message.channel.send("ごめんなさい、履歴の消去に失敗しました…")
        return
    if message.content == "!ログ確認":
        look_db.check_database()
    # メンションされた場合の処理＆!アリス コマンドで呼び出す（後方互換性）
    # 全角/半角の!、全角/半角スペース、改行に対応
    alice_command_pattern = re.compile(r'^[!！]アリス[ 　\n]')
    alice_command_match = alice_command_pattern.match(message.content)
    
    if discord_client.user.mentioned_in(message) or alice_command_match:
        
        if "タイマー" in message.content and ("残り" in message.content or "状況" in message.content):
          # timeeeファイルの関数を呼び出す
          status_message = timeee.get_remaining_timers(message.channel.id)
          await message.channel.send(status_message)
          return # Geminiに聞かずにここで終わらせる
        # メンション部分を除去してプロンプトを取得
        if discord_client.user.mentioned_in(message):
          prompt = message.content.replace(f'<@{discord_client.user.id}>', '').replace(f'<@!{discord_client.user.id}>', '').strip()
        elif alice_command_match:
          # マッチした部分を除去してプロンプトを取得
          prompt = message.content[alice_command_match.end():].strip()
        if message.channel_mentions:
         channel_id= message.channel_mentions[0].id
         prompt= prompt.replace(f'<#{channel_id}>', '')
        if channel_id in summary_tasks:
          summary_tasks[channel_id].cancel()
        summary_tasks[channel_id] = asyncio.create_task(db_func.summarize_and_cleanup(channel_id))
        # 添付ファイルを処理
        file_parts = []
        if message.attachments:
            file_parts = await file_func.process_attachments(message.attachments)
        
        # プロンプトまたは添付ファイルがある場合のみ応答
        if prompt or file_parts:
            # 即座に「入力中...」インジケーターを表示
            async with message.channel.typing():
                # 統合判定: 推論レベルと検索要否を同時に判定（案1 + 案2）
                judgment = await sendmessage.determine_level_and_search(
                    prompt=prompt if prompt else "",
                    channel_id=channel_id,
                    has_attachments=bool(file_parts)
                )
                thinking_level = judgment['level']
                needs_search = judgment['search']
                timer_second=judgment['minutes']
                timer_name=judgment['task']
                print(f"[統合判定] レベル: {thinking_level}, 検索: {needs_search}, プロンプト: {prompt[:50] if prompt else '(ファイルのみ)'}...")
                
                try:
                    # 推論レベルが高い場合、追加の思考中メッセージを送信
                    if thinking_level == 'high':
                        await message.channel.send("少し待ってください！アリスは思考中です…！")
                    
                    # 検索が必要な場合、ツールを設定
                    alice_tools = []
                    if needs_search:
                        await message.channel.send("アリス、検索中です！")
                        alice_tools.append(
                            types.Tool(google_search=types.GoogleSearch())
                        )
                    if timer_second!=0:
                        t_name = str(timer_name) if timer_name else "タイマー"
                        asyncio.create_task(timeee.set_timer(message.channel,timer_second,t_name))
                    # コンテンツを構築
                    current_parts = []
                    syslog=""
                    if timer_second != 0:
                        #ユーザーの発言の直後に、システムからの隠しメッセージを添える
                        syslog=f"\n\n[システム情報: タイマーを{timer_second}分で受け付けました。あなたは『了解しました』と設定完了の報告だけをしてください。何があっても時間経過が終わったかのように返信したりしないでください．またこの会話では，過去の会話を参考にして返信しないで下さい.]"
                
                    if prompt:
                        current_parts.append({"text": prompt+syslog})
                    if file_parts:
                        current_parts.extend(file_parts)
                    
                    history = sendmessage.get_recent_history(channel_id, limit=6)
                    
                    # Discord履歴取得機能（メンションされていない過去チャットも含む）
                    if ENABLE_DISCORD_HISTORY:
                        discord_history = await sendmessage.fetch_discord_history(
                            message.channel,
                            limit=DISCORD_HISTORY_LIMIT,
                            bot_id=discord_client.user.id,
                            max_chars=DISCORD_HISTORY_MAX_CHARS
                        )
                        # Discord履歴とDB履歴をマージ
                        history = sendmessage.merge_histories(discord_history, history, max_total=DISCORD_HISTORY_LIMIT)
    
                    input_contents = history + [{
                         "role": "user",
                         "parts": current_parts
                    }]
                    memories=""
                    memories=db_func.get_memories(channel_id)
                    # 現在の日本時間を取得
                    current_jst = timeee.get_japan_time()
                    full_system_instruction=""
                    enhanced_instruction = f"{SYSTEM_INSTRUCTION}\n\n[現在の日本時間]\n{current_jst}"
                    if alice_tools:
                        full_system_instruction=enhanced_instruction + "\n\n【重要】最新情報のためにGoogle検索を使ってください。"+ "\n\n以下はログより以前の会話履歴の要約です必要に応じて確認してください"+memories
                            
                        print("検索を実行\n")
                    else:
                      full_system_instruction=enhanced_instruction+ "\n\n以下はログより以前の会話履歴の要約です必要に応じて確認してください"+memories
                    current_config = types.GenerateContentConfig(
                            system_instruction=full_system_instruction,
                            tools=alice_tools,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=thinking_level
                            ))
                    # レートリミット対応の呼び出し（3段階フォールバック）
                    response = await sendmessage.generate_content_with_fallback(
                        client=gemini_client,
                        primary_model='gemini-3-flash-preview',
                        contents=input_contents,
                        config=current_config
                    )
                
                    # 応答の取得と保存
                    print(f"[DEBUG] Response type: {type(response)}")
                    print(f"[DEBUG] Response has text: {hasattr(response, 'text')}")
                    
                    # レスポンスからテキストを安全に取得
                    bot_response_text = None
                    try:
                        if response and hasattr(response, 'text') and response.text:
                            bot_response_text = response.text
                        elif response and hasattr(response, 'candidates') and response.candidates:
                            # 検索ツール使用時などのフォールバック
                            first_candidate = response.candidates[0]
                            if hasattr(first_candidate, 'content') and hasattr(first_candidate.content, 'parts') and first_candidate.content.parts:
                                parts_text = []
                                for part in first_candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        parts_text.append(part.text)
                                if parts_text:
                                    bot_response_text = ''.join(parts_text)
                        
                        if not bot_response_text:
                            print(f"[ERROR] レスポンスからテキストを抽出できませんでした: {response}")
                            bot_response_text = "応答の生成に失敗しました。もう一度お試しください。"
                    except Exception as extract_error:
                        print(f"[ERROR] レスポンス抽出エラー: {extract_error}")
                        bot_response_text = "応答の生成に失敗しました。もう一度お試しください。"

                    if file_parts:
                        file_summary = await file_func.summarize_attachments(prompt, file_parts)
                        save_user_text = f"{prompt}{file_summary}"
                    else:
                        save_user_text = prompt

                    sendmessage.save_message(curent_channel_id, 'user', save_user_text)
                    sendmessage.save_message(curent_channel_id, 'model', bot_response_text)

                    print(f"DB保存内容: {save_user_text}")
                    await sendmessage.send_long_message(message.channel, bot_response_text)

                except Exception as e:
                    print(f"エラー: {e}")
                    await message.channel.send(f"エラーが発生しました…アリス、リブートします。\n詳細: {e}")
        return
    
    # !光よ! コマンド
    if message.content.startswith("!光よ!"):
        await message.channel.send(file=discord.File("assets/光よ！.jpg"))
        return
    
discord_client.run(DISCORD_TOKEN)