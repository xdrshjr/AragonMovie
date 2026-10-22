const fs = require('fs');

function patch(path, replacements) {
  let text = fs.readFileSync(path, 'utf8');
  for (const [anchor, insert, where = 'after'] of replacements) {
    if (!text.includes(anchor)) {
      console.error(`ANCHOR MISSING in ${path}: ${anchor.slice(0, 70)}`);
      process.exit(1);
    }
    text = text.replace(anchor, where === 'after' ? anchor + insert : insert + anchor);
  }
  fs.writeFileSync(path, text);
  console.log(`patched ${path}`);
}

const EOL = '\r\n';

patch('config/settings.py', [
  [
    '    doubao_watermark: bool = False  # 是否在生成的图片中添加水印（false: 不添加水印）',
    [
      '',
      '    # 豆包 Seedance 视频生成（火山方舟 Ark 异步任务接口，非 OpenAI 兼容）',
      '    doubao_video_api_key: str = ""',
      '    doubao_video_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"',
      '    doubao_video_endpoint: str = "/contents/generations/tasks"',
      '    doubao_video_model: str = "doubao-seedance-2-0-260128"      # 图生视频',
      '    doubao_video_t2v_model: str = "doubao-seedance-2-0-260128"  # 文生视频',
      '    doubao_video_default_resolution: str = "720p"               # 480p / 720p / 1080p',
      '    doubao_video_default_ratio: str = "16:9"',
      '    doubao_video_default_duration: int = 5',
      '    doubao_video_watermark: bool = False',
    ].join(EOL),
  ],
  [
    '    tts_native_voice: str = "Cherry"',
    [
      '',
      '    # 火山引擎语音合成 2.0（v3 双向 WebSocket，seed-tts-2.0 资源）',
      '    tts_volc_api_key: str = ""',
      '    tts_volc_resource_id: str = "seed-tts-2.0"',
      '    tts_volc_voice: str = "zh_female_xiaohe_uranus_bigtts"',
      '    tts_volc_speed: float = 1.0',
      '    tts_volc_sample_rate: int = 24000',
    ].join(EOL),
  ],
  [
    '    video_service_type: Literal["veo3", "sora2", "ali_token_plan"] = "ali_token_plan"',
    '',
  ],
]);

patch('backend/config.py', [
  [
    '    doubao_watermark: bool = False',
    [
      '',
      '    # 豆包 Seedance 视频生成（火山方舟 Ark 异步任务接口）',
      '    doubao_video_api_key: str = ""',
      '    doubao_video_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"',
      '    doubao_video_endpoint: str = "/contents/generations/tasks"',
      '    doubao_video_model: str = "doubao-seedance-2-0-260128"',
      '    doubao_video_t2v_model: str = "doubao-seedance-2-0-260128"',
      '    doubao_video_default_resolution: str = "720p"',
      '    doubao_video_default_ratio: str = "16:9"',
      '    doubao_video_default_duration: int = 5',
      '    doubao_video_watermark: bool = False',
    ].join(EOL),
  ],
  [
    '    tts_native_voice: str = "Cherry"',
    [
      '',
      '    # 火山引擎语音合成 2.0（v3 双向 WebSocket）',
      '    tts_volc_api_key: str = ""',
      '    tts_volc_resource_id: str = "seed-tts-2.0"',
      '    tts_volc_voice: str = "zh_female_xiaohe_uranus_bigtts"',
      '    tts_volc_speed: float = 1.0',
      '    tts_volc_sample_rate: int = 24000',
    ].join(EOL),
  ],
  [
    '    video_service_type: Literal["veo3", "sora2", "ali_token_plan"] = "ali_token_plan"',
    '',
  ],
]);
