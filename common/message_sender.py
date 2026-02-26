"""
メッセージ送信処理モジュール

- 長いメッセージの分割送信
- Discord履歴の取得
- 履歴のマージ
- メンションの解決
"""

import discord
import asyncio
from typing import Optional, List, Dict, Any
from . import file_handler


async def send_long_message(
    channel, 
    text: str,
    long_message_notice: str = "Response is too long, generating file..."
) -> None:
    """
    長いメッセージを適切に処理して送信
    
    - 2000文字以内: 通常送信
    - 2000-5000文字: 複数メッセージに分割
    - 5000文字超: テキストファイルとして送信
    
    Args:
        channel: Discordチャンネルオブジェクト
        text: 送信するテキスト
        long_message_notice: ファイル生成時の通知メッセージ
    """
    MAX_LENGTH = 2000
    CHUNK_LENGTH = 1900  # 安全マージン

    if text is None:
        text = "(Empty response)"

    if len(text) <= MAX_LENGTH:
        await channel.send(text)
    elif len(text) <= 5000:
        # 複数メッセージに分割
        chunks = []
        while text:
            if len(text) <= CHUNK_LENGTH:
                chunks.append(text)
                break
            split_pos = text.rfind('\n', 0, CHUNK_LENGTH)
            if split_pos == -1:
                split_pos = CHUNK_LENGTH
            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip()
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                await channel.send(chunk)
            else:
                await channel.send(f"(Part {i+1}/{len(chunks)})\n{chunk}")
    else:
        # テキストファイルとして送信
        import io
        file_bytes = text.encode('utf-8')
        file = discord.File(
            fp=io.BytesIO(file_bytes),
            filename='response.txt'
        )
        await channel.send(long_message_notice, file=file)


async def resolve_mentions(message) -> str:
    """
    メンション形式を読みやすい形式に変換
    
    <@123456789> → @UserName
    <#123456789> → #ChannelName
    
    Args:
        message: Discord message object
    
    Returns:
        str: メンションが解決されたテキスト
    """
    content = message.content
    
    for user in message.mentions:
        content = content.replace(f'<@{user.id}>', f'@{user.display_name}')
        content = content.replace(f'<@!{user.id}>', f'@{user.display_name}')
    
    for channel in message.channel_mentions:
        content = content.replace(f'<#{channel.id}>', f'#{channel.name}')
    
    for role in message.role_mentions:
        content = content.replace(f'<@&{role.id}>', f'@{role.name}')
    
    return content


async def fetch_discord_history(
    channel,
    limit: int = 15,
    bot_id: Optional[int] = None,
    max_chars: int = 500,
    include_attachments: bool = True
) -> List[Dict[str, Any]]:
    """
    Discordチャンネルから直近のメッセージ履歴を取得し、Gemini API形式に変換
    
    Args:
        channel: Discord channel object
        limit: 取得するメッセージ数
        bot_id: BotのユーザーID（Botのメッセージをmodelとして識別）
        max_chars: 1メッセージあたりの最大文字数
        include_attachments: 添付ファイルを含めるかどうか
    
    Returns:
        list: Gemini API形式の履歴リスト
    """
    try:
        messages = []
        attachment_count = 0
        MAX_HISTORY_ATTACHMENTS = 3
        
        async for msg in channel.history(limit=limit):
            # システムメッセージはスキップ
            if msg.type != discord.MessageType.default and msg.type != discord.MessageType.reply:
                continue
            
            has_content = msg.content and msg.content.strip() != ""
            has_attachments = len(msg.attachments) > 0
            
            if not has_content and not has_attachments:
                continue
            
            parts = []
            
            if has_content:
                resolved_content = await resolve_mentions(msg)
                
                if len(resolved_content) > max_chars:
                    resolved_content = resolved_content[:max_chars] + "...(truncated)"
                
                if bot_id and msg.author.id == bot_id:
                    role = "model"
                else:
                    role = "user"
                    resolved_content = f"[{msg.author.display_name}] {resolved_content}"
                
                parts.append({"text": resolved_content})
            else:
                if bot_id and msg.author.id == bot_id:
                    role = "model"
                else:
                    role = "user"
                    parts.append({"text": f"[{msg.author.display_name}] (file attached)"})
            
            # 添付ファイルの処理
            if include_attachments and has_attachments and attachment_count < MAX_HISTORY_ATTACHMENTS:
                try:
                    supported_types = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
                    image_attachments = [
                        att for att in msg.attachments 
                        if att.content_type and att.content_type.split(';')[0] in supported_types
                    ]
                    
                    remaining_slots = MAX_HISTORY_ATTACHMENTS - attachment_count
                    image_attachments = image_attachments[:remaining_slots]
                    
                    if image_attachments:
                        file_parts = await file_handler.process_attachments(image_attachments)
                        if file_parts:
                            parts.extend(file_parts)
                            attachment_count += len(file_parts)
                            print(f"[Discord History] Added {len(file_parts)} attachments (msg ID: {msg.id})")
                except asyncio.TimeoutError:
                    print(f"[WARNING] Attachment download timeout (msg ID: {msg.id})")
                except Exception as att_error:
                    print(f"[WARNING] Attachment processing error: {att_error}")
            
            messages.append({
                "role": role,
                "parts": parts,
                "_msg_id": msg.id,
                "_timestamp": msg.created_at
            })
        
        # 古い順にソート
        messages.sort(key=lambda x: x["_timestamp"])
        
        # 内部用フィールドを削除
        for msg in messages:
            del msg["_msg_id"]
            del msg["_timestamp"]
        
        print(f"[Discord History] Retrieved {len(messages)} messages (channel: {getattr(channel, 'name', f'DM-{channel.id}')}, attachments: {attachment_count})")
        return messages
    
    except discord.Forbidden:
        print(f"[WARNING] No permission to read history for channel {channel.id}")
        return []
    except discord.HTTPException as e:
        print(f"[ERROR] Discord history fetch error: {e}")
        return []
    except Exception as e:
        print(f"[ERROR] Unexpected error (Discord history): {e}")
        return []


def merge_histories(
    discord_history: List[Dict[str, Any]], 
    db_history: List[Dict[str, Any]], 
    max_total: int = 15
) -> List[Dict[str, Any]]:
    """
    Discord履歴とDB履歴をマージ
    
    優先順位:
    1. Discord履歴を優先（より最新で正確）
    2. DB履歴は補完用
    
    Args:
        discord_history: fetch_discord_history()の戻り値
        db_history: get_recent_history()の戻り値
        max_total: マージ後の最大件数
    
    Returns:
        list: マージされた履歴
    """
    if not discord_history:
        return db_history[:max_total] if db_history else []
    
    if not db_history:
        return discord_history[:max_total]
    
    # Discord履歴を優先しつつ、DB履歴で不足分を補完
    merged = discord_history.copy()

    remaining = max_total - len(merged)
    if remaining > 0:
        merged.extend(db_history[-remaining:])

    if len(merged) > max_total:
        merged = merged[-max_total:]

    print(f"[History Merge] Discord: {len(discord_history)}, DB: {len(db_history)} -> Result: {len(merged)}")
    return merged
