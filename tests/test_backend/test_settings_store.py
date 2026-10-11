"""Tests for ModelSettingsStore: persistence, masking, hot-apply, reload."""
import json
import sys
from pathlib import Path

import pytest

# Ensure repo root is importable when pytest runs from anywhere
REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.settings_store import (  # noqa: E402
    ModelSettingsStore,
    mask_key,
    FIELD_MAP,
)
from backend.core.settings_models import ModelSettings, SettingsUpdateRequest  # noqa: E402
from backend.config import settings as backend_settings  # noqa: E402
from config.settings import settings as root_settings  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    s = ModelSettingsStore(file_path=tmp_path / "model_settings.json")
    # snapshot runtime so tests can restore
    snapshot = {attr: getattr(backend_settings, attr) for _, attr in FIELD_MAP}
    snapshot_root = {attr: getattr(root_settings, attr) for _, attr in FIELD_MAP}
    yield s
    for attr, value in snapshot.items():
        setattr(backend_settings, attr, value)
    for attr, value in snapshot_root.items():
        setattr(root_settings, attr, value)
    if s.file_path.exists():
        s.file_path.unlink()


class TestMaskKey:
    def test_empty(self):
        assert mask_key("") == ""
        assert mask_key(None) == ""

    def test_short(self):
        assert mask_key("abc") == "****"

    def test_normal(self):
        assert mask_key("sk-abcdefgh12345678") == "sk-a****5678"


class TestPersistenceAndHotApply:
    def test_update_persists_and_applies_both_singletons(self, store):
        req = SettingsUpdateRequest.model_validate({
            "video": {"service_type": "sora2", "sora2": {"model": "sora-2-pro"}},
        })
        result = store.update(req)

        assert result.video.service_type == "sora2"
        assert backend_settings.video_service_type == "sora2"
        assert root_settings.video_service_type == "sora2"
        assert root_settings.sora2_model == "sora-2-pro"

        # file contains full settings incl. real (non-masked) keys
        payload = json.loads(store.file_path.read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert payload["settings"]["video"]["sora2"]["model"] == "sora-2-pro"

    def test_reload_persisted_settings_on_fresh_store(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "text": {"fast_llm": {"model": "my-model"}}
        }))
        fresh = ModelSettingsStore(file_path=store.file_path)
        loaded = fresh.load()
        assert loaded.text.fast_llm.model == "my-model"

    def test_corrupt_file_falls_back_to_env(self, store):
        store.file_path.parent.mkdir(parents=True, exist_ok=True)
        store.file_path.write_text("{not json", encoding="utf-8")
        loaded = store.load()
        assert loaded.video.service_type in ("veo3", "sora2")


class TestWriteOnlyKeys:
    def test_none_keeps_existing_key(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "text": {"fast_llm": {"api_key": "sk-original-key-123"}}
        }))
        # api_key omitted entirely -> kept
        result = store.update(SettingsUpdateRequest.model_validate({
            "text": {"fast_llm": {"model": "new-model"}}
        }))
        assert result.text.fast_llm.api_key == "sk-original-key-123"

    def test_empty_string_clears_key(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "text": {"fast_llm": {"api_key": "sk-original-key-123"}}
        }))
        result = store.update(SettingsUpdateRequest.model_validate({
            "text": {"fast_llm": {"api_key": ""}}
        }))
        assert result.text.fast_llm.api_key == ""

    def test_masked_echo_keeps_existing_key(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "voice": {"api_key": "sk-tts-key-abcdef9876"}
        }))
        masked_now = mask_key("sk-tts-key-abcdef9876")
        result = store.update(SettingsUpdateRequest.model_validate({
            "voice": {"api_key": masked_now, "model": "tts-1-hd"}
        }))
        assert result.voice.api_key == "sk-tts-key-abcdef9876"
        assert result.voice.model == "tts-1-hd"


class TestMaskedView:
    def test_masked_never_contains_full_key(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "agent": {"api_key": "sk-agent-secret-key-9999"}
        }))
        masked = store.masked()
        assert masked["agent"]["api_key"] == "sk-a****9999"
        assert "secret" not in json.dumps(masked)


class TestExternalReload:
    def test_reload_if_changed_applies_external_edit(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "image": {"service_type": "doubao"}
        }))
        assert store.reload_if_changed() is False  # nothing changed yet

        payload = json.loads(store.file_path.read_text(encoding="utf-8"))
        payload["settings"]["image"]["service_type"] = "nano_banana"
        store.file_path.write_text(json.dumps(payload), encoding="utf-8")

        assert store.reload_if_changed() is True
        assert backend_settings.image_service_type == "nano_banana"
        assert root_settings.image_service_type == "nano_banana"

    def test_reload_if_changed_ignores_invalid_edit(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "image": {"service_type": "doubao"}
        }))
        store.file_path.write_text("{{{{broken", encoding="utf-8")
        assert store.reload_if_changed() is False
        assert backend_settings.image_service_type == "doubao"


class TestValidation:
    def test_invalid_service_type_rejected(self, store):
        with pytest.raises(Exception):
            ModelSettings.model_validate({"video": {"service_type": "unknown"}})

    def test_update_invalid_value_raises(self, store):
        with pytest.raises(Exception):
            store.update(SettingsUpdateRequest.model_validate({
                "agent": {"provider": "not-a-provider"}
            }))
