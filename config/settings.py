"""Configuration management module"""
from pydantic_settings import BaseSettings
from typing import Optional, List, Literal


class Settings(BaseSettings):
    """应用配置"""

    # 图片生成服务选择 (默认使用阿里云 Token Plan)
    image_service_type: Literal["doubao", "nano_banana", "midjourney", "ali_token_plan"] = "ali_token_plan"

    # 阿里云 Token Plan (Ali Coding Plan) 配置
    # OpenAI 兼容网关，一个 Key 覆盖文本/语音/图像/视频模型
    ali_token_plan_api_key: str = ""
    ali_token_plan_base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    # 图像生成 (wan2.7-image-pro)
    ali_image_endpoint: str = "/api/v1/services/aigc/multimodal-generation/generation"
    ali_image_model: str = "wan2.7-image-pro"
    # 视频生成 (happyhorse-1.1 系列: i2v=图生视频, t2v=文生视频, r2v=参考生视频)
    ali_video_endpoint: str = "/api/v1/services/aigc/video-generation/video-synthesis"
    ali_video_model: str = "happyhorse-1.1-i2v"
    ali_video_t2v_model: str = "happyhorse-1.1-t2v"
    ali_video_r2v_model: str = "happyhorse-1.1-r2v"
    ali_video_default_size: str = "1280x720"
    ali_video_default_duration: int = 5
    # 视频水印（true 时成品带 refiner_watermark 标记；默认关闭）
    ali_video_watermark: bool = False

    # Doubao (豆包) 配置
    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com"
    doubao_endpoint: str = "/api/v3/images/generations"
    doubao_model: str = "doubao-seedream-4-5-251128"
    doubao_watermark: bool = False  # 是否在生成的图片中添加水印（false: 不添加水印）
    # 豆包 Seedance 视频生成（火山方舟 Ark 异步任务接口，非 OpenAI 兼容）
    doubao_video_api_key: str = ""
    doubao_video_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_video_endpoint: str = "/contents/generations/tasks"
    doubao_video_model: str = "doubao-seedance-2-0-260128"      # 图生视频
    doubao_video_t2v_model: str = "doubao-seedance-2-0-260128"  # 文生视频
    doubao_video_default_resolution: str = "720p"               # 480p / 720p / 1080p
    doubao_video_default_ratio: str = "16:9"
    doubao_video_default_duration: int = 5
    doubao_video_watermark: bool = False

    # Nano Banana Pro配置
    nano_banana_api_key: str = ""
    nano_banana_base_url: str = "https://api.nanobananapro.com/v1"
    nano_banana_endpoint: str = "/generate"  # API 端点路径
    nano_banana_model: str = "dall-e-3"  # 图像生成模型名称

    # 视频生成服务选择 (默认使用阿里云 Token Plan happyhorse)
    video_service_type: Literal["veo3", "sora2", "ali_token_plan", "doubao"] = "ali_token_plan"

    # Veo3配置
    veo3_api_key: str = ""
    veo3_base_url: str = "https://api.kuai.host"
    veo3_endpoint: str = "/v1/videos"  # OpenAI 格式的视频生成端点
    veo3_model: str = "veo_3_1"  # 视频生成模型：veo_3_1 或 veo_3_1-fast
    veo3_upload_endpoint: Optional[str] = None  # OpenAI 格式不需要单独上传
    veo3_skip_upload: bool = True  # OpenAI 格式使用 multipart，无需单独上传

    # Sora2配置
    sora2_api_key: str = ""
    sora2_base_url: str = "https://api.kuai.host"
    sora2_endpoint: str = "/v1/videos"
    sora2_model: str = "sora-2"  # 模型: sora-2 或 sora-2-pro
    sora2_default_size: str = "1280x720"  # 默认分辨率: 720x1280, 1280x720, 1024x1792, 1792x1024
    sora2_default_duration: int = 8  # 默认时长（秒）: 4, 8, 12
    sora2_default_style: Optional[str] = None  # 默认风格: thanksgiving, comic, news, selfie, nostalgic, anime
    sora2_watermark: bool = False  # 是否添加水印
    sora2_private: bool = False  # 是否私有视频

    # 视频生成重试配置
    video_generation_max_retries: int = 3  # 视频生成失败时最大重试次数
    video_generation_retry_delay: float = 5.0  # 重试间隔（秒）
    video_generation_retry_backoff: float = 2.0  # 重试延迟倍增因子

    # Midjourney配置
    midjourney_api_key: str = ""
    midjourney_base_url: str = "https://api.kuai.host"
    midjourney_bot_type: str = "MID_JOURNEY"  # MID_JOURNEY 或 NIJI_JOURNEY
    midjourney_poll_interval: float = 3.0  # 轮询间隔（秒）
    midjourney_max_poll_attempts: int = 100  # 最大轮询次数
    midjourney_auto_upscale: bool = False  # 是否自动upscale获取单张图
    midjourney_upscale_index: int = 1  # 选择upscale哪一张1-4

    # 应用配置
    output_dir: str = "./output"
    temp_dir: str = "./temp"
    log_level: str = "INFO"
    max_concurrent_requests: int = 5

    # 图片生成并发配置
    image_max_concurrent: int = 3  # 图片生成最大并发数 (1-10)

    # 视频生成并发配置
    video_max_concurrent: int = 2  # 视频生成最大并发数 (1-5)

    # 场景连续性配置
    enable_scene_continuity: bool = True  # 是否启用场景间连续性处理
    continuity_frame_index: int = -5  # 提取前一视频的帧位置（负数表示倒数，-5表示倒数第5帧）
    continuity_reference_weight: float = 0.5  # 连续性参考图权重（0.0-1.0），平衡连贯性和创作自由度
    enable_smart_continuity_judge: bool = True  # 是否启用智能连续性判断（使用LLM判断场景是否连续）

    # 角色一致性配置
    enable_character_references: bool = True  # 是否启用角色参考图生成
    character_reference_mode: Literal["single_multi_view", "multiple_single_view"] = "single_multi_view"  # 单张多视角 or 多张单视角
    reference_views: List[str] = [  # 要生成的参考视图列表
        "front_view",
        "side_view",
        "close_up",
        "full_body"
    ]
    max_reference_images: int = 4  # 最大参考图数量
    reference_image_size: int = 1024  # 参考图尺寸（像素）
    reference_cfg_scale: float = 8.0  # 参考图生成的CFG引导强度
    reference_steps: int = 60  # 参考图生成的推理步数
    character_art_style: Literal["realistic", "anime", "semi_realistic"] = "realistic"  # 角色风格：realistic(写实), anime(动漫), semi_realistic(半写实)

    # 场景图片一致性配置
    enable_image_to_image: bool = True  # 是否启用图生图（基于角色参考图）
    scene_cfg_scale: float = 7.5  # 场景图生成的CFG引导强度
    scene_steps: int = 50  # 场景图生成的推理步数
    reference_image_weight: float = 0.7  # 参考图权重 (0.0-1.0)，控制对参考图的遵循程度

    # 智能时长计算配置
    enable_smart_duration: bool = True  # 是否启用智能时长计算
    duration_chinese_chars_per_sec: float = 3.5  # 中文朗读速度（字/秒）
    duration_english_words_per_sec: float = 2.5  # 英文朗读速度（词/秒）
    duration_base_time: float = 2.0  # 基础场景建立时长（秒）
    duration_min_guaranteed: float = 3.0  # 最小保障时长（秒）
    duration_action_base: float = 1.5  # 动作基础时长（秒）
    duration_emotion_padding: float = 0.3  # 情绪停顿填充（秒）
    duration_buffer_multiplier: float = 1.1  # 缓冲系数（1.1 = 10%余量）

    # LLM配置（用于提示词优化）
    fast_llm_api_key: str = ""
    fast_llm_api_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    fast_llm_model: str = "qwen3.8-max"
    enable_prompt_optimization: bool = True  # 是否启用提示词优化

    # Judge LLM配置（用于图片质量评分）
    judge_llm_api_key: str = ""
    judge_llm_api_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    judge_llm_model: str = "qwen3.8-max"
    enable_character_consistency_judge: bool = True  # 是否启用角色一致性评分
    candidate_images_per_scene: int = 3  # 每个场景生成的候选图片数量（1-5）
    judge_temperature: float = 0.3  # Judge LLM的温度参数（越低越稳定）

    # 可选配置
    tts_api_key: str = ""
    tts_base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    tts_model: str = "qwen-audio-3.0-tts-plus"
    tts_default_voice: str = "Cherry"
    tts_default_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3"
    tts_default_speed: float = 1.0
    enable_tts: bool = False
    # auto | openai_compatible | dashscope_native
    #
    # 注意：Ali Token Plan 网关虽然列出 qwen-audio-3.0-tts-plus，但**没有**
    # 一次性 HTTP 合成接口（/audio/speech 返回 400 InvalidParameter "url error"，
    # 只有 realtime 模型可用且需走 WebSocket）。provider=auto 时这类主机会自动
    # 改走下面的 DashScope 原生接口，而不是静默失败。
    tts_provider: Literal["auto", "openai_compatible", "dashscope_native", "volc_tts2"] = "auto"
    # DashScope 原生语音合成（qwen-tts / cosyvoice-v2）。
    # 必须填 DashScope（百炼）Key：Token Plan 的 Key 在 dashscope.aliyuncs.com
    # 上无效，复用它只会拿到 401。留空时不会静默降级，而是记录原因并跳过配音。
    tts_native_base_url: str = "https://dashscope.aliyuncs.com"
    tts_native_api_key: str = ""
    tts_native_model: str = "qwen-tts"
    tts_native_voice: str = "Cherry"
    # 火山引擎语音合成 2.0（v3 双向 WebSocket，seed-tts-2.0 资源）
    tts_volc_api_key: str = ""
    tts_volc_resource_id: str = "seed-tts-2.0"
    tts_volc_voice: str = "zh_female_xiaohe_uranus_bigtts"
    tts_volc_speed: float = 1.0
    tts_volc_sample_rate: int = 24000

    agent_enabled: bool = False
    agent_provider: Literal["openai", "anthropic", "google"] = "openai"
    agent_api_key: str = ""
    agent_base_url: Optional[str] = None
    agent_model: str = ""
    agent_max_turns: int = 20
    agent_timeout_seconds: int = 300
    aragon_cli_path: str = "aragon"

    openai_api_key: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from backend .env


# 全局配置实例
settings = Settings()
