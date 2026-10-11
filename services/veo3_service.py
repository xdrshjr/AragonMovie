"""Veo3 video generation API service client"""
import httpx
import asyncio
import time
from typing import Dict, Any, Optional, Union, List
from pathlib import Path

from config.settings import settings
from utils.retry import async_retry
from backend.core.exceptions import ServiceException
import logging


class VideoGenerationError(Exception):
    """视频生成基础异常"""
    def __init__(self, message: str, error_code: str = "", retryable: bool = True, error_type: str = ""):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.error_type = error_type  # 错误类型：audio_filtered, content_policy, etc.


class Veo3Service:
    """Veo3 API服务封装 - 图片到视频转换"""

    # 子类可覆盖的服务名（用于错误信息展示）
    SERVICE_NAME = "Veo3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        upload_endpoint: Optional[str] = None,
        skip_upload: Optional[bool] = None
    ):
        """
        初始化服务

        Args:
            api_key: API密钥
            base_url: API基础URL
            endpoint: API端点路径
            model: 视频生成模型名称
            upload_endpoint: 图片上传端点（如果需要上传）
            skip_upload: 是否跳过上传，直接使用 base64
        """
        self.api_key = api_key or settings.veo3_api_key
        self.base_url = base_url or settings.veo3_base_url
        self.endpoint = endpoint or settings.veo3_endpoint
        self.model = model or settings.veo3_model
        self.upload_endpoint = upload_endpoint or settings.veo3_upload_endpoint
        self.skip_upload = skip_upload if skip_upload is not None else settings.veo3_skip_upload
        self.logger = logging.getLogger(__name__)

        # 使用 Bearer token 认证
        # 注意：不设置默认 Content-Type，因为 multipart 请求需要不同的 Content-Type
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}"
            },
            timeout=120.0  # Veo3生成视频可能较慢
        )

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()

    @async_retry(
        max_attempts=3,
        backoff_factor=2.0,
        exceptions=(httpx.HTTPError, asyncio.TimeoutError)
    )
    async def image_to_video(
        self,
        image_path: Union[str, List[str]],
        duration: Optional[float] = None,
        fps: int = 30,
        resolution: str = "1920x1080",
        motion_strength: float = 0.5,
        camera_motion: Optional[str] = None,
        reference_weight: float = 0.5,
        **kwargs
    ) -> Dict[str, Any]:
        """
        将图片转换为视频

        Args:
            image_path: 图片文件路径（单张或多张列表）
            duration: 视频时长（秒，可选，默认None让模型自动决定）
            fps: 帧率
            resolution: 分辨率
            motion_strength: 运动强度（0.0-1.0）
            camera_motion: 摄像机运动类型（pan/tilt/zoom/static）
            reference_weight: 参考图权重（0.0-1.0），用于多图片模式
            **kwargs: 其他API参数

        Returns:
            API响应，包含任务ID或视频URL
        """
        # 处理单张或多张图片
        image_paths = [image_path] if isinstance(image_path, str) else image_path

        # veo OpenAI 格式：使用 multipart/form-data 直接上传图片
        if len(image_paths) == 1:
            self.logger.info(f"Generating video using single image from: {image_paths[0]}")
        else:
            self.logger.info(f"Generating video using {len(image_paths)} images (continuity mode)")
            self.logger.info(f"  - Base image: {image_paths[0]}")
            self.logger.info(f"  - Reference image: {image_paths[1]}")
            self.logger.info(f"  - Reference weight: {reference_weight}")

        # 构建 form data
        files = {}
        file_handles = []

        try:
            # 打开所有图片文件
            for idx, img_path in enumerate(image_paths):
                file_handle = open(img_path, 'rb')
                file_handles.append(file_handle)

                if idx == 0:
                    # 第一张图片作为主要参考
                    files['input_reference'] = (Path(img_path).name, file_handle, 'image/png')
                else:
                    # 额外的参考图（用于场景连续性）
                    files['additional_reference'] = (Path(img_path).name, file_handle, 'image/png')

            # 构建其他字段
            data = {
                'model': self.model,
                'prompt': kwargs.get('prompt', 'Generate video from this image'),
                'size': kwargs.get('size', '1920x1080'),
                'watermark': 'false'
            }

            # 添加参考权重（仅在多图片模式下）
            if len(image_paths) > 1:
                data['reference_weight'] = str(reference_weight)

            # 只有在明确指定duration时才添加，否则让视频模型自己决定
            if duration is not None:
                data['seconds'] = str(int(duration))
                self.logger.info(f"⚠️ Setting video duration to {duration}s (seconds={int(duration)})")

            self.logger.debug(f"Using model: {self.model}")
            self.logger.info(f"📤 Sending request with data: {data}")

            try:
                # 使用 multipart/form-data，需要临时移除 Content-Type header
                response = await self.client.post(
                    self.endpoint,  # /v1/videos
                    data=data,
                    files=files,
                    headers={"Authorization": f"Bearer {self.api_key}"}  # 只保留 Authorization
                )

                self.logger.debug(f"Veo response status: {response.status_code}")
                self.logger.debug(f"Veo response headers: {dict(response.headers)}")

                response.raise_for_status()

                result = response.json()
                self.logger.debug(f"Veo response: {result}")

                # OpenAI 格式返回：{"id": "video_xxx", "status": "queued", "progress": 0, ...}
                video_id = result.get('id')
                status = result.get('status')
                progress = result.get('progress', 0)

                self.logger.info(f"Video generation task created: {video_id}, status: {status}, progress: {progress}%")

                # 如果是异步任务（status=queued），等待完成
                if status in ['queued', 'processing'] and video_id:
                    result = await self._wait_for_completion(video_id)

                return result

            except httpx.HTTPStatusError as e:
                error_response = None
                error_code = ""
                error_message = f"Veo3 API request failed with status {e.response.status_code}"

                # 尝试解析错误响应
                try:
                    error_response = e.response.json()
                    if isinstance(error_response, dict):
                        # 提取错误信息（支持多种格式）
                        error_code = error_response.get('error', {}).get('code', '') if isinstance(error_response.get('error'), dict) else error_response.get('code', '')
                        error_msg = error_response.get('error', {}).get('message', '') if isinstance(error_response.get('error'), dict) else error_response.get('message', '')
                        if error_msg:
                            error_message = error_msg
                except Exception:
                    # 如果无法解析JSON，使用原始文本
                    error_response = {"raw_text": e.response.text}

                self.logger.error(f"Veo3 API request failed: {e.response.status_code}")
                self.logger.error(f"Error code: {error_code}")
                self.logger.error(f"Error message: {error_message}")
                self.logger.error(f"Response: {e.response.text[:500]}")

                # 抛出增强的ServiceException
                raise ServiceException(
                    message=error_message,
                    service_name=self.SERVICE_NAME,
                    retryable=e.response.status_code >= 500,  # 5xx错误可重试
                    original_error=e,
                    error_code=error_code,
                    error_type="video_generation_failed",
                    stage="video_generation",
                    api_response=error_response
                )

        finally:
            # 确保关闭所有文件句柄
            for file_handle in file_handles:
                try:
                    file_handle.close()
                except Exception as e:
                    self.logger.warning(f"Failed to close file handle: {e}")

    async def _upload_image(self, image_path: str) -> str:
        """
        上传图片到Veo3服务器

        Args:
            image_path: 本地图片路径

        Returns:
            上传后的图片URL
        """
        with open(image_path, 'rb') as f:
            files = {'file': (Path(image_path).name, f, 'image/png')}

            # 注意：上传图片时需要移除 Content-Type header
            headers = {"Authorization": f"Bearer {self.api_key}"}

            # 使用配置的上传端点
            upload_endpoint = self.upload_endpoint or "/upload-image"

            async with httpx.AsyncClient(base_url=self.base_url) as upload_client:
                response = await upload_client.post(
                    upload_endpoint,
                    files=files,
                    headers=headers,
                    timeout=60.0
                )

                self.logger.debug(f"Upload response status: {response.status_code}")
                self.logger.debug(f"Upload response headers: {dict(response.headers)}")

                response.raise_for_status()

                # 检查响应内容
                response_text = response.text
                self.logger.debug(f"Upload raw response: {response_text[:500]}")

                if not response_text or not response_text.strip():
                    raise ValueError(f"Empty response from upload API. Status: {response.status_code}")

                try:
                    result = response.json()
                except Exception as json_err:
                    self.logger.error(f"Failed to parse upload response. Raw text: {response_text[:500]}")
                    raise ValueError(f"Invalid JSON response from upload: {json_err}") from json_err

                image_url = result.get('url')
                if not image_url:
                    self.logger.error(f"No 'url' in response: {result}")
                    raise ValueError(f"Upload response missing 'url' field: {result}")

                self.logger.info(f"Image uploaded: {image_url}")
                return image_url

    async def _wait_for_completion(
        self,
        task_id: str,
        poll_interval: float = 5.0,
        max_wait_time: float = 600.0
    ) -> Dict[str, Any]:
        """
        等待视频生成任务完成

        Args:
            task_id: 任务ID
            poll_interval: 轮询间隔（秒）
            max_wait_time: 最大等待时间（秒）

        Returns:
            完成后的任务结果

        Raises:
            TimeoutError: 超过最大等待时间
        """
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_time:
                raise TimeoutError(
                    f"Video generation timeout after {max_wait_time}s"
                )

            # 查询任务状态
            status = await self.check_task_status(task_id)
            state = status.get('status')  # OpenAI 格式使用 'status' 字段
            progress = status.get('progress', 0)

            self.logger.info(
                f"Task {task_id} status: {state}, progress: {progress}% "
                f"({elapsed:.1f}s elapsed)"
            )

            if state == 'completed':
                # 任务完成，检查是否包含 video_url
                video_url = status.get('video_url')
                if video_url:
                    self.logger.info(f"Task {task_id} completed with video URL: {video_url}")
                    return status
                else:
                    # 如果没有 video_url，尝试通过 content 端点获取
                    self.logger.info(f"Task {task_id} completed, fetching video URL...")
                    video_url = await self._download_video_content(task_id)
                    status['video_url'] = video_url
                    return status
            elif state == 'failed':
                error_msg = status.get('error', 'Unknown error')
                error_code = ""

                # 解析错误信息
                if isinstance(error_msg, dict):
                    error_code = error_msg.get('code', '')
                    error_message = error_msg.get('message', str(error_msg))
                else:
                    error_message = str(error_msg)
                    # 尝试从错误消息中提取错误码
                    if 'code' in error_message.lower():
                        error_code = error_message

                self.logger.error(f"Video generation failed: code={error_code}, message={error_message}")

                # 判断错误类型
                error_type = self._classify_error_type(error_code, error_message)

                # 判断是否可重试
                retryable = self._is_retryable_error(error_code, error_message)

                # 抛出增强的ServiceException而不是VideoGenerationError
                raise ServiceException(
                    message=error_message,
                    service_name=self.SERVICE_NAME,
                    retryable=retryable,
                    original_error=None,
                    error_code=error_code,
                    error_type=error_type,
                    stage="video_generation_polling",
                    api_response=status
                )

            await asyncio.sleep(poll_interval)

    async def _download_video_content(self, task_id: str) -> str:
        """
        通过 OpenAI 格式的 content 端点获取视频下载链接

        Args:
            task_id: 任务ID

        Returns:
            视频下载URL
        """
        # OpenAI 格式：GET /v1/videos/{id}/content
        response = await self.client.get(f"{self.endpoint}/{task_id}/content", follow_redirects=False)

        self.logger.debug(f"Video content response status: {response.status_code}")
        self.logger.debug(f"Video content response headers: {dict(response.headers)}")

        # 如果返回 302/307 重定向，获取 Location 头中的实际视频 URL
        if response.status_code in (302, 307, 301):
            video_url = response.headers.get('Location')
            if video_url:
                self.logger.info(f"Got video URL from redirect: {video_url}")
                return video_url
            else:
                raise ValueError("Redirect response missing Location header")

        # 如果返回 200 且是 JSON，可能包含 video_url 字段
        response.raise_for_status()
        if 'application/json' in response.headers.get('content-type', ''):
            result = response.json()
            video_url = result.get('video_url') or result.get('url')
            if video_url:
                self.logger.info(f"Got video URL from JSON response: {video_url}")
                return video_url

        raise ValueError("Could not get video URL from content endpoint")

    def _classify_error_type(self, error_code: str, error_message: str) -> str:
        """
        分类错误类型

        Args:
            error_code: 错误码
            error_message: 错误消息

        Returns:
            错误类型字符串
        """
        error_upper = error_message.upper()
        error_code_upper = error_code.upper()

        # 音频过滤错误（通常是台词内容问题）
        if 'AUDIO_FILTERED' in error_upper or 'AUDIO_FILTERED' in error_code_upper:
            return 'audio_filtered'

        # 内容策略违规
        if 'CONTENT_POLICY' in error_upper or 'CONTENT_POLICY' in error_code_upper:
            return 'content_policy'

        # 版权违规
        if 'COPYRIGHT' in error_upper or 'COPYRIGHT' in error_code_upper:
            return 'copyright'

        # 无效提示词
        if 'INVALID_PROMPT' in error_upper or 'INVALID_PROMPT' in error_code_upper:
            return 'invalid_prompt'

        return 'unknown'

    def _is_retryable_error(self, error_code: str, error_message: str) -> bool:
        """
        判断错误是否可重试

        Args:
            error_code: 错误码
            error_message: 错误消息

        Returns:
            是否可重试
        """
        # 不可重试的错误码列表（内容审核、违规等）
        non_retryable_codes = [
            'PROMINENT_PEOPLE_FILTER_FAILED',  # 名人检测失败
            'CONTENT_POLICY_VIOLATION',  # 内容违规
            'NSFW_CONTENT_DETECTED',  # 不适宜内容
            'COPYRIGHT_VIOLATION',  # 版权违规
            'INVALID_INPUT',  # 无效输入
            'INVALID_PROMPT',  # 无效提示词
        ]

        # 可重试的错误码列表（临时性错误）
        retryable_codes = [
            'INTERNAL_ERROR',  # 内部错误
            'SERVICE_UNAVAILABLE',  # 服务不可用
            'TIMEOUT',  # 超时
            'RATE_LIMIT_EXCEEDED',  # 速率限制
            'INSUFFICIENT_QUOTA',  # 配额不足（可能短时间后恢复）
        ]

        error_upper = error_message.upper()

        # 检查明确的不可重试错误
        for code in non_retryable_codes:
            if code in error_code.upper() or code in error_upper:
                self.logger.warning(f"Non-retryable error detected: {code}")
                return False

        # 检查明确的可重试错误
        for code in retryable_codes:
            if code in error_code.upper() or code in error_upper:
                self.logger.info(f"Retryable error detected: {code}")
                return True

        # 默认：未知错误视为可重试（保守策略）
        self.logger.info(f"Unknown error type, treating as retryable: {error_message}")
        return True

    async def check_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        检查任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态信息
        """
        # OpenAI 格式的任务状态查询
        response = await self.client.get(f"{self.endpoint}/{task_id}")

        self.logger.debug(f"Task status response status: {response.status_code}")
        self.logger.debug(f"Task status response headers: {dict(response.headers)}")
        self.logger.debug(f"Task status response content: {response.text[:500]}")

        response.raise_for_status()

        # 检查是否是 JSON 响应
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            self.logger.error(f"Unexpected content type: {content_type}")
            self.logger.error(f"Response body: {response.text[:1000]}")
            raise ValueError(f"API returned non-JSON response: {content_type}")

        return response.json()

    async def download_video(
        self,
        video_url: str,
        save_path: Path
    ) -> Path:
        """
        下载生成的视频

        Args:
            video_url: 视频URL
            save_path: 保存路径

        Returns:
            实际保存的文件路径
        """
        self.logger.info(f"Downloading video from {video_url}")

        try:
            async with httpx.AsyncClient() as download_client:
                response = await download_client.get(
                    video_url,
                    timeout=300.0,  # 视频文件可能较大
                    follow_redirects=True
                )
                response.raise_for_status()

                save_path.parent.mkdir(parents=True, exist_ok=True)

                with open(save_path, 'wb') as f:
                    f.write(response.content)

                self.logger.info(f"Video saved to {save_path}")
                return save_path

        except Exception as e:
            self.logger.error(f"Failed to download video: {e}")
            raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
