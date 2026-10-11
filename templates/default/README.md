# AI Drama Project Template

This is the default project template for AI drama generation.

## Project Structure

```
your_project/
├── config.yaml           # Project configuration
├── script.txt            # Your drama script
├── characters/           # Character reference images (optional)
│   └── .gitkeep
└── outputs/              # Generated outputs
    ├── character_references/  # Generated character references
    ├── images/                # Scene images
    ├── videos/                # Scene videos
    ├── final/                 # Final composed video
    │   ├── your_drama.mp4
    │   └── your_drama.json    # Metadata
    └── generation.log
```

## Getting Started

### 1. Add Your Script

Create or edit `script.txt` with your drama script. Use the following format:

```
# 短剧标题

作者: 作者名
简介: 故事简介

## 角色
- 角色名: 描述, 年龄, 外貌特征

## 场景1: 地点 - 时间
地点: 具体地点描述
时间: 时间描述
天气: 天气状况
氛围: 氛围描述
镜头: 特写/中景/远景/全景
运镜: 静止/摇镜/推镜/拉镜/跟镜
风格: cinematic/anime/realistic
色调: warm/cool/vibrant

描述: 场景的具体描述

角色名（情绪|语气）: "对话内容"
```

See `examples/sample_scripts/` for complete examples.

### 2. Configure Your Project

Edit `config.yaml` to customize:

- **Image settings**: Resolution, quality, generation service
- **Video settings**: FPS, resolution, motion strength
- **Character settings**: Reference generation mode, art style
- **Composition**: Transitions, BGM, subtitles
- **Output**: Filename, intermediate file handling

### 3. API Keys

You have two options to configure API keys:

**Option 1: In config.yaml (Recommended for project-specific keys)**

Edit `config.yaml` and add your API keys:

```yaml
api_keys:
  doubao_api_key: "your_doubao_key_here"
  veo3_api_key: "your_veo3_key_here"
```

**Option 2: In .env file (Global keys for all projects)**

Create/edit `.env` file in the project root:

```bash
# Required for image generation (choose one)
DOUBAO_API_KEY=your_doubao_key_here
# or
NANO_BANANA_API_KEY=your_nano_banana_key_here

# Required for video generation
VEO3_API_KEY=your_veo3_key_here
```

**Priority**: config.yaml > .env file. If a key is set in both places, the config.yaml value will be used.

### 4. Generate Your Drama

Run the generation command:

```bash
# Basic generation
python cli.py generate path/to/your_project

# With custom log level
python cli.py generate path/to/your_project --log-level DEBUG

# Override configuration
python cli.py generate path/to/your_project --override video.fps=60
```

## Configuration Options

### Character References

**Auto-generate all characters** (default):
```yaml
characters:
  enable_references: true
  reference_mode: "single_multi_view"
  art_style: "realistic"
```

**Use existing character images**:
```yaml
characters:
  enable_references: true
  reference_images:
    小明:
      mode: "load"
      images:
        - "characters/xiaoming_ref.png"
```

**Mixed mode** (some generate, some load):
```yaml
characters:
  enable_references: true
  reference_images:
    小明:
      mode: "generate"
      views: ["front_view", "side_view"]
    小红:
      mode: "load"
      images:
        - "characters/xiaohong.png"
```

### Image Generation Services

Choose your preferred image generation service:

- **Doubao** (豆包): Recommended, supports image-to-image for consistency
- **Nano Banana Pro**: Alternative service
- **Midjourney**: High-quality artistic style

```yaml
image:
  service: "ali_token_plan"  # or "doubao", "nano_banana", "midjourney"
```

### Video Settings

Customize video generation:

```yaml
video:
  fps: 30              # Frame rate
  resolution: "1920x1080"
  motion_strength: 0.6  # Camera movement intensity
  model: "veo_3_1"     # Veo3 model variant
```

### Background Music

Add background music to your drama:

```yaml
composer:
  bgm:
    enabled: true
    file: "bgm/music.mp3"  # Relative to project folder
    volume: 0.3
```

## Validation

Validate your project before generation:

```bash
python cli.py validate path/to/your_project
```

This checks:
- Project structure
- Script file exists
- Configuration is valid
- API keys are configured
- Character reference images exist (if mode="load")

## Tips

1. **Start Simple**: Use the default configuration for your first project
2. **Test Scripts**: Validate your script format with smaller projects first
3. **Character Consistency**: Use character references for multi-scene consistency
4. **Resolution Trade-off**: Higher resolution = better quality but slower generation
5. **Concurrent Tasks**: Adjust `max_concurrent` based on your API rate limits

## Troubleshooting

**Issue**: Generation fails with API error
- Check API keys are valid and have sufficient quota
- Reduce `max_concurrent` to avoid rate limiting

**Issue**: Character appearance inconsistent
- Enable character references: `enable_references: true`
- Use `single_multi_view` mode for better consistency
- Increase `reference_weight` (0.7-0.9)

**Issue**: Video looks choppy
- Increase FPS: `video.fps: 60`
- Check motion_strength is appropriate for scene

## Support

For more information:
- See main documentation: `README.md`
- Check examples: `examples/sample_scripts/`
- View developer guide: `CLAUDE.md`
