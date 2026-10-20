"""Ali Token Plan (Ali Coding Plan) service clients.

阿里云 Token Plan 网关，一个 API Key 覆盖多种模型：

- 文本  : qwen3.8-max             → OpenAI 兼容 ``{base}/chat/completions``
  （复用 ``services/llm_service.py``，base_url 含 ``/compatible-mode/v1``）
- 语音  : qwen-audio-3.0-tts-plus → 兼容模式 ``/audio/speech`` 在该网关暂不可用
  （实测返回 InvalidParameter / cosyvoice engine 411；配置项保留，可指向其他网关）
- 图像  : wan2.7-image-pro        → DashScope 原生
  ``POST {host}/api/v1/services/aigc/multimodal-generation/generation``（同步）
- 视频  : happyhorse-1.1-i2v/t2v/r2v → DashScope 原生异步
  ``POST {host}/api/v1/services/aigc/video-generation/video-synthesis``
  （header ``X-DashScope-Async: enable``，轮询 ``GET {host}/api/v1/tasks/{id}``）

以上图像/视频协议已对真实网关逐字段验证（含 base64 data-uri 本地图输入）。
原生 API 使用网关主机名（不带 ``/compatible-mode/v1`` 后缀），本模块自动从
配置的 base_url 中剥离该后缀，因此设置中心只需维护一个 URL。
"""
import asyncio
import base64
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

from backend.core.exceptions import ServiceException
from config.settings import settings
from services.nano_banana_service import NanoBananaService
import logging

logger = logging.getLogger(__name__)

# DashScope 原生端点（token-plan 网关实测值）
NATIVE_IMAGE_ENDPOINT = "/api/v1/services/aigc/multimodal-generation/generation"
NATIVE_VIDEO_ENDPOINT = "/api/v1/services/aigc/video-generation/video-synthesis"
NATIVE_TASK_ENDPOINT = "/api/v1/tasks"

# 视频任务轮询参数（happyhorse i2v 实测约 2 分钟出片，留足余量）
DEFAULT_POLL_INTERVAL = 10.0
DEFAULT_MAX_WAIT = 1800.0


def native_base_url(base_url: str) -> str:
    """从 compatible-mode URL 推导 DashScope 原生 API 的主机根。

    ``https://host/compatible-mode/v1`` -> ``https://host``；
    已经是主机根时原样返回。
    """
    url = (base_url or "").rstrip("/")
    for suffix in ("/compatible-mode/v1", "/compatible-mode"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def image_to_data_uri(image: str) -> str:
    """把本地路径 / http URL / base64 串统一为可直接提交的 url 值。

    - http(s) URL：原样返回（网关自行拉取）
    - 本地文件：读取并编码为 ``data:image/<ext>;base64,...``
    - 其余：视为裸 base64，补 data URI 前缀
    """
    if image.startswith("http://") or image.startswith("https://"):
        return image
    if image.startswith("data:"):
        return image
    path = Path(image)
    if path.exists():
        ext = path.suffix.lstrip(".").lower() or "png"
        if ext == "jpg":
            ext = "jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode()
        return f"data:image/{ext};base64,{encoded}"
    return f"data:image/png;base64,{image}"


class AliTokenPlanImageService(NanoBananaService):
    """Ali Token Plan 图像生成（wan2.7-image-pro，DashScope 原生同步接口）"""

    SERVICE_NAME = "Ali Token Plan (wan)"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化服务（未显式传入的参数取 settings 中 ali_* 配置）

        Args:
            api_key: API密钥
            base_url: 网关 URL（可含 /compatible-mode/v1，内部自动剥离）
            endpoint: 原生图像端点（默认 multimodal-generation）
            model: 图像模型名称（如 wan2.7-image-pro）
        """
        resolved_base = base_url or settings.ali_token_plan_base_url
        resolved_endpoint = endpoint or settings.ali_image_endpoint or NATIVE_IMAGE_ENDPOINT
        super().__init__(
            api_key=api_key or settings.ali_token_plan_api_key,
            base_url=native_base_url(resolved_base),
            endpoint=resolved_endpoint,
            model=model or settings.ali_image_model,
        )
        # 原生 multimodal-generation 为同步出图，大分辨率可能超过默认 60s
        self.client.timeout = httpx.Timeout(300.0, connect=15.0)
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"AliTokenPlanImageService initialized | model={self.model} | "
            f"base_url={self.base_url} | endpoint={self.endpoint}"
        )

    async def generate_image(
        self,
        prompt: str,
        width: int = 1920,
        height: int = 1080,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        watermark: Optional[bool] = None,
        reference_image: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """文生图 / 图生图（DashScope 原生 multimodal-generation，同步返回）

        Args:
            prompt: 图片描述提示词
            width: 图片宽度（与 height 组合为 "W*H"）
            height: 图片高度
            negative_prompt: 负面提示词（可选，透传 parameters）
            seed: 随机种子（可选）
            watermark: 是否加水印（可选，默认不加）
            reference_image: 参考图（本地路径/URL/base64），提供时为图生图
            **kwargs: 忽略其余 OpenAI 风格参数（quality/style/cfg_scale/steps 等）

        Returns:
            统一格式: {"image_url": ..., "raw_response": {...}}

        Raises:
            ServiceException: API 请求失败或响应缺少图片
        """
        parameters: Dict[str, Any] = {
            "size": f"{width}*{height}",
            "n": 1,
            "watermark": bool(watermark),
        }
        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt
        if seed is not None:
            parameters["seed"] = seed

        content: List[Dict[str, str]] = []
        if reference_image:
            content.append({"image": image_to_data_uri(reference_image)})
            self.logger.info("Ali image generation in image-to-image mode")
        content.append({"text": prompt})

        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {"role": "user", "content": content}
                ]
            },
            "parameters": parameters,
        }

        self.logger.info(
            f"Generating image ({self.model}) | size={parameters['size']} | "
            f"prompt: {prompt[:50]}..."
        )

        try:
            response = await self.client.post(self.endpoint, json=payload)
        except httpx.HTTPError as e:
            raise ServiceException(
                message=f"Ali Token Plan image request failed: "
                        f"{e.__class__.__name__}: {e}",
                service_name=self.SERVICE_NAME,
                retryable=True,
                original_error=e,
                error_type="image_generation_failed",
                stage="image_generation",
            )

        if response.status_code != 200:
            raise self._image_error(response)

        result = self._extract_image_result(response)
        self.logger.info("Ali Token Plan image generated successfully")
        return result

    def _image_error(self, response: httpx.Response) -> ServiceException:
        """把非 200 响应转换为 ServiceException（5xx/429 可重试）。"""
        try:
            body = response.json()
        except ValueError:
            body = {"raw_text": response.text[:500]}
        code = body.get("code", "")
        message = body.get("message") or f"API returned {response.status_code}"
        self.logger.error(
            f"Ali image API failed: {response.status_code} {code} {message}"
        )
        return ServiceException(
            message=message,
            service_name=self.SERVICE_NAME,
            retryable=response.status_code >= 500 or response.status_code == 429,
            error_code=str(code),
            error_type="image_generation_failed",
            stage="image_generation",
            api_response=body,
        )

    def _extract_image_result(self, response: httpx.Response) -> Dict[str, Any]:
        """解析原生响应 output.choices[0].message.content[*].image。"""
        body = response.json()
        try:
            contents = body["output"]["choices"][0]["message"]["content"]
            for item in contents:
                if isinstance(item, dict) and item.get("image"):
                    return {
                        "image_url": item["image"],
                        "raw_response": body,
                    }
        except (KeyError, IndexError, TypeError):
            pass
        raise ServiceException(
            message=f"No image in Ali Token Plan response: {str(body)[:300]}",
            service_name=self.SERVICE_NAME,
            retryable=False,
            error_type="image_generation_failed",
            stage="image_generation",
            api_response=body,
        )


class AliTokenPlanVideoService:
    """Ali Token Plan 视频生成（happyhorse-1.1 系列，DashScope 原生异步接口）

    协议（已实测验证）：
    1. ``POST {host}/api/v1/services/aigc/video-generation/video-synthesis``
       header ``X-DashScope-Async: enable``，body
       ``{"model", "input": {"prompt", "media": [{"type": "first_frame",
       "url": <http 或 data-uri>}]}}, "parameters": {"duration": N}}``
    2. ``GET {host}/api/v1/tasks/{task_id}`` 轮询至
       ``task_status == SUCCEEDED``，取 ``output.video_url``。

    本地图片自动转 base64 data-uri（网关实测接受）；多张图片输入
    （场景连续性参考帧）仅首帧可用，其余记录警告后忽略。
    """

    SERVICE_NAME = "Ali Token Plan (happyhorse)"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        default_size: Optional[str] = None,
        default_duration: Optional[int] = None,
        watermark: Optional[bool] = None
    ):
        """
        初始化服务（未显式传入的参数取 settings 中 ali_* 配置）

        Args:
            api_key: API密钥
            base_url: 网关 URL（可含 /compatible-mode/v1，内部自动剥离）
            endpoint: 原生视频端点（默认 video-generation/video-synthesis）
            model: 视频模型（默认 happyhorse-1.1-i2v 图生视频）
            default_size: 默认分辨率（如 1280x720，供上层展示/日志）
            default_duration: 默认时长（秒）
            watermark: 是否请求带水印版本（默认取 settings.ali_video_watermark，
                网关默认会给成品加 ``refiner_watermark`` 标记，因此默认 False）
        """
        self.api_key = api_key or settings.ali_token_plan_api_key
        configured_base = base_url or settings.ali_token_plan_base_url
        self.base_url = native_base_url(configured_base)
        self.endpoint = endpoint or settings.ali_video_endpoint or NATIVE_VIDEO_ENDPOINT
        self.model = model or settings.ali_video_model
        self.default_size = default_size or settings.ali_video_default_size
        self.default_duration = (
            default_duration or settings.ali_video_default_duration
        )
        self.watermark = (
            watermark
            if watermark is not None
            else bool(getattr(settings, "ali_video_watermark", False))
        )
        # 备选模型（文生视频/参考生视频），供上层按需切换
        self.t2v_model = settings.ali_video_t2v_model
        self.r2v_model = settings.ali_video_r2v_model
        self.logger = logging.getLogger(__name__)

        if not self.api_key:
            self.logger.warning(
                "AliTokenPlanVideoService initialized without API key"
            )

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120.0,
        )
        self.logger.info(
            f"AliTokenPlanVideoService initialized | model={self.model} | "
            f"base_url={self.base_url} | endpoint={self.endpoint} | "
            f"default_duration={self.default_duration}s | watermark={self.watermark}"
        )

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()
        self.logger.info("AliTokenPlanVideoService HTTP client closed")

    async def image_to_video(
        self,
        image_path: Union[str, List[str], None],
        duration: Optional[float] = None,
        prompt: str = "Generate video from this image",
        **kwargs
    ) -> Dict[str, Any]:
        """图生视频：提交原生异步任务并轮询至完成。

        Args:
            image_path: 本地图片路径 / http URL / base64（列表时仅用首帧）；
                为 None 或空时走文生视频（t2v 模型）
            duration: 时长（秒），None 时用 default_duration
            prompt: 视频描述提示词
            **kwargs: 兼容 Veo3 风格参数（fps/resolution/motion_strength/
                camera_motion/reference_weight 等），本网关不支持则忽略

        Returns:
            与 OpenAI 视频任务同构的 dict：
            {"id", "status": "completed", "video_url", "progress": 100,
             "raw_response": {...}}

        Raises:
            ServiceException: 提交或任务失败
            TimeoutError: 超过最长等待时间
        """
        ignored = [k for k in ("fps", "motion_strength", "camera_motion",
                               "reference_weight", "resolution")
                   if kwargs.get(k) is not None]
        if ignored:
            self.logger.debug(
                f"Ignoring params unsupported by Ali gateway: {ignored}"
            )

        seconds = int(round(duration)) if duration else self.default_duration
        model, media = self._resolve_model_and_media(image_path)
        watermark = kwargs.get("watermark")
        payload = self._build_payload(model, prompt, media, seconds, watermark)

        self.logger.info(
            f"Submitting Ali video task | model={model} | duration={seconds}s | "
            f"media={'first_frame' if media else 'none'} | "
            f"watermark={payload['parameters']['watermark']} | "
            f"prompt: {prompt[:50]}..."
        )
        task_id = await self._submit_task(payload)
        output = await self._wait_for_completion(task_id)
        return self._to_openai_shape(task_id, output)

    def _resolve_model_and_media(self, image_path):
        """首帧媒体归一化；无图输入时切换 t2v 模型。"""
        if image_path is None or (
            isinstance(image_path, (list, tuple)) and not image_path
        ):
            return self.t2v_model, None
        images = (
            [image_path] if isinstance(image_path, str) else list(image_path)
        )
        if len(images) > 1:
            self.logger.warning(
                f"Ali gateway accepts a single first_frame; ignoring "
                f"{len(images) - 1} continuity reference image(s)"
            )
        media = [{"type": "first_frame", "url": image_to_data_uri(images[0])}]
        return self.model, media

    def _build_payload(self, model, prompt, media, seconds,
                       watermark: Optional[bool] = None) -> Dict[str, Any]:
        """构造 video-synthesis 请求体。

        ``parameters.watermark`` 是本网关控制成品水印的唯一开关：不传时返回的
        CDN 文件名带 ``refiner_watermark`` 标记（即默认带水印）。
        """
        input_body: Dict[str, Any] = {"prompt": prompt}
        if media:
            input_body["media"] = media

        params: Dict[str, Any] = {"duration": seconds}
        params["watermark"] = self.watermark if watermark is None else bool(watermark)

        return {
            "model": model,
            "input": input_body,
            "parameters": params,
        }

    async def _submit_task(self, payload: Dict[str, Any]) -> str:
        """POST 提交异步任务，返回 task_id。"""
        headers = {"X-DashScope-Async": "enable"}
        try:
            response = await self.client.post(
                self.endpoint, json=payload, headers=headers
            )
        except httpx.HTTPError as e:
            raise ServiceException(
                message=f"Ali video submit failed: {e.__class__.__name__}: {e}",
                service_name=self.SERVICE_NAME,
                retryable=True,
                original_error=e,
                error_type="video_generation_failed",
                stage="video_generation",
            )
        if response.status_code != 200:
            raise self._video_error(response, "video_generation")
        try:
            task_id = response.json()["output"]["task_id"]
        except (KeyError, ValueError) as e:
            raise ServiceException(
                message=f"Ali video submit returned no task_id: "
                        f"{response.text[:300]}",
                service_name=self.SERVICE_NAME,
                retryable=False,
                original_error=e,
                error_type="video_generation_failed",
                stage="video_generation",
            )
        self.logger.info(f"Ali video task submitted: {task_id}")
        return task_id

    async def _wait_for_completion(
        self,
        task_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_wait: float = DEFAULT_MAX_WAIT,
    ) -> Dict[str, Any]:
        """轮询任务直到 SUCCEEDED / FAILED，返回 output 字典。"""
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > max_wait:
                raise TimeoutError(
                    f"Ali video task {task_id} timed out after {max_wait}s"
                )
            output = await self.check_task_status(task_id)
            status = output.get("task_status")
            self.logger.info(
                f"Ali task {task_id} status: {status} ({elapsed:.0f}s elapsed)"
            )
            if status == "SUCCEEDED":
                return output
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                raise ServiceException(
                    message=output.get("message") or f"Ali video task {status}",
                    service_name=self.SERVICE_NAME,
                    retryable=self._is_retryable_code(output.get("code", "")),
                    error_code=str(output.get("code", "")),
                    error_type="video_generation_failed",
                    stage="video_generation_polling",
                    api_response=output,
                )
            await asyncio.sleep(poll_interval)

    async def check_task_status(self, task_id: str) -> Dict[str, Any]:
        """GET /api/v1/tasks/{id}，返回 output 字典。"""
        try:
            response = await self.client.get(f"{NATIVE_TASK_ENDPOINT}/{task_id}")
            response.raise_for_status()
            return response.json().get("output", {})
        except httpx.HTTPError as e:
            self.logger.warning(f"Ali task poll error (will retry): {e}")
            return {}

    def _to_openai_shape(self, task_id: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """把原生 output 转为下游期望的 OpenAI 视频任务结构。"""
        video_url = output.get("video_url")
        if not video_url:
            raise ServiceException(
                message=f"Ali task succeeded without video_url: {str(output)[:300]}",
                service_name=self.SERVICE_NAME,
                retryable=False,
                error_type="video_generation_failed",
                stage="video_generation_polling",
                api_response=output,
            )
        return {
            "id": task_id,
            "status": "completed",
            "progress": 100,
            "video_url": video_url,
            "raw_response": output,
        }

    def _video_error(self, response: httpx.Response, stage: str) -> ServiceException:
        """把非 200 响应转换为 ServiceException。"""
        try:
            body = response.json()
        except ValueError:
            body = {"raw_text": response.text[:500]}
        code = str(body.get("code", ""))
        message = body.get("message") or f"API returned {response.status_code}"
        self.logger.error(f"Ali video API failed: {response.status_code} {code} {message}")
        retryable = (
            response.status_code >= 500
            or response.status_code == 429
            or self._is_retryable_code(code)
        )
        return ServiceException(
            message=message,
            service_name=self.SERVICE_NAME,
            retryable=retryable,
            error_code=code,
            error_type="video_generation_failed",
            stage=stage,
            api_response=body,
        )

    @staticmethod
    def _is_retryable_code(code: str) -> bool:
        """网关任务级错误码是否值得重试（限流/内部错误类）。"""
        retryable_markers = (
            "THROTTLING", "INTERNALERROR", "SERVICEUNAVAILABLE",
            "TIMEOUT", "SYSTEM",
        )
        upper = (code or "").upper()
        return any(marker in upper for marker in retryable_markers)

    async def download_video(self, video_url: str, save_path: Path) -> Path:
        """下载生成的视频到本地（与 Veo3/Sora2 客户端接口一致）。"""
        self.logger.info(f"Downloading video from {video_url[:80]}...")
        async with httpx.AsyncClient() as download_client:
            response = await download_client.get(
                video_url, timeout=300.0, follow_redirects=True
            )
            response.raise_for_status()
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(response.content)
        self.logger.info(f"Video saved to {save_path}")
        return save_path

    async def __aenter__(self) -> "AliTokenPlanVideoService":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False
