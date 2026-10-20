"""BUG 6 regression: TTS provider resolution and the two transports.

The Ali Token Plan gateway lists ``qwen-audio-3.0-tts-plus`` but exposes no
one-shot HTTP synthesis route (/audio/speech -> 400 InvalidParameter "url
error"; the realtime model only answers over WebSocket). Before the fix the
pipeline just failed silently and produced a silent video; now the transport is
resolved explicitly and unusable configurations fail with an actionable message.
"""

import base64

import httpx
import pytest

from services.tts_service import (
    TTSError,
    TTSService,
    create_tts_service,
    reject_broken_speech_gateway,
)

TOKEN_PLAN_URL = (
    "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
)

AUDIO_BYTES = b"ID3-fake-mp3-bytes"


def _service(**kwargs) -> TTSService:
    """Build a service; tests that select the native transport pass a native key.

    ``native_api_key`` defaults to a DashScope key because the Token Plan key is
    NOT accepted by dashscope.aliyuncs.com (the client now refuses to reuse it).
    """
    defaults = dict(
        api_key="sk-token-plan",
        base_url=TOKEN_PLAN_URL,
        model="qwen-audio-3.0-tts-plus",
        default_voice="Cherry",
        native_api_key="sk-dashscope",
        native_base_url="https://dashscope.aliyuncs.com",
        native_model="qwen-tts",
        native_voice="Cherry",
    )
    defaults.update(kwargs)
    return TTSService(**defaults)


def _mock_client(service: TTSService, handler) -> None:
    service.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestProviderResolution:
    def test_broken_gateway_without_native_key_fails_fast(self):
        with pytest.raises(TTSError) as exc:
            _service(provider="auto", native_api_key=None)

        assert exc.value.retryable is False
        assert exc.value.code == "TTS_GATEWAY_UNSUPPORTED"
        message = str(exc.value)
        assert "dashscope_native" in message
        assert "TTS_BASE_URL" in message

    def test_broken_gateway_with_native_key_uses_native(self):
        service = _service(native_api_key="sk-dashscope")
        assert service.effective_provider == "dashscope_native"
        assert service.native_api_key == "sk-dashscope"

    def test_dashscope_host_maps_to_native(self):
        service = _service(
            base_url="https://dashscope.aliyuncs.com", api_key="sk-dashscope"
        )
        assert service.effective_provider == "dashscope_native"

    def test_openai_host_maps_to_compatible(self):
        service = _service(base_url="https://api.openai.com/v1", api_key="sk-openai")
        assert service.effective_provider == "openai_compatible"

    def test_token_plan_key_is_never_reused_for_dashscope(self):
        """With auto + no native key the gateway is rejected outright."""
        with pytest.raises(TTSError) as exc:
            _service(native_api_key=None)

        assert exc.value.retryable is False
        assert exc.value.code == "TTS_GATEWAY_UNSUPPORTED"

    def test_forced_native_with_token_plan_key_fails_with_missing_key(self):
        """provider=dashscope_native + only a Token Plan key must fail fast."""
        with pytest.raises(TTSError) as exc:
            _service(provider="dashscope_native", native_api_key=None)

        assert exc.value.retryable is False
        assert exc.value.code == "TTS_MISSING_KEY"
        assert "TTS_NATIVE_API_KEY" in str(exc.value)

    def test_explicit_compatible_on_broken_gateway_fails_fast(self):
        with pytest.raises(TTSError):
            _service(provider="openai_compatible")

    def test_non_strict_mode_does_not_raise(self):
        service = _service(provider="openai_compatible", strict=False)
        assert service.effective_provider == "openai_compatible"

    def test_cosyvoice_model_selects_its_endpoint(self):
        service = _service(
            provider="dashscope_native",
            api_key="sk-dashscope",
            native_model="cosyvoice-v2",
        )
        assert service.native_endpoint.endswith("/text2speech/synthesis")

    def test_reject_helper_ignores_normal_gateways(self):
        reject_broken_speech_gateway("https://api.siliconflow.cn/v1")  # no raise


class TestTransports:
    @pytest.mark.asyncio
    async def test_compatible_transport_posts_to_audio_speech(self):
        service = _service(base_url="https://api.openai.com/v1", api_key="sk-openai")
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, content=AUDIO_BYTES)

        _mock_client(service, handler)
        audio = await service.text_to_speech_bytes("你好")

        assert audio == AUDIO_BYTES
        assert seen["url"] == "https://api.openai.com/v1/audio/speech"

    @pytest.mark.asyncio
    async def test_native_transport_reads_base64_audio(self):
        service = _service(provider="dashscope_native", api_key="sk-dashscope")
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(
                200,
                json={
                    "output": {
                        "audio": {"data": base64.b64encode(AUDIO_BYTES).decode()}
                    },
                    "request_id": "req-1",
                },
            )

        _mock_client(service, handler)
        audio = await service.text_to_speech_bytes("你好")

        assert audio == AUDIO_BYTES
        assert seen["url"].endswith(
            "/api/v1/services/aigc/multimodal-generation/generation"
        )

    @pytest.mark.asyncio
    async def test_native_transport_downloads_audio_url(self):
        service = _service(provider="dashscope_native", api_key="sk-dashscope")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/generation"):
                return httpx.Response(
                    200,
                    json={"output": {"audio": {"url": "https://cdn.example.com/a.mp3"}}},
                )
            return httpx.Response(200, content=AUDIO_BYTES)

        _mock_client(service, handler)
        audio = await service.text_to_speech_bytes("你好")

        assert audio == AUDIO_BYTES

    @pytest.mark.asyncio
    async def test_native_empty_response_is_not_retryable(self):
        service = _service(provider="dashscope_native", api_key="sk-dashscope")

        def handler(request: httpx.Request) -> httpx.Response:
            # Exactly what the token-plan gateway answers for realtime models
            return httpx.Response(
                200, json={"status_name": "Success", "status_message": "Success."}
            )

        _mock_client(service, handler)
        with pytest.raises(TTSError) as exc:
            await service.text_to_speech_bytes("你好")

        assert exc.value.retryable is False
        assert exc.value.code == "TTS_NO_AUDIO"

    @pytest.mark.asyncio
    async def test_url_error_response_is_not_retried(self):
        service = _service(base_url="https://api.example.com/v1", api_key="k")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "code": "InvalidParameter",
                    "message": "url error, please check url",
                },
            )

        _mock_client(service, handler)
        with pytest.raises(TTSError) as exc:
            await service.text_to_speech_bytes("你好")

        assert exc.value.retryable is False
        assert "dashscope_native" in str(exc.value)


class TestFactory:
    def test_factory_uses_effective_settings(self, monkeypatch):
        from config.settings import settings as root_settings

        monkeypatch.setattr(root_settings, "tts_provider", "dashscope_native", raising=False)
        monkeypatch.setattr(
            root_settings, "tts_native_api_key", "sk-native", raising=False
        )

        service = create_tts_service()
        assert service.effective_provider == "dashscope_native"
