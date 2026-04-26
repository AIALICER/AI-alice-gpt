"""
ファイル処理モジュール

- Discordの添付ファイル処理
- ファイル内容の要約生成
"""

import aiohttp

from .config_base import OPENAI_MODEL, gpt_client


async def process_attachments(attachments) -> list:
    """
    Discordの添付ファイルを処理してGPT API入力形式に変換

    Args:
        attachments: Discord添付ファイルのリスト

    Returns:
        list: OpenAI Responses API content item のリスト
    """
    parts = []

    for attachment in attachments:
        try:
            # ファイルサイズチェック（20MB以下）
            if attachment.size > 20 * 1024 * 1024:
                print(f"File too large: {attachment.filename} ({attachment.size} bytes)")
                continue

            # ファイルをダウンロード（タイムアウト10秒）
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(attachment.url) as resp:
                    if resp.status == 200:
                        file_bytes = await resp.read()

                        # MIMEタイプを取得・調整
                        mime_type = attachment.content_type or "application/octet-stream"
                        if ";" in mime_type:
                            mime_type = mime_type.split(";")[0].strip()

                        # テキストやコードファイルは text/plain に統一
                        if mime_type.startswith("text/") or mime_type in [
                            "application/json",
                            "application/javascript",
                            "application/x-python",
                            "application/x-httpd-php",
                            "application/x-sh",
                            "application/xml",
                        ]:
                            mime_type = "text/plain"

                        if mime_type.startswith("image/"):
                            parts.append({"type": "input_image", "image_url": attachment.url})
                        else:
                            try:
                                text_content = file_bytes.decode("utf-8", errors="replace")
                            except Exception:
                                text_content = "(binary file attached)"
                            if len(text_content) > 3000:
                                text_content = text_content[:3000] + "...(truncated)"
                            parts.append(
                                {
                                    "type": "input_text",
                                    "text": f"[Attached file: {attachment.filename}]\n{text_content}",
                                }
                            )
                        print(f"File added: {attachment.filename} ({mime_type})")
        except Exception as e:
            print(f"File processing error ({attachment.filename}): {e}")

    return parts


async def summarize_attachments(prompt: str, file_parts: list) -> str:
    """
    添付ファイルの内容を1行程度のテキストに要約する

    Args:
        prompt: ユーザーのプロンプト（コンテキスト用）
        file_parts: process_attachments()で取得したパーツリスト

    Returns:
        str: 要約テキスト
    """
    if not file_parts:
        return ""

    summary_instruction = (
        "あなたは優秀なアシスタントです。提供された添付ファイル（画像や書類）の内容を、"
        "後で思い返せるように「1行で」簡潔に説明してください。"
        "例：富士山が写った青空の写真 / 請求書の内容が書かれたPDFファイル"
    )

    try:
        input_items = []
        if prompt:
            input_items.append({"type": "input_text", "text": prompt})
        input_items.extend(file_parts)
        summary_response = gpt_client.responses.create(
            model=OPENAI_MODEL,
            input=[{"role": "user", "content": input_items}],
            instructions=summary_instruction,
            max_output_tokens=120,
        )
        return f" [File summary: {(summary_response.output_text or '').strip()}]"
    except Exception as e:
        print(f"Summary generation error: {e}")
        return " [File attached]"
