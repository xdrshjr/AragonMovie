# -*- coding: utf-8 -*-
"""Tests for Ali Token Plan integration in the runtime Settings Center.

Covers: shared-key mirroring semantics (set/clear/omitted), masking of the
new secret paths, and hot-apply onto both settings singletons.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.settings_store import (  # noqa: E402
    ModelSettingsStore,
    FIELD_MAP,
    SECRET_PATHS,
    mask_key,
)
from backend.core.settings_models import (  # noqa: E402
    ModelSettings,
    SettingsUpdateRequest,
)
from backend.config import settings as backend_settings  # noqa: E402
from config.settings import settings as root_settings  # noqa: E402

ALI_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"


@pytest.fixture()
def store(tmp_path):
    s = ModelSettingsStore(file_path=tmp_path / "model_settings.json")
    snapshot = {attr: getattr(backend_settings, attr) for _, attr in FIELD_MAP}
    snapshot_root = {attr: getattr(root_settings, attr) for _, attr in FIELD_MAP}
    yield s
    for attr, value in snapshot.items():
        setattr(backend_settings, attr, value)
    for attr, value in snapshot_root.items():
        setattr(root_settings, attr, value)
    if s.file_path.exists():
        s.file_path.unlink()


class TestAliSettingsSchema:
    def test_defaults_use_ali_token_plan(self):
        ms = ModelSettings()
        assert ms.image.service_type == "ali_token_plan"
        assert ms.video.service_type == "ali_token_plan"
        assert ms.image.ali_token_plan.model == "wan2.7-image-pro"
        assert ms.image.ali_token_plan.base_url == ALI_URL
        assert ms.video.ali_token_plan.model == "happyhorse-1.1-i2v"
        assert ms.video.ali_token_plan.t2v_model == "happyhorse-1.1-t2v"
        assert ms.video.ali_token_plan.r2v_model == "happyhorse-1.1-r2v"
        assert ms.text.fast_llm.model == "qwen3.8-max"
        assert ms.text.judge_llm.model == "qwen3.8-max"
        assert ms.voice.model == "qwen-audio-3.0-tts-plus"
        assert ms.voice.base_url == ALI_URL

    def test_secret_paths_include_ali_keys(self):
        assert "image.ali_token_plan.api_key" in SECRET_PATHS
        assert "video.ali_token_plan.api_key" in SECRET_PATHS

    def test_field_map_covers_all_ali_attrs(self):
        mapped_attrs = {attr for _, attr in FIELD_MAP}
        for attr in (
            "ali_token_plan_api_key",
            "ali_token_plan_base_url",
            "ali_image_endpoint",
            "ali_image_model",
            "ali_video_endpoint",
            "ali_video_model",
            "ali_video_t2v_model",
            "ali_video_r2v_model",
            "ali_video_default_size",
            "ali_video_default_duration",
        ):
            assert attr in mapped_attrs, f"{attr} missing from FIELD_MAP"
            assert hasattr(root_settings.__class__, attr) or hasattr(
                root_settings, attr
            ), f"{attr} missing from root settings"
            assert hasattr(backend_settings, attr), (
                f"{attr} missing from backend settings"
            )


class TestAliSharedKeyMirroring:
    def test_setting_video_key_mirrors_to_image(self, store):
        result = store.update(SettingsUpdateRequest.model_validate({
            "video": {"ali_token_plan": {"api_key": "sk-shared-ali-key-001"}}
        }))
        assert result.video.ali_token_plan.api_key == "sk-shared-ali-key-001"
        assert result.image.ali_token_plan.api_key == "sk-shared-ali-key-001"

    def test_setting_image_key_mirrors_to_video(self, store):
        result = store.update(SettingsUpdateRequest.model_validate({
            "image": {"ali_token_plan": {"api_key": "sk-shared-ali-key-002"}}
        }))
        assert result.image.ali_token_plan.api_key == "sk-shared-ali-key-002"
        assert result.video.ali_token_plan.api_key == "sk-shared-ali-key-002"

    def test_clearing_one_key_clears_both(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "video": {"ali_token_plan": {"api_key": "sk-shared-ali-key-003"}}
        }))
        result = store.update(SettingsUpdateRequest.model_validate({
            "image": {"ali_token_plan": {"api_key": ""}}
        }))
        assert result.image.ali_token_plan.api_key == ""
        assert result.video.ali_token_plan.api_key == ""

    def test_omitted_key_keeps_both(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "video": {"ali_token_plan": {"api_key": "sk-shared-ali-key-004"}}
        }))
        result = store.update(SettingsUpdateRequest.model_validate({
            "video": {"ali_token_plan": {"model": "happyhorse-1.1-t2v"}}
        }))
        assert result.video.ali_token_plan.api_key == "sk-shared-ali-key-004"
        assert result.image.ali_token_plan.api_key == "sk-shared-ali-key-004"
        assert result.video.ali_token_plan.model == "happyhorse-1.1-t2v"

    def test_masked_echo_does_not_corrupt_key(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "video": {"ali_token_plan": {"api_key": "sk-shared-ali-key-005"}}
        }))
        echoed = mask_key("sk-shared-ali-key-005")
        result = store.update(SettingsUpdateRequest.model_validate({
            "image": {"ali_token_plan": {"api_key": echoed}}
        }))
        assert result.image.ali_token_plan.api_key == "sk-shared-ali-key-005"
        assert result.video.ali_token_plan.api_key == "sk-shared-ali-key-005"

    def test_masked_view_never_leaks_ali_key(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "video": {"ali_token_plan": {"api_key": "sk-secret-ali-key-9999"}}
        }))
        masked = store.masked()
        assert "secret-ali" not in json.dumps(masked)
        assert masked["video"]["ali_token_plan"]["api_key"] == "sk-s****9999"
        assert masked["image"]["ali_token_plan"]["api_key"] == "sk-s****9999"


class TestAliHotApply:
    def test_update_applies_ali_values_to_both_singletons(self, store):
        store.update(SettingsUpdateRequest.model_validate({
            "video": {
                "service_type": "ali_token_plan",
                "ali_token_plan": {
                    "api_key": "sk-hot-apply-key",
                    "model": "happyhorse-1.1-t2v",
                    "default_duration": 8,
                },
            },
            "image": {
                "service_type": "ali_token_plan",
                "ali_token_plan": {"model": "wan2.7-image-pro"},
            },
        }))
        assert backend_settings.video_service_type == "ali_token_plan"
        assert root_settings.video_service_type == "ali_token_plan"
        assert backend_settings.ali_video_model == "happyhorse-1.1-t2v"
        assert root_settings.ali_video_model == "happyhorse-1.1-t2v"
        assert backend_settings.ali_video_default_duration == 8
        assert root_settings.ali_video_default_duration == 8
        assert backend_settings.ali_token_plan_api_key == "sk-hot-apply-key"
        assert root_settings.ali_token_plan_api_key == "sk-hot-apply-key"
        assert backend_settings.image_service_type == "ali_token_plan"
        assert root_settings.image_service_type == "ali_token_plan"
