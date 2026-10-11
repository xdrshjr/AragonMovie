"""Service wrapper for existing AI generation services

This module provides a unified interface to all existing services
with proper error handling and logging.
"""
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
import time

# Add parent directory to path to import existing services
parent_dir = Path(__file__).parent.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from services.llm_service import LLMService
from services.image_service_factory import ImageServiceFactory
from services.video_service_factory import VideoServiceFactory
from services.veo3_service import VideoGenerationError
from backend.config import settings
from backend.core.exceptions import ServiceException, ValidationException
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class LLMServiceWrapper:
    """Wrapper for LLM services"""
    
    def __init__(self):
        try:
            self.service = LLMService(
                api_key=settings.fast_llm_api_key,
                api_url=settings.fast_llm_api_url,
                model=settings.fast_llm_model
            )
            logger.info("LLM service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")
            raise ServiceException(
                f"Failed to initialize LLM service: {str(e)}",
                service_name="LLMService",
                retryable=False,
                original_error=e
            )
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate chat completion
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Chat completion response
        """
        start_time = time.time()
        logger.debug(f"LLM chat completion request | messages={len(messages)} | temperature={temperature} | max_tokens={max_tokens}")
        
        try:
            response = await self.service.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            duration = time.time() - start_time
            
            # Extract content for logging
            content_preview = ""
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"].get("content", "")
                content_preview = content[:100] if content else "<empty>"
            
            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            logger.info(
                f"LLM chat completion success | duration={duration:.2f}s | "
                f"prompt_tokens={prompt_tokens} | completion_tokens={completion_tokens} | "
                f"content_preview={content_preview}..."
            )
            logger.debug(f"Full response structure: choices={len(response.get('choices', []))} | usage={usage}")
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"LLM chat completion failed | duration={duration:.2f}s | error={str(e)}")
            raise ServiceException(
                f"LLM chat completion failed: {str(e)}",
                service_name="LLMService",
                retryable=True,
                original_error=e
            )
    
    async def optimize_prompt(
        self,
        prompt: str,
        prompt_type: str = "image"
    ) -> str:
        """Optimize a prompt for image/video generation
        
        Args:
            prompt: Original prompt
            prompt_type: Type of prompt ('image' or 'video')
            
        Returns:
            Optimized prompt
        """
        start_time = time.time()
        logger.debug(f"LLM prompt optimization | type={prompt_type} | length={len(prompt)}")
        
        try:
            # Map prompt_type to optimization_context
            optimization_context = "图片生成" if prompt_type == "image" else "视频生成"
            
            optimized = await self.service.optimize_prompt(
                original_prompt=prompt,
                optimization_context=optimization_context
            )
            
            duration = time.time() - start_time
            logger.info(
                f"LLM prompt optimization success | duration={duration:.2f}s | "
                f"original_length={len(prompt)} | optimized_length={len(optimized)}"
            )
            logger.debug(f"Original: {prompt[:100]}...")
            logger.debug(f"Optimized: {optimized[:100]}...")
            
            return optimized
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"LLM prompt optimization failed | duration={duration:.2f}s | error={str(e)}")
            raise ServiceException(
                f"Prompt optimization failed: {str(e)}",
                service_name="LLMService",
                retryable=True,
                original_error=e
            )


    async def close(self):
        """Close the underlying LLM client (used on hot-reconfigure)."""
        try:
            await self.service.close()
            logger.info("LLM service client closed")
        except Exception as e:
            logger.error(f"Error closing LLM service: {e}")


class ImageServiceWrapper:
    """Wrapper for image generation services"""
    
    def __init__(self):
        self.factory = ImageServiceFactory
        logger.info("Image service wrapper initialized")
    
    async def generate_image(
        self,
        prompt: str,
        service_type: Optional[str] = None,
        width: int = 1920,
        height: int = 1080,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate an image
        
        Args:
            prompt: Image description prompt
            service_type: Service to use (doubao, nano_banana, midjourney)
            width: Image width
            height: Image height
            **kwargs: Additional service-specific parameters
            
        Returns:
            Dictionary with image_url or image_b64
        """
        service_type = service_type or settings.image_service_type
        start_time = time.time()
        
        logger.info(f"Image generation request | service={service_type} | size={width}x{height}")
        logger.debug(f"Prompt: {prompt[:100]}...")
        
        try:
            # Create service instance
            service = self.factory.create_service(service_type=service_type)
            
            # Generate image
            result = await service.generate_image(
                prompt=prompt,
                width=width,
                height=height,
                **kwargs
            )
            
            duration = time.time() - start_time
            logger.info(f"Image generation success | service={service_type} | duration={duration:.2f}s")
            
            return {
                "service": service_type,
                "result": result,
                "duration": duration
            }
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Image generation failed | service={service_type} | "
                f"duration={duration:.2f}s | error={str(e)}"
            )
            raise ServiceException(
                f"Image generation failed: {str(e)}",
                service_name=f"ImageService ({service_type})",
                retryable=True,
                original_error=e
            )
    
    def get_available_services(self) -> List[str]:
        """Get list of available image services
        
        Returns:
            List of service names
        """
        return self.factory.get_available_services()


class VideoServiceWrapper:
    """Wrapper for video generation services"""
    
    def __init__(self):
        try:
            # Respect the runtime-selected service (veo3/sora2/ali_token_plan)
            self.service = VideoServiceFactory.create_service()
            self.service_type = settings.video_service_type
            logger.info(
                f"Video service initialized ({self.service_type}: "
                f"{type(self.service).__name__}, model={self.service.model})"
            )
        except Exception as e:
            logger.error(f"Failed to initialize video service: {e}")
            raise ServiceException(
                f"Failed to initialize video service: {str(e)}",
                service_name=f"VideoService ({settings.video_service_type})",
                retryable=False,
                original_error=e
            )
    
    async def generate_video(
        self,
        image_path: str,
        prompt: Optional[str] = None,
        duration: Optional[float] = None,
        fps: int = 30,
        resolution: str = "1920x1080",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate video from image
        
        Args:
            image_path: Path to input image
            prompt: Video generation prompt
            duration: Video duration in seconds
            fps: Frames per second
            resolution: Video resolution
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with video_url and task information
        """
        start_time = time.time()
        
        logger.info(f"Video generation request | duration={duration}s | fps={fps} | resolution={resolution}")
        logger.debug(f"Image: {image_path}")
        if prompt:
            logger.debug(f"Prompt: {prompt[:100]}...")
        
        try:
            result = await self.service.image_to_video(
                image_path=image_path,
                duration=duration,
                fps=fps,
                resolution=resolution,
                prompt=prompt or "Generate video from this image",
                **kwargs
            )
            
            duration_time = time.time() - start_time
            logger.info(f"Video generation success | duration={duration_time:.2f}s")
            
            return {
                "service": self.service_type,
                "result": result,
                "duration": duration_time
            }
            
        except VideoGenerationError as e:
            duration_time = time.time() - start_time
            logger.error(
                f"Video generation failed | duration={duration_time:.2f}s | "
                f"error_type={e.error_type} | retryable={e.retryable} | message={str(e)}"
            )
            raise ServiceException(
                f"Video generation failed: {str(e)}",
                service_name=f"VideoService ({self.service_type})",
                retryable=e.retryable,
                original_error=e
            )
        except Exception as e:
            duration_time = time.time() - start_time
            logger.error(f"Video generation failed | duration={duration_time:.2f}s | error={str(e)}")
            raise ServiceException(
                f"Video generation failed: {str(e)}",
                service_name=f"VideoService ({self.service_type})",
                retryable=True,
                original_error=e
            )
    
    async def close(self):
        """Close the service client"""
        try:
            await self.service.close()
            logger.info("Video service client closed")
        except Exception as e:
            logger.error(f"Error closing video service: {e}")


# Global service instances
_llm_service: Optional[LLMServiceWrapper] = None
_image_service: Optional[ImageServiceWrapper] = None
_video_service: Optional[VideoServiceWrapper] = None


def get_llm_service() -> LLMServiceWrapper:
    """Get global LLM service instance"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMServiceWrapper()
    return _llm_service


def get_image_service() -> ImageServiceWrapper:
    """Get global image service instance"""
    global _image_service
    if _image_service is None:
        _image_service = ImageServiceWrapper()
    return _image_service


def get_video_service() -> VideoServiceWrapper:
    """Get global video service instance"""
    global _video_service
    if _video_service is None:
        _video_service = VideoServiceWrapper()
    return _video_service


async def reset_runtime_services():
    """Drop cached service singletons after runtime settings changes.

    Old wrappers are closed gracefully (releasing their httpx clients);
    the next request rebuilds each wrapper from the CURRENT settings.
    Called by ModelSettingsStore.apply_to_runtime() when an event loop is
    running, and safe to call at any other time via *_sync().
    """
    global _llm_service, _image_service, _video_service
    old_llm, _llm_service = _llm_service, None
    old_video, _video_service = _video_service, None
    _image_service = None

    for old in (old_llm, old_video):
        if old is None:
            continue
        try:
            await old.close()
        except Exception as e:  # noqa: BLE001 - best-effort cleanup
            logger.debug(f"Ignored error while closing stale service: {e}")

    logger.info("Runtime service singletons reset (will rebuild from current settings)")


def reset_runtime_services_sync():
    """Sync variant of reset_runtime_services() for non-async contexts."""
    global _llm_service, _image_service, _video_service
    _llm_service = None
    _image_service = None
    _video_service = None
    logger.info("Runtime service singletons reset (sync, no graceful close)")

