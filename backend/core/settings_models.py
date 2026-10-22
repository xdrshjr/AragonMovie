"""Model settings schemas for the runtime Settings Center.

Five categories of external services can be reconfigured at runtime:

- text  : fast LLM (prompt optimization) + judge LLM (image scoring)
- voice : TTS (OpenAI-compatible /audio/speech)
- video : Veo3 / Sora2 (runtime-selectable)
- image : Doubao / NanoBanana / Midjourney (runtime-selectable)
- agent : the LLM that powers AragonAgent-based assisted configuration

Write-only API-key semantics
----------------------------
Every ``api_key`` field is optional on input:

- ``None`` / absent  -> keep the currently stored key
- empty string ``""`` -> clear the key
- any other string   -> replace the key

``GET /api/v1/settings`` always returns MASKED keys (see :func:`mask_key`).
The persisted JSON file stores the real keys; it lives under
``backend/data/`` which is git-ignored.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

# ==================== Text (LLM) ====================


class FastLLMConfig(BaseModel):
    """Fast LLM for script polishing / prompt optimization"""
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    api_url: str = Field("https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    model: str = Field("qwen3.8-max")


class JudgeLLMConfig(BaseModel):
    """Multimodal judge LLM for character-consistency scoring"""
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    api_url: str = Field("https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    model: str = Field("qwen3.8-max")


class TextSettings(BaseModel):
    fast_llm: FastLLMConfig = Field(default_factory=FastLLMConfig)
    judge_llm: JudgeLLMConfig = Field(default_factory=JudgeLLMConfig)
    enable_prompt_optimization: bool = True
    enable_character_consistency_judge: bool = True


# ==================== Voice (TTS) ====================


class VoiceSettings(BaseModel):
    """TTS configuration.

    ``provider`` picks the transport:

    - ``openai_compatible``: ``POST {base_url}/audio/speech``
    - ``dashscope_native``: DashScope native synthesis (qwen-tts / cosyvoice-v2)
    - ``auto``: DashScope host -> native, Token Plan gateway -> native
      (its /audio/speech route does not exist), everything else -> compatible
    """
    enabled: bool = Field(False, description="Enable the TTS service")
    provider: Literal[
        "auto", "openai_compatible", "dashscope_native", "volc_tts2"
    ] = "auto"
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: str = Field("https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    model: str = Field("qwen-audio-3.0-tts-plus")
    default_voice: str = Field("Cherry")
    default_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3"
    default_speed: float = Field(1.0, ge=0.25, le=4.0)
    # DashScope native synthesis transport
    native_base_url: str = Field("https://dashscope.aliyuncs.com")
    native_api_key: Optional[str] = Field(None, description="DashScope key (write-only)")
    native_model: str = Field("qwen-tts")
    native_voice: str = Field("Cherry")
    # 火山引擎语音合成 2.0（v3 双向 WebSocket，provider=volc_tts2 时生效）
    volc_api_key: Optional[str] = Field(
        None, description="Volcano TTS 2.0 API key (write-only)"
    )
    volc_resource_id: str = Field("seed-tts-2.0")
    volc_voice: str = Field("zh_female_xiaohe_uranus_bigtts")


# ==================== Video ====================


class Veo3Config(BaseModel):
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: str = Field("https://api.kuai.host")
    endpoint: str = Field("/v1/videos")
    model: str = Field("veo_3_1")
    skip_upload: bool = True


class Sora2Config(BaseModel):
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: str = Field("https://api.kuai.host")
    endpoint: str = Field("/v1/videos")
    model: str = Field("sora-2")
    default_size: str = Field("1280x720")
    default_duration: int = Field(8, ge=4, le=25)
    default_style: Optional[str] = Field(None)
    watermark: bool = False
    private: bool = False


class AliTokenPlanVideoConfig(BaseModel):
    """Ali Token Plan video generation (happyhorse-1.1 family, OpenAI-compatible).

    ``model`` is the image-to-video model used by the pipeline; ``t2v_model``
    and ``r2v_model`` are exposed for text-to-video / reference-to-video use.
    """
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: str = Field("https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    endpoint: str = Field("/api/v1/services/aigc/video-generation/video-synthesis")
    model: str = Field("happyhorse-1.1-i2v")
    t2v_model: str = Field("happyhorse-1.1-t2v")
    r2v_model: str = Field("happyhorse-1.1-r2v")
    default_size: str = Field("1280x720")
    default_duration: int = Field(5, ge=1, le=60)
    watermark: bool = Field(
        False,
        description="Request the watermarked variant (refiner_watermark) from the gateway",
    )


class DoubaoVideoConfig(BaseModel):
    """Volcano Ark Seedance video generation (image-to-video / text-to-video).

    Ark is not OpenAI-compatible: it uses an async task API
    (/contents/generations/tasks) and takes resolution/duration/ratio as
    JSON fields.
    """
    api_key: Optional[str] = Field(None, description="Ark API key (write-only)")
    base_url: str = Field("https://ark.cn-beijing.volces.com/api/v3")
    endpoint: str = Field("/contents/generations/tasks")
    model: str = Field("doubao-seedance-2-0-260128", description="Image-to-video model")
    t2v_model: str = Field("doubao-seedance-2-0-260128", description="Text-to-video model")
    default_resolution: Literal["480p", "720p", "1080p"] = "720p"
    default_ratio: str = Field("16:9")
    default_duration: int = Field(5, ge=4, le=15)
    watermark: bool = False


class VideoSettings(BaseModel):
    service_type: Literal[
        "veo3", "sora2", "ali_token_plan", "doubao"
    ] = "ali_token_plan"
    veo3: Veo3Config = Field(default_factory=Veo3Config)
    sora2: Sora2Config = Field(default_factory=Sora2Config)
    ali_token_plan: AliTokenPlanVideoConfig = Field(
        default_factory=AliTokenPlanVideoConfig
    )
    doubao: DoubaoVideoConfig = Field(default_factory=DoubaoVideoConfig)


# ==================== Image ====================


class DoubaoConfig(BaseModel):
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: str = Field("https://ark.cn-beijing.volces.com")
    endpoint: str = Field("/api/v3/images/generations")
    model: str = Field("doubao-seedream-4-5-251128")
    watermark: bool = False


class NanoBananaConfig(BaseModel):
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: str = Field("https://nanoapi.poloai.top")
    endpoint: str = Field("/v1/images/generations")
    model: str = Field("gemini-3-pro-image-preview")


class AliTokenPlanImageConfig(BaseModel):
    """Ali Token Plan image generation (wan2.7-image-pro, OpenAI-compatible)"""
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: str = Field("https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    endpoint: str = Field("/api/v1/services/aigc/multimodal-generation/generation")
    model: str = Field("wan2.7-image-pro")


class MidjourneyConfig(BaseModel):
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: str = Field("https://api.kuai.host")
    bot_type: Literal["MID_JOURNEY", "NIJI_JOURNEY"] = "MID_JOURNEY"
    poll_interval: float = Field(3.0, gt=0)
    max_poll_attempts: int = Field(100, ge=1)
    auto_upscale: bool = False
    upscale_index: int = Field(1, ge=1, le=4)


class ImageSettings(BaseModel):
    service_type: Literal[
        "doubao", "nano_banana", "midjourney", "ali_token_plan"
    ] = "ali_token_plan"
    doubao: DoubaoConfig = Field(default_factory=DoubaoConfig)
    nano_banana: NanoBananaConfig = Field(default_factory=NanoBananaConfig)
    midjourney: MidjourneyConfig = Field(default_factory=MidjourneyConfig)
    ali_token_plan: AliTokenPlanImageConfig = Field(
        default_factory=AliTokenPlanImageConfig
    )


# ==================== Agent ====================


class AgentSettings(BaseModel):
    """The LLM powering AragonAgent-based assisted configuration.

    provider ``openai`` covers any OpenAI-compatible endpoint (DeepSeek,
    Qwen/DashScope, Moonshot, local gateways, ...) via ``base_url``.
    """
    enabled: bool = Field(False, description="Enable agent-assisted configuration")
    provider: Literal["openai", "anthropic", "google"] = "openai"
    api_key: Optional[str] = Field(None, description="API key (write-only)")
    base_url: Optional[str] = Field(
        None, description="OpenAI-compatible base URL; empty for official APIs"
    )
    model: str = Field("", description="Model id, e.g. gpt-4o / deepseek-chat")
    max_turns: int = Field(20, ge=1, le=100)
    timeout_seconds: int = Field(300, ge=10, le=3600)
    aragon_cli_path: str = Field("aragon", description="Path to the aragon CLI executable")


# ==================== Aggregate ====================


class ModelSettings(BaseModel):
    text: TextSettings = Field(default_factory=TextSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    video: VideoSettings = Field(default_factory=VideoSettings)
    image: ImageSettings = Field(default_factory=ImageSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)


class SettingsUpdateRequest(BaseModel):
    """Partial settings update.

    Absent categories are left untouched. Inside a present category, absent
    fields keep their current values and ``api_key=None`` keeps the stored
    key (write-only semantics).
    """
    text: Optional[TextSettings] = None
    voice: Optional[VoiceSettings] = None
    video: Optional[VideoSettings] = None
    image: Optional[ImageSettings] = None
    agent: Optional[AgentSettings] = None


# ==================== Connection-test models ====================


class ConnectionTestResult(BaseModel):
    category: Literal["text", "voice", "video", "image", "agent"] = Field(...)
    target: str = Field("", description="Human-readable target that was probed, e.g. 'fast_llm'")
    success: bool = Field(...)
    latency_ms: Optional[int] = Field(None, description="Round-trip latency in milliseconds")
    message: str = Field("", description="Short result summary")
    detail: Optional[str] = Field(None, description="Error detail / response excerpt on failure")
    verified: str = Field(
        "full",
        description="'full' = real request succeeded; 'partial' = only reachability/auth verified",
    )


class AgentStatusResponse(BaseModel):
    aragon_installed: bool = Field(..., description="Whether the aragon CLI is available")
    aragon_version: Optional[str] = Field(None)
    aragon_path: Optional[str] = Field(None)
    agent_configured: bool = Field(..., description="Agent LLM (key+model) configured")
    agent_enabled: bool = Field(...)
    mode: Literal["aragon", "llm_fallback", "unavailable"] = Field(
        ..., description="Effective assistant mode"
    )
    message: str = Field("")
