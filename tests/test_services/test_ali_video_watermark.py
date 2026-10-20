"""BUG 7 regression: the Ali video watermark switch reaches the request body.

The gateway returns a ``refiner_watermark``-tagged CDN file when
``parameters.watermark`` is absent; ``_build_payload`` used to send only
``{"duration": N}``, so users had no way to ask for a clean file.
"""

import pytest

from services.ali_token_plan_service import AliTokenPlanVideoService
from services.video_service_factory import VideoServiceFactory


@pytest.fixture()
def service():
    svc = AliTokenPlanVideoService(
        api_key="sk-test",
        base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        model="happyhorse-1.1-i2v",
        default_duration=5,
        watermark=False,
    )
    yield svc


class TestBuildPayload:
    def test_watermark_is_sent_as_false_by_default(self, service):
        payload = service._build_payload(
            "happyhorse-1.1-i2v", "a calm street", None, 5
        )
        assert payload["parameters"]["watermark"] is False
        assert payload["parameters"]["duration"] == 5

    def test_watermark_true_is_forwarded(self, service):
        payload = service._build_payload(
            "happyhorse-1.1-i2v", "prompt", None, 8, watermark=True
        )
        assert payload["parameters"]["watermark"] is True

    def test_service_level_watermark_is_used(self):
        svc = AliTokenPlanVideoService(
            api_key="sk-test",
            base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            watermark=True,
        )
        payload = svc._build_payload("m", "p", None, 5)
        assert payload["parameters"]["watermark"] is True

    def test_media_keeps_first_frame_contract(self, service):
        media = [{"type": "first_frame", "url": "data:image/png;base64,AAA"}]
        payload = service._build_payload("m", "p", media, 5)
        assert payload["input"]["media"] == media
        assert payload["parameters"] == {"duration": 5, "watermark": False}


class TestFactory:
    def test_factory_forwards_watermark_override(self, monkeypatch):
        from config.settings import settings as root_settings

        monkeypatch.setattr(root_settings, "ali_token_plan_api_key", "sk-x", raising=False)

        svc = VideoServiceFactory.create_service(
            service_type="ali_token_plan",
            config_override={"watermark": True},
        )
        assert svc.watermark is True

    def test_factory_defaults_to_settings_value(self, monkeypatch):
        from config.settings import settings as root_settings

        monkeypatch.setattr(root_settings, "ali_token_plan_api_key", "sk-x", raising=False)
        monkeypatch.setattr(root_settings, "ali_video_watermark", True, raising=False)

        svc = VideoServiceFactory.create_service(service_type="ali_token_plan")
        assert svc.watermark is True
