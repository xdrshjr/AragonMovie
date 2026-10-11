"""Pydantic models for API requests and responses

This module defines all data models used in the API endpoints including
request models, response models, and task-related models.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from enum import Enum


# ==================== Task Models ====================

class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskInfo(BaseModel):
    """Basic task information"""
    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    progress: int = Field(0, ge=0, le=100, description="Task progress percentage")
    created_at: datetime = Field(..., description="Task creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    message: Optional[str] = Field(None, description="Status message or error description")


class TaskResult(BaseModel):
    """Task result with output data"""
    task_id: str
    status: TaskStatus
    progress: int = 100
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = Field(None, description="Task result data")
    error: Optional[Dict[str, Any]] = Field(None, description="Error information if failed")


# ==================== LLM Models ====================

class ChatMessage(BaseModel):
    """Chat message for LLM conversations"""
    role: Literal["system", "user", "assistant"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat completion request"""
    messages: List[ChatMessage] = Field(..., description="Conversation messages")
    model: Optional[str] = Field(None, description="LLM model to use")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, ge=1, description="Maximum tokens to generate")
    stream: bool = Field(False, description="Enable streaming response")


class ChatResponse(BaseModel):
    """Chat completion response"""
    id: str = Field(..., description="Response ID")
    object: str = "chat.completion"
    created: int = Field(..., description="Creation timestamp")
    model: str = Field(..., description="Model used")
    choices: List[Dict[str, Any]] = Field(..., description="Response choices")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage statistics")


class PromptOptimizationRequest(BaseModel):
    """Request to optimize a prompt"""
    prompt: str = Field(..., description="Original prompt to optimize")
    type: Literal["image", "video"] = Field(..., description="Optimization type")
    style: Optional[str] = Field(None, description="Desired style")
    enhance_details: bool = Field(True, description="Enhance prompt details")


class PromptOptimizationResponse(BaseModel):
    """Response from prompt optimization"""
    original_prompt: str
    optimized_prompt: str
    improvements: List[str] = Field(default_factory=list, description="List of improvements made")


# ==================== Image Models ====================

class ImageGenerationRequest(BaseModel):
    """Request to generate an image"""
    prompt: str = Field(..., min_length=1, description="Image description prompt")
    service: Optional[
        Literal["doubao", "nano_banana", "midjourney", "ali_token_plan"]
    ] = Field(
        None, 
        description="Image service to use (default: from config)"
    )
    width: int = Field(1920, ge=64, le=4096, description="Image width in pixels")
    height: int = Field(1080, ge=64, le=4096, description="Image height in pixels")
    quality: Literal["low", "medium", "high", "ultra"] = Field("high", description="Image quality")
    style: Optional[str] = Field(None, description="Image style")
    negative_prompt: Optional[str] = Field(None, description="Negative prompt")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")
    cfg_scale: Optional[float] = Field(None, ge=1.0, le=20.0, description="CFG guidance scale")
    steps: Optional[int] = Field(None, ge=20, le=100, description="Generation steps")
    optimize_prompt: bool = Field(False, description="Auto-optimize prompt with LLM")


class ImageToImageRequest(BaseModel):
    """Request for image-to-image generation"""
    prompt: str = Field(..., min_length=1, description="Image description prompt")
    image: str = Field(..., description="Base64 encoded reference image or URL")
    service: Optional[Literal["doubao", "ali_token_plan"]] = Field(
        None,
        description="Image service (doubao / ali_token_plan support i2i)"
    )
    width: int = Field(1920, ge=64, le=4096)
    height: int = Field(1080, ge=64, le=4096)
    reference_weight: float = Field(0.7, ge=0.0, le=1.0, description="Reference image weight")
    negative_prompt: Optional[str] = Field(None)
    seed: Optional[int] = Field(None)
    cfg_scale: Optional[float] = Field(None, ge=1.0, le=20.0)
    steps: Optional[int] = Field(None, ge=20, le=100)


class ImageGenerationResponse(BaseModel):
    """Response from image generation"""
    task_id: Optional[str] = Field(None, description="Task ID for async operations")
    image_url: Optional[str] = Field(None, description="Generated image URL")
    image_b64: Optional[str] = Field(None, description="Base64 encoded image")
    service: str = Field(..., description="Service used")
    duration: Optional[float] = Field(None, description="Generation duration in seconds")


# ==================== Video Models ====================

class VideoGenerationRequest(BaseModel):
    """Request to generate a video from an image"""
    image: str = Field(..., description="Base64 encoded image or URL")
    prompt: Optional[str] = Field(None, description="Video generation prompt")
    duration: Optional[int] = Field(None, ge=1, le=10, description="Video duration in seconds")
    fps: int = Field(30, ge=24, le=60, description="Frames per second")
    resolution: str = Field("1920x1080", description="Video resolution")
    motion_strength: float = Field(0.5, ge=0.0, le=1.0, description="Motion strength")
    camera_motion: Optional[Literal["pan", "tilt", "zoom", "static"]] = Field(
        None,
        description="Camera motion type"
    )
    optimize_prompt: bool = Field(False, description="Auto-optimize prompt with LLM")


class VideoGenerationResponse(BaseModel):
    """Response from video generation (async)"""
    task_id: str = Field(..., description="Task ID for polling status")
    status: TaskStatus = Field(..., description="Initial task status")
    message: str = Field(..., description="Status message")


class VideoStatusResponse(BaseModel):
    """Video generation status response"""
    task_id: str
    status: TaskStatus
    progress: int = Field(ge=0, le=100)
    video_url: Optional[str] = Field(None, description="Video URL when completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: datetime
    updated_at: datetime


# ==================== Service Info Models ====================

class ServiceInfo(BaseModel):
    """Information about an available service"""
    name: str = Field(..., description="Service name")
    type: str = Field(..., description="Service type (image/video/llm)")
    available: bool = Field(..., description="Whether service is configured and available")
    features: List[str] = Field(default_factory=list, description="Supported features")


class ServicesListResponse(BaseModel):
    """List of available services"""
    image_services: List[ServiceInfo]
    video_services: List[ServiceInfo]
    llm_services: List[ServiceInfo]


# ==================== Workflow Models ====================

class WorkflowConfig(BaseModel):
    """Configuration for workflow generation"""
    video_fps: int = Field(30, ge=24, le=60, description="Video frames per second")
    video_duration: float = Field(5.0, ge=1.0, le=10.0, description="Video duration in seconds")
    image_width: int = Field(1920, ge=512, le=4096, description="Image width in pixels")
    image_height: int = Field(1080, ge=512, le=4096, description="Image height in pixels")
    add_transitions: bool = Field(True, description="Add transitions between scenes")
    transition_duration: float = Field(0.5, ge=0.0, le=2.0, description="Transition duration in seconds")
    add_subtitles: bool = Field(False, description="Add subtitles to video")
    enable_character_references: bool = Field(True, description="Enable character reference generation")
    bgm_volume: float = Field(0.0, ge=0.0, le=1.0, description="Background music volume")
    
    # Advanced options
    image_cfg_scale: Optional[float] = Field(None, ge=1.0, le=20.0, description="Image generation CFG scale")
    image_steps: Optional[int] = Field(None, ge=20, le=100, description="Image generation steps")
    video_motion_strength: float = Field(0.5, ge=0.0, le=1.0, description="Video motion strength")
    max_concurrent_requests: int = Field(3, ge=1, le=10, description="Max concurrent API requests")


class WorkflowGenerationRequest(BaseModel):
    """Request to generate a full video workflow"""
    script: str = Field(..., min_length=10, description="Polished script text in markdown format")
    video_type: Optional[str] = Field(
        None,
        description="Video type: news_broadcast, anime, movie, short_drama"
    )
    video_subtype: Optional[str] = Field(
        None,
        description="Video subtype (varies by type)"
    )
    character_images: Optional[Dict[str, str]] = Field(
        None,
        description="Character name -> base64/url mapping (optional, will generate if not provided)"
    )
    scene_images: Optional[Dict[str, str]] = Field(
        None,
        description="Scene ID -> base64/url mapping (optional, will generate if not provided)"
    )
    config: Optional[WorkflowConfig] = Field(None, description="Workflow configuration")

    @validator('script')
    def validate_script_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Script cannot be empty")
        return v


class AssetInfo(BaseModel):
    """Information about a workflow asset"""
    filename: str = Field(..., description="Asset filename")
    url: str = Field(..., description="URL to fetch the asset")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    type: str = Field(..., description="Asset type: image, video, json, etc.")
    path: Optional[str] = Field(None, description="Server-side path (for internal use)")


class AssetsManifest(BaseModel):
    """Manifest of all assets generated in workflow"""
    character_references: List[AssetInfo] = Field(default_factory=list, description="Character reference images")
    scene_images: List[AssetInfo] = Field(default_factory=list, description="Scene images")
    scene_videos: List[AssetInfo] = Field(default_factory=list, description="Individual scene videos")
    final_video: Optional[AssetInfo] = Field(None, description="Final composed video")
    metadata_file: Optional[AssetInfo] = Field(None, description="Generation metadata file")


class WorkflowResult(BaseModel):
    """Result from workflow generation"""
    video_url: str = Field(..., description="URL to the final composed video")
    video_path: str = Field(..., description="Server-side path to the video file")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Generation metadata")
    assets: AssetsManifest = Field(..., description="All generated assets")
    duration: float = Field(..., description="Total generation duration in seconds")
    scene_count: int = Field(..., ge=0, description="Number of scenes generated")
    character_count: int = Field(..., ge=0, description="Number of characters detected")


class WorkflowGenerationResponse(BaseModel):
    """Response from workflow generation request"""
    task_id: str = Field(..., description="Task ID for polling status")
    status: TaskStatus = Field(..., description="Initial task status")
    message: str = Field(..., description="Status message")


class WorkflowStatusResponse(BaseModel):
    """Workflow generation status response"""
    task_id: str = Field(..., description="Task ID")
    status: TaskStatus = Field(..., description="Current status")
    progress: int = Field(ge=0, le=100, description="Progress percentage")
    current_stage: Optional[str] = Field(None, description="Current processing stage")
    result: Optional[WorkflowResult] = Field(None, description="Result when completed")
    error: Optional[Dict[str, Any]] = Field(None, description="Error information if failed")
    created_at: datetime = Field(..., description="Task creation time")
    updated_at: datetime = Field(..., description="Last update time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")


# ==================== Quick Mode Models ====================

class QuickModeSceneConfig(BaseModel):
    """Configuration for a single scene in quick mode"""
    scene_id: str = Field(..., description="Scene identifier (scene_001, scene_002, etc.)")
    image: str = Field(..., description="Base64 encoded image or URL")
    duration: int = Field(..., ge=1, le=10, description="Video duration in seconds")
    prompt: Optional[str] = Field(None, description="Optional prompt for video generation")
    camera_motion: Optional[Literal["static", "pan", "tilt", "zoom"]] = Field(
        None,
        description="Camera motion type"
    )
    motion_strength: Optional[float] = Field(None, ge=0.0, le=1.0, description="Motion strength parameter")

    @validator('scene_id')
    def validate_scene_id_format(cls, v):
        """Validate scene ID follows scene_XXX format"""
        import re
        if not re.match(r'^scene_\d{3}$', v):
            raise ValueError("Scene ID must follow format 'scene_XXX' where XXX is a 3-digit number (e.g., scene_001)")
        return v


class QuickModeWorkflowRequest(BaseModel):
    """Request for quick mode workflow - bypasses script parsing and image generation"""
    mode: Literal["quick"] = "quick"
    scenes: List[QuickModeSceneConfig] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="List of scene configurations with images"
    )
    config: Optional[WorkflowConfig] = Field(None, description="Workflow configuration (optional)")

    @validator('scenes')
    def validate_scene_sequence(cls, v):
        """Validate scenes are in sequential order without gaps"""
        scene_numbers = []
        for scene in v:
            # Extract number from scene_XXX
            num = int(scene.scene_id.split('_')[1])
            scene_numbers.append(num)

        # Check for sequential order
        scene_numbers_sorted = sorted(scene_numbers)
        expected = list(range(1, len(scene_numbers) + 1))

        if scene_numbers_sorted != expected:
            raise ValueError(
                f"Scene IDs must be sequential starting from scene_001. "
                f"Expected: {expected}, Got: {scene_numbers_sorted}"
            )

        return v

