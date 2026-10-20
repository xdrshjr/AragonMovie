"""Review regression: the settings-center voice probe must not duplicate (and
drift from) the transport logic in services/tts_service.py, and it must probe
the endpoint the runtime would actually use (cosyvoice has its own path).
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.settings_models import ModelSettings, VoiceSettings  # noqa: E402
from backend.core import settings_tester  # noqa: E402
from services.tts_service import (  # noqa: E402
    NATIVE_COSYVOICE_ENDPOINT,
    NATIVE_QWEN_TTS_ENDPOINT,
    TTSError,
    TTSService,
)


def _settings(**voice_kwargs) -> ModelSettings:
    settings = ModelSettings()
    settings.voice = VoiceSettings(**voice_kwargs)
    return settings


class TestSingleSourceOfTruth:
    def test_tester_reuses_service_resolution(self):
        """No local copy of the host->transport mapping may exist."""
        assert not hasattr(
            settings_tester, "_resolve_voice_transport"
        ), "settings_tester must reuse TTSService's resolution, not re-implement it"

    @pytest.mark.parametrize(
        "provider,base_url,has_native_key,expected",
        [
            ("auto", "https://api.siliconflow.cn/v1", False, "openai_compatible"),
            ("auto", "https://dashscope.aliyuncs.com", False, "dashscope_native"),
            (
                "auto",
                "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                True,
                "dashscope_native",
            ),
            ("openai_compatible", "https://api.openai.com/v1", False, "openai_compatible"),
        ],
    )
    def test_resolution_matches_service(
        self, provider, base_url, has_native_key, expected
    ):
        service = TTSService(
            api_key="sk-test",
            base_url=base_url,
            provider=provider,
            native_api_key="sk-native" if has_native_key else None,
        )
        assert service.effective_provider == expected


class TestCosyvoiceProbe:
    @pytest.mark.asyncio
    async def test_cosyvoice_probes_its_own_endpoint(self, monkeypatch):
        """Selecting cosyvoice-v2 must probe text2speech/synthesis, not the qwen path."""
        seen = {}

        class _Resp:
            status_code = 200
            text = ""
            content = b""

            def json(self):
                return {"output": {"audio": {"url": "https://cdn/audio.mp3"}}}

        class _Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, headers=None, json=None):
                seen["url"] = url
                seen["payload"] = json
                return _Resp()

        monkeypatch.setattr(settings_tester.httpx, "AsyncClient", _Client)
        monkeypatch.setattr(settings_tester, "TIMEOUT", 5.0)

        results = await settings_tester.test_voice(
            _settings(
                provider="dashscope_native",
                native_api_key="sk-native",
                native_model="cosyvoice-v2",
                native_base_url="https://dashscope.aliyuncs.com",
            )
        )

        assert seen["url"].endswith(NATIVE_COSYVOICE_ENDPOINT)
        assert seen["payload"]["model"] == "cosyvoice-v2"
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_qwen_tts_probes_multimodal_endpoint(self, monkeypatch):
        seen = {}

        class _Resp:
            status_code = 200
            text = ""
            content = b""

            def json(self):
                return {"output": {"audio": {"data": "QUJD"}}}

        class _Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, headers=None, json=None):
                seen["url"] = url
                return _Resp()

        monkeypatch.setattr(settings_tester.httpx, "AsyncClient", _Client)
        monkeypatch.setattr(settings_tester, "TIMEOUT", 5.0)

        await settings_tester.test_voice(
            _settings(
                provider="dashscope_native",
                native_api_key="sk-native",
                native_model="qwen-tts",
            )
        )

        assert seen["url"].endswith(NATIVE_QWEN_TTS_ENDPOINT)


class TestNativeKeyFailFast:
    def test_token_plan_key_is_not_sent_to_dashscope(self):
        """TTS_API_KEY (Token Plan) must not be reused as a DashScope key."""
        with pytest.raises(TTSError) as exc:
            TTSService(
                api_key="sk-token-plan",
                base_url=(
                    "https://token-plan.cn-beijing.maas.aliyuncs.com"
                    "/compatible-mode/v1"
                ),
                provider="auto",
                native_api_key=None,
            )
        assert exc.value.retryable is False
        assert exc.value.code in ("TTS_MISSING_KEY", "TTS_GATEWAY_UNSUPPORTED")

    def test_dashscope_key_is_reused_when_host_is_dashscope(self):
        service = TTSService(
            api_key="sk-dashscope",
            base_url="https://dashscope.aliyuncs.com",
            provider="dashscope_native",
            native_api_key=None,
        )
        assert service.effective_provider == "dashscope_native"
        assert service.native_api_key == "sk-dashscope"

    def test_explicit_native_key_wins(self):
        service = TTSService(
            api_key="sk-token-plan",
            base_url=(
                "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
            ),
            provider="auto",
            native_api_key="sk-dashscope",
        )
        assert service.effective_provider == "dashscope_native"
        assert service.native_api_key == "sk-dashscope"

    def test_strict_false_still_constructs(self):
        service = TTSService(
            api_key="sk-token-plan",
            base_url=(
                "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
            ),
            provider="auto",
            native_api_key=None,
            strict=False,
        )
        assert service.effective_provider == "openai_compatible"
