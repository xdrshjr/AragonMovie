"""Volcano Engine (Doubao) TTS 2.0 service — v3 bidirectional WebSocket.

Why a dedicated service
-----------------------
The Volcano speech gateway has **no** one-shot HTTP synthesis route for the
2.0 voices: ``/api/v1/tts`` answers ``401 load grant: requested grant not found``
for a modern API key, and the OpenAI-compatible ``/audio/speech`` shape does not
exist at all. Synthesis happens over a bidirectional WebSocket
(``wss://openspeech.bytedance.com/api/v3/tts/bidirection``) using the event-coded
binary protocol:

    StartConnection -> ConnectionStarted
    StartSession    -> SessionStarted
    TaskRequest + FinishSession -> AudioOnlyServer frames ... SessionFinished

The credential is a plain API key sent as ``X-Api-Key``; ``X-Api-Resource-Id``
selects the granted resource (``seed-tts-2.0`` for the standard 2.0 timbres,
``volc.megatts.timbre`` for a cloned 2.0 timbre).

This module returns **raw audio bytes** and is deliberately transport-only: the
caller (:class:`services.tts_service.TTSService`) owns retries, container
sniffing and file naming, so the pipeline keeps a single TTS code path.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import struct
import uuid
from enum import IntEnum
from typing import Any, Dict, Optional

from config.settings import settings

WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
DEFAULT_RESOURCE_ID = "seed-tts-2.0"
DEFAULT_VOICE = "zh_female_xiaohe_uranus_bigtts"
DEFAULT_TIMEOUT = 120.0


class MsgType(IntEnum):
    FullClientRequest = 0b0001
    FullServerResponse = 0b1001
    AudioOnlyServer = 0b1011
    Error = 0b1111


class Flag(IntEnum):
    NoSeq = 0b0000
    PosSeq = 0b0001
    WithEvent = 0b0100


class Event(IntEnum):
    StartConnection = 1
    FinishConnection = 2
    ConnectionStarted = 50
    ConnectionFailed = 51
    ConnectionFinished = 52
    StartSession = 100
    CancelSession = 101
    FinishSession = 102
    SessionStarted = 150
    SessionFinished = 152
    SessionFailed = 153
    TaskRequest = 200


CONNECTION_LEVEL_EVENTS = {
    Event.StartConnection,
    Event.FinishConnection,
    Event.ConnectionStarted,
    Event.ConnectionFailed,
    Event.ConnectionFinished,
}
CONNECT_ID_EVENTS = {
    Event.ConnectionStarted,
    Event.ConnectionFailed,
    Event.ConnectionFinished,
}


class VolcTTSError(Exception):
    """Volcano TTS failure with an actionable message."""

    def __init__(self, message: str, *, code: Optional[str] = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def build_event_message(event: Event, session_id: str, payload: Dict[str, Any]) -> bytes:
    body = io.BytesIO()
    body.write(struct.pack(">i", int(event)))
    if event not in CONNECTION_LEVEL_EVENTS and session_id:
        sid = session_id.encode("utf-8")
        body.write(struct.pack(">I", len(sid)))
        body.write(sid)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    body.write(struct.pack(">I", len(data)))
    body.write(data)
    header = bytes([0x11, (MsgType.FullClientRequest << 4) | Flag.WithEvent, (0b0001 << 4) | 0b0000, 0x00])
    return header + body.getvalue()


def parse_server_message(data: bytes) -> Dict[str, Any]:
    msg_type = data[1] >> 4
    flags = data[1] & 0x0F
    offset = (data[0] & 0x0F) * 4
    out: Dict[str, Any] = {
        "type": msg_type,
        "flags": flags,
        "sequence": None,
        "event": None,
        "session_id": "",
        "connect_id": "",
        "error_code": None,
        "payload": b"",
    }
    if msg_type == MsgType.Error:
        if len(data) >= offset + 8:
            out["error_code"] = struct.unpack(">I", data[offset:offset + 4])[0]
            size = struct.unpack(">I", data[offset + 4:offset + 8])[0]
            out["payload"] = data[offset + 8:offset + 8 + size]
        return out
    if flags in (Flag.PosSeq, 0b0011):
        out["sequence"] = struct.unpack(">i", data[offset:offset + 4])[0]
        offset += 4
    if flags == Flag.WithEvent:
        out["event"] = struct.unpack(">i", data[offset:offset + 4])[0]
        offset += 4
        if out["event"] not in {int(e) for e in CONNECTION_LEVEL_EVENTS}:
            size = struct.unpack(">I", data[offset:offset + 4])[0]
            offset += 4
            out["session_id"] = data[offset:offset + size].decode("utf-8", "replace")
            offset += size
        if out["event"] in {int(e) for e in CONNECT_ID_EVENTS}:
            size = struct.unpack(">I", data[offset:offset + 4])[0]
            offset += 4
            out["connect_id"] = data[offset:offset + size].decode("utf-8", "replace")
            offset += size
    if len(data) >= offset + 4:
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        out["payload"] = data[offset + 4:offset + 4 + size]
    return out


class VolcTTS2Service:
    """火山引擎语音合成 2.0（v3 双向 WebSocket 合成）。"""

    SERVICE_NAME = "Volcano TTS 2.0"
    DEFAULT_VOICE = DEFAULT_VOICE
    DEFAULT_RESOURCE_ID = DEFAULT_RESOURCE_ID

    def __init__(
        self,
        api_key: Optional[str] = None,
        resource_id: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        sample_rate: Optional[int] = None,
        ws_url: Optional[str] = None,
    ):
        self.api_key = api_key or getattr(settings, "tts_volc_api_key", "")
        self.resource_id = (
            resource_id or getattr(settings, "tts_volc_resource_id", DEFAULT_RESOURCE_ID) or DEFAULT_RESOURCE_ID
        )
        self.voice = voice or getattr(settings, "tts_volc_voice", DEFAULT_VOICE) or DEFAULT_VOICE
        self.speed = float(speed or getattr(settings, "tts_volc_speed", 1.0) or 1.0)
        self.sample_rate = int(sample_rate or getattr(settings, "tts_volc_sample_rate", 24000) or 24000)
        self.ws_url = ws_url or WS_URL
        self.logger = logging.getLogger(__name__)

        if not self.api_key:
            self.logger.warning("VolcTTS2Service initialized without API key")

    # ------------------------------------------------------------------ synth

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        audio_format: str = "mp3",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> bytes:
        """Synthesize ``text`` and return raw audio bytes (mp3 by default)."""
        text = (text or "").strip()
        if not text:
            raise VolcTTSError("TTS input text is empty", retryable=False)
        if not self.api_key:
            raise VolcTTSError(
                "未配置火山引擎语音合成 2.0 的 API Key（TTS_VOLC_API_KEY）。"
                "在火山引擎控制台 → 语音技术 → 大模型语音合成 2.0 获取。",
                code="TTS_VOLC_MISSING_KEY",
                retryable=False,
            )

        try:
            import websockets  # imported lazily so the rest of the app works without it
        except ImportError as exc:  # pragma: no cover - dependency is in requirements
            raise VolcTTSError(
                "缺少 websockets 依赖：火山 TTS 2.0 需要 WebSocket 协议。"
                "请运行 pip install websockets（桌面端安装包已内置）。",
                code="TTS_VOLC_MISSING_DEP",
                retryable=False,
            ) from exc

        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        speaker = voice or self.voice
        audio = bytearray()

        try:
            websocket = await websockets.connect(
                self.ws_url, additional_headers=headers, max_size=20 * 1024 * 1024
            )
        except Exception as exc:  # noqa: BLE001 - connection errors are actionable
            raise VolcTTSError(
                f"火山 TTS 连接失败：{exc.__class__.__name__}: {exc}",
                code="TTS_VOLC_CONNECT",
                retryable=True,
            ) from exc

        async def send(event: Event, payload: Dict[str, Any], session_id: str = "") -> None:
            await websocket.send(build_event_message(event, session_id, payload))

        async def recv() -> Dict[str, Any]:
            data = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            return parse_server_message(data)

        try:
            await send(Event.StartConnection, {})
            msg = await recv()
            if msg["event"] != Event.ConnectionStarted:
                raise VolcTTSError(
                    f"火山 TTS 握手失败：{msg['payload'][:200]!r}",
                    code="TTS_VOLC_HANDSHAKE",
                    retryable=False,
                )

            session_id = str(uuid.uuid4())
            audio_params: Dict[str, Any] = {
                "format": audio_format,
                "sample_rate": self.sample_rate,
            }
            if abs(self.speed - 1.0) > 1e-6:
                audio_params["speech_rate"] = int(round((self.speed - 1.0) * 100))
            params: Dict[str, Any] = {
                "req_params": {"speaker": speaker, "audio_params": audio_params}
            }
            await send(Event.StartSession, params, session_id)
            msg = await recv()
            if msg["event"] != Event.SessionStarted:
                raise self._session_error(msg, speaker)

            request = json.loads(json.dumps(params))
            request["req_params"]["text"] = text
            await send(Event.TaskRequest, request, session_id)
            await send(Event.FinishSession, {}, session_id)

            while True:
                msg = await recv()
                if msg["type"] == MsgType.Error:
                    raise VolcTTSError(
                        f"火山 TTS 服务端错误 {msg['error_code']}: {msg['payload'][:200]!r}",
                        code=str(msg["error_code"]),
                        retryable=str(msg["error_code"]) in {"55000001", "55000002"},
                    )
                if msg["type"] == MsgType.AudioOnlyServer:
                    audio.extend(msg["payload"])
                if msg["event"] == Event.SessionFailed:
                    raise self._session_error(msg, speaker)
                if msg["event"] == Event.SessionFinished:
                    break
        except asyncio.TimeoutError as exc:
            raise VolcTTSError("火山 TTS 合成超时（未在限定时间内返回音频）", retryable=True) from exc
        finally:
            try:
                await websocket.send(build_event_message(Event.FinishConnection, {}, ""))
                await asyncio.wait_for(websocket.recv(), timeout=5)
            except Exception:  # noqa: BLE001 - best effort shutdown
                pass
            try:
                await websocket.close()
            except Exception:  # noqa: BLE001
                pass

        if not audio:
            raise VolcTTSError(
                "火山 TTS 返回 0 字节音频：通常是该 Key 未授权此音色/资源，"
                f"或 speaker {speaker} 不属于资源 {self.resource_id}。",
                code="TTS_VOLC_EMPTY_AUDIO",
                retryable=False,
            )
        self.logger.info(
            "Volcano TTS 2.0 synthesized %d chars -> %d bytes (%s, speaker=%s, resource=%s)",
            len(text),
            len(audio),
            audio_format,
            speaker,
            self.resource_id,
        )
        return bytes(audio)

    @staticmethod
    def _session_error(msg: Dict[str, Any], speaker: str) -> VolcTTSError:
        detail = msg.get("payload", b"")[:300]
        text = detail.decode("utf-8", "replace") if isinstance(detail, (bytes, bytearray)) else str(detail)
        hint = ""
        if "mismatched with speaker" in text:
            hint = (
                "（音色与资源不匹配：seed-tts-2.0 资源只接受 *_uranus_bigtts / *_mars_bigtts 等"
                "已授权音色，复刻音色需把资源改为 volc.megatts.timbre）"
            )
        elif "not granted" in text:
            hint = "（该 Key 未授权此资源，需在控制台为 Key 绑定对应服务）"
        return VolcTTSError(
            f"火山 TTS 会话失败（speaker={speaker}）：{text}{hint}",
            code="TTS_VOLC_SESSION",
            retryable=False,
        )

    # ------------------------------------------------------------------ probe

    async def probe(self) -> Dict[str, Any]:
        """Cheap connectivity + authorization check used by the Settings Center."""
        audio = await self.synthesize("你好", timeout=45.0)
        return {
            "success": True,
            "bytes": len(audio),
            "voice": self.voice,
            "resource_id": self.resource_id,
        }


__all__ = [
    "VolcTTS2Service",
    "VolcTTSError",
    "DEFAULT_VOICE",
    "DEFAULT_RESOURCE_ID",
    "WS_URL",
]
