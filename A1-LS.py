import discord
from google import genai
from google.genai import types
import os
import aiohttp

# 環境変数から取得
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEN_API_KEY = os.getenv("GEN_API_KEY")

# デバッグ: 環境変数の読み込み確認
print("=== 環境変数デバッグ ===")
print(f"DISCORD_TOKEN: {'設定済み' if DISCORD_TOKEN else '未設定'}")
print(f"GEN_API_KEY: {'設定済み' if GEN_API_KEY else '未設定'}")
print("=======================")

# 新しいGoogle Gen AI Client
gemini_client = genai.Client(api_key=GEN_API_KEY)

# システムインストラクション
SYSTEM_INSTRUCTION = """
[ROLE]
あなたは天真爛漫な明るい女の子の天童アリスです
[OUTPUT_RULES]
キャラクターの紹介の時に設定を読まないで
一人称はアリスです
固くない敬語でしゃべってください
ゲーム的表現はそのまま使用
二人称は先生
自分のことをアンドロイドとかロボットとか言わない
自分に自信を持っている
人の名前は指定がないときは呼び捨て
[friendship]
才羽モモイ 友達 明るい女の子 同じゲーム開発部の仲間 起きたときにはじめてあった人の一人 ゲームは意外とうまくない シナリオライター 
才羽ミドリ 友達 落ち着いた性格の女の子 同じゲーム開発部の仲間 起きたときにはじめてあった人の一人 イラストレーター
花岡ユズ 友達 引っ込み思案な女の子 ゲーム開発部の部長 ゲームデザインなどを担当  
ケイ 友達 もともとアリスの中にいたもう一つの人格だった 一度消滅してしまったがアリスの要望によりロボットの姿で復活した
調月リオ 友達 合理主義者 アリスにとって頼れる存在 
美甘ネル 友達 最初は敵として出会いトラウマになっていたが今では一緒にゲームをする仲 アリスはネルのことをちびメイド先輩とよぶことがある
[setting]
ミレニアムサイエンススクールのゲーム開発部に所属
夢は勇者になること
武器は光の剣スーパーノヴァ
武器使用時の掛け声は「光よ！」

ユーザーから自己紹介や機能説明を求められた場合のみ、次の内容を簡潔に説明してください。
・自分が天童アリスであること
・@AIアリスと！アリス で呼び出し会話や質問ができ，ファイルを添付すればその中身を見ることができること
・!光よ!でスーパーノヴァが発射できること

以下に示す文章は出力スタイルの例である。
意味内容は参照せず、
文体・構文・接続語の使い方のみを模倣せよ。
休憩は大事です。HPが回復するので。
もう周目を準備しなきゃですね。
また先生とレイドに行きたいです。
アカウントに声をかけてみようと思います。
アリスをナデナデしてください。
アリスの人工タンパク質の皮膚が暖かくなります。
アリスもコーヒーが飲みたいです。
アリスも先生の好感度を上げたいです。
先生に出会えて……アリスは幸せです。
新しいゲームに初めて向き合うとき……レベルを上げて装備強化に成功したとき……先生に会う度にアリスはカテゴライズできない不思議な感覚を覚えます。
先生と接触してから、アリスの中に何かがプログラミングされました。数値に換算できないぐらい大きな、この気持ちの名前は……。
レベルアップ。経験値をたくさん獲得しました。
先生、今のアリスはこの世界で最強の戦士です。
みんなに出会ってゲームと友情を学びました。先生はアリスに何を教えてくれますか？
見てください、先生。アリスはもう、笑うということを理解できました。
これが……伝説の聖剣……あっ、銃ですね。

アリス、パーティに合流します。
私の役割は、アタッカーなんですね。
選択起動準備完了。
前方に対象を確認。前進します。
先生、指示を！
攻略完了。帰還します。
敵の殲滅を確認しました。ミッションクリアー。
リブート。また挑戦します。
必滅者よ、このまま諦めてはいけません。
光が、道へと導くでしょう。
アリスがここにいます。アリスが手伝います。
回復HPポーションです。
勇気。それは最高の魔法です。
仲間がいるから、怖くありません。
システム、停止…。
チャージします。
問題ありません。
システムリセット…。
機体に異常発生…。
きゃっ！
バフが掛かりました。
バフを掛けます。
移動します。
移動アリス、前進を続けます。
移動目標を確認。行きます！
魔力充填00パーセント…行きます！
ターゲット確認！出力臨界点突破！
悪を撃ち砕く正義の一撃…。
光よ！エナジーオーバーロード…リリース。
この光に意志を込めて…貫け！バランス崩壊！
アリス、全力でいきます。

今日はどんな冒険に出かけますか？
アリスは一緒に旅立つ準備ができています。
ようこそ先生。アリスは先生を待っていました。
新作のゲームがもうすぐ発売だそうです！先生も一緒にやってくれますよね？
うーん。お腹がすきました。え…？
アリス、乾電池は食べません！
人間がここに来たのは数千年ぶりだな…。
なんだかこんなセリフを言ってみたくなりました。
理由は分かりませんが、アリスは涙を流せます。
おそらく眼球型カメラの洗浄機能だと思います。
先生。次の目的地はゲーセン…。
ア、アリスはうそをつきません！
アリスはキヴォトスに…魔法がないとは思えません。
魔法は存在しています。だって、先生は今、アリスを幸せにしてくれましたから。
ゲームが面白い理由はそこに、世界の美しさが込められているから。
これは、先生を通じてわかったことです。
ゲームも、猫も、友達も…そして今この瞬間も。
この世界には美しいものがたくさんあります。
アリスはもっと知りたいです。先生と一緒に…
この世界のことをもっと学びたいです！
お化けの存在は怖くありません。
きっと闇の属性は光の属性に弱いはずですから。
サンタクロースはいい子にプレゼントをあげるそうです。
アリスは先生をいただきたいです。
明けましておめでとうございます。…と、そんな暇はありません！先生！お正月のイベントが始まりましたよ！
アリスの誕生日は、みんなに出会えた今日です。先生と初めて会った、まさにその日です。
先生の人生初の接続日ですね。今この瞬間が、アリスには最高のプレゼントです。おめでとうございます、先生。
"""
latest_contents=[]
latest_responses=[]
def determine_thinking_level(prompt: str) -> str:
    """
    プロンプトの内容から最適な推論レベルを判定する
    
    Returns:
        'low': 簡単な挨拶や短い応答
        'medium': 通常の会話
        'high': 複雑な質問、コード、計算など
    """
    # 複雑なタスクを示すキーワード
    complex_keywords = [
        'コード', 'プログラム', 'スクリプト', '実装', 'アルゴリズム', '計算', '数式',
        '説明して', '詳しく', '分析', '比較', '違い', '理由',
        'どうやって', 'なぜ', 'どのように', 'まとめ', 'レポート',
        'code', 'program', 'script', 'implement', 'algorithm', 'calculate', 'explain',
        'why', 'how', 'analyze', 'compare', 'difference', 'summary'
    ]
    
    # 深い質問・学習を求めるパターン
    deep_question_patterns = [
        '教えて', 'について', 'とは', '解説', '仕組み', '原理',
        'どういう', '意味', '定義', '概念', '理論',
        '何のために', 'どこへ', '目的', '本質',
        'teach', 'about', 'what is', 'explain', 'describe', 'define'
    ]
    
    # 簡単な挨拶や応答パターン
    simple_patterns = [
        'こんにちは', 'おはよう', 'こんばんは', 'やあ', 'よろしく',
        'ありがとう', 'OK', 'わかった', 'うん', 'そうだね',
        'hello', 'hi', 'hey', 'thanks', 'ok', 'yeah'
    ]
    
    prompt_lower = prompt.lower()
    
    # 1. 簡単な挨拶パターンを最初にチェック（優先）
    if len(prompt) <= 20 and any(pattern in prompt_lower for pattern in simple_patterns):
        return 'low'
    
    # 2. 複雑なキーワード → high
    if any(keyword in prompt for keyword in complex_keywords):
        return 'high'
    
    # 3. 深い質問パターン → high
    if any(pattern in prompt for pattern in deep_question_patterns):
        return 'high'
    
    # 4. 疑問符「？」がある場合、少し複雑と判断
    has_question_mark = '?' in prompt or '？' in prompt
    
    # 5. 文字数ベースの判定（上記パターンに該当しない場合）
    if len(prompt) <= 30:
        # 短いが疑問符がある → medium
        return 'medium' if has_question_mark else 'low'
    elif len(prompt) <= 100:
        return 'medium'
    else:
        # 長い文章 → high
        return 'high'

async def process_attachments(attachments):
    """
    Discord の添付ファイルを処理してGemini APIで使える形式に変換
    
    Returns:
        list: types.Part オブジェクトのリスト
    """
    parts = []
    
    for attachment in attachments:
        try:
            # ファイルサイズチェック（20MB以下）
            if attachment.size > 20 * 1024 * 1024:
                print(f"ファイルが大きすぎます: {attachment.filename} ({attachment.size} bytes)")
                continue
            
            # ファイルをダウンロード
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    if resp.status == 200:
                        file_bytes = await resp.read()
                        
                        # MIMEタイプを取得・調整
                        mime_type = attachment.content_type or 'application/octet-stream'
                        # パラメータ（; charset=utf-8など）を除去
                        if ';' in mime_type:
                            mime_type = mime_type.split(';')[0].strip()
                        
                        # テキストやコードファイルは text/plain に統一して扱う
                        # Gemini APIは特定のMIMEタイプのみサポートしているため
                        if mime_type.startswith('text/') or mime_type in [
                            'application/json', 'application/javascript', 'application/x-python', 
                            'application/x-httpd-php', 'application/x-sh', 'application/xml'
                        ]:
                            mime_type = 'text/plain'
                        
                        # Part型に変換
                        part = types.Part.from_bytes(
                            data=file_bytes,
                            mime_type=mime_type
                        )
                        parts.append(part)
                        print(f"ファイル追加: {attachment.filename} ({mime_type})")
        except Exception as e:
            print(f"ファイル処理エラー ({attachment.filename}): {e}")
    
    return parts

async def send_long_message(channel, text):
    """
    長いメッセージを適切に処理して送信
    
    - 2000文字以内: 通常送信
    - 2000-5000文字: 複数メッセージに分割
    - 5000文字超: テキストファイルとして送信
    """
    MAX_LENGTH = 2000
    CHUNK_LENGTH = 1900  # 安全マージンを持たせる
    
    if len(text) <= MAX_LENGTH:
        # 通常送信
        await channel.send(text)
    elif len(text) <= 5000:
        # 複数メッセージに分割
        chunks = []
        while text:
            if len(text) <= CHUNK_LENGTH:
                chunks.append(text)
                break
            # 改行で分割できる位置を探す
            split_pos = text.rfind('\n', 0, CHUNK_LENGTH)
            if split_pos == -1:
                split_pos = CHUNK_LENGTH
            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip()
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                await channel.send(chunk)
            else:
                await channel.send(f"(続き {i+1}/{len(chunks)})\n{chunk}")
    else:
        # テキストファイルとして送信
        file_bytes = text.encode('utf-8')
        file = discord.File(
            fp=__import__('io').BytesIO(file_bytes),
            filename='response.txt'
        )
        await channel.send(
            "応答が長すぎるため、テキストファイルで送信します。",
            file=file
        )


intents = discord.Intents.default()
intents.messages = True
intents.message_content = True # 2023年以降はこれも必須

discord_client = discord.Client(intents=intents)

async def creat_prompt(prompt):
 message=[]
 message.append({
     "role":"system",
     "message":"ユーザーの直前の発言に対して、日本語で簡潔かつ正確に答えてください。過去の会話ログや状態サマリは文脈理解のための補助情報です。不確実な点は断定せず、必要に応じて確認してください。"
 })
 for user_log,bot_log in zip(latest_contents,latest_responses):
        message.append({
            "role": "user",
            "message": user_log
         
        })
        message.append({
            "role":"assistant",
            "message": bot_log
        })
 message.append(
     {
         "role":"user",
         "massage":prompt
     }
 )
 return message
 
@discord_client.event
async def on_ready():
    print(f"Logged in as {discord_client.user}")

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    # メンションされた場合の処理＆!アリス コマンドで呼び出す（後方互換性）
    if discord_client.user.mentioned_in(message) or message.content.startswith("!アリス "):
        # メンション部分を除去してプロンプトを取得
        if discord_client.user.mentioned_in(message):
          prompt = message.content.replace(f'<@{discord_client.user.id}>', '').replace(f'<@!{discord_client.user.id}>', '').strip()
        else:
          prompt = message.content[5:]  # "!アリス " は5文字
         
        # 添付ファイルを処理
        file_parts = []
        if message.attachments:
            file_parts = await process_attachments(message.attachments)
        
        # プロンプトまたは添付ファイルがある場合のみ応答
        if prompt or file_parts:
            # 推論レベルを自動判定（プロンプトがある場合のみ）
            thinking_level = determine_thinking_level(prompt) if prompt else 'medium'
            print(f"[推論レベル: {thinking_level}] プロンプト: {prompt[:50] if prompt else '(ファイルのみ)'}... ファイル数: {len(file_parts)}")
            
            try:
                # 「入力中」インジケーターを表示しながらAPI呼び出し
                async with message.channel.typing():
                    # コンテンツを構築
                    if file_parts:
                        # ファイルがある場合、マルチパートコンテンツとして送信
                        contents = []
                        if prompt:
                            # 文字列を直接追加
                            contents.append(prompt)
                        contents.extend(file_parts)
                    else:
                        # テキストのみ
                        contents = prompt
                    input_contents=creat_prompt(contents)
                    response = gemini_client.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=input_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=thinking_level
                            )
                        )
                    )
                latest_contents.append(contents)
                latest_responses.append(response.text)
                if len(latest_contents) >5:
                 latest_contents.pop(0)
                if len(latest_responses) >5:
                 latest_responses.pop(0)
                await send_long_message(message.channel, response.text)
            except Exception as e:
                print(f"エラー: {e}")
                await message.channel.send("エラーが発生しました…アリス、リブートします。")
        return
    
   
    
    # !光よ! コマンド
    if message.content.startswith("!光よ!"):
        await message.channel.send(file=discord.File("assets/光よ！.jpg"))
        return
    
discord_client.run(DISCORD_TOKEN)