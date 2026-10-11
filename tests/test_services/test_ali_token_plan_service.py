# -*- coding: utf-8 -*-
"""Tests for the Ali Token Plan (Ali Coding Plan) service clients + factory wiring.

Protocol notes (verified against the live token-plan gateway):
- image: DashScope-native sync POST /api/v1/services/aigc/multimodal-generation/generation
- video: DashScope-native async POST /api/v1/services/aigc/video-generation/video-synthesis
  (X-DashScope-Async: enable) + GET /api/v1/tasks/{id} polling
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.exceptions import ServiceException  # noqa: E402
from config.settings import settings  # noqa: E402
from services.ali_token_plan_service import (  # noqa: E402
    AliTokenPlanImageService,
    AliTokenPlanVideoService,
    image_to_data_uri,
    native_base_url,
)
from services.image_service_factory import ImageServiceFactory  # noqa: E402
from services.video_service_factory import VideoServiceFactory  # noqa: E402

ALI_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
ALI_HOST = "https://token-plan.cn-beijing.maas.aliyuncs.com"
NATIVE_IMG = "/api/v1/services/aigc/multimodal-generation/generation"
NATIVE_VID = "/api/v1/services/aigc/video-generation/video-synthesis"


@pytest.fixture()
def ali_key():
    """Temporarily inject a test key into the global settings singleton."""
    original = settings.ali_token_plan_api_key
    settings.ali_token_plan_api_key = "sk-test-ali-token-plan"
    yield "sk-test-ali-token-plan"
    settings.ali_token_plan_api_key = original


def _mock_client(**handlers):
    client = MagicMock()
    client.aclose = AsyncMock()
    for name, value in handlers.items():
        setattr(client, name, AsyncMock(return_value=value))
    return client


def _http_response(json_body, status_code=200, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = str(json_body)
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


class TestHelpers:
    def test_native_base_url_strips_compatible_suffix(self):
        assert native_base_url(ALI_URL) == ALI_HOST
        assert native_base_url("https://host/compatible-mode") == "https://host"
        assert native_base_url("https://host") == "https://host"
        assert native_base_url("https://host/") == "https://host"

    def test_image_to_data_uri_http_passthrough(self):
        url = "https://cdn.example.com/a.png"
        assert image_to_data_uri(url) == url

    def test_image_to_data_uri_local_file(self, tmp_path):
        f = tmp_path / "a.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = image_to_data_uri(str(f))
        assert out.startswith("data:image/png;base64,")

    def test_image_to_data_uri_bare_base64(self):
        out = image_to_data_uri("QUJD")
        assert out == "data:image/png;base64,QUJD"


class TestAliTokenPlanImageService:
    def test_defaults_come_from_settings(self, ali_key):
        svc = AliTokenPlanImageService()
        assert svc.api_key == ali_key
        assert svc.base_url == ALI_HOST
        assert svc.endpoint == NATIVE_IMG
        assert svc.model == "wan2.7-image-pro"
        assert svc.SERVICE_NAME == "Ali Token Plan (wan)"

    def test_explicit_overrides_win(self, ali_key):
        svc = AliTokenPlanImageService(
            api_key="sk-other",
            base_url="https://example.com/v1",
            endpoint="/custom/gen",
            model="wan-custom",
        )
        assert svc.api_key == "sk-other"
        assert svc.base_url == "https://example.com/v1"
        assert svc.endpoint == "/custom/gen"
        assert svc.model == "wan-custom"

    @pytest.mark.asyncio
    async def test_generate_image_posts_native_payload(self, ali_key):
        svc = AliTokenPlanImageService()
        svc.client = _mock_client(post=_http_response({
            "output": {"choices": [{"message": {
                "role": "assistant",
                "content": [{"image": "https://cdn/img.png"}],
            }}]},
            "usage": {"image_count": 1},
        }))

        result = await svc.generate_image("a cat", width=1024, height=1024)

        assert result["image_url"] == "https://cdn/img.png"
        _, kwargs = svc.client.post.call_args
        payload = kwargs["json"]
        assert payload["model"] == "wan2.7-image-pro"
        assert payload["parameters"]["size"] == "1024*1024"
        assert payload["parameters"]["watermark"] is False
        content = payload["input"]["messages"][0]["content"]
        assert content == [{"text": "a cat"}]
        await svc.close()

    @pytest.mark.asyncio
    async def test_generate_image_i2i_sends_reference(self, ali_key, tmp_path):
        svc = AliTokenPlanImageService()
        svc.client = _mock_client(post=_http_response({
            "output": {"choices": [{"message": {
                "content": [{"image": "https://cdn/i2i.png"}],
            }}]},
        }))
        ref = tmp_path / "ref.png"
        ref.write_bytes(b"\x89PNG-fake")

        result = await svc.generate_image(
            "keep the face", reference_image=str(ref)
        )
        assert result["image_url"] == "https://cdn/i2i.png"
        content = svc.client.post.call_args[1]["json"]["input"]["messages"][0]["content"]
        assert content[0]["image"].startswith("data:image/png;base64,")
        assert content[1] == {"text": "keep the face"}
        await svc.close()

    @pytest.mark.asyncio
    async def test_generate_image_api_error_raises_service_exception(self, ali_key):
        svc = AliTokenPlanImageService()
        svc.client = _mock_client(post=_http_response(
            {"code": "InvalidParameter", "message": "url error"},
            status_code=400,
        ))
        with pytest.raises(ServiceException) as exc_info:
            await svc.generate_image("a cat")
        assert exc_info.value.retryable is False
        assert "url error" in exc_info.value.message
        await svc.close()

    @pytest.mark.asyncio
    async def test_generate_image_missing_image_raises(self, ali_key):
        svc = AliTokenPlanImageService()
        svc.client = _mock_client(post=_http_response({
            "output": {"choices": [{"message": {"content": []}}]},
        }))
        with pytest.raises(ServiceException):
            await svc.generate_image("a cat")
        await svc.close()


class TestAliTokenPlanVideoService:
    def test_defaults_come_from_settings(self, ali_key):
        svc = AliTokenPlanVideoService()
        assert svc.api_key == ali_key
        assert svc.base_url == ALI_HOST
        assert svc.endpoint == NATIVE_VID
        assert svc.model == "happyhorse-1.1-i2v"
        assert svc.t2v_model == "happyhorse-1.1-t2v"
        assert svc.r2v_model == "happyhorse-1.1-r2v"
        assert svc.default_size == "1280x720"
        assert svc.default_duration == 5
        assert svc.SERVICE_NAME == "Ali Token Plan (happyhorse)"

    @pytest.mark.asyncio
    async def test_i2v_full_flow_with_mocked_client(self, ali_key, tmp_path):
        """submit (async header + first_frame media) -> poll -> SUCCEEDED."""
        image_file = tmp_path / "scene.png"
        image_file.write_bytes(b"\x89PNG-fake-bytes")

        svc = AliTokenPlanVideoService()
        svc.client = _mock_client(
            post=_http_response(
                {"output": {"task_id": "t-1", "task_status": "PENDING"}}
            ),
            get=_http_response({
                "output": {
                    "task_id": "t-1",
                    "task_status": "SUCCEEDED",
                    "video_url": "https://cdn/out.mp4",
                }
            }),
        )

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await svc.image_to_video(
                str(image_file), prompt="a horse gallops", duration=6
            )

        assert result["status"] == "completed"
        assert result["video_url"] == "https://cdn/out.mp4"
        assert result["id"] == "t-1"

        _, post_kwargs = svc.client.post.call_args
        assert post_kwargs["headers"] == {"X-DashScope-Async": "enable"}
        body = post_kwargs["json"]
        assert body["model"] == "happyhorse-1.1-i2v"
        assert body["input"]["prompt"] == "a horse gallops"
        assert body["parameters"]["duration"] == 6
        media = body["input"]["media"]
        assert media[0]["type"] == "first_frame"
        assert media[0]["url"].startswith("data:image/png;base64,")
        # poll hit the native tasks endpoint
        get_args = svc.client.get.call_args[0]
        assert get_args[0] == "/api/v1/tasks/t-1"
        await svc.close()

    @pytest.mark.asyncio
    async def test_default_duration_applied(self, ali_key, tmp_path):
        image_file = tmp_path / "scene.png"
        image_file.write_bytes(b"fake")
        svc = AliTokenPlanVideoService()
        svc.client = _mock_client(
            post=_http_response(
                {"output": {"task_id": "t-2", "task_status": "PENDING"}}
            ),
            get=_http_response({"output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn/o.mp4",
            }}),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await svc.image_to_video(str(image_file), prompt="x")
        body = svc.client.post.call_args[1]["json"]
        assert body["parameters"]["duration"] == 5
        await svc.close()

    @pytest.mark.asyncio
    async def test_no_image_switches_to_t2v_model(self, ali_key):
        svc = AliTokenPlanVideoService()
        svc.client = _mock_client(
            post=_http_response(
                {"output": {"task_id": "t-3", "task_status": "PENDING"}}
            ),
            get=_http_response({"output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn/o.mp4",
            }}),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await svc.image_to_video(None, prompt="text only video")
        body = svc.client.post.call_args[1]["json"]
        assert body["model"] == "happyhorse-1.1-t2v"
        assert "media" not in body["input"]
        await svc.close()

    @pytest.mark.asyncio
    async def test_multiple_images_uses_first_frame_only(self, ali_key, tmp_path):
        a = tmp_path / "a.png"; a.write_bytes(b"a")
        b = tmp_path / "b.png"; b.write_bytes(b"b")
        svc = AliTokenPlanVideoService()
        svc.client = _mock_client(
            post=_http_response(
                {"output": {"task_id": "t-4", "task_status": "PENDING"}}
            ),
            get=_http_response({"output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://cdn/o.mp4",
            }}),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await svc.image_to_video([str(a), str(b)], prompt="x")
        media = svc.client.post.call_args[1]["json"]["input"]["media"]
        assert len(media) == 1
        await svc.close()

    @pytest.mark.asyncio
    async def test_task_failure_raises_service_exception(self, ali_key, tmp_path):
        f = tmp_path / "s.png"; f.write_bytes(b"x")
        svc = AliTokenPlanVideoService()
        svc.client = _mock_client(
            post=_http_response(
                {"output": {"task_id": "t-5", "task_status": "PENDING"}}
            ),
            get=_http_response({"output": {
                "task_status": "FAILED",
                "code": "InvalidParameter",
                "message": "Input should be 'first_frame'",
            }}),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(ServiceException) as exc_info:
                await svc.image_to_video(str(f), prompt="x")
        assert exc_info.value.retryable is False
        assert "first_frame" in exc_info.value.message
        await svc.close()

    @pytest.mark.asyncio
    async def test_submit_error_raises_service_exception(self, ali_key):
        svc = AliTokenPlanVideoService()
        svc.client = _mock_client(post=_http_response(
            {"code": "Throttling", "message": "rate limited"},
            status_code=429,
        ))
        with pytest.raises(ServiceException) as exc_info:
            await svc.image_to_video(None, prompt="x")
        assert exc_info.value.retryable is True
        await svc.close()

    @pytest.mark.asyncio
    async def test_download_video_writes_file(self, ali_key, tmp_path):
        svc = AliTokenPlanVideoService()
        fake = _http_response({})
        fake.content = b"MP4-BYTES"
        with patch("httpx.AsyncClient") as client_cls:
            instance = MagicMock()
            instance.get = AsyncMock(return_value=fake)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            client_cls.return_value = instance
            out = await svc.download_video(
                "https://cdn/out.mp4", tmp_path / "v.mp4"
            )
        assert Path(out).read_bytes() == b"MP4-BYTES"
        await svc.close()


class TestFactoryWiring:
    def test_image_factory_creates_ali_service(self, ali_key):
        svc = ImageServiceFactory.create_service(service_type="ali_token_plan")
        assert isinstance(svc, AliTokenPlanImageService)
        assert "ali_token_plan" in ImageServiceFactory.get_available_services()

    def test_image_factory_supports_i2i(self, ali_key):
        assert ImageServiceFactory.supports_image_to_image("ali_token_plan") is True

    def test_video_factory_creates_ali_service(self, ali_key):
        svc = VideoServiceFactory.create_service(service_type="ali_token_plan")
        assert isinstance(svc, AliTokenPlanVideoService)
        assert "ali_token_plan" in VideoServiceFactory.get_supported_services()

    def test_video_factory_override(self, ali_key):
        svc = VideoServiceFactory.create_service(
            service_type="ali_token_plan",
            config_override={"model": "happyhorse-1.1-r2v", "default_duration": 10},
        )
        assert svc.model == "happyhorse-1.1-r2v"
        assert svc.default_duration == 10

    def test_video_factory_requires_key(self):
        original = settings.ali_token_plan_api_key
        settings.ali_token_plan_api_key = ""
        try:
            with pytest.raises(ValueError, match="Ali Token Plan API key"):
                VideoServiceFactory.create_service(service_type="ali_token_plan")
        finally:
            settings.ali_token_plan_api_key = original


class TestDefaultServiceSelection:
    def test_defaults_point_to_ali_token_plan(self):
        # Class-level defaults: immune to env-var pollution in ambient shells.
        from config.settings import Settings

        defaults = {
            name: field.default for name, field in Settings.model_fields.items()
        }
        assert defaults["image_service_type"] == "ali_token_plan"
        assert defaults["video_service_type"] == "ali_token_plan"
        assert defaults["fast_llm_model"] == "qwen3.8-max"
        assert defaults["fast_llm_api_url"] == ALI_URL
        assert defaults["judge_llm_model"] == "qwen3.8-max"
        assert defaults["judge_llm_api_url"] == ALI_URL
        assert defaults["tts_model"] == "qwen-audio-3.0-tts-plus"
        assert defaults["tts_base_url"] == ALI_URL
        assert defaults["ali_image_model"] == "wan2.7-image-pro"
        assert defaults["ali_image_endpoint"] == NATIVE_IMG
        assert defaults["ali_video_model"] == "happyhorse-1.1-i2v"
        assert defaults["ali_video_endpoint"] == NATIVE_VID
        assert defaults["ali_video_t2v_model"] == "happyhorse-1.1-t2v"
        assert defaults["ali_video_r2v_model"] == "happyhorse-1.1-r2v"
        assert defaults["ali_token_plan_base_url"] == ALI_URL

    def test_backend_defaults_point_to_ali_token_plan(self):
        from backend.config import BackendSettings

        defaults = {
            name: field.default
            for name, field in BackendSettings.model_fields.items()
        }
        assert defaults["image_service_type"] == "ali_token_plan"
        assert defaults["video_service_type"] == "ali_token_plan"
        assert defaults["fast_llm_model"] == "qwen3.8-max"
        assert defaults["tts_model"] == "qwen-audio-3.0-tts-plus"
        assert defaults["ali_image_endpoint"] == NATIVE_IMG
        assert defaults["ali_video_endpoint"] == NATIVE_VID
        assert defaults["ali_token_plan_base_url"] == ALI_URL
