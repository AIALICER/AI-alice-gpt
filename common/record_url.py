import re
import sqlite3
import discord
from typing import Any

from .config_base import OPENAI_FALLBACK_MODEL, gpt_async_client
from . import url_handler
from . import file_handler
from . import gemini_handler as gpt_handler


async def add_memory_with_context(
    message: discord.Message,
    interaction: discord.Interaction = None,
    db_path: str = "",
    display_name: str = "Bot",
) -> None:
    """メッセージからURLやファイルを抽出し、内容を要約して url_memories テーブルに保存する。"""
    if interaction:
        executing_user_id = interaction.user.id
    elif hasattr(message, "author"):
        executing_user_id = message.author.id
    elif hasattr(message, "user"):
        executing_user_id = message.user.id
    else:
        executing_user_id = 0

    channel_id = message.channel.id
    message_link = message.jump_url
    raw_text = message.content
    file_summary = ""

    if message.attachments:
        file_parts = await file_handler.process_attachments(message.attachments[:10])
        if file_parts:
            file_summary = await file_handler.summarize_attachments(raw_text, file_parts)

    url_context = ""
    if raw_text:
        url_contents = await url_handler.process_urls_in_text(raw_text)
        if url_contents:
            url_context = url_handler.format_url_contents(url_contents)

    summary_input = f"User Message: {raw_text}\n"
    if url_context:
        summary_input += f"URL Content: {url_context[:300]}\n"
    if file_summary:
        summary_input += f"File Summary: {file_summary}\n"

    summary_prompt = (
        "以下の情報を元に、このやり取りの内容を30文字程度の日本語で一行要約してください。\n"
        "検索に役立つ具体的なキーワード（技術名、サイト名、エラー内容等）を優先的に含めてください。\n\n"
        f"{summary_input}"
    )

    try:
        config = {
            "system_instruction": "あなたは記憶整理の専門家です。簡潔な一行インデックスを作成してください。",
            "max_output_tokens": 60,
        }
        response = await gpt_handler.generate_content_with_fallback(
            client=gpt_async_client,
            primary_model=OPENAI_FALLBACK_MODEL,
            contents=[{"role": "user", "content": summary_prompt}],
            config=config,
        )
        summary_text = response.text.strip() if hasattr(response, "text") else "内容の解析に失敗しました"
    except Exception as e:
        print(f"[{display_name}] Memory Summary Error: {e}")
        summary_text = raw_text[:30] + "..."

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO url_memories (channel_id, user_id, summary, message_link)
                VALUES (?, ?, ?, ?)
            """,
                (channel_id, executing_user_id, summary_text, message_link),
            )
            conn.commit()
            print(f"[{display_name}] Memory saved for user {executing_user_id}: {summary_text}")
    except Exception as e:
        print(f"[{display_name}] DB Store Error: {e}")


async def find_best_memory_from_limited_list(query: str, limit: int, db_path: str):
    """指定件数の履歴からGPTに最適な1件を選ばせる。"""
    memories = []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, summary, message_link, timestamp FROM url_memories ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            memories = cursor.fetchall()
    except Exception as e:
        print(f"DB Fetch Error: {e}")
        return None

    if not memories:
        return None

    memory_list_text = ""
    for m in memories:
        memory_list_text += f"ID: {m['id']} | 要約: {m['summary']} | 日時: {m['timestamp']}\n"

    config = {
        "system_instruction": "あなたは記憶検索の専門家です。関連するIDを1つだけ抽出してください。",
        "max_output_tokens": 20,
        "temperature": 0.0,
    }

    judgement_prompt = (
        f"以下の履歴から、ユーザーのクエリ『{query}』に最も関連するIDを1つ選んで数字のみ回答してください。\n"
        f"無ければ 'NONE' と回答してください。\n\n"
        f"--- 履歴 ---\n{memory_list_text}"
    )

    try:
        response = await gpt_handler.generate_content_with_fallback(
            client=gpt_async_client,
            primary_model=OPENAI_FALLBACK_MODEL,
            contents=[{"role": "user", "content": judgement_prompt}],
            config=config,
        )

        best_id_text = response.text.strip()
        if "NONE" in best_id_text or not any(char.isdigit() for char in best_id_text):
            return None

        match = re.search(r"\d+", best_id_text)
        if not match:
            return None

        best_id = int(match.group())
        return next((m for m in memories if m["id"] == best_id), None)

    except Exception as e:
        print(f"GPT Judgement Error: {e}")
        return None


async def create_memory_thread(
    interaction: discord.Interaction,
    query: str,
    limit: int,
    db_path: str,
    display_name: str,
    messages: Any,
) -> None:
    best_memory = await find_best_memory_from_limited_list(query, limit, db_path)

    thread = await interaction.channel.create_thread(
        name=f"記憶探索：{query[:10]} (最新{limit}件より)",
        type=discord.ChannelType.private_thread,
    )
    await thread.add_user(interaction.user)

    if best_memory:
        embed = discord.Embed(
            title=messages.MEMORY_TITLE,
            description=messages.MEMORY_DEST,
            color=discord.Color.green(),
        )
        embed.add_field(name="📌 要約", value=best_memory["summary"], inline=False)
        embed.add_field(name="📅 日時", value=best_memory["timestamp"])
        embed.add_field(name="🔗 リンク", value=f"[当時のメッセージへ]({best_memory['message_link']})")

        await thread.send(content=f"{interaction.user.mention}" + messages.MEMORY_CHAT, embed=embed)
    else:
        await thread.send(messages.MEMORY_NOFIND.format(limit=limit, query=query) + messages.MEMORY_ER)

    await interaction.followup.send(f"スレッドを作成しました: {thread.mention}", ephemeral=True)
