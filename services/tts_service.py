"""TTS (text-to-speech) API service client - 语音合成

Two transports are supported, selected by ``provider``:

1. ``openai_compatible`` — ``POST {base_url}/audio/speech``::

       {
           "model": "tts-1",
           "voice": "alloy",
           "input": "text to speak",
           "response_format": "mp3",
           "speed": 1.0
       }

   The response body is raw audio bytes. Works with OpenAI and any gateway that
   implements the same shape (SiliconFlow, Volcano Ark proxies, local gateways).

2. ``dashscope_native`` — DashScope native HTTP synthesis::

       POST {native_base_url}/api/v1/services/aigc/multimodal-generation/generation
       {"model": "qwen-tts", "input": {"text": "...", "voice": "Cherry"}}

   The audio comes back as ``output.audio.url`` (downloaded here) or
   ``output.audio.data`` (base64).

Why two transports
------------------
The Ali **Token Plan** gateway (``token-plan.*.maas.aliyuncs.com``) lists
``qwen-audio-3.0-tts-plus`` in its model catalogue but does **not** expose a
one-shot HTTP synthesis route: ``/audio/speech`` answers
``400 InvalidParameter: url error``, the native multimodal route answers the
same, and the only 200 response comes from
``qwen-audio-3.0-realtime-plus`` with an empty body (it requires a WebSocket
stream). Pointing ``TTS_BASE_URL`` at that gateway therefore cannot work, so
:class:`TTSService` fails fast with an actionable message instead of letting the
pipeline silently produce a silent video. Use ``provider=dashscope_native``
against ``https://dashscope.aliyuncs.com`` (DashScope key) or any other
OpenAI-compatible TTS gateway.

Use :meth:`text_to_speech_bytes` to get bytes directly, or
:meth:`text_to_speech` to write an audio file to disk. :func:`create_tts_service`
builds a client from the effective runtime settings.
"""
import asyncio
import base64
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Union

import httpx

from config.settings import settings
import logging


# DashScope native synthesis endpoints
DASHSCOPE_NATIVE_BASE_URL = "https://dashscope.aliyuncs.com"
NATIVE_QWEN_TTS_ENDPOINT = "/api/v1/services/aigc/multimodal-generation/generation"
NATIVE_COSYVOICE_ENDPOINT = "/api/v1/services/aigc/text2speech/synthesis"

# Hosts whose /audio/speech route is known to be unavailable (documented + 实测)
KNOWN_BROKEN_SPEECH_HOSTS = ("token-plan.", "maas.aliyuncs.com")

TTSProvider = Literal["auto", "openai_compatible", "dashscope_native"]


class TTSError(Exception):
    """Raised when TTS synthesis fails"""

    def __init__(self, message: str, status_code: Optional[int] = None,
                 response_text: str = "", retryable: bool = True,
                 code: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.retryable = retryable
        self.code = code


def _host_of(url: str) -> str:
    url = (url or "").strip().lower()
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url.split("/", 1)[0]


def sniff_audio_format(data: bytes) -> Optional[str]:
    """Best-effort container detection from magic bytes.

    The DashScope native route ignores ``response_format`` and returns whatever
    the model produces, so callers must not label the bytes with the requested
    format blindly.
    """
    if not data:
        return None
    head = data[:12]
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    if head.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"OggS"):
        return "opus"
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"#!AMR"):
        return "amr"
    return None


def native_endpoint_for(model: str, override: Optional[str] = None) -> str:
    """DashScope native endpoint for a synthesis model.

    cosyvoice has its own route; qwen-tts uses the multimodal generation route.
    Both the runtime client and the settings-center probe use this, so they can
    never diverge.
    """
    if override:
        return override
    if "cosyvoice" in (model or "").lower():
        return NATIVE_COSYVOICE_ENDPOINT
    return NATIVE_QWEN_TTS_ENDPOINT


def resolve_tts_transport(
    base_url: str,
    provider: str = "auto",
    *,
    has_native_key: bool = False,
    strict: bool = True,
) -> str:
    """Resolve ``auto`` into ``openai_compatible`` / ``dashscope_native``.

    Single source of truth shared by :class:`TTSService` and the settings-center
    connection test. Raises :class:`TTSError` (non-retryable) for gateways that
    cannot synthesize speech and have no usable native fallback.
    """
    if provider in ("openai_compatible", "dashscope_native"):
        if provider == "openai_compatible" and strict:
            reject_broken_speech_gateway(base_url)
        return provider

    host = _host_of(base_url)
    if "dashscope.aliyuncs.com" in host:
        return "dashscope_native"
    if any(marker in host for marker in KNOWN_BROKEN_SPEECH_HOSTS):
        if has_native_key:
            return "dashscope_native"
        if strict:
            reject_broken_speech_gateway(base_url)
        return "openai_compatible"
    return "openai_compatible"


def is_known_broken_speech_gateway(base_url: str) -> bool:
    """True when ``base_url`` points at a host without a one-shot speech route."""
    host = _host_of(base_url)
    return any(marker in host for marker in KNOWN_BROKEN_SPEECH_HOSTS)


def reject_broken_speech_gateway(base_url: str) -> None:
    """Fail fast on gateways without a working one-shot /audio/speech route.

    Raises:
        TTSError: non-retryable, with the concrete remedies in the message.
    """
    host = _host_of(base_url)
    if not any(marker in host for marker in KNOWN_BROKEN_SPEECH_HOSTS):
        return

    raise TTSError(
        "TTS is not available on this gateway: the Ali Token Plan gateway "
        f"({host}) lists qwen-audio-3.0-tts-plus but exposes no one-shot HTTP "
        "synthesis route (/audio/speech -> 400 InvalidParameter 'url error'; "
        "the realtime model only answers over WebSocket). "
        "Fix by either (a) setting TTS_PROVIDER=dashscope_native with "
        "TTS_NATIVE_BASE_URL=https://dashscope.aliyuncs.com and a DashScope key "
        "(model qwen-tts or cosyvoice-v2), or (b) pointing TTS_BASE_URL / "
        "TTS_API_KEY at any OpenAI-compatible TTS gateway.",
        status_code=None,
        retryable=False,
        code="TTS_GATEWAY_UNSUPPORTED",
    )


class TTSService:
    """语音合成服务封装（OpenAI 兼容 /audio/speech 或 DashScope 原生接口）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        default_voice: Optional[str] = None,
        provider: Optional[TTSProvider] = None,
        native_base_url: Optional[str] = None,
        native_api_key: Optional[str] = None,
        native_model: Optional[str] = None,
        native_voice: Optional[str] = None,
        native_endpoint: Optional[str] = None,
        strict: bool = True,
    ):
        """
        初始化服务

        Args:
            api_key: 兼容模式 API 密钥
            base_url: 兼容模式基础 URL（需包含 /v1 等版本前缀）
            model: 兼容模式 TTS 模型名，如 tts-1 / tts-1-hd
            default_voice: 默认音色
            provider: auto / openai_compatible / dashscope_native
            native_base_url: DashScope 原生主机根（默认 dashscope.aliyuncs.com）
            native_api_key: 原生接口密钥（缺省复用 api_key）
            native_model: 原生模型（qwen-tts / cosyvoice-v2）
            native_voice: 原生音色（缺省取 settings.tts_native_voice）
            native_endpoint: 原生端点覆盖（缺省按模型自动选择）
            strict: True 时对已知不可用的网关组合直接报错
        """
        self.provider: TTSProvider = (
            provider or getattr(settings, "tts_provider", "auto") or "auto"
        )
        self.api_key = api_key or settings.tts_api_key
        self.base_url = (base_url or settings.tts_base_url).rstrip("/")
        self.model = model or settings.tts_model
        self.default_voice = default_voice or settings.tts_default_voice

        self.native_base_url = (
            native_base_url
            or getattr(settings, "tts_native_base_url", DASHSCOPE_NATIVE_BASE_URL)
            or DASHSCOPE_NATIVE_BASE_URL
        ).rstrip("/")
        explicit_native_key = native_api_key or getattr(
            settings, "tts_native_api_key", ""
        )
        self._native_key_explicit = bool(explicit_native_key)
        # TTS_API_KEY may only double as the native key when the configured host
        # already IS DashScope; a Token Plan key is rejected by
        # dashscope.aliyuncs.com, so reusing it there is a silent misconfiguration.
        self._host_is_dashscope = "dashscope.aliyuncs.com" in _host_of(self.base_url)
        self._native_key_reusable = self._native_key_explicit or self._host_is_dashscope
        self.native_api_key = explicit_native_key or (
            self.api_key if self._host_is_dashscope else ""
        )
        self.native_model = (
            native_model
            or getattr(settings, "tts_native_model", "")
            or "qwen-tts"
        )
        self.native_voice = (
            native_voice
            or getattr(settings, "tts_native_voice", "")
            or self.default_voice
        )
        self.native_endpoint = native_endpoint or self._default_native_endpoint()

        self.logger = logging.getLogger(__name__)
        self.effective_provider = self._resolve_provider(strict=strict)

        if self.effective_provider == "openai_compatible" and not self.api_key:
            self.logger.warning("TTSService initialized without API key")
        if self.effective_provider == "dashscope_native" and not self.native_api_key:
            self.logger.warning(
                "TTSService (dashscope_native) initialized without API key"
            )

        self.client = httpx.AsyncClient(
            headers={"Content-Type": "application/json"},
            timeout=120.0,
        )

    # ------------------------------------------------------------------
    # provider resolution
    # ------------------------------------------------------------------

    def _default_native_endpoint(self) -> str:
        return native_endpoint_for(self.native_model)

    def _resolve_provider(self, strict: bool = True) -> str:
        """Resolve ``auto`` into a concrete transport and reject broken combos."""
        resolved = resolve_tts_transport(
            self.base_url,
            self.provider,
            has_native_key=self._native_key_explicit,
            strict=strict,
        )
        host = _host_of(self.base_url)

        if resolved == "dashscope_native":
            if any(marker in host for marker in KNOWN_BROKEN_SPEECH_HOSTS):
                self.logger.warning(
                    f"TTSService | /audio/speech is unavailable on {host}; "
                    "using the DashScope native synthesis endpoint"
                )
            if not self._native_key_reusable:
                # Every request would just 401; fail fast with instructions
                # instead (non-strict callers may still build an object).
                if strict:
                    raise TTSError(
                        "TTS native transport selected but no DashScope API key "
                        "is configured: TTS_API_KEY belongs to "
                        f"{_host_of(self.base_url)} and is not accepted by "
                        "dashscope.aliyuncs.com. Set TTS_NATIVE_API_KEY (or "
                        "TTS_NATIVE_MODEL/TTS_PROVIDER with a DashScope key).",
                        retryable=False,
                        code="TTS_MISSING_KEY",
                    )
                self.logger.warning(
                    "TTSService | dashscope_native selected but the configured "
                    "API key is not a DashScope key; synthesis will fail with 401"
                )
        return resolved

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def text_to_speech_bytes(
        self,
        text: str,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
        model: Optional[str] = None,
    ) -> bytes:
        """
        合成语音并返回音频字节

        Retries transient failures (5xx / 429 / network) up to 3 times with
        exponential backoff; non-retryable errors (4xx, empty input, unsupported
        gateway) raise immediately.

        Args:
            text: 要合成的文本
            voice: 音色（默认取配置）
            response_format: 音频格式 mp3/opus/aac/flac/wav/pcm（原生接口忽略）
            speed: 语速 0.25-4.0（原生接口忽略）
            model: 覆盖默认模型

        Returns:
            音频文件的原始字节

        Raises:
            TTSError: 合成失败
        """
        last_exc: Optional[TTSError] = None
        for attempt in range(3):
            try:
                if self.effective_provider == "dashscope_native":
                    return await self._native_once(
                        text, voice=voice, model=model,
                    )
                return await self._speech_once(
                    text, voice=voice, response_format=response_format,
                    speed=speed, model=model,
                )
            except TTSError as e:
                if not e.retryable:
                    raise
                last_exc = e
                if attempt < 2:
                    delay = 2.0 ** attempt
                    self.logger.warning(
                        f"TTS attempt {attempt + 1}/3 failed: {e}; retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def text_to_speech(
        self,
        text: str,
        output_path: Union[str, Path],
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
        model: Optional[str] = None,
    ) -> Path:
        """
        合成语音并写入音频文件

        Args:
            text: 要合成的文本
            output_path: 输出音频文件路径（扩展名应与格式匹配）
            voice: 音色
            response_format: 音频格式
            speed: 语速
            model: 覆盖默认模型

        Returns:
            写入的文件路径
        """
        audio = await self.text_to_speech_bytes(
            text, voice=voice, response_format=response_format,
            speed=speed, model=model,
        )
        output_path = Path(output_path)

        # Keep the extension honest: the native route may ignore response_format
        # and hand back e.g. WAV bytes for a ".mp3" path (and ffmpeg/players
        # trust the extension).
        actual = sniff_audio_format(audio)
        if actual and output_path.suffix.lstrip(".").lower() != actual:
            corrected = output_path.with_suffix(f".{actual}")
            self.logger.info(
                f"TTS audio container is {actual}, writing {corrected} "
                f"instead of {output_path.name}"
            )
            output_path = corrected

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)
        self.logger.info(f"TTS audio saved: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # OpenAI-compatible transport
    # ------------------------------------------------------------------

    async def _speech_once(
        self,
        text: str,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
        model: Optional[str] = None,
    ) -> bytes:
        """Single /audio/speech attempt (no retry logic)."""
        if not text or not text.strip():
            raise TTSError("TTS input text is empty", retryable=False)

        payload = {
            "model": model or self.model,
            "voice": voice or self.default_voice,
            "input": text,
            "response_format": response_format or settings.tts_default_format,
            "speed": speed if speed is not None else settings.tts_default_speed,
        }

        self.logger.info(
            f"TTS request | transport=openai_compatible | model={payload['model']} "
            f"| voice={payload['voice']} | format={payload['response_format']} "
            f"| chars={len(text)}"
        )

        try:
            response = await self.client.post(
                f"{self.base_url}/audio/speech",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )

            if response.status_code != 200:
                raise self._http_error(response, "openai_compatible")

            audio = response.content
            if not audio:
                raise TTSError("TTS API returned empty audio body", retryable=True)

            self.logger.info(f"TTS success | audio_bytes={len(audio)}")
            return audio

        except httpx.HTTPError as e:
            raise TTSError(f"TTS request failed: {e.__class__.__name__}: {e}")

    # ------------------------------------------------------------------
    # DashScope native transport
    # ------------------------------------------------------------------

    async def _native_once(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
    ) -> bytes:
        """Single native synthesis attempt (no retry logic)."""
        if not text or not text.strip():
            raise TTSError("TTS input text is empty", retryable=False)

        payload = {
            "model": model or self.native_model,
            "input": {"text": text, "voice": voice or self.native_voice},
        }
        self.logger.info(
            f"TTS request | transport=dashscope_native | model={payload['model']} "
            f"| voice={payload['input']['voice']} | chars={len(text)}"
        )

        try:
            response = await self.client.post(
                f"{self.native_base_url}{self.native_endpoint}",
                headers={"Authorization": f"Bearer {self.native_api_key}"},
                json=payload,
            )
            if response.status_code != 200:
                raise self._http_error(response, "dashscope_native")

            audio = await self._extract_native_audio(response.json())
            self.logger.info(f"TTS success | audio_bytes={len(audio)}")
            return audio

        except httpx.HTTPError as e:
            raise TTSError(f"TTS request failed: {e.__class__.__name__}: {e}")

    async def _extract_native_audio(self, body: Dict[str, Any]) -> bytes:
        """从原生响应中取出音频字节（data base64 或 url 下载）"""
        output = body.get("output") or {}
        audio_node = output.get("audio") if isinstance(output, dict) else None

        if isinstance(audio_node, str) and audio_node:
            return await self._download(audio_node)

        if isinstance(audio_node, dict):
            data = audio_node.get("data")
            if isinstance(data, str) and data:
                try:
                    return base64.b64decode(data)
                except Exception:  # noqa: BLE001
                    raise TTSError(
                        "DashScope native TTS returned undecodable base64 audio",
                        retryable=False,
                    )
            url = audio_node.get("url")
            if isinstance(url, str) and url:
                return await self._download(url)

        raise TTSError(
            "DashScope native TTS returned no audio "
            f"(keys={sorted(output.keys()) if isinstance(output, dict) else type(output)}). "
            "Check that TTS_NATIVE_MODEL supports one-shot HTTP synthesis "
            "(qwen-tts / cosyvoice-v2); realtime models only stream over WebSocket.",
            retryable=False,
            code="TTS_NO_AUDIO",
        )

    async def _download(self, url: str) -> bytes:
        try:
            response = await self.client.get(url)
        except httpx.HTTPError as e:
            raise TTSError(f"TTS audio download failed: {e.__class__.__name__}: {e}")
        if response.status_code != 200 or not response.content:
            raise TTSError(
                f"TTS audio download failed with status {response.status_code}",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )
        return response.content

    # ------------------------------------------------------------------
    # error helpers
    # ------------------------------------------------------------------

    def _http_error(self, response: httpx.Response, transport: str) -> TTSError:
        """Build a TTSError with the gateway's own code/message."""
        code: Optional[str] = None
        message = ""
        try:
            body = response.json()
            code = body.get("code") or body.get("error", {}).get("code")
            message = (
                body.get("message")
                or body.get("error", {}).get("message")
                or ""
            )
        except Exception:  # noqa: BLE001
            message = (response.text or "")[:500]

        retryable = response.status_code >= 500 or response.status_code == 429
        detail = message or "no error detail"

        if code in ("InvalidParameter", "TTS_GATEWAY_UNSUPPORTED") and "url error" in detail:
            # The signature failure of a gateway without an HTTP synthesis route.
            detail += (
                " | This gateway exposes no one-shot speech route: use "
                "TTS_PROVIDER=dashscope_native (dashscope.aliyuncs.com) or another "
                "OpenAI-compatible TTS gateway."
            )
            retryable = False

        return TTSError(
            f"TTS API ({transport}) returned {response.status_code}: {detail}",
            status_code=response.status_code,
            response_text=(response.text or "")[:2000],
            retryable=retryable,
            code=code,
        )

    async def __aenter__(self) -> "TTSService":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False


def create_tts_service(strict: bool = True, **overrides: Any) -> TTSService:
    """Build a TTSService from the effective runtime settings.

    Args:
        strict: Fail fast when the configured gateway cannot synthesize speech.
        **overrides: Passed to :class:`TTSService` (api_key, provider, ...).

    Raises:
        TTSError: When the effective configuration is known to be unusable.
    """
    return TTSService(strict=strict, **overrides)
