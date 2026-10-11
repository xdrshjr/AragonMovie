"""Backend configuration using Pydantic Settings"""
from pydantic_settings import BaseSettings
from typing import Optional, Literal
from pathlib import Path
import os


class BackendSettings(BaseSettings):
    """Backend configuration loaded from environment variables"""
    
    # ==================== Server Configuration ====================
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    api_title: str = "AI Movie Agent API"
    api_version: str = "1.0.0"
    api_description: str = """
    Comprehensive API for AI-powered image and video generation.

    Features:
    - Image generation services (Doubao, NanoBanana, Midjourney)
    - Video generation from images (Veo3, Sora2)
    - LLM-powered prompt optimization
    - Async task management with polling
    - OpenAI-compatible endpoints
    """
    
    # ==================== LLM Configuration ====================
    fast_llm_api_key: str = ""
    fast_llm_api_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    fast_llm_model: str = "qwen3.8-max"
    enable_prompt_optimization: bool = True
    
    judge_llm_api_key: str = ""
    judge_llm_api_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    judge_llm_model: str = "qwen3.8-max"
    enable_character_consistency_judge: bool = True
    
    # ==================== Image Service Configuration ====================
    image_service_type: Literal["doubao", "nano_banana", "midjourney", "ali_token_plan"] = "ali_token_plan"

    # ==================== Ali Token Plan (Ali Coding Plan) ====================
    # OpenAI-compatible gateway; one key covers text/voice/image/video models
    ali_token_plan_api_key: str = ""
    ali_token_plan_base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    # Image generation (wan2.7-image-pro)
    ali_image_endpoint: str = "/api/v1/services/aigc/multimodal-generation/generation"
    ali_image_model: str = "wan2.7-image-pro"
    # Video generation (happyhorse-1.1 family: i2v/t2v/r2v)
    ali_video_endpoint: str = "/api/v1/services/aigc/video-generation/video-synthesis"
    ali_video_model: str = "happyhorse-1.1-i2v"
    ali_video_t2v_model: str = "happyhorse-1.1-t2v"
    ali_video_r2v_model: str = "happyhorse-1.1-r2v"
    ali_video_default_size: str = "1280x720"
    ali_video_default_duration: int = 5
    
    # Doubao
    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com"
    doubao_endpoint: str = "/api/v3/images/generations"
    doubao_model: str = "doubao-seedream-4-5-251128"
    doubao_watermark: bool = False
    
    # Nano Banana
    nano_banana_api_key: str = ""
    nano_banana_base_url: str = "https://api.nanobananapro.com/v1"
    nano_banana_endpoint: str = "/generate"
    nano_banana_model: str = "dall-e-3"
    
    # Midjourney
    midjourney_api_key: str = ""
    midjourney_base_url: str = "https://api.kuai.host"
    midjourney_bot_type: str = "MID_JOURNEY"
    midjourney_poll_interval: float = 3.0
    midjourney_max_poll_attempts: int = 100
    midjourney_auto_upscale: bool = False
    midjourney_upscale_index: int = 1
    
    # ==================== Video Service Configuration ====================
    # Video service selection
    video_service_type: Literal["veo3", "sora2", "ali_token_plan"] = "ali_token_plan"

    # Veo3 Video Generation Service
    veo3_api_key: str = ""
    veo3_base_url: str = "https://api.kuai.host"
    veo3_endpoint: str = "/v1/videos"
    veo3_model: str = "veo_3_1"
    veo3_skip_upload: bool = True

    # Sora2 Video Generation Service
    sora2_api_key: str = ""
    sora2_base_url: str = "https://api.kuai.host"
    sora2_endpoint: str = "/v1/videos"
    sora2_model: str = "sora-2"
    sora2_default_size: str = "1280x720"
    sora2_default_duration: int = 8
    sora2_default_style: Optional[str] = None
    sora2_watermark: bool = False
    sora2_private: bool = False

    # Video generation retry configuration
    video_generation_max_retries: int = 3
    video_generation_retry_delay: float = 5.0
    video_generation_retry_backoff: float = 2.0
    
    # ==================== Task Management ====================
    task_storage_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379"
    task_retention_hours: int = 24
    max_concurrent_tasks: int = 10
    
    # ==================== Concurrency ====================
    image_max_concurrent: int = 3
    video_max_concurrent: int = 2
    
    # ==================== Logging ====================
    log_dir: str = "./logs"
    log_rotation: str = "1 day"
    log_retention: str = "30 days"
    log_format: str = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
    
    # ==================== TTS (Voice) Service Configuration ====================
    # OpenAI-compatible /audio/speech endpoint (also works with compatible gateways)
    enable_tts: bool = False
    tts_api_key: str = ""
    tts_base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    tts_model: str = "qwen-audio-3.0-tts-plus"
    tts_default_voice: str = "Cherry"
    tts_default_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3"
    tts_default_speed: float = 1.0

    # ==================== Agent Assist Configuration ====================
    # Agent-assisted setup powered by AragonAgent (aragon exec subprocess)
    agent_enabled: bool = False
    agent_provider: Literal["openai", "anthropic", "google"] = "openai"
    agent_api_key: str = ""
    agent_base_url: Optional[str] = None
    agent_model: str = ""
    agent_max_turns: int = 20
    agent_timeout_seconds: int = 300
    aragon_cli_path: str = "aragon"

    # ==================== Optional Features ====================
    enable_image_to_image: bool = True
    enable_smart_duration: bool = True
    enable_character_references: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = BackendSettings()

# Override log_level from environment if set (for uvicorn reload support)
if os.getenv('LOG_LEVEL'):
    settings.log_level = os.getenv('LOG_LEVEL')

