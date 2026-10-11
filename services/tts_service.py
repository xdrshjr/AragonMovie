"""TTS (text-to-speech) API service client - 语音合成

OpenAI-compatible /audio/speech endpoint. Works with OpenAI, and with any
compatible gateway (e.g. SiliconFlow, DashScope, Volcano Ark proxies, local
gateways) that implements the same request shape:

    POST {base_url}/audio/speech
    {
        "model": "tts-1",
        "voice": "alloy",
        "input": "text to speak",
        "response_format": "mp3",
        "speed": 1.0
    }

The response body is raw audio bytes. Use :meth:`text_to_speech_bytes` to get
bytes directly, or :meth:`text_to_speech` to write an audio file to disk.
"""
import asyncio
from pathlib import Path
from typing import Optional, Union

import httpx

from config.settings import settings
import logging


class TTSError(Exception):
    """Raised when TTS synthesis fails"""

    def __init__(self, message: str, status_code: Optional[int] = None,
                 response_text: str = "", retryable: bool = True):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.retryable = retryable


class TTSService:
    """语音合成服务封装（OpenAI 兼容 /audio/speech）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        default_voice: Optional[str] = None,
    ):
        """
        初始化服务

        Args:
            api_key: API密钥
            base_url: API基础URL（需包含 /v1 等版本前缀）
            model: TTS模型名称，如 tts-1 / tts-1-hd
            default_voice: 默认音色，如 alloy / echo / onyx
        """
        self.api_key = api_key or settings.tts_api_key
        self.base_url = (base_url or settings.tts_base_url).rstrip("/")
        self.model = model or settings.tts_model
        self.default_voice = default_voice or settings.tts_default_voice
        self.logger = logging.getLogger(__name__)

        if not self.api_key:
            self.logger.warning("TTSService initialized without API key")

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            timeout=120.0,
        )

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()

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
        exponential backoff; non-retryable errors (4xx, empty input) raise
        immediately.

        Args:
            text: 要合成的文本
            voice: 音色（默认取配置）
            response_format: 音频格式 mp3/opus/aac/flac/wav/pcm
            speed: 语速 0.25-4.0
            model: 覆盖默认模型

        Returns:
            音频文件的原始字节

        Raises:
            TTSError: 合成失败
        """
        last_exc: Optional[TTSError] = None
        for attempt in range(3):
            try:
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

    async def _speech_once(
        self,
        text: str,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
        model: Optional[str] = None,
    ) -> bytes:
        """Single TTS attempt (no retry logic)."""
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
            f"TTS request | model={payload['model']} | voice={payload['voice']} "
            f"| format={payload['response_format']} | chars={len(text)}"
        )

        try:
            response = await self.client.post("/audio/speech", json=payload)

            if response.status_code != 200:
                error_text = ""
                try:
                    error_body = response.json()
                    error_text = str(error_body.get("error", {}).get("message", ""))
                except Exception:  # noqa: BLE001
                    error_text = response.text[:500] if response.text else ""

                retryable = response.status_code >= 500 or response.status_code == 429
                raise TTSError(
                    f"TTS API returned {response.status_code}: {error_text or 'no error detail'}",
                    status_code=response.status_code,
                    response_text=response.text[:2000] if response.text else "",
                    retryable=retryable,
                )

            audio = response.content
            if not audio:
                raise TTSError("TTS API returned empty audio body", retryable=True)

            self.logger.info(f"TTS success | audio_bytes={len(audio)}")
            return audio

        except httpx.HTTPError as e:
            raise TTSError(f"TTS request failed: {e.__class__.__name__}: {e}")

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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)
        self.logger.info(f"TTS audio saved: {output_path}")
        return output_path

    async def __aenter__(self) -> "TTSService":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False
