"""Nano Banana Pro API service client"""
import httpx
import asyncio
import base64
from typing import Dict, Any, Optional
from pathlib import Path
from config.settings import settings
from utils.retry import async_retry
from backend.core.exceptions import ServiceException
import logging


class NanoBananaService:
    """Nano Banana Pro API服务封装 - 图片生成"""

    # 子类可覆盖的服务名（用于错误信息展示）
    SERVICE_NAME = "Nano Banana Pro"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化服务

        Args:
            api_key: API密钥
            base_url: API基础URL
            endpoint: API端点路径（如 /generate, /v1/images/generations 等）
            model: 图像生成模型名称（如 dall-e-3, gpt-image-1.5 等）
        """
        self.api_key = api_key or settings.nano_banana_api_key
        self.base_url = base_url or settings.nano_banana_base_url
        self.endpoint = endpoint or settings.nano_banana_endpoint
        self.model = model or settings.nano_banana_model
        self.logger = logging.getLogger(__name__)

        # 构建 headers - 支持多种认证方式
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",  # 标准 Bearer token
        }

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=60.0
        )

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()

    def _normalize_image_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化不同 API 的响应格式

        支持:
        - OpenAI 格式: {"data": [{"url": "...", "b64_json": "..."}]}
        - 自定义格式: {"image_url": "...", "image_base64": "..."}

        Returns:
            统一格式: {"image_url": "...", "image_base64": "...", "raw_response": {...}}
        """
        normalized = {"raw_response": response}

        # OpenAI 格式
        if "data" in response and isinstance(response["data"], list) and len(response["data"]) > 0:
            first_image = response["data"][0]
            if "url" in first_image:
                normalized["image_url"] = first_image["url"]
            if "b64_json" in first_image:
                normalized["image_base64"] = first_image["b64_json"]
            return normalized

        # 自定义格式
        if "image_url" in response:
            normalized["image_url"] = response["image_url"]
        if "image_base64" in response:
            normalized["image_base64"] = response["image_base64"]
        if "url" in response:
            normalized["image_url"] = response["url"]
        if "b64_json" in response:
            normalized["image_base64"] = response["b64_json"]

        return normalized

    @async_retry(
        max_attempts=3,
        backoff_factor=2.0,
        exceptions=(httpx.HTTPError, asyncio.TimeoutError)
    )
    async def generate_image(
        self,
        prompt: str,
        width: int = 1920,
        height: int = 1080,
        quality: str = "high",
        style: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        cfg_scale: Optional[float] = None,
        steps: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成图片

        Args:
            prompt: 图片描述提示词
            width: 图片宽度
            height: 图片高度
            quality: 质量（high/medium/low）
            style: 风格（可选）
            negative_prompt: 负面提示词
            seed: 随机种子，用于确定性生成（可选）
            cfg_scale: CFG引导强度，控制prompt遵循程度（可选）
            steps: 推理步数，影响生成质量（可选）
            **kwargs: 其他API参数

        Returns:
            API响应，包含图片URL或Base64数据
        """
        # 构建请求 payload（按用户配置）
        payload = {
            "model": self.model,  # 使用配置的模型
            "prompt": prompt,
            "size": f"{width}x{height}",  # OpenAI 格式
            "n": 1,  # 生成1张图
            **kwargs
        }

        # 可选参数
        if quality and quality != "high":
            payload["quality"] = quality

        if style:
            payload["style"] = style

        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        # 一致性控制参数
        if seed is not None:
            payload["seed"] = seed

        if cfg_scale is not None:
            payload["cfg_scale"] = cfg_scale

        if steps is not None:
            payload["steps"] = steps

        self.logger.info(f"Generating image with prompt: {prompt[:50]}...")
        self.logger.debug(f"Using model: {self.model}")
        self.logger.debug(f"Request payload: {payload}")

        try:
            # 使用配置的端点
            response = await self.client.post(
                self.endpoint,
                json=payload
            )

            self.logger.debug(f"Response status: {response.status_code}")
            self.logger.debug(f"Response headers: {dict(response.headers)}")

            response.raise_for_status()

            # 检查响应内容
            response_text = response.text
            self.logger.debug(f"Raw response: {response_text[:200]}")

            if not response_text or not response_text.strip():
                raise ValueError(f"Empty response from API. Status: {response.status_code}")

            try:
                result = response.json()
            except Exception as json_err:
                self.logger.error(f"Failed to parse JSON response. Raw text: {response_text[:500]}")
                raise ValueError(f"Invalid JSON response: {json_err}") from json_err

            self.logger.info(f"Image generated successfully")
            self.logger.debug(f"API response structure: {list(result.keys()) if isinstance(result, dict) else type(result)}")

            # 转换为统一格式（兼容 OpenAI 和自定义格式）
            normalized_result = self._normalize_image_response(result)

            return normalized_result

        except httpx.HTTPStatusError as e:
            error_response = None
            error_code = ""
            error_message = f"API request failed with status {e.response.status_code}"

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

            self.logger.error(f"Nano Banana API request failed: {e.response.status_code}")
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
                error_type="image_generation_failed",
                stage="image_generation",
                api_response=error_response
            )

    async def download_image(
        self,
        image_url: str,
        save_path: Path
    ) -> Path:
        """
        下载图片到本地

        Args:
            image_url: 图片URL
            save_path: 保存路径

        Returns:
            实际保存的文件路径
        """
        self.logger.info(f"Downloading image from {image_url}")

        try:
            async with httpx.AsyncClient() as download_client:
                response = await download_client.get(
                    image_url,
                    timeout=120.0,
                    follow_redirects=True
                )
                response.raise_for_status()

                # 确保目录存在
                save_path.parent.mkdir(parents=True, exist_ok=True)

                # 保存图片
                with open(save_path, 'wb') as f:
                    f.write(response.content)

                self.logger.info(f"Image saved to {save_path}")
                return save_path

        except Exception as e:
            self.logger.error(f"Failed to download image: {e}")
            raise

    async def save_base64_image(
        self,
        base64_data: str,
        save_path: Path
    ) -> Path:
        """
        保存Base64编码的图片

        Args:
            base64_data: Base64编码的图片数据
            save_path: 保存路径

        Returns:
            实际保存的文件路径
        """
        self.logger.info(f"Saving base64 image to {save_path}")

        try:
            # 移除data URL前缀（如果存在）
            if ',' in base64_data:
                base64_data = base64_data.split(',')[1]

            # 解码Base64数据
            image_data = base64.b64decode(base64_data)

            # 确保目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存图片
            with open(save_path, 'wb') as f:
                f.write(image_data)

            self.logger.info(f"Base64 image saved to {save_path}")
            return save_path

        except Exception as e:
            self.logger.error(f"Failed to save base64 image: {e}")
            raise

    async def generate_and_save(
        self,
        prompt: str,
        save_path: Path,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成图片并保存到本地（一步到位）

        Args:
            prompt: 图片描述提示词
            save_path: 保存路径
            **kwargs: 其他生成参数

        Returns:
            包含图片路径和API响应的字典
        """
        # 生成图片
        result = await self.generate_image(prompt, **kwargs)

        # 保存图片
        if 'image_url' in result:
            # 从URL下载
            actual_path = await self.download_image(result['image_url'], save_path)
        elif 'image_base64' in result:
            # 从Base64保存
            actual_path = await self.save_base64_image(result['image_base64'], save_path)
        else:
            raise ValueError("API response doesn't contain image_url or image_base64")

        return {
            'image_path': str(actual_path),
            'prompt': prompt,
            'api_response': result
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
