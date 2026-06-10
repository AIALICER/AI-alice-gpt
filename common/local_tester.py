import asyncio
import inspect
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


def _ensure_slash_commands_registered(bot):
    """ローカル実行前にスラッシュコマンドを登録する。"""
    if bot.tree.get_commands():
        return

    original_run = bot.client.run
    bot.client.run = lambda _token: None
    try:
        bot.run(local=False, message=None)
    finally:
        bot.client.run = original_run


def _coerce_arg_value(raw_value, parameter):
    """コマンドシグネチャに合わせて引数型を補正する。"""
    annotation = parameter.annotation
    annotation_name = type(annotation).__name__

    if annotation is int or annotation_name == "RangeTransformer":
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return raw_value

    return raw_value


def _parse_command_args(command, args):
    """スラッシュコマンド引数を位置引数/キーワード引数に分解する。"""
    signature = inspect.signature(command.callback)
    parameters = list(signature.parameters.values())[1:]  # interaction を除外
    param_map = {p.name: p for p in parameters}

    raw_positional = []
    raw_kwargs = {}

    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            raw_kwargs[key] = value
        else:
            raw_positional.append(arg)

    positional_params = [p for p in parameters if p.name not in raw_kwargs]
    positional_args = []
    for idx, raw in enumerate(raw_positional):
        if idx < len(positional_params):
            positional_args.append(_coerce_arg_value(raw, positional_params[idx]))
        else:
            positional_args.append(raw)

    kwargs = {}
    for key, raw in raw_kwargs.items():
        if key in param_map:
            kwargs[key] = _coerce_arg_value(raw, param_map[key])
        else:
            kwargs[key] = raw

    return positional_args, kwargs


class MockInteraction:
    def __init__(self, user, channel, command_name, options=None):
        self.user = user
        self.channel = channel
        self.guild = None
        self.channel_id = channel.id
        self.guild_id = None
        self.command_name = command_name
        self.options = options or {}
        self.response = AsyncMock()
        self.response.send_message = AsyncMock(side_effect=self._mock_send_message)
        self.response.defer = AsyncMock()
        self.followup = AsyncMock()
        self.followup.send = AsyncMock(side_effect=self._mock_followup_send)

    async def _mock_send_message(
        self, content=None, embed=None, file=None, ephemeral=False, **kwargs
    ):
        prefix = "[Bot (Ephemeral)]: " if ephemeral else "[Bot]: "
        if content:
            print(f"\n{prefix}{content}")
        if embed:
            print(f"\n{prefix}Embed: {embed.title if hasattr(embed, 'title') else 'No Title'}")
            if hasattr(embed, "description"):
                print(f"{embed.description}")
        return MagicMock(id=int(uuid.uuid4().int >> 64))

    async def _mock_followup_send(self, content=None, embed=None, file=None, **kwargs):
        if content:
            print(f"\n[Bot Followup]: {content}")
        if embed:
            print(
                f"\n[Bot Followup Embed]: {embed.title if hasattr(embed, 'title') else 'No Title'}"
            )
            if hasattr(embed, "description"):
                print(f"{embed.description}")
        return MagicMock(id=int(uuid.uuid4().int >> 64))


async def run_local(bot):
    """ローカル対話モード"""
    print(f"--- {bot.display_name} Local Chat Mode ---")
    setup_bot_mocks(bot)
    _ensure_slash_commands_registered(bot)
    author = MockAuthor()
    channel = MockChannel()
    while True:
        try:
            user_input = await asyncio.to_thread(input, f"\n[{author.display_name}]: ")
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input.strip():
                continue

            # スラッシュコマンドの処理
            if user_input.startswith("/"):
                parts = user_input[1:].split()
                cmd_name = parts[0]
                args = parts[1:]

                # 登録されているコマンドを探す
                command = None
                for cmd in bot.tree.get_commands():
                    if cmd.name == cmd_name:
                        command = cmd
                        break

                if command:
                    print(f"--- Executing Slash Command: /{cmd_name} ---")
                    pos_args, kwargs = _parse_command_args(command, args)

                    interaction = MockInteraction(author, channel, cmd_name, kwargs)
                    try:
                        await command.callback(interaction, *pos_args, **kwargs)
                    except Exception as e:
                        print(f"Error executing command: {e}")
                        import traceback

                        traceback.print_exc()
                else:
                    print(f"Unknown command: /{cmd_name}")
                continue

            message = MockMessage(f"<@{bot.client.user.id}> {user_input}", author, channel)
            await bot._handle_message(message)
        except (EOFError, KeyboardInterrupt):
            break


async def run_single_shot(bot, message_text):
    """シングルショットテスト"""
    setup_bot_mocks(bot)
    _ensure_slash_commands_registered(bot)
    author = MockAuthor()
    channel = MockChannel()

    if message_text.startswith("/"):
        parts = message_text[1:].split()
        cmd_name = parts[0]
        args = parts[1:]

        command = None
        for cmd in bot.tree.get_commands():
            if cmd.name == cmd_name:
                command = cmd
                break

        if command:
            print(f"[{author.display_name}]: {message_text}")
            print(f"--- Executing Slash Command: /{cmd_name} ---")
            pos_args, kwargs = _parse_command_args(command, args)

            interaction = MockInteraction(author, channel, cmd_name, kwargs)
            try:
                await command.callback(interaction, *pos_args, **kwargs)
            except Exception as e:
                print(f"Error executing command: {e}")
                import traceback

                traceback.print_exc()
        else:
            print(f"Unknown command: /{cmd_name}")
        return

    message = MockMessage(f"<@{bot.client.user.id}> {message_text}", author, channel)
    print(f"[{author.display_name}]: {message_text}")
    await bot._handle_message(message)
