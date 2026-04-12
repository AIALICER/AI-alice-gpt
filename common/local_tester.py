import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock


class MockChannel:
    def __init__(self, channel_id=123456789):
        self.id = channel_id
        self.send = AsyncMock(side_effect=self._mock_send)
        self.typing = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
        )

    async def _mock_send(self, content=None, embed=None, file=None, **kwargs):
        if content:
            print(f"\n[Bot]: {content}")
        if embed:
            print(f"\n[Bot Embed]: {embed.title if hasattr(embed, 'title') else 'No Title'}")
            if hasattr(embed, "description"):
                print(f"{embed.description}")
        return MagicMock(id=int(uuid.uuid4().int >> 64))


class MockAuthor:
    def __init__(self, user_id=987654321, display_name="User", name="user_account"):
        self.id = user_id
        self.display_name = display_name
        self.name = name
        self.mention = f"<@{user_id}>"


class MockMessage:
    def __init__(self, content, author, channel):
        self.id = int(uuid.uuid4().int >> 64)
        self.content = content
        self.author = author
        self.channel = channel
        self.attachments = []
        self.channel_mentions = []
        self.mention_everyone = False


def setup_bot_mocks(bot):
    """Botのclientなどをモック化する"""
    if not isinstance(bot.client, MagicMock):
        bot.client = MagicMock()
        bot.client.user = MagicMock()
        bot.client.user.id = 111222333
        bot.client.user.display_name = bot.display_name
        bot.client.user.name = bot.character_name
        bot.client.user.mention = f"<@{bot.client.user.id}>"

        def mock_mentioned_in(message):
            return (
                f"<@{bot.client.user.id}>" in message.content
                or f"<@!{bot.client.user.id}>" in message.content
            )

        bot.client.user.mentioned_in = MagicMock(side_effect=mock_mentioned_in)


async def run_local(bot):
    """ローカル対話モード"""
    print(f"--- {bot.display_name} Local Chat Mode ---")
    setup_bot_mocks(bot)
    author = MockAuthor()
    channel = MockChannel()
    while True:
        try:
            user_input = await asyncio.to_thread(input, f"\n[{author.display_name}]: ")
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input.strip():
                continue
            message = MockMessage(f"<@{bot.client.user.id}> {user_input}", author, channel)
            await bot._handle_message(message)
        except (EOFError, KeyboardInterrupt):
            break


async def run_single_shot(bot, message_text):
    """シングルショットテスト"""
    setup_bot_mocks(bot)
    author = MockAuthor()
    channel = MockChannel()
    message = MockMessage(f"<@{bot.client.user.id}> {message_text}", author, channel)
    print(f"[{author.display_name}]: {message_text}")
    await bot._handle_message(message)
