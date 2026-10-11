"""Image generation API endpoints (REST v1)

Provides endpoints for text-to-image and image-to-image generation.
"""
from fastapi import APIRouter, HTTPException, status
from typing import List
import base64
from pathlib import Path
import tempfile

from backend.core.models import (
    ImageGenerationRequest,
    ImageToImageRequest,
    ImageGenerationResponse,
    ServiceInfo,
    ServicesListResponse
)
from backend.core.service_wrapper import get_image_service, get_llm_service
from backend.core.exceptions import ServiceException
from backend.config import settings
from backend.utils.logger import get_logger
from backend.utils.helpers import decode_base64_to_file

logger = get_logger(__name__)
router = APIRouter()


@router.get("/services", response_model=List[str], summary="List Image Services")
async def list_image_services():
    """
    List available image generation services.
    
    Returns a list of configured and available image generation services.
    """
    try:
        image_service = get_image_service()
        services = image_service.get_available_services()
        logger.info(f"Available image services: {services}")
        return services
    except Exception as e:
        logger.error(f"Failed to list services: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list services: {str(e)}"
        )


@router.post("/generate", response_model=ImageGenerationResponse, summary="Generate Image")
async def generate_image(request: ImageGenerationRequest):
    """
    Generate an image from a text prompt.
    
    This endpoint generates an image using the specified service (Doubao, NanoBanana, or Midjourney).
    The prompt can be automatically optimized using LLM if requested.
    
    **Parameters:**
    - **prompt**: Text description of the desired image
    - **service**: Image service to use (default: from config)
    - **width/height**: Image dimensions in pixels
    - **quality**: Image quality level
    - **style**: Optional style specification
    - **negative_prompt**: What to avoid in the generation
    - **seed**: Random seed for reproducibility
    - **cfg_scale**: Guidance scale (how closely to follow prompt)
    - **steps**: Number of generation steps
    - **optimize_prompt**: Auto-optimize prompt with LLM
    
    **Returns:**
    - Generated image URL or base64 data
    - Service used
    - Generation duration
    """
    logger.info(f"Image generation request | service={request.service or settings.image_service_type}")
    
    try:
        prompt = request.prompt
        
        # Optimize prompt if requested
        if request.optimize_prompt and settings.enable_prompt_optimization:
            logger.info("Optimizing prompt with LLM")
            llm_service = get_llm_service()
            prompt = await llm_service.optimize_prompt(prompt, prompt_type="image")
            logger.debug(f"Optimized prompt: {prompt[:100]}...")
        
        # Generate image
        image_service = get_image_service()
        result = await image_service.generate_image(
            prompt=prompt,
            service_type=request.service,
            width=request.width,
            height=request.height,
            quality=request.quality,
            style=request.style,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            cfg_scale=request.cfg_scale,
            steps=request.steps
        )
        
        # Extract image URL or base64 from result
        service_result = result.get("result", {})
        image_url = None
        image_b64 = None
        
        if isinstance(service_result, dict):
            # Try different possible keys for URL
            image_url = (
                service_result.get("image_url") or 
                service_result.get("url") or
                None
            )
            
            # Try different possible keys for base64
            image_b64 = (
                service_result.get("b64_json") or 
                service_result.get("image_base64") or
                service_result.get("image_b64") or
                None
            )
        
        # Log what we're returning
        has_url = bool(image_url and image_url.strip())
        has_b64 = bool(image_b64 and image_b64.strip())
        
        if not has_url and not has_b64:
            logger.error(
                f"Image generation returned no usable data | "
                f"service={result.get('service')} | "
                f"result_keys={list(service_result.keys()) if isinstance(service_result, dict) else 'not_dict'} | "
                f"result_sample={str(service_result)[:200]}"
            )
        else:
            logger.info(
                f"Image result extracted | has_url={has_url} | has_b64={has_b64} | "
                f"url_length={len(image_url) if image_url else 0}"
            )
        
        logger.info(f"Image generation successful | duration={result.get('duration', 0):.2f}s")
        
        return ImageGenerationResponse(
            image_url=image_url,
            image_b64=image_b64,
            service=result.get("service", "unknown"),
            duration=result.get("duration")
        )
        
    except ServiceException as e:
        logger.error(f"Image generation failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.message
        )
    except Exception as e:
        logger.exception(f"Unexpected error in image generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/generate-i2i", response_model=ImageGenerationResponse, summary="Image-to-Image Generation")
async def generate_image_to_image(request: ImageToImageRequest):
    """
    Generate an image from a reference image and prompt.
    
    This endpoint performs image-to-image generation, using a reference image
    to guide the generation process. Currently only supported by Doubao service
    (ali_token_plan/nano_banana fall back to text-to-image when a reference is given).
    
    **Parameters:**
    - **prompt**: Text description
    - **image**: Base64 encoded reference image or URL
    - **service**: Must be 'doubao' (only service supporting i2i)
    - **width/height**: Output dimensions
    - **reference_weight**: How closely to follow reference image (0.0-1.0)
    - **negative_prompt**: What to avoid
    - **seed**: Random seed
    - **cfg_scale**: Guidance scale
    - **steps**: Generation steps
    
    **Returns:**
    - Generated image URL or base64 data
    """
    logger.info(f"Image-to-image request | service={request.service or 'doubao'}")
    
    # Validate service (doubao + ali_token_plan support reference-image input)
    service_type = request.service or "doubao"
    if service_type not in ("doubao", "ali_token_plan"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Image-to-image generation is only supported by "
                "'doubao' and 'ali_token_plan' services"
            )
        )
    
    try:
        # Handle reference image (URL or base64)
        reference_image = request.image
        
        # Generate image with reference
        image_service = get_image_service()
        
        # Note: This requires the doubao service to be configured for i2i
        result = await image_service.generate_image(
            prompt=request.prompt,
            service_type=service_type,
            width=request.width,
            height=request.height,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            cfg_scale=request.cfg_scale,
            steps=request.steps,
            reference_image=reference_image,
            reference_image_weight=request.reference_weight
        )
        
        # Extract result
        service_result = result.get("result", {})
        
        # Try different possible keys for URL and base64
        image_url = None
        image_b64 = None
        
        if isinstance(service_result, dict):
            image_url = (
                service_result.get("image_url") or 
                service_result.get("url") or
                None
            )
            image_b64 = (
                service_result.get("b64_json") or 
                service_result.get("image_base64") or
                service_result.get("image_b64") or
                None
            )
        
        logger.info(f"Image-to-image generation successful | duration={result.get('duration', 0):.2f}s")
        
        return ImageGenerationResponse(
            image_url=image_url,
            image_b64=image_b64,
            service=result.get("service", "doubao"),
            duration=result.get("duration")
        )
        
    except ServiceException as e:
        logger.error(f"Image-to-image generation failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.message
        )
    except Exception as e:
        logger.exception(f"Unexpected error in image-to-image generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

