"""
ボイスチャンネル会話ハンドラ

ユーザー: VC で声を入れる
アリス: VC テキストチャットに文字で返事する

マイク受信は discord-ext-voice-recv を使う。
Opus デコードは wants_opus=True + 自前デコードで corrupted stream を回避する。
"""

from __future__ import annotations

import asyncio
import audioop
import io
import time
import traceback
import wave
from dataclasses import dataclass, field
from typing import Any

import discord
from discord.ext import voice_recv

from .config_base import OPENAI_MODEL, gpt_async_client, gpt_client
from . import db_handler
from . import gemini_handler as gpt_handler

_DISCORD_RATE = 48000
_CHANNELS = 2
_SAMPLE_WIDTH = 2

# 無音判定（16bit PCM の RMS）— DAVE 平文時はやや小さめでも拾う
_SPEECH_RMS = 120
_SILENCE_SECONDS = 0.55  # 発話終了→Gemini送信までの待ち（短いほど速い）
_MIN_UTTERANCE_SECONDS = 0.35
_MAX_UTTERANCE_SECONDS = 8.0
_MIN_PCM_BYTES = int(_DISCORD_RATE * _CHANNELS * _SAMPLE_WIDTH * _MIN_UTTERANCE_SECONDS)

_VC_ADDRESS_HINTS = (
    "アリス",
    "ありす",
    "alice",
    "AL-1S",
    "AL1S",
)


def _vc_system_addendum(*, human_count: int, speaker: str, members: list[str]) -> str:
    member_line = "、".join(members) if members else "不明"
    if human_count <= 1:
        rule = (
            "VCの人間は話者1人だけです。"
            "ノイズ・無音・明らかな独り言以外は基本的に返答する（判定=返す）。"
        )
    else:
        # 2人以上は同じ緩めルール（以前の3人以上は呼びかけ必須で厳しすぎた）
        rule = (
            f"VCに人間が{human_count}人います。"
            "明らかに他者同士だけの雑談・自分たち同士の会話なら無視（判定=無視）でよい。"
            "ただし次のときは返す（判定=返す）: "
            "アリスへの呼びかけ・質問・意見を求められた、話題にアリスが自然に入れる、"
            "話者がアリスに話しかけている雰囲気がある。"
            "迷ったら無視より返す寄りでよい。"
        )
    return (
        "\n\n[VOICE_CHAT_MODE]\n"
        "あなたは今 Discord のボイスチャットに参加しているアリスです。\n"
        f"話者: {speaker}\n"
        f"VC参加者（人間）: {member_line}（{human_count}人）\n"
        f"{rule}\n"
        "手順:\n"
        "1. 音声を日本語で正確に文字起こしする\n"
        "2. 上の参加人数ルールで、アリスが今返す必要があるか判定する\n"
        "3. 判定=返す のときだけアリスとして1〜4文で返答する\n"
        "出力は次の形式だけ:\n"
        "聞き取り: （文字起こし）\n"
        "判定: 返す または 無視\n"
        "返答: （返すときだけ。無視のときは空か「なし」）\n"
        "音声が無音やノイズだけのときは聞き取りを（聞き取れず）にし、判定=無視。\n"
        "二人称は先生のままです。\n"
    )


def _parse_should_reply(raw: str) -> bool | None:
    """判定行を読む。不明なら None。"""
    for line in raw.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if s.startswith("判定:") or s.startswith("判定："):
            val = s.split(":", 1)[-1].split("：", 1)[-1].strip().lower()
            if any(x in val for x in ("無視", "しない", "no", "skip", "false", "なし")):
                return False
            if any(x in val for x in ("返す", "はい", "yes", "true", "する")):
                return True
    return None


def _local_should_reply_hint(transcript: str, human_count: int) -> bool | None:
    """
    参加人数と文字起こしからの簡易ヒント。
    True/False で確定、None はモデル判定に任せる。
    （複数人でも呼びかけ無しを強制無視しない＝緩め）
    """
    t = (transcript or "").strip()
    if not t or t in {"（聞き取れず）", "(聞き取れず)", "聞き取れず"}:
        return False
    addressed = any(h.lower() in t.lower() for h in _VC_ADDRESS_HINTS)
    if addressed:
        return True
    return None


# Live API は長い system_instruction や不安定な WS で 1008 abort しやすいので短くする
_VC_LIVE_SYSTEM = (
    "あなたはブルーアーカイブのアリスです。先生のマイク音声に日本語で短く答えてください。"
    "二人称は先生です。"
)


def _patch_voice_recv_router() -> None:
    """PacketRouter が OpusError で listen を止めないようにする。"""
    from discord.ext.voice_recv import router as vr_router

    if getattr(vr_router.PacketRouter, "_alice_opus_safe", False):
        return

    def _safe_do_run(self: Any) -> None:
        while not self._end_thread.is_set():
            self.waiter.wait()
            with self._lock:
                for decoder in list(self.waiter.items):
                    try:
                        data = decoder.pop_data()
                    except Exception:
                        continue
                    if data is not None:
                        try:
                            self.sink.write(data.source, data)
                        except Exception:
                            continue

    vr_router.PacketRouter._do_run = _safe_do_run  # type: ignore[method-assign]
    vr_router.PacketRouter._alice_opus_safe = True  # type: ignore[attr-defined]


def _pcm_to_wav_mono16k(pcm_stereo_48k: bytes) -> bytes:
    mono16k = _pcm_to_mono16k(pcm_stereo_48k)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(_SAMPLE_WIDTH)
        wf.setframerate(16000)
        wf.writeframes(mono16k)
    return buf.getvalue()


def _pcm_to_mono16k(pcm_stereo_48k: bytes) -> bytes:
    mono = audioop.tomono(pcm_stereo_48k, _SAMPLE_WIDTH, 0.5, 0.5)
    try:
        mono = audioop.mul(mono, _SAMPLE_WIDTH, 1.8)
    except Exception:
        pass
    pcm16k, _ = audioop.ratecv(mono, _SAMPLE_WIDTH, 1, _DISCORD_RATE, 16000, None)
    return pcm16k


def _dave_decrypt_opus(voice_client: Any, user_id: int, opus: bytes) -> tuple[bytes | None, str]:
    """
    Discord Voice E2EE (DAVE) を復号する。

    Returns:
        (payload, status)
        status: 'none' | 'passthrough' | 'ok' | 'fail' | 'not_ready' | 'drop'
        payload が None のときはそのパケットを捨てる（暗号化のまま Opus 化しない）
    """
    conn = getattr(voice_client, "_connection", None)
    if conn is None:
        return opus, "none"
    session = getattr(conn, "dave_session", None)
    if session is None:
        return opus, "none"

    uid = int(user_id)
    try:
        can_pt = bool(session.can_passthrough(uid))
    except Exception:
        can_pt = False

    ready = bool(getattr(session, "ready", False))
    if not ready:
        return (opus, "passthrough") if can_pt else (opus, "not_ready")

    # 先に decrypt を試し、平文ならそのまま、失敗かつ非 passthrough なら破棄
    try:
        import davey

        decrypted = session.decrypt(uid, davey.MediaType.audio, bytes(opus))
        if decrypted is None:
            return (opus, "passthrough") if can_pt else (None, "drop")
        out = bytes(decrypted)
        if not out:
            return (opus, "passthrough") if can_pt else (None, "drop")
        return out, "ok"
    except Exception as exc:
        msg = str(exc)
        if "UnencryptedWhenPassthroughDisabled" in msg or "Unencrypted" in msg:
            if not getattr(_dave_decrypt_opus, "_logged_unenc", False):
                print(f"[VC] DAVE: 平文パケットをそのまま使用 ({type(exc).__name__})")
                _dave_decrypt_opus._logged_unenc = True  # type: ignore[attr-defined]
            return opus, "passthrough"
        if can_pt:
            return opus, "passthrough"
        if not getattr(_dave_decrypt_opus, "_logged_fail", False):
            print(f"[VC] DAVE decrypt 失敗: {type(exc).__name__}: {exc}")
            _dave_decrypt_opus._logged_fail = True  # type: ignore[attr-defined]
        return None, "drop"


def _patch_voice_recv_dave() -> None:
    """voice_recv PacketDecoder で DAVE 復号（成功時のみ印を付ける）。"""
    from discord.ext.voice_recv import opus as vr_opus

    if getattr(vr_opus.PacketDecoder, "_alice_dave_patched", False):
        return

    _orig = vr_opus.PacketDecoder._process_packet

    def _process_packet(self: Any, packet: Any) -> Any:
        try:
            import davey
        except ImportError:
            return _orig(self, packet)

        vc = getattr(self.sink, "voice_client", None)
        conn = getattr(vc, "_connection", None) if vc is not None else None
        session = getattr(conn, "dave_session", None) if conn is not None else None

        dave_done = False
        if (
            session is not None
            and getattr(session, "ready", False)
            and packet is not None
            and not getattr(packet, "is_silence", lambda: False)()
            and getattr(packet, "decrypted_data", None)
        ):
            member = self._get_cached_member()
            if member is None and vc is not None:
                self._cached_id = vc._get_id_from_ssrc(self.ssrc)
                member = self._get_cached_member()
            if member is not None:
                try:
                    if session.can_passthrough(int(member.id)):
                        # 平文想定。sink 側で再判定させるため印は付けない
                        pass
                    else:
                        packet.decrypted_data = session.decrypt(
                            int(member.id),
                            davey.MediaType.audio,
                            bytes(packet.decrypted_data),
                        )
                        dave_done = True
                except Exception as exc:
                    msg = str(exc)
                    if "Unencrypted" in msg:
                        # このパケットは平文。印なしで sink に渡す
                        pass
                    elif not getattr(_patch_voice_recv_dave, "_logged", False):
                        print(f"[VC] PacketDecoder DAVE 失敗: {type(exc).__name__}: {exc}")
                        _patch_voice_recv_dave._logged = True  # type: ignore[attr-defined]
                        # 暗号化のまま Opus 化しない
                        packet.decrypted_data = b""

        data = _orig(self, packet)
        if dave_done and data is not None:
            try:
                data._alice_dave_done = True  # type: ignore[attr-defined]
            except Exception:
                pass
        return data

    vr_opus.PacketDecoder._process_packet = _process_packet  # type: ignore[method-assign]
    vr_opus.PacketDecoder._alice_dave_patched = True  # type: ignore[attr-defined]


def _log_dave_status(
    voice_client: Any, display_name: str, user_id: int | None = None
) -> None:
    conn = getattr(voice_client, "_connection", None)
    if conn is None:
        print(f"[{display_name}] DAVE: connection なし")
        return
    session = getattr(conn, "dave_session", None)
    version = getattr(conn, "dave_protocol_version", 0)
    if session is None:
        print(f"[{display_name}] DAVE: session なし (protocol={version})")
        return
    ready = getattr(session, "ready", False)
    can_pt: Any = "n/a"
    if user_id is not None:
        try:
            can_pt = bool(session.can_passthrough(int(user_id)))
        except Exception as exc:
            can_pt = f"error:{exc}"
    print(
        f"[{display_name}] DAVE: protocol={version} ready={ready} "
        f"passthrough={can_pt} can_encrypt={getattr(conn, 'can_encrypt', None)}"
    )


@dataclass
class _UserSpeechState:
    buffer: bytearray = field(default_factory=bytearray)
    last_voice_at: float = 0.0
    started_at: float = 0.0
    decoder: discord.opus.Decoder | None = None
    dave_ok: int = 0
    dave_fail: int = 0
    dave_skip: int = 0


class SpeechToTextSink(voice_recv.AudioSink):
    """ユーザー音声をバッファし、無音で区切ってコールバックする。"""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        bot_user_id: int,
        on_utterance,
    ):
        super().__init__()
        self.loop = loop
        self.bot_user_id = bot_user_id
        self.on_utterance = on_utterance
        self._states: dict[int, _UserSpeechState] = {}
        self._flushing: set[int] = set()
        self._dave_status_logged = False
        self._pkt = 0
        self._decode_ok = 0
        self._decode_fail = 0
        self._none_user = 0

    def wants_opus(self) -> bool:
        # DAVE 復号を挟むため opus のまま受け取り、自前で PCM 化する
        return True

    def write(self, user: discord.abc.User | None, data: voice_recv.VoiceData) -> None:
        if user is None:
            self._none_user += 1
            if self._none_user in (1, 50, 200):
                print(f"[VC] user=None の音声パケットをスキップ中 ({self._none_user})")
            return
        if user.id == self.bot_user_id:
            return
        opus = data.opus
        if not opus:
            return

        state = self._states.get(user.id)
        if state is None:
            state = _UserSpeechState(decoder=discord.opus.Decoder())
            self._states[user.id] = state

        raw_opus = opus
        dave_status = "none"
        already = bool(getattr(data, "_alice_dave_done", False))
        if already:
            dave_status = "ok"
            state.dave_ok += 1
        elif self.voice_client is not None:
            if not self._dave_status_logged:
                _log_dave_status(self.voice_client, "VC", user.id)
                self._dave_status_logged = True
            decrypted, dave_status = _dave_decrypt_opus(
                self.voice_client, user.id, raw_opus
            )
            if dave_status == "drop" or decrypted is None:
                state.dave_fail += 1
                self._pkt += 1
                if self._pkt % 50 == 0:
                    print(
                        f"[VC] pkt={self._pkt} drop dave={dave_status} "
                        f"decode_ok={self._decode_ok} decode_fail={self._decode_fail}"
                    )
                return
            opus = decrypted
            if dave_status == "ok":
                state.dave_ok += 1
            elif dave_status == "fail":
                state.dave_fail += 1
            else:
                state.dave_skip += 1

        assert state.decoder is not None
        pcm: bytes | None = None
        try:
            pcm = state.decoder.decode(opus, fec=False)
            self._decode_ok += 1
        except Exception:
            self._decode_fail += 1
            state.dave_fail += 1
            try:
                state.decoder = discord.opus.Decoder()
            except Exception:
                state.decoder = None
            self._pkt += 1
            if self._pkt % 50 == 0:
                print(
                    f"[VC] pkt={self._pkt} decode_fail dave={dave_status} "
                    f"decode_ok={self._decode_ok} decode_fail={self._decode_fail}"
                )
            return
        if not pcm:
            return

        self._pkt += 1
        now = time.monotonic()
        rms = audioop.rms(pcm, _SAMPLE_WIDTH)
        if self._pkt <= 3 or self._pkt % 50 == 0:
            print(
                f"[VC] pkt={self._pkt} rms={rms} dave={dave_status} "
                f"buf={len(state.buffer)} decode_ok={self._decode_ok} "
                f"decode_fail={self._decode_fail}"
            )

        if rms >= _SPEECH_RMS:
            if not state.buffer:
                state.started_at = now
            state.buffer.extend(pcm)
            state.last_voice_at = now
            if (now - state.started_at) >= _MAX_UTTERANCE_SECONDS:
                self._schedule_flush(user, state)
            return

        if state.buffer and state.last_voice_at:
            if (now - state.last_voice_at) >= _SILENCE_SECONDS:
                self._schedule_flush(user, state)

    def _schedule_flush(self, user: discord.abc.User, state: _UserSpeechState) -> None:
        if user.id in self._flushing:
            return
        pcm = bytes(state.buffer)
        dave_ok, dave_fail, dave_skip = state.dave_ok, state.dave_fail, state.dave_skip
        state.buffer.clear()
        state.last_voice_at = 0.0
        state.started_at = 0.0
        state.dave_ok = 0
        state.dave_fail = 0
        state.dave_skip = 0
        try:
            state.decoder = discord.opus.Decoder()
        except Exception:
            state.decoder = None

        if len(pcm) < _MIN_PCM_BYTES:
            return

        rms = audioop.rms(pcm, _SAMPLE_WIDTH)
        self._flushing.add(user.id)

        async def _run() -> None:
            try:
                await self.on_utterance(user, pcm, rms, dave_ok, dave_fail, dave_skip)
            finally:
                self._flushing.discard(user.id)

        asyncio.run_coroutine_threadsafe(_run(), self.loop)

    def cleanup(self) -> None:
        self._states.clear()
        self._flushing.clear()


class VCHandler:
    def __init__(
        self,
        client: discord.Client,
        *,
        system_instruction: str = "",
        display_name: str = "アリス",
        conversation_model: str | None = None,
        db_path: str | None = None,
    ):
        self.client = client
        self.display_name = display_name
        self.system_instruction = system_instruction
        self.conversation_model = conversation_model or OPENAI_MODEL
        self.db_path = db_path

        self.vc: voice_recv.VoiceRecvClient | None = None
        self.channel: discord.VoiceChannel | None = None
        self.audio_sink: SpeechToTextSink | None = None

        self.send_task: asyncio.Task | None = None
        self.receive_task: asyncio.Task | None = None
        self.reply_task: asyncio.Task | None = None

        self._history: list[dict[str, Any]] = []
        self._reply_lock = asyncio.Lock()
        self._busy = False

    @property
    def connected(self) -> bool:
        return self.vc is not None and self.vc.is_connected()

    def is_voice_text_channel(self, channel: discord.abc.Messageable) -> bool:
        if self.channel is None:
            return False
        return getattr(channel, "id", None) == self.channel.id

    def _vc_human_members(self) -> list[discord.Member]:
        if self.channel is None:
            return []
        return [m for m in self.channel.members if not getattr(m, "bot", False)]

    async def _persist_sql(
        self,
        role: str,
        content: str,
        author_name: str | None = None,
    ) -> None:
        """Gemini 文脈とは別に、VC 発話を chat_history へ残す。"""
        if not self.db_path or self.channel is None or not content:
            return
        try:
            await asyncio.to_thread(
                db_handler.save_message,
                self.db_path,
                int(self.channel.id),
                role,
                content,
                author_name,
            )
        except Exception as exc:
            print(f"[{self.display_name}] VC履歴SQL保存エラー: {exc}")

    async def connect_channel(self, channel: discord.VoiceChannel) -> voice_recv.VoiceRecvClient:
        if self.connected:
            await self.disconnect()

        _patch_voice_recv_router()
        _patch_voice_recv_dave()

        existing = discord.utils.get(self.client.voice_clients, guild=channel.guild)
        if existing is not None and existing.is_connected():
            await existing.disconnect(force=True)

        self.channel = channel
        self.vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
        assert self.client.user is not None
        self.audio_sink = SpeechToTextSink(
            loop=self.client.loop,
            bot_user_id=self.client.user.id,
            on_utterance=self._on_utterance,
        )
        self.vc.listen(self.audio_sink)
        print(f"[{self.display_name}] VC接続(音声→文字): {channel.name} ({channel.id})")
        # DAVE ハンドシェイク完了を少し待って状態を出す
        async def _delayed_dave_log() -> None:
            await asyncio.sleep(2.0)
            if self.vc is not None:
                _log_dave_status(self.vc, self.display_name)

        asyncio.create_task(_delayed_dave_log())
        return self.vc

    async def connect_channnel(self, channel: discord.VoiceChannel) -> voice_recv.VoiceRecvClient:
        return await self.connect_channel(channel)

    async def disconnect(self) -> None:
        await self.cleanup_voice_tasks()
        if self.vc is not None:
            try:
                if self.vc.is_listening():
                    self.vc.stop_listening()
                if self.vc.is_playing():
                    self.vc.stop()
                await self.vc.disconnect()
            except Exception as exc:
                print(f"[{self.display_name}] VC切断エラー: {exc}")
        self.vc = None
        self.channel = None
        self.audio_sink = None
        self._history.clear()

    async def cleanup_voice_tasks(self) -> None:
        for task in (self.send_task, self.receive_task, self.reply_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self.send_task = None
        self.receive_task = None
        self.reply_task = None

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.id != self.client.user.id:
            return
        if before.channel is not None and after.channel is None:
            print(f"[{self.display_name}] BotがVCから切断されました")
            await self.cleanup_voice_tasks()
            self.vc = None
            self.channel = None
            self.audio_sink = None

    async def handle_text_message(self, message: discord.Message) -> None:
        """VCテキストからも話せる（補助）。本線はマイク入力。"""
        if message.author.bot:
            return
        if not self.connected or not self.is_voice_text_channel(message.channel):
            return
        text = (message.content or "").strip()
        if not text:
            return
        if self._busy:
            await message.channel.send("少し待ってください！アリスは考え中です…")
            return
        self.reply_task = asyncio.create_task(self._reply_to_text(message.channel, text, message.author))

    async def _on_utterance(
        self,
        user: discord.abc.User,
        pcm: bytes,
        rms: int = 0,
        dave_ok: int = 0,
        dave_fail: int = 0,
        dave_skip: int = 0,
    ) -> None:
        if self.channel is None or not self.connected:
            return
        if self._busy:
            return
        display = getattr(user, "display_name", None) or user.name
        humans = self._vc_human_members()
        sec = len(pcm) / float(_DISCORD_RATE * _CHANNELS * _SAMPLE_WIDTH)
        print(
            f"[{self.display_name}] 音声受信: {display} "
            f"({len(pcm)} bytes, {sec:.1f}s, rms={rms}, humans={len(humans)}, "
            f"dave_ok={dave_ok}, dave_fail={dave_fail}, dave_skip={dave_skip})"
        )
        if rms < 80:
            if len(humans) <= 1:
                await self.channel.send(
                    "……音がほとんど入っていませんでした。マイクがミュートになっていないか確認してください！"
                )
            return
        self.reply_task = asyncio.create_task(self._reply_to_voice(user, pcm))

    async def _reply_to_voice(self, user: discord.abc.User, pcm: bytes) -> None:
        async with self._reply_lock:
            self._busy = True
            try:
                t0 = time.monotonic()
                transcript, should_reply, reply = await self._generate_reply_from_audio(
                    pcm, user
                )
                print(
                    f"[{self.display_name}] VC Gemini所要: {time.monotonic() - t0:.2f}s "
                    f"判定={'返す' if should_reply else '無視'} "
                    f"聞き取り={transcript!r}"
                )
                display = getattr(user, "display_name", None) or user.name
                shown = transcript or "（聞き取れず）"
                tag = "返す" if should_reply else "無視"
                await self._persist_sql(
                    "user",
                    f"[VC音声・{tag}] {shown}",
                    display,
                )
                if should_reply and reply:
                    await self._persist_sql("model", reply, None)
                    print(f"[{self.display_name}] VC DB saved: [VC音声・返す] {shown}")
                elif not should_reply:
                    print(f"[{self.display_name}] VC DB saved: [VC音声・無視] {shown}")

                if not should_reply:
                    return
                if self.channel is not None:
                    try:
                        await self.channel.typing()
                    except Exception:
                        pass
                if not reply:
                    await self.channel.send(
                        "……うまく聞き取れませんでした。もう一度お願いします！"
                    )
                    return
                unheard = transcript in {
                    "（聞き取れず）",
                    "(聞き取れず)",
                    "聞き取れず",
                    "",
                }
                if transcript and not unheard:
                    await self.channel.send(
                        f"**{display}**（聞き取り）: {transcript}\n{reply}"
                    )
                else:
                    await self.channel.send(f"**{display}** へ\n{reply}")
            except Exception as exc:
                print(f"[{self.display_name}] VC音声返信エラー: {exc}")
                traceback.print_exc()
                try:
                    if self.channel is not None:
                        await self.channel.send(
                            f"VC会話でエラーが発生しました…\n詳細: {exc}"
                        )
                except Exception:
                    pass
            finally:
                self._busy = False

    async def _reply_to_text(
        self,
        channel: discord.abc.Messageable,
        text: str,
        author: discord.abc.User,
    ) -> None:
        async with self._reply_lock:
            self._busy = True
            try:
                await channel.typing()
                author_name = getattr(author, "display_name", None) or author.name
                await self._persist_sql(
                    "user",
                    f"[VCテキスト] {text}",
                    author_name,
                )
                reply = await self._generate_reply_text(text)
                if not reply:
                    await channel.send("……うまく返事できませんでした。")
                    return
                await self._persist_sql("model", reply, None)
                await channel.send(reply)
            except Exception as exc:
                print(f"[{self.display_name}] VCテキスト返信エラー: {exc}")
                traceback.print_exc()
            finally:
                self._busy = False

    async def _generate_reply_from_audio_live(
        self, pcm16k_mono: bytes, user: discord.abc.User
    ) -> tuple[str, str]:
        """互換: Live API の代わりに Whisper+GPT を使う。"""
        transcript, should_reply, reply = await self._generate_reply_from_audio(
            pcm16k_mono, user
        )
        if should_reply:
            return transcript, reply
        return transcript, ""

    async def _transcribe_wav(self, wav_bytes: bytes) -> str:
        """OpenAI Whisper で WAV を文字起こしする。"""
        import io as _io

        def _sync() -> str:
            bio = _io.BytesIO(wav_bytes)
            bio.name = "utterance.wav"
            result = gpt_client.audio.transcriptions.create(
                model="whisper-1",
                file=bio,
                language="ja",
            )
            return (getattr(result, "text", None) or "").strip()

        return await asyncio.to_thread(_sync)

    async def _generate_reply_from_audio(
        self, pcm: bytes, user: discord.abc.User
    ) -> tuple[str, bool, str]:
        """音声→聞き取り+返答判定+返答。返す必要がなければ should_reply=False。"""
        display = getattr(user, "display_name", None) or user.name
        humans = self._vc_human_members()
        human_count = len(humans)
        member_names = [
            getattr(m, "display_name", None) or m.name for m in humans
        ]
        wav = await asyncio.to_thread(_pcm_to_wav_mono16k, pcm)
        prompt = (
            f"{display} がマイクで話しました。"
            f"VC人間人数={human_count}。"
            "文字起こしし、参加人数ルールで返答するか判定し、指定形式で答えてください。"
        )
        # Whisper STT -> GPT text reply
        try:
            transcript = await self._transcribe_wav(wav)
        except Exception as exc:
            print(f"[VC Audio] Whisper failed: {exc}")
            return "", False, ""

        if not transcript.strip():
            return "", False, ""

        system_instruction = (self.system_instruction or "") + _vc_system_addendum(
            human_count=human_count,
            speaker=display,
            members=member_names,
        )
        contents: list[Any] = []
        for item in self._history[-6:]:
            role = item.get("role", "user") if isinstance(item, dict) else "user"
            if role == "model":
                role = "assistant"
            texts: list[str] = []
            parts = item.get("parts", []) if isinstance(item, dict) else []
            for part in parts:
                if isinstance(part, dict) and part.get("text"):
                    texts.append(str(part["text"]))
            if texts:
                contents.append({"role": role, "content": "\n".join(texts)})
        contents.append({
            "role": "user",
            "content": (
                f"{prompt}\n\n聞き取り済みテキスト: {transcript}\n"
                "上の形式（聞き取り/判定/返答）で答えてください。"
                f"聞き取り欄には次をそのまま使ってよい: {transcript}"
            ),
        })
        config = {"system_instruction": system_instruction, "max_output_tokens": 500}
        try:
            print(
                f"[VC Audio] GPT model={self.conversation_model} "
                f"humans={human_count} transcript={transcript[:40]!r}"
            )
            response = await gpt_handler.generate_content_with_fallback(
                client=gpt_async_client,
                primary_model=self.conversation_model,
                contents=contents,
                config=config,
                character_name="alice",
            )
        except gpt_handler.CharacterError as exc:
            return transcript, True, exc.character_message

        raw = (getattr(response, "text", None) or "").strip()
        parsed_transcript, should_reply, reply = _parse_voice_response(raw, human_count)
        if parsed_transcript:
            transcript = parsed_transcript
        if should_reply and not reply and raw:
            reply = raw
        if should_reply and reply:
            shown = transcript or "（音声）"
            self._history.append(
                {"role": "user", "parts": [{"text": f"[音声:{display}] {shown}"}]}
            )
            self._history.append({"role": "model", "parts": [{"text": reply}]})
            if len(self._history) > 20:
                self._history = self._history[-20:]
        return transcript, should_reply, reply

    async def _generate_reply_text(self, user_text: str) -> str:
        humans = self._vc_human_members()
        human_count = len(humans)
        member_names = [
            getattr(m, "display_name", None) or m.name for m in humans
        ]
        self._history.append(
            {
                "role": "user",
                "parts": [{"text": f"[VCテキスト] {user_text}"}],
            }
        )
        if len(self._history) > 20:
            self._history = self._history[-20:]

        system_instruction = (self.system_instruction or "") + _vc_system_addendum(
            human_count=human_count,
            speaker="テキスト投稿者",
            members=member_names,
        )
        gpt_history = []
        for item in self._history:
            role = item.get("role", "user")
            if role == "model":
                role = "assistant"
            texts = []
            for part in item.get("parts", []):
                if isinstance(part, dict) and part.get("text"):
                    texts.append(str(part["text"]))
            if texts:
                gpt_history.append({"role": role, "content": "\n".join(texts)})
        config = {"system_instruction": system_instruction, "max_output_tokens": 500}
        try:
            response = await gpt_handler.generate_content_with_fallback(
                client=gpt_async_client,
                primary_model=self.conversation_model,
                contents=gpt_history,
                config=config,
                character_name="alice",
            )
        except gpt_handler.CharacterError as exc:
            return exc.character_message
        reply = (getattr(response, "text", None) or "").strip()
        if reply:
            self._history.append({"role": "model", "parts": [{"text": reply}]})
        return reply


def _parse_voice_response(raw: str, human_count: int = 1) -> tuple[str, bool, str]:
    """聞き取り / 判定 / 返答 を解析する。"""
    if not raw:
        return "", False, ""
    lines = raw.replace("\r\n", "\n").split("\n")
    mode = None
    buf: list[str] = []
    collected: dict[str, str] = {}

    def _flush() -> None:
        nonlocal buf, mode
        if mode and buf:
            collected[mode] = "\n".join(buf).strip()
        buf = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("聞き取り:") or stripped.startswith("聞き取り："):
            _flush()
            mode = "transcript"
            rest = stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            buf = [rest] if rest else []
        elif stripped.startswith("判定:") or stripped.startswith("判定："):
            _flush()
            mode = "judgment"
            rest = stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            buf = [rest] if rest else []
        elif stripped.startswith("返答:") or stripped.startswith("返答："):
            _flush()
            mode = "reply"
            rest = stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            buf = [rest] if rest else []
        else:
            if mode is not None:
                buf.append(line)
            else:
                buf.append(line)
                mode = "reply"
    _flush()

    transcript = collected.get("transcript", "").strip()
    reply = collected.get("reply", "").strip()
    if reply in {"なし", "無", "-", "—", "ー"}:
        reply = ""

    judgment_raw = collected.get("judgment", "")
    should_reply = _parse_should_reply(
        f"判定: {judgment_raw}" if judgment_raw else raw
    )
    local_hint = _local_should_reply_hint(transcript, human_count)
    if local_hint is False:
        should_reply = False
    elif local_hint is True:
        should_reply = True
    elif should_reply is None:
        # 判定行なし: 聞き取れて返答があれば返す（人数によらず緩め）
        should_reply = bool(reply) and transcript not in {
            "（聞き取れず）",
            "(聞き取れず)",
            "聞き取れず",
            "",
        }

    if not should_reply:
        reply = ""
    return transcript, bool(should_reply), reply
