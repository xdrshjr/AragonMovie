

# AI短剧自动化生成系统

基于Python和多Agent架构的AI短剧自动生成工具，提供**双界面**支持：CLI命令行和Web浏览器界面，让视频创作更灵活便捷。

## 功能特性

- 🎬 自动剧本解析与分镜设计
- 🖼️ AI驱动的分镜图片生成（Nano Banana Pro）
- 🎥 图片到视频的智能转换（Veo3 / Sora2，可配置切换）
- ✂️ 自动视频合成与后期处理
- 👤 角色一致性参考图生成（支持加载/自动生成）
- 🧠 **LLM角色一致性判断**（多候选图片评分选优）
- 🔄 断点续传与错误恢复
- 📊 实时进度监控与日志可视化
- 🛠️ 双界面支持：**CLI命令行** + **Web浏览器**
- 🌐 REST API + OpenAI兼容API

## 系统架构

### 双界面架构

系统提供两种使用方式，共享同一核心生成引擎：

**1. CLI界面**（命令行）
- 直接通过 `cli.py` 管理项目和生成视频
- 适合自动化脚本、批处理任务
- 完整的断点续传和配置覆盖支持

**2. Web界面**（浏览器）
- **后端**: FastAPI + REST API + OpenAI兼容API
- **前端**: Next.js 14 + React 18 + TypeScript
- 可视化项目管理和工作流执行
- 实时进度监控和日志查看
- 开发服务器: `http://localhost:3000` (前端) + `http://localhost:8000` (后端)

### 多Agent协作架构

核心视频生成管道由以下Agent组成：

- **DramaGenerationOrchestrator**: 主控协调器，管理整体工作流
- **ScriptParserAgent**: 解析文本剧本，生成结构化分镜脚本
- **ImageGenerationAgent**: 调用Nano Banana Pro API生成分镜图片（支持多候选图片并发生成）
- **VideoGenerationAgent**: 调用Veo3或Sora2 API将图片转换为视频片段（支持动态切换）
- **VideoComposerAgent**: 拼接视频片段并进行后期处理

**角色一致性判断**（可选）：
- 为每个场景生成N张候选图片（推荐3-5张）
- 使用Judge LLM（如Doubao多模态模型）对比角色参考图评分
- 自动选择最高分候选图片进行视频生成
- 并发评估所有候选，提升效率

## 快速开始

### 1. 环境要求

- Python 3.9+
- Node.js 18.0+ 和 npm 9.0+ (Web界面)
- FFmpeg 4.0+

### 2. 安装依赖

**后端和CLI依赖（Python）：**

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境 (Windows)
.\venv\Scripts\activate

# 激活虚拟环境 (macOS/Linux)
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**前端依赖（Node.js）：**

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install
```

### 3. 配置API密钥

复制`.env.example`为`.env`并填入你的API密钥：

```bash
cp .env.example .env
```

编辑`.env`文件，填入以下配置：

```bash
# 必需的API密钥
NANO_BANANA_API_KEY=your_nano_banana_api_key_here

# 视频服务选择（veo3 或 sora2）
VIDEO_SERVICE_TYPE=veo3

# Veo3 视频生成服务
VEO3_API_KEY=your_veo3_api_key_here

# Sora2 视频生成服务（可选，如需使用Sora2）
SORA2_API_KEY=your_sora2_api_key_here
SORA2_MODEL=sora-2  # sora-2 或 sora-2-pro
SORA2_DEFAULT_SIZE=1280x720
SORA2_DEFAULT_DURATION=8
SORA2_DEFAULT_STYLE=  # 可选: thanksgiving, comic, news, selfie, nostalgic, anime

# 可选的API密钥
DOUBAO_API_KEY=your_doubao_api_key_here  # 用于剧本优化

# 角色一致性判断配置（可选）
ENABLE_CHARACTER_CONSISTENCY_JUDGE=true
CANDIDATE_IMAGES_PER_SCENE=3  # 每个场景生成的候选图片数量（1-5，推荐3-5）
JUDGE_LLM_API_KEY=your_judge_api_key_here  # Judge LLM API密钥
JUDGE_LLM_MODEL=doubao-seed-1-6-251015  # Judge LLM模型名称
JUDGE_TEMPERATURE=0.3  # Judge LLM温度参数
```

### 4. 启动服务

**方式1: 使用CLI界面（命令行）**

```bash
# 直接使用CLI命令（见下方"CLI使用指南"）
python cli.py init my_drama
python cli.py generate projects/my_drama
```

**方式2: 使用Web界面（浏览器）**

```bash
# 启动后端服务器
cd backend
python run_dev.py
# 后端运行在: http://localhost:8000
# API文档: http://localhost:8000/docs

# 新开终端，启动前端服务器
cd frontend
npm run dev
# 前端运行在: http://localhost:3000
```

然后在浏览器访问 `http://localhost:3000` 即可使用可视化界面。

---

## CLI使用指南

### 创建和生成项目

```bash
# 创建新项目
python cli.py init my_drama

# 编辑项目脚本和配置
# - 编辑 projects/my_drama/script.txt
# - 编辑 projects/my_drama/config.yaml

# 验证项目配置
python cli.py validate projects/my_drama

# 生成视频
python cli.py generate projects/my_drama

# 查看所有项目
python cli.py list
```

### 高级CLI选项

```bash
# 使用自定义脚本创建项目
python cli.py init my_drama --script examples/sample_scripts/programmer_day.txt

# 覆盖配置参数
python cli.py generate projects/my_drama --override video.fps=60

# 从断点恢复生成
python cli.py generate projects/my_drama --resume

# 跳过角色参考图生成
python cli.py generate projects/my_drama --skip-characters

# 自定义输出文件名
python cli.py generate projects/my_drama --output my_video.mp4

# 调试模式
python cli.py generate projects/my_drama --log-level DEBUG
```

---

## Web界面使用指南

### 后端API

**REST API v1** (`http://localhost:8000/api/v1/`):
- `/llm/*` - LLM服务（剧本优化、角色一致性判断）
- `/images/*` - 图片生成端点
- `/videos/*` - 视频生成端点
- `/tasks/*` - 异步任务管理
- `/workflow/*` - 完整工作流编排
- `/projects/*` - 项目CRUD操作

**OpenAI兼容API** (`http://localhost:8000/v1/`):
- `/chat/completions` - 聊天完成端点
- `/images/generations` - 图片生成端点
- `/videos/generations` - 视频生成端点

**API文档**:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 前端功能

- **项目管理**: 创建、查看、删除项目
- **工作流执行**: 分步配置和执行视频生成
- **进度监控**: 实时查看生成进度和日志
- **结果预览**: 预览生成的图片和视频

---

## 项目结构

```
ai-movie-agent-guide/
│
├── cli.py                           # CLI入口
├── init_project.py                  # 项目初始化脚本
├── requirements.txt                 # Python依赖
│
├── agents/                          # Agent模块
│   ├── base_agent.py               # Agent基类 + MessageBus + 工作流状态管理
│   ├── script_parser_agent.py      # 剧本解析Agent
│   ├── image_generator_agent.py    # 图片生成Agent（支持多候选并发）
│   ├── video_generator_agent.py    # 视频生成Agent
│   ├── video_composer_agent.py     # 视频合成Agent
│   └── orchestrator_agent.py       # 主控Agent
│
├── backend/                         # FastAPI后端
│   ├── main.py                     # FastAPI应用初始化
│   ├── run_dev.py                  # 开发服务器启动脚本
│   ├── config.py                   # Pydantic配置
│   │
│   ├── api/                        # API路由
│   │   ├── router.py               # 主路由（组合v1和OpenAI API）
│   │   ├── v1/                     # REST API v1
│   │   │   ├── llm.py
│   │   │   ├── images.py
│   │   │   ├── videos.py
│   │   │   ├── tasks.py
│   │   │   └── workflow.py
│   │   ├── openai/                 # OpenAI兼容端点
│   │   │   ├── chat.py
│   │   │   ├── images.py
│   │   │   └── videos.py
│   │   └── routes/
│   │       └── projects.py         # 项目CRUD
│   │
│   ├── core/                       # 核心后端服务
│   │   ├── task_manager.py         # 异步任务执行与跟踪
│   │   ├── workflow_service.py     # 连接FastAPI和CLI生成逻辑
│   │   ├── project_manager.py      # 项目持久化
│   │   ├── models.py               # API的Pydantic模型
│   │   └── exceptions.py           # 自定义异常类
│   │
│   ├── middleware/                 # FastAPI中间件
│   │   ├── logging.py
│   │   └── error_handler.py
│   │
│   └── utils/                      # 后端工具
│       ├── logger.py
│       ├── asset_manager.py
│       └── log_helpers.py
│
├── frontend/                        # Next.js前端
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   │
│   └── src/
│       ├── app/                    # App Router页面
│       │   ├── page.tsx            # 首页
│       │   ├── layout.tsx          # 根布局
│       │   ├── projects/
│       │   │   ├── new/page.tsx
│       │   │   └── [projectId]/page.tsx
│       │   └── workflow/
│       │       └── [projectId]/page.tsx
│       │
│       ├── components/             # React组件
│       │   ├── steps/              # 分步工作流组件
│       │   └── ui/                 # 可复用UI组件
│       │
│       └── lib/                    # 工具和类型
│           ├── api.ts              # API客户端
│           ├── types.ts            # TypeScript类型定义
│           └── types/              # 额外的类型定义
│
├── core/                            # 核心模块（CLI）
│   ├── project_manager.py          # CLI项目管理器
│   ├── config_loader.py            # YAML配置加载器
│   ├── runner.py                   # 项目执行运行器
│   ├── validators.py               # 验证逻辑
│   └── errors.py                   # 错误定义
│
├── services/                        # 外部API封装
│   ├── nano_banana_service.py      # Nano Banana API
│   ├── veo3_service.py             # Veo3 API
│   ├── sora2_service.py            # Sora2 API
│   ├── video_service_factory.py    # 视频服务工厂
│   └── doubao_service.py           # Doubao API
│
├── utils/                           # 共享工具（CLI）
│   ├── retry.py                    # @async_retry装饰器
│   ├── concurrency.py              # 并发限制、速率限制、结果缓存
│   ├── checkpoint.py               # 断点管理
│   ├── progress_monitor.py         # 进度跟踪
│   ├── task_queue.py               # 异步任务队列
│   └── video_utils.py              # FFmpeg封装
│
├── config/                          # 配置（CLI）
│   └── settings.py                 # Pydantic配置（从.env加载）
│
├── models/                          # 数据模型
│   ├── script_models.py            # Script, Scene, Character, Dialogue模型
│   └── config_models.py            # 配置模型
│
├── projects/                        # 用户项目（CLI）
│   └── [project_name]/             # 单个项目
│       ├── config.yaml             # 项目配置
│       ├── script.txt              # 剧本文件
│       ├── characters/             # 角色参考图
│       └── outputs/                # 输出目录
│           ├── images/             # 生成的图片
│           ├── videos/             # 生成的视频片段
│           └── final/              # 最终视频
│
├── templates/                       # 项目模板
│   └── default/                    # 默认模板
│       └── config.yaml             # 模板配置
│
├── tests/                           # 测试模块
│   ├── test_agents/
│   ├── test_services/
│   ├── test_integration/
│   └── test_performance/
│
├── examples/                        # 示例代码
│   ├── complete_workflow_example.py
│   └── sample_scripts/             # 示例剧本
│
├── docs/                            # 文档
│   ├── CHARACTER_CONSISTENCY_JUDGING.md
│   └── ...
│
├── .env                             # 环境变量（gitignore）
├── .env.example                     # 环境变量模板
├── .gitignore
├── CLAUDE.md                        # Claude Code项目指南
└── README.md                        # 项目说明
```

## CLI命令参考

### init - 创建新项目
```bash
python cli.py init <project_name> [options]

选项:
  --template TEMPLATE    使用指定模板 (默认: default)
  --script FILE          从文件复制剧本
  --description TEXT     项目描述
```

### generate - 生成视频
```bash
python cli.py generate <project_path> [options]

选项:
  --log-level LEVEL      日志级别 (DEBUG|INFO|WARNING|ERROR)
  --output FILENAME      自定义输出文件名
  --override KEY=VALUE   覆盖配置参数
  --dry-run              仅验证不生成
  --resume               从断点恢复
  --skip-characters      跳过角色参考图生成
```

### validate - 验证项目
```bash
python cli.py validate <project_path>
```

### list - 列出所有项目
```bash
python cli.py list
```

## 配置文件说明

项目配置文件 `config.yaml` 包含以下主要部分：

```yaml
# 项目元信息
title: "我的短剧"
description: "项目描述"

# 剧本配置
script:
  file: "script.txt"

# 图片生成配置
image:
  service: "nano_banana"
  model: "flux-dev"
  width: 1280
  height: 720
  max_concurrent: 3  # 图片生成最大并发数 (1-10)，推荐3-5

# 视频生成配置
video:
  # 服务选择: veo3 或 sora2（可选，默认使用环境变量配置）
  # service_type: sora2

  # 自定义服务配置（可选）
  # service_config:
  #   model: sora-2-pro
  #   default_duration: 12
  #   default_style: anime

  duration: 5
  fps: 24
  max_concurrent: 2  # 视频生成最大并发数 (1-5)，推荐2-3

# 角色一致性配置
characters:
  enable_references: true
  reference_images:
    角色名:
      mode: "generate"  # 或 "load"
      path: "characters/character.jpg"  # mode=load时使用

# 输出配置
output:
  filename: "output.mp4"
  format: "mp4"
```

### 并发配置优化

系统支持多线程并发生成图片和视频，可以显著提升生成速度：

- **image.max_concurrent**: 图片生成最大并发数
  - 范围: 1-10
  - 推荐值: 3-5
  - 说明: 值越大生成越快，但会增加API负载和内存占用

- **video.max_concurrent**: 视频生成最大并发数
  - 范围: 1-5
  - 推荐值: 2-3
  - 说明: 视频生成较慢，建议使用较低并发数

**示例**: 如果设置 `image.max_concurrent: 3` 和 `video.max_concurrent: 3`，系统将同时生成3张图片和3个视频，大幅提升整体生成速度。

### 角色一致性判断配置

启用角色一致性判断后，系统将为每个场景生成多张候选图片，使用LLM评分选出最佳候选：

**环境变量配置** (`.env`):
```bash
# 启用角色一致性判断
ENABLE_CHARACTER_CONSISTENCY_JUDGE=true

# 每个场景生成的候选图片数量（1-5，推荐3-5）
CANDIDATE_IMAGES_PER_SCENE=3

# Judge LLM配置
JUDGE_LLM_API_KEY=your_judge_api_key
JUDGE_LLM_MODEL=doubao-seed-1-6-251015  # 支持多模态的LLM模型
JUDGE_TEMPERATURE=0.3  # LLM温度参数（0.0-1.0）
```

**工作原理**:
1. 为每个场景并发生成N张候选图片
2. 使用Judge LLM对比角色参考图，为每张候选图片评分（并发评分）
3. 自动选择评分最高的候选图片用于视频生成
4. 可选保留或删除未选中的候选图片

**注意事项**:
- 启用后会增加API调用次数（N倍图片生成 + N次LLM评分）
- 推荐使用支持多模态的LLM模型（如Doubao）
- Judge LLM需要支持图片+文本输入
- 详细文档见 `docs/CHARACTER_CONSISTENCY_JUDGING.md`

## 剧本格式

剧本文件 `script.txt` 应遵循以下格式：

```
标题: 程序员的一天

场景1: 办公室 - 早晨
特写镜头
小明坐在电脑前，眼神疲惫，手指快速敲击键盘。
小明: "又是一个bug，这代码谁写的？"

场景2: 办公室 - 中午
中景镜头
小明和同事们围坐在一起吃外卖。
同事: "今天又要加班吗？"
小明: "项目deadline快到了，没办法。"
```

格式说明：
- 标题行：`标题: [剧名]`
- 场景行：`场景N: [地点] - [时间]`
- 镜头类型：特写镜头、中景镜头、远景镜头等
- 场景描述：描述场景中的动作和氛围
- 对话：`角色名: "对话内容"`

## 工作流程

### CLI工作流

1. **项目初始化**: 使用 `cli.py init` 创建项目结构
2. **编写剧本**: 在 `script.txt` 中编写剧本
3. **配置参数**: 在 `config.yaml` 中调整生成参数
4. **验证项目**: 使用 `cli.py validate` 检查配置
5. **生成视频**: 使用 `cli.py generate` 开始生成
   - 解析剧本 (0-10%)
   - 生成分镜图片 (10-40%)
     - 若启用角色一致性判断，为每个场景生成多张候选图片
     - LLM评分并自动选择最佳候选
   - 生成视频片段 (40-70%)
   - 合成最终视频 (70-95%)
   - 保存元数据 (95-100%)

### Web工作流

1. **启动服务**: 启动后端和前端开发服务器
2. **创建项目**: 在Web界面创建新项目
3. **配置工作流**: 按步骤配置剧本、角色、生成参数
4. **执行生成**: 启动工作流并实时监控进度
5. **查看结果**: 预览和下载生成的视频

## 成本提示

- Nano Banana Pro、Veo3和Sora2都是按使用量计费的API服务
- 建议在正式使用前先阅读官方定价文档
- 开发阶段可使用较低分辨率和较短时长进行测试
- 预估成本：生成一个5分钟短剧约需调用API 20-30次
- **启用角色一致性判断后**：
  - 图片生成调用次数 = 场景数 × 候选图片数（如3）
  - 额外增加Judge LLM调用次数 = 场景数 × 候选图片数
  - 建议先小规模测试后再大规模使用

## 常见问题

### 如何启用角色一致性判断？

在 `.env` 文件中配置：
```bash
ENABLE_CHARACTER_CONSISTENCY_JUDGE=true
CANDIDATE_IMAGES_PER_SCENE=3  # 每个场景生成3张候选图片
JUDGE_LLM_API_KEY=your_judge_api_key
JUDGE_LLM_MODEL=doubao-seed-1-6-251015
```

角色一致性判断会：
- 为每个场景生成N张候选图片（并发生成）
- 使用Judge LLM对比角色参考图评分（并发评分）
- 自动选择评分最高的候选图片用于视频生成

### 如何跳过角色参考图生成？
```bash
python cli.py generate projects/my_drama --skip-characters
```

### 如何从断点恢复生成？
```bash
python cli.py generate projects/my_drama --resume
```

### 如何调整视频质量？
在 `config.yaml` 中修改：
```yaml
image:
  width: 1920  # 提高分辨率
  height: 1080
video:
  fps: 30  # 提高帧率
```

### 如何使用自己的角色参考图？
在 `config.yaml` 中配置：
```yaml
characters:
  enable_references: true
  reference_images:
    小明:
      mode: "load"
      path: "characters/xiaoming.jpg"
```

## 开发指南

### 运行测试

**Python后端测试**:
```bash
# 运行所有测试
python -m pytest

# 运行特定测试文件
python -m pytest tests/test_agents/test_image_video_generation.py -v

# 运行带上下文的测试
python -m pytest tests/test_agents/test_image_video_generation.py -v --tb=short

# 运行特定测试类
python -m pytest tests/test_agents/test_image_video_generation.py::TestConcurrencyUtilities -v

# 运行异步测试
python -m pytest tests/test_agents/test_script_parser.py -v
```

**前端测试**:
```bash
cd frontend

# 类型检查
npm run type-check

# 构建检查
npm run build
```

### 代码格式化

**Python**:
```bash
# 格式化代码
black .

# 代码检查
flake8

# 类型检查
mypy .
```

**前端**:
```bash
cd frontend

# 格式化（如果配置了prettier）
npm run format  # 需要在package.json中配置
```

## 技术栈

### 后端 & CLI
- **Python 3.9+**: 核心语言
- **FastAPI**: Web API框架
- **Uvicorn**: ASGI服务器
- **Pydantic**: 数据验证和配置管理
- **httpx/aiohttp**: 异步HTTP客户端
- **MoviePy**: 视频编辑
- **FFmpeg**: 视频处理
- **pytest**: 测试框架
- **loguru**: 日志管理

### 前端
- **Next.js 14.2**: React框架（App Router）
- **React 18.3**: UI库
- **TypeScript 5.3**: 类型安全
- **Tailwind CSS 3.4**: 样式框架
- **js-yaml**: YAML解析

### 视频生成服务

系统支持多种视频生成服务，可通过配置切换：

#### Veo3（默认）
- 高质量图片转视频
- 支持任意时长（1-30秒）
- 支持自定义motion strength和camera motion

#### Sora2（新增）
- OpenAI Sora2模型
- 支持多种风格（anime, comic, nostalgic等）
- 支持角色一致性（character_url参数）
- 支持故事板模式（多镜头连续生成）
- 时长限制：4/8/12秒（基础模式）或10/15/25秒（故事板模式）

**配置切换**:
```bash
# .env
VIDEO_SERVICE_TYPE=sora2  # 或 veo3
SORA2_API_KEY=sk-YOUR_KEY_HERE
```

详细文档：
- [Sora2集成指南](docs/dev-plan/01-sora-dev/SORA2_INTEGRATION_GUIDE.md)
- [Sora2 API参考](docs/dev-plan/01-sora-dev/SORA2_API_REFERENCE.md)

### 外部服务
- **Nano Banana Pro**: AI图片生成
- **Veo3**: AI视频生成（默认）
- **Sora2**: AI视频生成（可选，OpenAI格式）
- **Doubao (火山引擎方舟)**: LLM服务（剧本优化、角色一致性判断）

## 贡献指南

欢迎提交Issue和Pull Request！

开发流程：
1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 许可证

MIT License

## 联系方式

xdrshjr@gmail.com

如有问题或建议，请提交Issue。
