"""
Project YAML Configuration Schema

Pydantic models for validating and parsing project configuration files.
"""

from typing import Optional, Dict, List, Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from pathlib import Path


class ProjectMetadataConfig(BaseModel):
    """Project metadata configuration"""
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    author: Optional[str] = Field(None, description="Project author")
    version: str = Field("1.0", description="Project version")


class ScriptConfig(BaseModel):
    """Script file configuration"""
    file: str = Field("script.txt", description="Script filename (relative to project folder)")
    encoding: str = Field("utf-8", description="Script file encoding")


class CharacterReferenceImageConfig(BaseModel):
    """Individual character reference image configuration"""
    mode: Literal["generate", "load"] = Field("generate", description="Mode: generate new or load existing")
    images: Optional[List[str]] = Field(None, description="Image paths for mode=load (relative to project folder)")
    views: Optional[List[str]] = Field(None, description="Views to generate for mode=generate")

    @model_validator(mode='after')
    def validate_mode_requirements(self):
        """Validate that required fields are present based on mode"""
        if self.mode == "load" and not self.images:
            raise ValueError("images field is required when mode='load'")
        return self


class CharacterConfig(BaseModel):
    """Character reference configuration"""
    enable_references: bool = Field(True, description="Enable character reference generation")
    reference_mode: Literal["single_multi_view", "multiple_single_view"] = Field(
        "single_multi_view",
        description="Reference generation mode"
    )
    art_style: Literal["realistic", "anime", "semi_realistic"] = Field(
        "realistic",
        description="Art style for character references"
    )
    reference_images: Optional[Dict[str, CharacterReferenceImageConfig]] = Field(
        None,
        description="Character-specific image configurations"
    )


class ImageConfig(BaseModel):
    """Image generation configuration"""
    service: Literal[
        "doubao", "nano_banana", "midjourney", "ali_token_plan"
    ] = Field(
        "ali_token_plan",
        description="Image generation service"
    )
    max_concurrent: int = Field(3, ge=1, le=10, description="Maximum concurrent image generation tasks")
    width: int = Field(1920, ge=512, le=4096, description="Image width in pixels")
    height: int = Field(1080, ge=512, le=4096, description="Image height in pixels")
    quality: Literal["low", "medium", "high", "ultra"] = Field("high", description="Image quality level")

    # Advanced parameters
    cfg_scale: float = Field(7.5, ge=1.0, le=20.0, description="CFG scale for image generation")
    steps: int = Field(50, ge=20, le=100, description="Number of generation steps")
    enable_image_to_image: bool = Field(True, description="Enable image-to-image with character references")
    reference_weight: float = Field(0.7, ge=0.0, le=1.0, description="Weight of character reference images")


class VideoConfig(BaseModel):
    """Video generation configuration"""
    service: Literal["veo3", "sora2", "ali_token_plan"] = Field(
        "ali_token_plan", description="Video generation service"
    )
    max_concurrent: int = Field(2, ge=1, le=5, description="Maximum concurrent video generation tasks")
    fps: int = Field(30, ge=24, le=60, description="Frames per second")
    resolution: str = Field("1920x1080", description="Video resolution")
    motion_strength: float = Field(0.6, ge=0.0, le=1.0, description="Motion strength parameter")
    model: str = Field("veo_3_1", description="Video generation model")

    # Scene continuity configuration
    enable_scene_continuity: bool = Field(True, description="Enable scene-to-scene continuity")
    continuity_frame_index: int = Field(-5, description="Frame index to extract from previous video (negative = from end)")
    continuity_reference_weight: float = Field(0.5, ge=0.0, le=1.0, description="Reference frame weight for continuity")
    enable_smart_continuity_judge: bool = Field(True, description="Enable LLM-based smart continuity judgment")

    @field_validator('resolution')
    @classmethod
    def validate_resolution(cls, v: str) -> str:
        """Validate resolution format"""
        if 'x' not in v:
            raise ValueError("Resolution must be in format 'WIDTHxHEIGHT' (e.g., '1920x1080')")
        try:
            width, height = map(int, v.split('x'))
            if width < 512 or height < 512:
                raise ValueError("Resolution must be at least 512x512")
        except ValueError as e:
            raise ValueError(f"Invalid resolution format: {e}")
        return v


class BGMConfig(BaseModel):
    """Background music configuration"""
    enabled: bool = Field(False, description="Enable background music")
    file: Optional[str] = Field(None, description="BGM file path (relative to project folder)")
    volume: float = Field(0.3, ge=0.0, le=1.0, description="BGM volume (0.0 to 1.0)")

    @model_validator(mode='after')
    def validate_bgm_file(self):
        """Validate BGM file is provided when enabled"""
        if self.enabled and not self.file:
            raise ValueError("BGM file must be specified when BGM is enabled")
        return self


class SubtitlesConfig(BaseModel):
    """Subtitles configuration"""
    enabled: bool = Field(False, description="Enable subtitles (future feature)")


class ComposerConfig(BaseModel):
    """Video composition configuration"""
    add_transitions: bool = Field(True, description="Add transitions between scenes")
    transition_type: Literal["fade", "crossfade", "dissolve", "none"] = Field(
        "fade",
        description="Transition effect type"
    )
    transition_duration: float = Field(0.5, ge=0.0, le=2.0, description="Transition duration in seconds")
    fps: int = Field(30, ge=24, le=60, description="Output video FPS")
    preset: Literal["ultrafast", "fast", "medium", "slow"] = Field(
        "medium",
        description="FFmpeg encoding preset"
    )
    threads: int = Field(4, ge=1, le=16, description="Number of encoding threads")

    # Audio settings
    bgm: BGMConfig = Field(default_factory=BGMConfig, description="Background music settings")
    subtitles: SubtitlesConfig = Field(default_factory=SubtitlesConfig, description="Subtitle settings")


class OutputConfig(BaseModel):
    """Output configuration"""
    directory: str = Field("outputs", description="Output directory (relative to project folder)")
    filename: str = Field(..., description="Output video filename")
    save_intermediate: bool = Field(True, description="Save intermediate images and videos")
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {"enabled": True, "format": "json"},
        description="Metadata generation settings"
    )

    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate filename has proper extension"""
        if not v.endswith('.mp4'):
            v = f"{v}.mp4"
        return v


class PerformanceConfig(BaseModel):
    """Performance configuration"""
    max_concurrent_requests: int = Field(5, ge=1, le=20, description="Global max concurrent requests")
    enable_checkpoints: bool = Field(True, description="Enable checkpoint saving for resume")


class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field("INFO", description="Logging level")
    save_to_file: bool = Field(True, description="Save logs to file")
    file: str = Field("outputs/generation.log", description="Log file path (relative to project folder)")


class QuickModeConfig(BaseModel):
    """Quick mode specific configuration"""
    default_duration: int = Field(5, ge=1, le=10, description="Default scene duration in seconds")
    default_motion_strength: float = Field(0.6, ge=0.0, le=1.0, description="Default motion strength")
    allow_custom_prompts: bool = Field(True, description="Allow per-scene custom prompts")
    max_scenes: int = Field(50, ge=1, le=100, description="Maximum number of scenes allowed")


class APIKeysConfig(BaseModel):
    """API keys configuration"""
    # Image generation services
    doubao_api_key: Optional[str] = Field(None, description="Doubao API key")
    nano_banana_api_key: Optional[str] = Field(None, description="Nano Banana Pro API key")
    midjourney_api_key: Optional[str] = Field(None, description="Midjourney API key")

    # Video generation services
    veo3_api_key: Optional[str] = Field(None, description="Veo3 API key")
    sora2_api_key: Optional[str] = Field(None, description="Sora2 API key")

    # Ali Token Plan (shared key for text/voice/image/video)
    ali_token_plan_api_key: Optional[str] = Field(
        None, description="Ali Token Plan API key"
    )
    sora2_api_key: Optional[str] = Field(None, description="Sora2 API key")

    # Ali Token Plan (shared key for text/voice/image/video)
    ali_token_plan_api_key: Optional[str] = Field(
        None, description="Ali Token Plan API key"
    )

    # Optional services
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key (optional)")


class ProjectConfig(BaseModel):
    """Root project configuration model"""

    # Required sections
    project: ProjectMetadataConfig = Field(..., description="Project metadata")
    script: ScriptConfig = Field(default_factory=ScriptConfig, description="Script configuration")
    output: OutputConfig = Field(..., description="Output configuration")

    # Optional sections with defaults
    characters: CharacterConfig = Field(default_factory=CharacterConfig, description="Character configuration")
    image: ImageConfig = Field(default_factory=ImageConfig, description="Image generation configuration")
    video: VideoConfig = Field(default_factory=VideoConfig, description="Video generation configuration")
    composer: ComposerConfig = Field(default_factory=ComposerConfig, description="Video composition configuration")
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig, description="Performance configuration")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Logging configuration")
    api_keys: APIKeysConfig = Field(default_factory=APIKeysConfig, description="API keys configuration (optional, falls back to environment variables)")
    quick_mode: QuickModeConfig = Field(default_factory=QuickModeConfig, description="Quick mode configuration")

    # UI settings
    enable_global_progress_bar: bool = Field(True, description="Enable global progress bar display at bottom of screen")

    @model_validator(mode='after')
    def validate_cross_config(self):
        """Validate cross-configuration dependencies"""
        # Ensure video FPS matches composer FPS
        if self.video.fps != self.composer.fps:
            # Auto-sync composer FPS to video FPS
            self.composer.fps = self.video.fps

        # Ensure output filename is set
        if not self.output.filename:
            self.output.filename = f"{self.project.name}.mp4"

        return self

    def resolve_paths(self, base_path: Path) -> None:
        """
        Resolve all relative paths to absolute paths based on project base path

        Args:
            base_path: Project folder path
        """
        # Script path
        self.script.file = str(base_path / self.script.file)

        # Character reference images
        if self.characters.reference_images:
            for char_name, char_config in self.characters.reference_images.items():
                if char_config.mode == "load" and char_config.images:
                    char_config.images = [
                        str(base_path / img_path) for img_path in char_config.images
                    ]

        # BGM file
        if self.composer.bgm.enabled and self.composer.bgm.file:
            self.composer.bgm.file = str(base_path / self.composer.bgm.file)

        # Output directory and log file
        self.output.directory = str(base_path / self.output.directory)
        self.logging.file = str(base_path / self.logging.file)

    def to_orchestrator_config(self) -> Dict[str, Any]:
        """
        Convert project config to orchestrator config format

        Returns:
            Dict compatible with DramaGenerationOrchestrator
        """
        return {
            # Image settings
            'image': {
                'service': self.image.service,
                'max_concurrent': self.image.max_concurrent,
                'width': self.image.width,
                'height': self.image.height,
                'cfg_scale': self.image.cfg_scale,
                'steps': self.image.steps,
                'enable_image_to_image': self.image.enable_image_to_image,
                'reference_weight': self.image.reference_weight,
            },

            # Video settings
            'video': {
                'service': self.video.service,
                'max_concurrent': self.video.max_concurrent,
                'fps': self.video.fps,
                'resolution': self.video.resolution,
                'motion_strength': self.video.motion_strength,
                'model': self.video.model,
            },

            # Composer settings
            'composer': {
                'add_transitions': self.composer.add_transitions,
                'transition_type': self.composer.transition_type,
                'transition_duration': self.composer.transition_duration,
                'fps': self.composer.fps,
                'preset': self.composer.preset,
                'threads': self.composer.threads,
            },

            # Character reference settings
            'enable_character_references': self.characters.enable_references,
            'character_reference': {
                'reference_mode': self.characters.reference_mode,
                'art_style': self.characters.art_style,
            },

            # BGM and subtitles
            'bgm_path': self.composer.bgm.file if self.composer.bgm.enabled else None,
            'bgm_volume': self.composer.bgm.volume if self.composer.bgm.enabled else 0.0,
            'add_subtitles': self.composer.subtitles.enabled,

            # Performance settings
            'max_concurrent_requests': self.performance.max_concurrent_requests,
            'enable_checkpoints': self.performance.enable_checkpoints,

            # Logging settings
            'log_level': self.logging.level,
            'log_file': self.logging.file,

            # UI settings
            'enable_global_progress_bar': self.enable_global_progress_bar,
        }
