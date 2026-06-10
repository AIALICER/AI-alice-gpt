#!/usr/bin/env python3
"""AI-Alice から AI-Alice-gpt へ機能を同期（GPT API 部分は維持）。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

REF = Path(r"C:\Users\uchid\AI-Alice")
DST = Path(__file__).resolve().parents[1]

COPY_AS_IS = [
    "common/error_messages.py",
    "common/fuzzy_matcher.py",
    "common/github_issue_handler.py",
    "common/good_example_handler.py",
    "common/game_sale_handler.py",
    "check_game_sales.py",
    "AGENTS.md",
    "ai-instructions.md",
    "characters/momoi",
    "characters/peroro",
]

COPY_THEN_PATCH = [
    "common/local_tester.py",
    "common/message_sender.py",
    "common/record_url.py",
    "common/url_handler.py",
    "common/__init__.py",
    "characters/bot_id_list.py",
    "characters/AL_1S/messages.py",
    "characters/AL_1S/alice.py",
    "characters/Key/Key.py",
    "characters/Yuka/Yuka.py",
    "characters/momoi/momoi.py",
    "characters/peroro/peroro.py",
    "pyproject.toml",
    "README.md",
]

SKIP_IN_TOOLS = {"build", "dist", "dist_staging", "__pycache__", ".pyc"}


def copy_tree_filtered(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if any(part in SKIP_IN_TOOLS for part in rel.parts):
            continue
        if item.is_dir():
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def patch_bot_base(text: str) -> str:
    text = text.replace("from google.genai import types\n", "")
    text = text.replace("    gemini_handler,", "    gemini_handler as gpt_handler,")
    text = text.replace(
        "     GeminiModels,\n     USER_BIRTHDAY_CHANNEL_ID,\n     gemini_client,",
        "     OPENAI_MODEL,\n     OPENAI_FALLBACK_MODEL,\n     USER_BIRTHDAY_CHANNEL_ID,\n     gpt_async_client,",
    )
    text = text.replace("gemini_handler.", "gpt_handler.")
    text = text.replace("gemini_client", "gpt_async_client")
    text = text.replace("GeminiModels.MAIN", "OPENAI_MODEL")
    text = text.replace("GeminiModels.LIGHT", "OPENAI_FALLBACK_MODEL")
    text = text.replace("GeminiModels.OLD", "OPENAI_MODEL")
    text = text.replace("generate_game_descriptions_with_gemini", "generate_game_descriptions_with_gpt")
    text = text.replace("_process_gemini_request", "_process_gpt_request")
    text = text.replace("google_link:types.Part", "google_link: dict | None")
    text = text.replace('print(f"[{self.display_name}] Gemini model:', 'print(f"[{self.display_name}] GPT model:')
    text = text.replace('"""会話で使う Gemini モデル名', '"""会話で使う GPT モデル名')
    text = text.replace('with timer.measure_step("Gemini API 呼び出し"):', 'with timer.measure_step("GPT API 呼び出し"):')
    text = text.replace(
        'ブルアカキャラ誕生日の告知メッセージをGemini APIで生成する。',
        'ブルアカキャラ誕生日の告知メッセージをGPT APIで生成する。',
    )
    text = text.replace('"""Gemini APIへのリクエストを処理', '"""GPT APIへのリクエストを処理')

    text = text.replace(
        'tools.append(types.Tool(google_search=types.GoogleSearch()))',
        'tools.append({"type": "web_search_preview"})',
    )

    text = re.sub(
        r'current_parts\.append\(\{"text": ([^}]+)\}\)',
        r'current_parts.append({"type": "input_text", "text": \1})',
        text,
    )
    text = re.sub(
        r'current_parts\.append\(\s*\{\s*"text":',
        'current_parts.append({"type": "input_text", "text":',
        text,
    )
    text = text.replace(
        'current_parts[0]["text"] =',
        'current_parts[0]["text"] =',
    )

    text = text.replace(
        'input_contents = history + [{"role": "user", "parts": current_parts}]',
        'input_contents = history + [{"role": "user", "content": current_parts}]',
    )

    text = text.replace(
        """            current_config = types.GenerateContentConfig(
                system_instruction=full_system_instruction,
                tools=tools,
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
            )""",
        """            current_config = {
                "system_instruction": full_system_instruction,
                "tools": tools,
                "reasoning_level": thinking_level,
                "max_output_tokens": 2000,
            }""",
    )

    text = text.replace(
        """                retry_config = types.GenerateContentConfig(
                    system_instruction=full_system_instruction,
                    tools=tools,
                    thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                )""",
        """                retry_config = {
                    "system_instruction": full_system_instruction,
                    "tools": tools,
                    "reasoning_level": "minimal",
                    "max_output_tokens": 1200,
                }""",
    )

    text = text.replace(
        'await asyncio.to_thread(\n                    db_handler.save_message,\n                    self.db_path,\n                    current_channel_id,\n                    "model",',
        'await asyncio.to_thread(\n                    db_handler.save_message,\n                    self.db_path,\n                    current_channel_id,\n                    "assistant",',
    )

  # birthday messages
    birthday_block_old = """            response = await gpt_async_client.aio.models.generate_content(
                model=OPENAI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=self.system_instruction),
            )
            return response.text.strip() if response and response.text else fallback"""
    birthday_block_new = """            response = await gpt_handler.generate_content_with_fallback(
                client=gpt_async_client,
                primary_model=OPENAI_MODEL,
                contents=[{"role": "user", "content": prompt}],
                config={"system_instruction": self.system_instruction, "max_output_tokens": 300},
            )
            return response.text.strip() if response and response.text else fallback"""
    text = text.replace(birthday_block_old, birthday_block_new)

    issue_block_old = """            response = await gpt_async_client.aio.models.generate_content(
                model=OPENAI_FALLBACK_MODEL,
                contents=gemini_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                ),
            )"""
    issue_block_new = """            response = await gpt_handler.generate_content_with_fallback(
                client=gpt_async_client,
                primary_model=OPENAI_FALLBACK_MODEL,
                contents=[{"role": "user", "content": gemini_prompt}],
                config={"system_instruction": self.system_instruction, "max_output_tokens": 800},
            )"""
    text = text.replace(issue_block_old, issue_block_new)

    # youtube: types.Part.from_uri -> text note
    text = text.replace(
        """                if youtube_match:
                    video_url = youtube_match.group(0)
                    youtube_cont=types.Part.from_uri(
                     file_uri=video_url,
                     mime_type='video/mp4')
                    prompt = prompt.replace(video_url, "").strip()""",
        """                if youtube_match:
                    video_url = youtube_match.group(0)
                    youtube_cont = {"type": "input_text", "text": f"[YouTube URL] {video_url}"}
                    prompt = prompt.replace(video_url, "").strip()""",
    )

    # twitter image: types.Part.from_bytes -> input_image
    text = text.replace(
        """                            twitter_part = types.Part.from_bytes(
                                data=image_data,
                                mime_type="image/jpeg"
                            )
                            file_parts.append(twitter_part)""",
        """                            file_parts.append({"type": "input_image", "image_url": image_url})""",
    )

    # history URL parsing: parts -> content
    text = text.replace(
        """                    for history_item in history[-8:]:
                        for part in history_item.get("parts", []):
                            text = part.get("text") if isinstance(part, dict) else None
                            if text:
                                history_texts.append(text)""",
        """                    for history_item in history[-8:]:
                        history_content = history_item.get("content", "")
                        if isinstance(history_content, str):
                            history_texts.append(history_content)
                        elif isinstance(history_content, list):
                            for part in history_content:
                                if isinstance(part, dict) and part.get("type") == "input_text":
                                    history_texts.append(part.get("text", ""))""",
    )

    # simplify extract response for GPTResponse
    extract_old = '''    async def _extract_response_text(
        self, response, input_contents: list, full_system_instruction: str, tools: list
    ) -> str:
        """レスポンスからテキストを安全に抽出"""

        bot_response_text = None

        try:
            # 方法1: response.text を直接取得
            if response and hasattr(response, "text") and response.text:
                bot_response_text = response.text

            # 方法2: candidates.content.parts から取得
            if (
                not bot_response_text
                and response
                and hasattr(response, "candidates")
                and response.candidates
            ):
                first_candidate = response.candidates[0]
                if hasattr(first_candidate, "content") and first_candidate.content:
                    if hasattr(first_candidate.content, "parts") and first_candidate.content.parts:
                        parts_text = []
                        for part in first_candidate.content.parts:
                            if hasattr(part, "text") and part.text:
                                parts_text.append(part.text)
                        if parts_text:
                            bot_response_text = "".join(parts_text)

            # 空レスポンス時のリトライ
            if not bot_response_text:
                print(f"[{self.display_name}] Empty, retrying...")
                retry_config = {
                    "system_instruction": full_system_instruction,
                    "tools": tools,
                    "reasoning_level": "minimal",
                    "max_output_tokens": 1200,
                }
                retry_model = self._conversation_model_name()
                retry_strict = getattr(self, "test_model_name", None) is not None
                retry_response = await gpt_handler.generate_content_with_fallback(
                    client=gpt_async_client,
                    primary_model=retry_model,
                    contents=input_contents,
                    config=retry_config,
                    strict_primary_model=retry_strict,
                )
                if retry_response and hasattr(retry_response, "text") and retry_response.text:
                    bot_response_text = retry_response.text
                else:
                    print(f"[{self.display_name}] Retry failed")

            if not bot_response_text:
                print(f"[{self.display_name}] Extract failed")
                bot_response_text = self.messages.RESPONSE_FAILED

        except Exception as extract_error:
            print(
                f"[{self.display_name}] Extract error: {type(extract_error).__name__}: {extract_error}"
            )
            bot_response_text = self.messages.RESPONSE_FAILED

        return bot_response_text'''

    extract_new = '''    async def _extract_response_text(
        self, response, input_contents: list, full_system_instruction: str, tools: list
    ) -> str:
        """レスポンスからテキストを安全に抽出"""
        bot_response_text = None
        try:
            if response and hasattr(response, "text") and response.text:
                bot_response_text = response.text
            if not bot_response_text:
                print(f"[{self.display_name}] Empty, retrying...")
                retry_config = {
                    "system_instruction": full_system_instruction,
                    "tools": tools,
                    "reasoning_level": "minimal",
                    "max_output_tokens": 1200,
                }
                retry_response = await gpt_handler.generate_content_with_fallback(
                    client=gpt_async_client,
                    primary_model=self._conversation_model_name(),
                    contents=input_contents,
                    config=retry_config,
                )
                if retry_response and hasattr(retry_response, "text") and retry_response.text:
                    bot_response_text = retry_response.text
            if not bot_response_text:
                bot_response_text = self.messages.RESPONSE_FAILED
        except Exception as extract_error:
            print(
                f"[{self.display_name}] Extract error: {type(extract_error).__name__}: {extract_error}"
            )
            bot_response_text = self.messages.RESPONSE_FAILED
        return bot_response_text'''

    text = text.replace(extract_old, extract_new)

    return text


def patch_game_sale_handler(text: str) -> str:
    text = text.replace("generate_game_descriptions_with_gemini", "generate_game_descriptions_with_gpt")
    text = text.replace("Gemini でアリス口調", "GPT でアリス口調")
    text = text.replace("[Gemini Game Desc]", "[GPT Game Desc]")
    text = text.replace("from google.genai import types\n\n    from .config_base import GeminiModels, gemini_client\n    from .gemini_handler import generate_content_with_fallback", "from .config_base import OPENAI_MODEL, gpt_async_client\n    from . import gemini_handler as gpt_handler")
    text = text.replace(
        """        config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION if _SYSTEM_INSTRUCTION else None,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
            max_output_tokens=1000,
            temperature=0.3,
        )

        response = await generate_content_with_fallback(
            gemini_client,
            GeminiModels.MAIN,
            prompt,
            config,
            needs_search=False,
            character_name="alice",
        )""",
        """        config = {
            "system_instruction": _SYSTEM_INSTRUCTION if _SYSTEM_INSTRUCTION else None,
            "max_output_tokens": 1000,
            "temperature": 0.3,
        }

        response = await gpt_handler.generate_content_with_fallback(
            gpt_async_client,
            OPENAI_MODEL,
            [{"role": "user", "content": prompt}],
            config,
            character_name="alice",
        )""",
    )
    return text


def patch_record_url(text: str) -> str:
    text = text.replace("from .config_base import GeminiModels, gemini_client", "from .config_base import OPENAI_MODEL, gpt_async_client")
    text = text.replace("from . import gemini_handler", "from . import gemini_handler as gpt_handler")
    text = text.replace("gemini_handler.", "gpt_handler.")
    text = text.replace("gemini_client", "gpt_async_client")
    text = text.replace("GeminiModels.MAIN", "OPENAI_MODEL")
    text = text.replace("GeminiModels.LIGHT", "OPENAI_FALLBACK_MODEL")
    text = text.replace("types.GenerateContentConfig", "dict")
    return text


def patch_bot_model_cli(text: str) -> str:
    return text.replace("Gemini", "GPT").replace("gemini", "gpt").replace(
        "from .config_base import GeminiModels",
        "from .config_base import OPENAI_MODEL, OPENAI_FALLBACK_MODEL",
    ).replace(
        "GeminiModels.MAIN", "OPENAI_MODEL"
    ).replace(
        "GeminiModels.FLASH_35", "OPENAI_FALLBACK_MODEL"
    ).replace(
        "GeminiModels.OLD", "OPENAI_MODEL"
    ).replace(
        "-gemini-3.5-flash", "-gpt-fallback"
    ).replace(
        "--gemini-3.5-flash", "--gpt-fallback"
    ).replace(
        "gemini_preset", "gpt_preset"
    ).replace(
        'dest="gemini_preset"', 'dest="gpt_preset"'
    ).replace(
        "ns.gemini_preset", "ns.gpt_preset"
    )


def patch_character_script(text: str) -> str:
    text = text.replace("GEN_API_KEY: Google Gemini API Key", "OPENAI_API_KEY: OpenAI API Key")
    text = text.replace("-gemini-3.5-flash", "-gpt-fallback")
    text = text.replace("--gemini-3.5-flash", "--gpt-fallback")
    text = text.replace("gemini-2.5-flash", "gpt-4o-mini")
    return text


def patch_common_init(text: str) -> str:
    text = text.replace("Gemini API", "GPT API")
    text = text.replace("gemini_client", "gpt_async_client")
    text = text.replace("GeminiModels", "OPENAI_MODEL")
    return text


def main() -> None:
    for rel in COPY_AS_IS:
        src = REF / rel
        dst = DST / rel
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            copy_tree_filtered(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        print(f"copied: {rel}")

    tools_src = REF / "tools"
    tools_dst = DST / "tools"
    if tools_dst.exists():
        shutil.rmtree(tools_dst)
    copy_tree_filtered(tools_src, tools_dst)
    print("copied: tools/")

    for rel in COPY_THEN_PATCH:
        src = REF / rel
        dst = DST / rel
        if not src.exists():
            print(f"skip missing: {rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        content = src.read_text(encoding="utf-8")
        if rel == "common/record_url.py":
            content = patch_record_url(content)
        elif rel.endswith(".py") and "characters/" in rel:
            content = patch_character_script(content)
        elif rel == "common/__init__.py":
            content = patch_common_init(content)
        dst.write_text(content, encoding="utf-8")
        print(f"patched copy: {rel}")

    bot_src = (REF / "common/bot_base.py").read_text(encoding="utf-8")
    bot_dst = DST / "common/bot_base.py"
    bot_dst.write_text(patch_bot_base(bot_src), encoding="utf-8")
    print("patched: common/bot_base.py")

    game_src = (DST / "common/game_sale_handler.py").read_text(encoding="utf-8")
    (DST / "common/game_sale_handler.py").write_text(patch_game_sale_handler(game_src), encoding="utf-8")
    print("patched: common/game_sale_handler.py")

    cli_src = (REF / "common/bot_model_cli.py").read_text(encoding="utf-8")
    (DST / "common/bot_model_cli.py").write_text(patch_bot_model_cli(cli_src), encoding="utf-8")
    print("patched: common/bot_model_cli.py")

    # merge bot_id_list: keep normal
    bot_id_path = DST / "characters/bot_id_list.py"
    text = bot_id_path.read_text(encoding="utf-8")
    if '"normal"' not in text:
        text = text.replace(
            '    "peroro": {\n        "bot_id": 1509808752805806200,\n        "display_name": "ペロロ様",\n    },\n}',
            '    "peroro": {\n        "bot_id": 1509808752805806200,\n        "display_name": "ペロロ様",\n    },\n    "normal": {\n        "bot_id": None,\n        "display_name": "AIノーマル",\n    },\n}',
        )
        text = text.replace(
            '    "peroro": None,\n}',
            '    "peroro": None,\n    "normal": "alice",\n}',
        )
        bot_id_path.write_text(text, encoding="utf-8")
        print("merged: normal into bot_id_list.py")

    # compose.yaml: reference + normal service
    compose_src = (REF / "compose.yaml").read_text(encoding="utf-8")
    if "normal:" not in compose_src:
        compose_src = compose_src.replace(
            "\nnetworks:",
            """
  # normal Discord Bot
  normal:
    build: .
    container_name: ai-normal
    command: python characters/normal/Normal.py
    restart: unless-stopped
    stop_grace_period: 10s
    env_file:
      - .env
    environment:
      - PYTHONUNBUFFERED=1
    networks:
      - shared-network
    volumes:
      - ./data:/app/data
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:""",
        )
    (DST / "compose.yaml").write_text(compose_src, encoding="utf-8")
    print("updated: compose.yaml")

    # requirements: gpt deps + reference extras
    req_lines = [
        "discord.py>=2.0.0",
        "openai>=1.100.0",
        "aiohttp>=3.8.0",
        "python-dotenv>=1.0.0",
        "beautifulsoup4>=4.12.0",
        "requests>=2.31.0",
        "thefuzz[speedup]>=0.22.0",
        "PyJWT[crypto]>=2.8.0",
    ]
    (DST / "requirements.txt").write_text("\n".join(req_lines) + "\n", encoding="utf-8")
    print("updated: requirements.txt")

    # .env.example merge
    env_example = """# アリス用Discord Bot Token
DISCORD_TOKEN=YOUR_TOKEN

# ケイ用Discord Bot Token
KEI_DISCORD_TOKEN=YOUR_TOKEN

# ユウカ用Discord Bot Token
YUKA_DISCORD_TOKEN=YOUR_TOKEN

# モモイ用Discord Bot Token
MOMOI_DISCORD_TOKEN=YOUR_TOKEN

# ペロロ用Discord Bot Token
PERORO_DISCORD_TOKEN=YOUR_TOKEN

# normal用Discord Bot Token
NORMAL_DISCORD_TOKEN=YOUR_TOKEN

# OpenAI API Key
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_API_KEY_2=YOUR_OPENAI_API_KEY
OPENAI_MODEL=gpt-4o-mini
OPENAI_FALLBACK_MODEL=gpt-4.1-mini

# GitHub Issue 作成（GitHub App 推奨）
GITHUB_APP_ID=4014615
GITHUB_APP_PRIVATE_KEY_PATH=secrets/github-app.pem
GITHUB_OWNER=Aosy0
GITHUB_REPO=AI-Alice

# ブルアカキャラ誕生日の告知チャンネルID（お遊戯会）
BLUEARCHIVE_BIRTHDAY_CHANNEL_ID=YOUR_CHANNNEL_ID
"""
    (DST / ".env.example").write_text(env_example, encoding="utf-8")
    print("updated: .env.example")

    # enhance gemini_handler with CharacterError + character_name param
    handler_path = DST / "common/gemini_handler.py"
    handler = handler_path.read_text(encoding="utf-8")
    if "class CharacterError" not in handler:
        handler = handler.replace(
            "@dataclass\nclass GPTResponse:",
            'class CharacterError(Exception):\n    """キャラクター別エラーメッセージを保持する例外クラス"""\n\n    def __init__(self, message: str, original_exception: Exception | None = None):\n        super().__init__(message)\n        self.original_exception = original_exception\n        self.character_message = message\n\n\n@dataclass\nclass GPTResponse:',
        )
    if "character_name: str" not in handler.split("async def generate_content_with_fallback")[1][:200]:
        handler = handler.replace(
            "async def generate_content_with_fallback(client, primary_model: str, contents, config):",
            "async def generate_content_with_fallback(\n    client,\n    primary_model: str,\n    contents,\n    config,\n    needs_search: bool = False,\n    character_name: str = \"alice\",\n    *,\n    strict_primary_model: bool = False,\n):",
        )
        handler = handler.replace(
            "    raise last_exception or Exception(\"All models and keys failed.\")",
            """    from .error_messages import get_character_error_message

    error_str = str(last_exception) if last_exception else ""
    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
        error_type = "quota"
    elif _is_timeout_error(error_str):
        error_type = "timeout"
    else:
        error_type = "default"
    error_message = get_character_error_message(character_name, error_type)
    raise CharacterError(error_message, last_exception)""",
        )
    handler_path.write_text(handler, encoding="utf-8")
    print("enhanced: common/gemini_handler.py")

    # Normal.py: add bot_model_cli like others
    normal_py = DST / "characters/normal/Normal.py"
    if normal_py.exists():
        normal_py.write_text(
            normal_py.read_text(encoding="utf-8")
            .replace("import argparse\n\n    parser = argparse.ArgumentParser()\n    parser.add_argument(\"--local\", action=\"store_true\")\n    parser.add_argument(\"-m\", \"--message\")\n    args = parser.parse_args()",
                     "from common.bot_model_cli import parse_bot_run_args\n\n    args = parse_bot_run_args()")
            .replace("bot.run(local=args.local, message=args.message)", "bot.run(local=args.local, message=args.message, model_name=args.model_name)"),
            encoding="utf-8",
        )
        print("updated: characters/normal/Normal.py")

    characters_init = DST / "characters/__init__.py"
    characters_init.write_text(
        '''"""
characters - キャラクター設定パッケージ

各キャラクター固有の設定、メッセージ、システムインストラクションを管理する。

利用可能なキャラクター:
- AL_1S: 天童アリス
- Key: ケイ
- Yuka: ユウカ
- momoi: モモイ
- peroro: ペロロ
- normal: ノーマル

Bot IDの一元管理:
- bot_id_list.py: 全キャラクターのDiscord Bot IDを管理
"""

from . import bot_id_list
''',
        encoding="utf-8",
    )
    print("updated: characters/__init__.py")


if __name__ == "__main__":
    main()
