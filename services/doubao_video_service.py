"""Doubao Seedance video service (Volcano Ark).

Why this service exists
-----------------------
Volcano Ark exposes image-to-video (i2v) and text-to-video (t2v) through an
asynchronous task API that is **not** OpenAI-compatible, so neither
``Veo3Service``/``Sora2Service`` nor the DashScope-based
``AliTokenPlanVideoService`` can drive it.

Wire protocol (verified against the live Ark endpoint)
-----------------------------------------------------
1. ``POST {base}/contents/generations/tasks`` with
   ``{"model", "content": [{"type": "text", "text": <prompt>},
   {"type": "image_url", "image_url": {"url": <http url | data-uri>}}],
   "resolution": "720p", "duration": 10, "ratio": "16:9"}``
   -> ``{"id": "cgt-..."}``
2. ``GET {base}/contents/generations/tasks/{id}`` polled until
   ``status`` is ``succeeded`` (``content.video_url``) or ``failed``.
3. Download the mp4 from ``video_url`` (signed CDN URL, no auth header).

``resolution``/``duration``/``ratio`` are JSON fields — Ark rejects them when
they are appended to the prompt text (unlike the zenmux gateway).
"""
from __future__ import annotations

import asyncio
import base64
import mimetypes
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

from backend.core.exceptions import ServiceException
from config.settings import settings

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_TASKS_ENDPOINT = "/contents/generations/tasks"
DEFAULT_MODEL = "doubao-seedance-2-0-260128"
DEFAULT_T2V_MODEL = "doubao-seedance-2-0-260128"
DEFAULT_POLL_INTERVAL = 5.0
# Seedance takes minutes for a 10s 720p clip; keep the ceiling generous.
DEFAULT_MAX_WAIT = 900.0

# Ark accepts these knobs only as discrete values.
SUPPORTED_RESOLUTIONS = ("480p", "720p", "1080p")
# seedance 1.0 pro is limited to 5/10s; 2.x accepts 4-15s. Snapping keeps both
# happy without the agent having to know which model is configured.
SUPPORTED_DURATIONS = (4, 5, 6, 8, 10, 12, 15)
SUPPORTED_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive")


def _snap(value: float, allowed) -> Any:
    return min(allowed, key=lambda candidate: abs(candidate - value))


class DoubaoVideoService:
    """Volcano Ark Seedance 图生视频 / 文生视频服务。"""

    SERVICE_NAME = "Doubao Seedance (Ark)"
    SUPPORTED_DURATIONS = SUPPORTED_DURATIONS
    SUPPORTED_RESOLUTIONS = SUPPORTED_RESOLUTIONS

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        t2v_model: Optional[str] = None,
        default_resolution: Optional[str] = None,
        default_ratio: Optional[str] = None,
        default_duration: Optional[int] = None,
        watermark: Optional[bool] = None,
    ):
        self.api_key = api_key or getattr(settings, "doubao_video_api_key", "")
        self.base_url = (base_url or getattr(settings, "doubao_video_base_url", DEFAULT_BASE_URL)).rstrip("/")
        self.endpoint = endpoint or getattr(settings, "doubao_video_endpoint", DEFAULT_TASKS_ENDPOINT)
        self.model = model or getattr(settings, "doubao_video_model", DEFAULT_MODEL)
        self.t2v_model = t2v_model or getattr(settings, "doubao_video_t2v_model", DEFAULT_T2V_MODEL)
        self.default_resolution = (
            default_resolution or getattr(settings, "doubao_video_default_resolution", "720p")
        )
        self.default_ratio = default_ratio or getattr(settings, "doubao_video_default_ratio", "16:9")
        self.default_duration = int(
            default_duration or getattr(settings, "doubao_video_default_duration", 5)
        )
        self.watermark = (
            watermark
            if watermark is not None
            else bool(getattr(settings, "doubao_video_watermark", False))
        )
        # Kept for callers that read a ``default_size`` off the service (the
        # agent does this for Sora2-style services).
        self.default_size = "1280x720" if self.default_resolution == "720p" else "1920x1080"
        self.default_style = None
        self.private = False
        self.logger = __import__("logging").getLogger(__name__)

        if not self.api_key:
            self.logger.warning("DoubaoVideoService initialized without API key")

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120.0,
        )
        self.logger.info(
            f"DoubaoVideoService initialized | model={self.model} | "
            f"base_url={self.base_url} | resolution={self.default_resolution} | "
            f"duration={self.default_duration}s | watermark={self.watermark}"
        )

    # ------------------------------------------------------------------ utils

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "DoubaoVideoService":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.close()
        return False

    @staticmethod
    def to_data_uri(image: Union[str, Path]) -> str:
        """Local file -> base64 data URI; http(s)/data URIs pass through."""
        if isinstance(image, str) and (image.startswith("http://") or image.startswith("https://")):
            return image
        if isinstance(image, str) and image.startswith("data:"):
            return image
        path = Path(image)
        if not path.exists():
            raise ServiceException(
                message=f"Seedance input image not found: {path}",
                service_name=DoubaoVideoService.SERVICE_NAME,
                retryable=False,
                error_type="video_generation_failed",
                stage="video_generation",
            )
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def _normalise_resolution(self, raw: Optional[str]) -> str:
        """Accept ``720p``, ``1280x720`` or ``1920x1080`` and pick an Ark value."""
        if not raw:
            return self.default_resolution
        value = str(raw).strip().lower()
        if value in SUPPORTED_RESOLUTIONS:
            return value
        if "x" in value:
            try:
                height = int(value.split("x")[1])
            except (IndexError, ValueError):
                return self.default_resolution
            if height >= 1080:
                return "1080p"
            if height >= 720:
                return "720p"
            return "480p"
        return self.default_resolution

    def _normalise_ratio(self, raw: Optional[str]) -> str:
        value = (raw or self.default_ratio or "16:9").strip().lower()
        return value if value in SUPPORTED_RATIOS else "16:9"

    # -------------------------------------------------------------- interface

    async def image_to_video(
        self,
        image_path: Optional[Union[str, List[str]]],
        duration: Optional[float] = None,
        prompt: str = "Generate video from this image",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Submit an Ark Seedance task and poll it to completion.

        Args:
            image_path: first-frame image (local path / http URL / data URI).
                ``None`` or an empty list switches to the text-to-video model.
            duration: requested seconds; snapped to an Ark-supported value.
            prompt: motion / camera description.
            **kwargs: ``resolution``/``size``, ``ratio``/``aspect_ratio``,
                ``watermark``, ``camera_motion`` etc. Unknown keys are ignored.

        Returns:
            OpenAI-shaped task dict: ``{"id", "status", "progress",
            "video_url", "raw_response"}``.
        """
        image = image_path
        if isinstance(image, (list, tuple)):
            if len(image) > 1:
                self.logger.warning(
                    "Seedance accepts a single first frame; ignoring %d extra reference image(s)",
                    len(image) - 1,
                )
            image = image[0] if image else None

        if duration:
            seconds = _snap(float(duration), SUPPORTED_DURATIONS)
            if abs(float(duration) - seconds) > 0.01:
                self.logger.warning(
                    "Requested duration %ss snapped to %ss (Seedance constraint)", duration, seconds
                )
        else:
            seconds = _snap(float(self.default_duration), SUPPORTED_DURATIONS)

        resolution = self._normalise_resolution(kwargs.get("resolution") or kwargs.get("size"))
        ratio = self._normalise_ratio(kwargs.get("ratio") or kwargs.get("aspect_ratio"))
        watermark = kwargs.get("watermark")
        model = self.model if image else self.t2v_model

        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image:
            content.append({"type": "image_url", "image_url": {"url": self.to_data_uri(image)}})

        payload: Dict[str, Any] = {
            "model": model,
            "content": content,
            "resolution": resolution,
            "duration": int(seconds),
            "ratio": ratio,
        }
        if watermark is not None:
            payload["watermark"] = bool(watermark)

        self.logger.info(
            "Submitting Seedance task | model=%s | duration=%ss | resolution=%s | ratio=%s | "
            "image=%s | prompt=%s...",
            model,
            seconds,
            resolution,
            ratio,
            "yes" if image else "no (t2v)",
            prompt[:60],
        )

        task_id = await self._submit(payload)
        output = await self._wait_for_completion(task_id)
        return self._to_openai_shape(task_id, output)

    # ------------------------------------------------------------------ http

    async def _submit(self, payload: Dict[str, Any]) -> str:
        try:
            response = await self.client.post(self.endpoint, json=payload)
        except httpx.HTTPError as exc:
            raise ServiceException(
                message=f"Seedance submit failed: {exc.__class__.__name__}: {exc}",
                service_name=self.SERVICE_NAME,
                retryable=True,
                original_error=exc,
                error_type="video_generation_failed",
                stage="video_generation",
            )
        if response.status_code != 200:
            raise self._video_error(response, "video_generation")
        try:
            task_id = response.json()["id"]
        except (KeyError, ValueError) as exc:
            raise ServiceException(
                message=f"Seedance submit returned no task id: {response.text[:300]}",
                service_name=self.SERVICE_NAME,
                retryable=False,
                original_error=exc,
                error_type="video_generation_failed",
                stage="video_generation",
            )
        self.logger.info(f"Seedance task submitted: {task_id}")
        return task_id

    async def check_task_status(self, task_id: str) -> Dict[str, Any]:
        try:
            response = await self.client.get(f"{self.endpoint}/{task_id}")
            if response.status_code != 200:
                self.logger.warning(
                    f"Seedance poll returned {response.status_code}: {response.text[:200]}"
                )
                return {}
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.warning(f"Seedance poll error (will retry): {exc}")
            return {}

    async def _wait_for_completion(
        self,
        task_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_wait: float = DEFAULT_MAX_WAIT,
    ) -> Dict[str, Any]:
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > max_wait:
                raise TimeoutError(f"Seedance task {task_id} timed out after {max_wait}s")
            output = await self.check_task_status(task_id)
            status = (output.get("status") or "").lower()
            if status:
                self.logger.info(
                    "Seedance task %s status: %s (%.0fs elapsed)", task_id, status, elapsed
                )
            if status == "succeeded":
                return output
            if status in ("failed", "cancelled", "canceled", "expired"):
                error = output.get("error") or {}
                raise ServiceException(
                    message=(
                        error.get("message")
                        if isinstance(error, dict)
                        else str(error)
                    )
                    or f"Seedance task {status}",
                    service_name=self.SERVICE_NAME,
                    retryable=str(error.get("code", "")).upper() in {"RATE_LIMIT", "INTERNAL"},
                    error_code=str(error.get("code", "")) if isinstance(error, dict) else "",
                    error_type="video_generation_failed",
                    stage="video_generation_polling",
                    api_response=output,
                )
            await asyncio.sleep(poll_interval)

    @staticmethod
    def _to_openai_shape(task_id: str, output: Dict[str, Any]) -> Dict[str, Any]:
        # Ark answers ``content`` as a single object for these models; older
        # responses use a list. Accept both shapes.
        content = output.get("content")
        items = content if isinstance(content, list) else [content] if content else []
        video_url = None
        for item in items:
            if isinstance(item, dict) and item.get("video_url"):
                video_url = item["video_url"]
                break
        if not video_url:
            raise ServiceException(
                message=f"Seedance task succeeded without video_url: {str(output)[:300]}",
                service_name=DoubaoVideoService.SERVICE_NAME,
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
        try:
            body = response.json()
        except ValueError:
            body = {"raw_text": response.text[:500]}
        error = body.get("error") if isinstance(body, dict) else None
        code = str((error or {}).get("code", "")) if isinstance(error, dict) else ""
        message = (
            (error or {}).get("message") if isinstance(error, dict) else None
        ) or f"Ark API returned {response.status_code}"
        self.logger.error(f"Seedance API failed: {response.status_code} {code} {message}")

        # Inputs that look like a real person are rejected by Ark's safety
        # filter. Retrying the same image is pointless, so fail fast with the
        # concrete remedies instead of burning 4 attempts.
        sensitive = "SensitiveContent" in code or "SensitiveContent" in message
        retryable = (response.status_code >= 500 or response.status_code == 429) and not sensitive
        if sensitive:
            message = (
                f"{message} —— 火山方舟判定输入图片可能包含真人（内容安全策略）。"
                "可改用插画/电影感风格的场景图，或在设置里关闭「场景连续性参考帧」"
                "（ENABLE_SCENE_CONTINUITY=false），避免使用上一镜头视频截帧作为输入。"
            )
        if "ModelNotOpen" in code or "NotFound" in code:
            message = (
                f"{message} —— 该 Key 未开通模型 {self.model}，请在火山方舟控制台开通 "
                "Seedance 视频生成（或改用其他模型 ID）"
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

    async def download_video(self, video_url: str, save_path: Path) -> Path:
        """Download the produced mp4 (signed CDN URL, no auth header)."""
        self.logger.info(f"Downloading Seedance video from {video_url[:80]}...")
        async with httpx.AsyncClient() as download_client:
            response = await download_client.get(video_url, timeout=600.0, follow_redirects=True)
            response.raise_for_status()
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(response.content)
        self.logger.info(f"Video saved to {save_path} ({save_path.stat().st_size / 1024:.0f} KB)")
        return save_path


__all__ = ["DoubaoVideoService", "SUPPORTED_DURATIONS", "SUPPORTED_RESOLUTIONS", "DEFAULT_MODEL"]
