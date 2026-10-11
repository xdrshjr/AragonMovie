"""Image service factory - 图片生成服务工厂"""
from typing import Optional, Literal
from config.settings import settings
import logging


ImageServiceType = Literal["doubao", "nano_banana", "midjourney", "ali_token_plan"]


class ImageServiceFactory:
    """图片生成服务工厂 - 根据配置创建不同的服务实例"""

    _logger = logging.getLogger(__name__)

    @staticmethod
    def create_service(
        service_type: Optional[ImageServiceType] = None,
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        创建图片生成服务实例

        Args:
            service_type: 服务类型 ("doubao" 或 "nano_banana")
                         如果为None，则使用配置文件中的默认值
            api_key: API密钥（可选，优先级高于配置文件）
            **kwargs: 传递给服务构造函数的其他参数

        Returns:
            服务实例 (DoubaoService 或 NanoBananaService)

        Raises:
            ValueError: 如果服务类型不支持
        """
        # 使用配置的默认服务
        if service_type is None:
            service_type = settings.image_service_type
            ImageServiceFactory._logger.info(f"Using default image service: {service_type}")

        if service_type == "doubao":
            from services.doubao_service import DoubaoService
            ImageServiceFactory._logger.info("Creating Doubao (豆包) service instance")
            return DoubaoService(
                api_key=api_key or settings.doubao_api_key,
                **kwargs
            )

        elif service_type == "nano_banana":
            from services.nano_banana_service import NanoBananaService
            ImageServiceFactory._logger.info("Creating Nano Banana service instance")
            return NanoBananaService(
                api_key=api_key or settings.nano_banana_api_key,
                **kwargs
            )

        elif service_type == "ali_token_plan":
            from services.ali_token_plan_service import AliTokenPlanImageService
            ImageServiceFactory._logger.info(
                "Creating Ali Token Plan image service instance"
            )
            return AliTokenPlanImageService(
                api_key=api_key or settings.ali_token_plan_api_key,
                **kwargs
            )

        else:
            raise ValueError(
                f"Unsupported image service type: {service_type}. "
                f"Supported types: 'doubao', 'nano_banana', 'ali_token_plan'"
            )

    @staticmethod
    def get_available_services() -> list[str]:
        """
        获取所有可用的服务类型

        Returns:
            服务类型列表
        """
        return ["doubao", "nano_banana", "ali_token_plan"]

    @staticmethod
    def supports_image_to_image(service_type: Optional[ImageServiceType] = None) -> bool:
        """
        检查服务是否支持图生图功能

        Args:
            service_type: 服务类型，如果为None则检查默认服务

        Returns:
            是否支持图生图
        """
        if service_type is None:
            service_type = settings.image_service_type

        # 豆包支持图生图
        if service_type == "doubao":
            return True

        # Ali Token Plan (wan2.7-image-pro) 原生支持参考图输入
        if service_type == "ali_token_plan":
            return True

        # Nano Banana目前不支持图生图（如果后续支持，可以修改这里）
        if service_type == "nano_banana":
            return False

        return False
