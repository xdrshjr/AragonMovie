"""Video Service Factory Module

This module provides a factory class for creating video generation service instances
dynamically based on configuration. It supports multiple video generation services
(Veo3, Sora2) and allows runtime service selection and configuration override.

Factory Pattern Benefits:
- Centralized service creation logic
- Easy to add new video services
- Runtime service selection based on configuration
- Configuration override support for testing and flexibility
- Type-safe service instantiation

Usage Examples:
    # Example 1: Use default configuration from settings
    service = VideoServiceFactory.create_service()

    # Example 2: Explicitly specify service type
    service = VideoServiceFactory.create_service(service_type="sora2")

    # Example 3: Override configuration parameters
    service = VideoServiceFactory.create_service(
        service_type="sora2",
        config_override={'model': 'sora-2-pro', 'default_duration': 12}
    )

    # Example 4: Use in async context
    async with VideoServiceFactory.create_service(service_type="sora2") as service:
        result = await service.image_to_video(...)
"""
from typing import Union, Optional, Dict, Any
import logging

from services.veo3_service import Veo3Service
from services.sora2_service import Sora2Service
from services.ali_token_plan_service import AliTokenPlanVideoService
from services.doubao_video_service import DoubaoVideoService
from config.settings import settings


class VideoServiceFactory:
    """Factory class for creating video generation service instances

    This factory class provides a centralized way to create video generation
    service instances (Veo3Service or Sora2Service) based on configuration.
    It supports runtime service selection and configuration override.

    The factory pattern is used here to:
    1. Decouple service creation from usage
    2. Provide a single point of control for service instantiation
    3. Enable easy testing with mock services
    4. Support runtime service switching

    Attributes:
        SUPPORTED_SERVICES (list): List of supported service types
    """

    SUPPORTED_SERVICES = ["veo3", "sora2", "ali_token_plan", "doubao"]

    @staticmethod
    def create_service(
        service_type: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None
    ) -> Union[Veo3Service, Sora2Service, AliTokenPlanVideoService, DoubaoVideoService]:
        """Create a video generation service instance

        This method creates and returns a video generation service instance
        based on the specified service type or the default configuration.
        It validates the API key and applies any configuration overrides.

        Args:
            service_type: Video service type to create ('veo3' or 'sora2').
                If None, uses settings.video_service_type.
            config_override: Optional dictionary of configuration parameters
                to override default settings. Supported keys depend on the
                service type:
                - Common: api_key, base_url, endpoint, model
                - Veo3: skip_upload
                - Sora2: default_size, default_duration, default_style,
                  watermark, private

        Returns:
            Union[Veo3Service, Sora2Service]: An instance of the requested
                video generation service.

        Raises:
            ValueError: If service_type is not supported (not in 'veo3', 'sora2')
            ValueError: If API key is not configured for the selected service

        Examples:
            >>> # Create service with default configuration
            >>> service = VideoServiceFactory.create_service()
            >>> print(type(service).__name__)
            'Veo3Service'

            >>> # Create Sora2 service explicitly
            >>> service = VideoServiceFactory.create_service(service_type="sora2")
            >>> print(type(service).__name__)
            'Sora2Service'

            >>> # Override configuration
            >>> service = VideoServiceFactory.create_service(
            ...     service_type="sora2",
            ...     config_override={'model': 'sora-2-pro'}
            ... )
            >>> print(service.model)
            'sora-2-pro'
        """
        # Initialize logger
        logger = logging.getLogger(__name__)

        # Step 1: Determine service type (use default if not specified)
        service_type = service_type or settings.video_service_type
        logger.info(f"Creating video service: {service_type}")

        # Step 2: Validate service type
        if service_type not in VideoServiceFactory.SUPPORTED_SERVICES:
            error_msg = (
                f"Unsupported video service type: {service_type}. "
                f"Supported types: {', '.join(VideoServiceFactory.SUPPORTED_SERVICES)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Step 3: Prepare configuration override
        config_override = config_override or {}
        logger.debug(f"Configuration override: {config_override}")

        # Step 4: Create service instance based on type
        if service_type == "veo3":
            return VideoServiceFactory._create_veo3_service(config_override, logger)
        elif service_type == "sora2":
            return VideoServiceFactory._create_sora2_service(config_override, logger)
        elif service_type == "ali_token_plan":
            return VideoServiceFactory._create_ali_token_plan_service(
                config_override, logger
            )
        elif service_type == "doubao":
            return VideoServiceFactory._create_doubao_service(
                config_override, logger
            )
        else:
            # This should never happen due to validation above, but kept for safety
            error_msg = f"Unsupported video service type: {service_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    @staticmethod
    def _create_veo3_service(
        config_override: Dict[str, Any],
        logger: logging.Logger
    ) -> Veo3Service:
        """Create Veo3Service instance with configuration

        Args:
            config_override: Configuration parameters to override
            logger: Logger instance for logging

        Returns:
            Veo3Service: Configured Veo3 service instance

        Raises:
            ValueError: If Veo3 API key is not configured
        """
        # Extract configuration (override > settings)
        api_key = config_override.get('api_key') or settings.veo3_api_key
        base_url = config_override.get('base_url') or settings.veo3_base_url
        endpoint = config_override.get('endpoint') or settings.veo3_endpoint
        model = config_override.get('model') or settings.veo3_model
        skip_upload = config_override.get('skip_upload', settings.veo3_skip_upload)

        # Validate API key
        if not api_key:
            error_msg = "Veo3 API key not configured. Please set VEO3_API_KEY in .env file."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Log configuration (excluding API key)
        logger.debug(f"Veo3 configuration:")
        logger.debug(f"  - base_url: {base_url}")
        logger.debug(f"  - endpoint: {endpoint}")
        logger.debug(f"  - model: {model}")
        logger.debug(f"  - skip_upload: {skip_upload}")

        # Create service instance
        service = Veo3Service(
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            model=model,
            skip_upload=skip_upload
        )

        logger.info(
            f"Veo3Service created successfully: "
            f"model={service.model}, base_url={service.base_url}"
        )

        return service

    @staticmethod
    def _create_sora2_service(
        config_override: Dict[str, Any],
        logger: logging.Logger
    ) -> Sora2Service:
        """Create Sora2Service instance with configuration

        Args:
            config_override: Configuration parameters to override
            logger: Logger instance for logging

        Returns:
            Sora2Service: Configured Sora2 service instance

        Raises:
            ValueError: If Sora2 API key is not configured
        """
        # Extract configuration (override > settings)
        api_key = config_override.get('api_key') or settings.sora2_api_key
        base_url = config_override.get('base_url') or settings.sora2_base_url
        endpoint = config_override.get('endpoint') or settings.sora2_endpoint
        model = config_override.get('model') or settings.sora2_model
        default_size = config_override.get('default_size') or settings.sora2_default_size
        default_duration = config_override.get('default_duration') or settings.sora2_default_duration
        default_style = config_override.get('default_style') or settings.sora2_default_style
        watermark = config_override.get('watermark', settings.sora2_watermark)
        private = config_override.get('private', settings.sora2_private)

        # Validate API key
        if not api_key:
            error_msg = "Sora2 API key not configured. Please set SORA2_API_KEY in .env file."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Log configuration (excluding API key)
        logger.debug(f"Sora2 configuration:")
        logger.debug(f"  - base_url: {base_url}")
        logger.debug(f"  - endpoint: {endpoint}")
        logger.debug(f"  - model: {model}")
        logger.debug(f"  - default_size: {default_size}")
        logger.debug(f"  - default_duration: {default_duration}s")
        if default_style:
            logger.debug(f"  - default_style: {default_style}")
        logger.debug(f"  - watermark: {watermark}")
        logger.debug(f"  - private: {private}")

        # Create service instance
        service = Sora2Service(
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            model=model,
            default_size=default_size,
            default_duration=default_duration,
            default_style=default_style,
            watermark=watermark,
            private=private
        )

        logger.info(
            f"Sora2Service created successfully: "
            f"model={service.model}, base_url={service.base_url}"
        )

        return service

    @staticmethod
    def _create_ali_token_plan_service(
        config_override: Dict[str, Any],
        logger: logging.Logger
    ) -> AliTokenPlanVideoService:
        """Create AliTokenPlanVideoService instance with configuration

        Args:
            config_override: Configuration parameters to override
                (api_key, base_url, endpoint, model, default_size,
                default_duration)
            logger: Logger instance for logging

        Returns:
            AliTokenPlanVideoService: Configured service instance

        Raises:
            ValueError: If the Ali Token Plan API key is not configured
        """
        api_key = (
            config_override.get("api_key")
            or settings.ali_token_plan_api_key
        )
        if not api_key:
            error_msg = (
                "Ali Token Plan API key not configured. "
                "Set ALI_TOKEN_PLAN_API_KEY in .env or via the Settings UI."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        service = AliTokenPlanVideoService(
            api_key=api_key,
            base_url=config_override.get("base_url"),
            endpoint=config_override.get("endpoint"),
            model=config_override.get("model"),
            default_size=config_override.get("default_size"),
            default_duration=config_override.get("default_duration"),
            watermark=config_override.get(
                "watermark",
                getattr(settings, "ali_video_watermark", False),
            ),
        )

        logger.info(
            f"AliTokenPlanVideoService created successfully: "
            f"model={service.model}, base_url={service.base_url}"
        )
        return service

    @staticmethod
    def _create_doubao_service(
        config_override: Dict[str, Any],
        logger: logging.Logger
    ) -> DoubaoVideoService:
        """Create DoubaoVideoService (Volcano Ark Seedance).

        Raises:
            ValueError: when no Ark API key is configured.
        """
        api_key = config_override.get("api_key") or settings.doubao_video_api_key
        if not api_key:
            error_msg = (
                "Doubao video API key not configured. Set DOUBAO_VIDEO_API_KEY "
                "in .env or via the Settings UI (Volcano Ark API key)."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        service = DoubaoVideoService(
            api_key=api_key,
            base_url=config_override.get("base_url"),
            endpoint=config_override.get("endpoint"),
            model=config_override.get("model"),
            t2v_model=config_override.get("t2v_model"),
            default_resolution=config_override.get("default_resolution"),
            default_ratio=config_override.get("default_ratio"),
            default_duration=config_override.get("default_duration"),
            watermark=config_override.get("watermark"),
        )
        logger.info(
            f"DoubaoVideoService created successfully: model={service.model}, "
            f"base_url={service.base_url}"
        )
        return service

    @staticmethod
    def get_supported_services() -> list:
        """Get list of supported video service types

        Returns:
            list: List of supported service type strings
        """
        return VideoServiceFactory.SUPPORTED_SERVICES.copy()

    @staticmethod
    def is_service_supported(service_type: str) -> bool:
        """Check if a service type is supported

        Args:
            service_type: Service type to check

        Returns:
            bool: True if service type is supported, False otherwise
        """
        return service_type in VideoServiceFactory.SUPPORTED_SERVICES
