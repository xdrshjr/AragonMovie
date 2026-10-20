"""BUG 6 + BUG 7: settings-center round-trip for the new voice and watermark fields."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.core.settings_store import (  # noqa: E402
    FIELD_MAP,
    get_settings_store,
)


@pytest.fixture()
def client(tmp_path):
    from backend.main import app

    store = get_settings_store()
    original_path = store.file_path
    store.file_path = tmp_path / "model_settings.json"
    store._current = None
    store._file_hash = None

    from backend.config import settings as backend_settings
    from config.settings import settings as root_settings

    snapshot = {attr: getattr(backend_settings, attr) for _, attr in FIELD_MAP}
    snapshot_root = {attr: getattr(root_settings, attr) for _, attr in FIELD_MAP}

    with TestClient(app) as c:
        yield c

    for attr, value in snapshot.items():
        setattr(backend_settings, attr, value)
    for attr, value in snapshot_root.items():
        setattr(root_settings, attr, value)
    store.file_path = original_path
    store._current = None
    store._file_hash = None


class TestFieldMap:
    def test_voice_provider_fields_are_mapped(self):
        attrs = {attr for _, attr in FIELD_MAP}
        assert "tts_provider" in attrs
        assert "tts_native_base_url" in attrs
        assert "tts_native_api_key" in attrs
        assert "tts_native_model" in attrs
        assert "tts_native_voice" in attrs
        assert "ali_video_watermark" in attrs

    def test_new_attributes_exist_on_both_settings_singletons(self):
        from backend.config import settings as backend_settings
        from config.settings import settings as root_settings

        for attr in (
            "tts_provider",
            "tts_native_base_url",
            "tts_native_api_key",
            "tts_native_model",
            "tts_native_voice",
            "ali_video_watermark",
        ):
            assert hasattr(backend_settings, attr), f"BackendSettings missing {attr}"
            assert hasattr(root_settings, attr), f"Settings missing {attr}"


class TestVoiceSettingsApi:
    def test_provider_and_native_fields_round_trip(self, client):
        r = client.put("/api/v1/settings", json={
            "voice": {
                "enabled": True,
                "provider": "dashscope_native",
                "native_base_url": "https://dashscope.aliyuncs.com",
                "native_api_key": "sk-dashscope-1234",
                "native_model": "qwen-tts",
                "native_voice": "Cherry",
            }
        })
        assert r.status_code == 200

        voice = r.json()["settings"]["voice"]
        assert voice["provider"] == "dashscope_native"
        assert voice["native_model"] == "qwen-tts"
        # secret is masked on the way out
        assert voice["native_api_key"] == "sk-d****1234"

        # and it was hot-applied to the runtime singletons
        from backend.config import settings as backend_settings
        assert backend_settings.tts_provider == "dashscope_native"
        assert backend_settings.tts_native_api_key == "sk-dashscope-1234"

    def test_invalid_provider_is_rejected(self, client):
        r = client.put("/api/v1/settings", json={
            "voice": {"provider": "carrier-pigeon"}
        })
        assert r.status_code == 422


class TestAliVideoWatermarkApi:
    def test_watermark_flag_round_trip(self, client):
        r = client.put("/api/v1/settings", json={
            "video": {"ali_token_plan": {"watermark": True}}
        })
        assert r.status_code == 200
        assert r.json()["settings"]["video"]["ali_token_plan"]["watermark"] is True

        from backend.config import settings as backend_settings
        from config.settings import settings as root_settings

        assert backend_settings.ali_video_watermark is True
        assert root_settings.ali_video_watermark is True

    def test_voice_probe_explains_broken_gateway(self, client):
        """The voice test endpoint must not claim success on a gateway that
        cannot synthesize speech."""
        client.put("/api/v1/settings", json={
            "voice": {
                "enabled": True,
                "provider": "auto",
                "base_url": (
                    "https://token-plan.cn-beijing.maas.aliyuncs.com"
                    "/compatible-mode/v1"
                ),
                "api_key": "",
            }
        })
        r = client.post("/api/v1/settings/test/voice")
        assert r.status_code == 200
        results = r.json()
        assert results, "expected one probe result"
        assert results[0]["success"] is False
        assert "DashScope" in results[0]["message"]
