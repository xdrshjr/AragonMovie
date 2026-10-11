# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI短剧自动化生成系统 (AI Drama Automation System) - A multi-agent architecture system that generates complete short drama videos from text scripts. The system provides **dual interfaces**:

1. **CLI Interface**: Direct command-line access for project management and video generation
2. **Web Interface**: FastAPI backend + Next.js frontend for browser-based workflows

Both interfaces share the same core video generation pipeline, which integrates Nano Banana Pro (image generation), Veo3/Sora2 (video generation with runtime selection), and optional LLM services for character consistency judging.

## Core Commands

### Development Setup
```bash
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env to add API keys
```

### Testing
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_agents/test_image_video_generation.py

# Run with verbose output and short traceback
python -m pytest tests/test_agents/test_image_video_generation.py -v --tb=short

# Run specific test class
python -m pytest tests/test_agents/test_image_video_generation.py::TestConcurrencyUtilities -v --tb=short

# Run async tests
python -m pytest tests/test_agents/test_script_parser.py -v
```

### Project Initialization
```bash
# Initialize project structure
python init_project.py

# Run example workflow
python examples/complete_workflow_example.py
```

### CLI Interface

**CLI Commands**:
```bash
# Create new project
python cli.py init my_drama

# Generate complete drama video
python cli.py generate projects/my_drama

# Validate project configuration
python cli.py validate projects/my_drama

# List all projects
python cli.py list

# Advanced options
python cli.py generate projects/my_drama --log-level DEBUG
python cli.py generate projects/my_drama --override video.fps=60
python cli.py generate projects/my_drama --resume  # Resume from checkpoint
python cli.py generate projects/my_drama --skip-characters  # Skip character reference generation
```

### Web Interface (Backend + Frontend)

**Backend (FastAPI)**:
```bash
# Run development server
cd backend
python run_dev.py

# Server will start at http://localhost:8000
# API docs: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

**Frontend (Next.js)**:
```bash
# Install dependencies
cd frontend
npm install

# Run development server
npm run dev
# Starts at http://localhost:3000

# Build for production
npm run build
npm start

# Type check
npm run type-check
```

### Code Quality
```bash
# Format code
black .

# Lint code
flake8

# Type check
mypy .
```

## System Architecture

### Dual Interface Architecture

The system operates with two distinct entry points that share the same core generation pipeline:

**CLI Path**: `cli.py` → `ProjectManager` → `ProjectRunner` → Agents
**Web Path**: Frontend → `FastAPI` → `WorkflowService` → `ProjectRunner` → Agents

Both paths converge at the agent layer, ensuring consistent video generation logic.

### Backend API Architecture (FastAPI)

**API Router Structure** (`backend/api/router.py`):
- **REST API v1** (`/api/v1/*`):
  - `/llm/*` - LLM services (script polishing, judging)
  - `/images/*` - Image generation endpoints
  - `/videos/*` - Video generation endpoints
  - `/tasks/*` - Async task management
  - `/workflow/*` - Complete workflow orchestration
  - `/projects/*` - Project CRUD operations

- **OpenAI-Compatible API** (`/v1/*`):
  - `/chat/completions` - Chat completion endpoint
  - `/images/generations` - Image generation endpoint
  - `/videos/generations` - Video generation endpoint

**Key Backend Services**:
1. **TaskManager** (`backend/core/task_manager.py`):
   - Async task submission and tracking
   - In-memory task storage with automatic cleanup
   - Status callback system for project synchronization
   - Semaphore-based concurrency control

2. **WorkflowService** (`backend/core/workflow_service.py`):
   - Bridges FastAPI and CLI-based generation logic
   - Creates temporary project structures for web-based workflows
   - Manages asset URL generation and storage
   - Progress callback translation

3. **ProjectManager** (`backend/core/project_manager.py`):
   - Project persistence and metadata management
   - Task-to-project synchronization
   - Status tracking and result aggregation

**Middleware**:
- CORS middleware for frontend communication
- Custom logging middleware
- Exception handlers for consistent error responses

### Frontend Architecture (Next.js)

**Tech Stack**:
- Next.js 14.2 (App Router)
- React 18.3
- TypeScript 5.3
- Tailwind CSS 3.4

**Key Pages**:
- `/` - Home page with project grid
- `/projects/new` - New project creation wizard
- `/projects/[projectId]` - Project detail view
- `/workflow/[projectId]` - Workflow execution page

**Component Structure**:
- Step-based workflow (Step0-Step5)
- Reusable UI components (`components/ui/*`)
- ModeSidebar for workflow type selection
- Real-time progress monitoring with LogViewer

**API Integration** (`lib/api.ts`):
- Centralized API client with fetch wrappers
- Type-safe request/response handling
- Error boundary integration

### Multi-Agent Video Generation Pipeline

The core video generation pipeline uses specialized agents that collaborate:

1. **DramaGenerationOrchestrator** (`agents/orchestrator_agent.py`) - Main coordinator that orchestrates the entire workflow
2. **ScriptParserAgent** (`agents/script_parser_agent.py`) - Parses text scripts into structured Scene objects
3. **ImageGenerationAgent** (`agents/image_generator_agent.py`) - Generates storyboard images using Nano Banana Pro API
4. **VideoGenerationAgent** (`agents/video_generator_agent.py`) - Converts images to video clips using Veo3 or Sora2 API (runtime selectable via VideoServiceFactory)
5. **VideoComposerAgent** (`agents/video_composer_agent.py`) - Composes final video with transitions, BGM, and effects

### Key Design Patterns

**BaseAgent Pattern** (`agents/base_agent.py`):
- All agents inherit from `BaseAgent` abstract class
- Required methods: `execute()`, `validate_input()`
- Built-in lifecycle hooks: `on_error()`, `on_complete()`
- State management via `AgentState` enum (IDLE, RUNNING, WAITING, COMPLETED, ERROR)

**Message Bus Communication** (`agents/base_agent.py:108-154`):
- Agents communicate via async message queue
- Message format: `AgentMessage` with sender_id, receiver_id, message_type, payload, correlation_id
- Subscribe/publish pattern for decoupled communication

**Workflow State Management** (`agents/base_agent.py:156-216`):
- State machine with valid transitions: INITIALIZED → PARSING_SCRIPT → GENERATING_IMAGES → GENERATING_VIDEOS → COMPOSING_VIDEO → POST_PROCESSING → COMPLETED
- Checkpoint support for resume capability
- Prevent invalid state transitions

**Error Handling Strategy** (`agents/base_agent.py:218-263`):
- Centralized `ErrorHandler` with registered exception handlers
- Retry configuration with exponential backoff
- Context-aware error logging

### Data Models

**Core Models** (`models/script_models.py`):
- `Script` - Top-level model containing characters and scenes
- `Scene` - Individual scene with location, time, shot_type, camera_movement, duration (1-10s)
- `Character` - Character definition with appearance details
- `Dialogue` - Dialog with character, content, emotion, voice_style

**Scene to Prompt Conversion** (`models/script_models.py:100-137`):
- `Scene.to_image_prompt()` generates AI-ready image prompts
- Combines location, time, weather, atmosphere, characters, action, shot_type, visual_style

**Shot Types & Camera Movements** (`models/script_models.py:9-27`):
- ShotType: CLOSE_UP, MEDIUM_SHOT, LONG_SHOT, EXTREME_CLOSE_UP, FULL_SHOT, OVER_SHOULDER
- CameraMovement: STATIC, PAN, TILT, ZOOM, DOLLY, TRACKING

### Service Layer

**Nano Banana Pro Service** (`services/nano_banana_service.py`):
- Async image generation API client
- Supports Base64 and file-based image storage
- Retry logic via `@async_retry` decorator

**Veo3 Service** (`services/veo3_service.py`):
- Async video generation API client
- Image upload and async task polling
- Maps camera movements to motion strength parameters

**Sora2 Service** (`services/sora2_service.py`):
- Async video generation API client (OpenAI format)
- Supports multiple resolutions and styles
- Character consistency via character_url parameter
- Storyboard mode for multi-shot videos
- Retry logic via `@async_retry` decorator

**Video Service Factory** (`services/video_service_factory.py`):
- Factory pattern for creating video services
- Runtime service selection based on config
- Config override support for custom parameters

**Configuration** (`config/settings.py`):
- Uses `pydantic-settings` for environment-based config
- Auto-loads from `.env` file
- Key settings: API keys, output_dir, temp_dir, max_concurrent_requests

### Utility Infrastructure

**Async Retry** (`utils/retry.py`):
- `@async_retry` decorator for automatic retry with exponential backoff
- Configurable max_attempts, backoff_factor, exception types
- Example: `@async_retry(max_attempts=3, backoff_factor=2.0)`

**Concurrency Control** (`utils/concurrency.py`):
- `ConcurrencyLimiter` - Semaphore-based concurrent task limiting
- `RateLimiter` - Token bucket rate limiting
- `ResultCache` - In-memory result caching

**Checkpoint Management** (`utils/checkpoint.py`):
- Save/load workflow state at each stage
- Resume from last successful checkpoint on failure
- Checkpoint stages: parsing, image_generation, video_generation, composition

**Progress Monitoring** (`utils/progress_monitor.py`):
- `ProgressMonitor` - Track completion percentage and ETA
- `ConsoleProgressMonitor` - Visual progress bar display
- Callbacks for real-time progress updates

**Task Queue** (`utils/task_queue.py`):
- Async task queue with worker pool
- Task submission, result retrieval, statistics tracking
- Supports timeout and graceful shutdown

**Video Processing** (`utils/video_utils.py`):
- FFmpeg wrapper for video operations
- Video concatenation, audio mixing, format conversion
- Transition effects (fade, crossfade)

## Important Implementation Details

### Orchestrator Progress Mapping
The orchestrator divides progress into stages:
- 0-10%: Script parsing
- 10-40%: Image generation
- 40-70%: Video generation
- 70-95%: Video composition
- 95-100%: Metadata saving

Sub-progress is mapped using `_create_sub_progress_callback()` to translate child task progress to overall progress.

### Concurrent Image/Video Generation
Both image and video agents support concurrent processing with configurable limits:
- Set via `max_concurrent` in config.yaml or settings.py
- Uses `asyncio.Semaphore` for concurrency control
- Progress callbacks track individual task completion
- **Candidate Generation**: When character consistency judging is enabled, multiple candidate images are generated concurrently using `asyncio.gather()`
- **Concurrent Judging**: LLM evaluation of candidates also runs concurrently, with all judge tasks executed in parallel
- Example: With `candidate_images_per_scene: 3`, all 3 candidates are generated simultaneously, then all 3 are judged simultaneously

### Character Consistency Judging

**LLM-Based Quality Scoring** (see `docs/CHARACTER_CONSISTENCY_JUDGING.md`):
- Generate N candidate images per scene (configurable: 1-5, recommended: 3-5)
- Use Judge LLM (e.g., Doubao multimodal) to score each candidate against character reference images
- Automatically select highest-scoring candidate for video generation
- Optionally save/delete non-selected candidates

**Configuration**:
```bash
# .env
ENABLE_CHARACTER_CONSISTENCY_JUDGE=true
CANDIDATE_IMAGES_PER_SCENE=3
JUDGE_LLM_API_KEY=your_judge_api_key
JUDGE_LLM_MODEL=doubao-seed-1-6-251015
JUDGE_TEMPERATURE=0.3
```

**Judge LLM API Requirements**:
- Must support multimodal input (image + text)
- Currently supports 火山引擎方舟 API (Volcano Engine Ark)
- API format: Responses API with `input_image` and `input_text` content types

### Script Parsing Format
Expected script format (see `examples/sample_scripts/programmer_day.txt`):
```
标题: [Title]

场景1: [Location] - [Time]
[Shot type indication]
[Description and action]
[Character]: "[Dialogue]"
```

### API Integration Points
- **Nano Banana Pro**: Synchronous polling for image generation completion
- **Veo3**: Async task submission + polling for video generation status (default service)
- **Sora2**: Async task submission + polling for video generation status (alternative service, OpenAI format)
- All services implement retry logic for transient failures

### Testing Strategy
- Use `pytest.fixture` for reusable test data (e.g., `sample_scenes`)
- Use `@pytest.mark.asyncio` for async tests
- Mock external API calls with `unittest.mock.AsyncMock`
- Integration tests in `tests/test_integration/`
- Performance benchmarks in `tests/test_performance/`

## Development Guidelines

### Agent Implementation
When creating new agents:
1. Inherit from `BaseAgent`
2. Implement `execute(input_data)` - core processing logic
3. Implement `validate_input(input_data)` - input validation
4. Call `await self.on_error(e)` and `await self.on_complete(result)` appropriately
5. Update state via `self.state = AgentState.RUNNING`

### Error Handling
- Use `@async_retry` decorator for API calls
- Register custom error handlers with `ErrorHandler.register_handler()`
- Include context dict when calling `error_handler.handle_error(e, context)`
- Log errors with correlation_id for request tracing

**Enhanced Error Handling (2025-01)**:
- API services (Nano Banana Pro, Veo3, Sora2) capture complete error responses
- `ServiceException` includes: error_code, error_type, stage, api_response, retryable flag
- Task manager preserves full error context including traceback and service details
- Frontend displays detailed error information with expandable details section
- Errors show: service name, stage, error type, API error code, retryability, full API response
- Backend exceptions are properly propagated through task manager to frontend
- Custom exception classes in `backend/core/exceptions.py`:
  - `TaskNotFoundException` - Task ID not found
  - `TaskCancelledException` - Task was cancelled
  - `StorageException` - Storage operation failed
  - `ServiceException` - External service error (contains full API response)

### Resource Management
- Always call `await agent.close()` to cleanup resources
- Use `async with` context managers where possible
- Clear checkpoints after successful completion
- Clean up temp files in output/temp directories

### Configuration
- Never commit API keys - use `.env` file
- Access config via `config.settings` singleton
- Override config per-agent via constructor `config` parameter
- Use `Optional[str]` for optional API keys (e.g., openai_api_key)
- Backend config loaded via `backend/config.py` using Pydantic settings
- Frontend uses environment variables via Next.js `.env.local`

### Runtime Settings Center (2026-10)
Users configure text/voice/video/image/agent model services at runtime via the
`/settings` page; changes persist to `backend/data/model_settings.json` (git-ignored,
contains REAL keys; API reads return masked keys) and are HOT-APPLIED to both the
`backend.config.settings` and root `config.settings` singletons, then cached service
wrappers are reset (`backend/core/service_wrapper.py::reset_runtime_services`).
- `backend/core/settings_store.py` - ModelSettingsStore (persist/mask/apply/reload)
- `backend/core/settings_models.py` - five-category Pydantic models; `api_key` is
  write-only: absent/null = keep, `""` = clear, string = replace
- `backend/api/v1/settings.py` - GET/PUT `/api/v1/settings`, POST `.../test/{category}`
  (text|voice|video|image|agent), GET `.../agent/status`, POST `.../agent/chat` (SSE)
- `services/tts_service.py` + `backend/api/v1/tts.py` - OpenAI-compatible TTS
  (`/audio/speech`), `POST /api/v1/tts/generate` returns raw audio bytes
- Agent-assisted configuration is powered by AragonAgent
  (https://github.com/xdrshjr/AragonAgent): `backend/core/agent_assist.py` spawns
  `aragon exec --output-format stream-json --permission-mode strict --allow-tool
  read_file,write_file,edit_file,list_dir,glob,grep` with the user-configured agent
  LLM mapped to `ARAGON_PROVIDER/ARAGON_MODEL/ARAGON_BASE_URL` + provider key env.
  The agent edits the settings file; the backend re-validates + hot-reloads it after
  each turn and emits `settings_updated`. Without the aragon CLI it degrades to a
  single-shot LLM advice mode that returns a JSON patch the UI can apply.
- Frontend: `frontend/src/app/settings/page.tsx`, `components/settings/*`,
  SSE client in `lib/api.ts` (`apiClient.settings.chat`). Note: the seven previously
  missing `lib/` modules (api/types/logger/videoTypes/imageHelpers/yamlParser/
  yamlValidator) were reconstructed from their call sites - the frontend now builds.
- Tests: `tests/test_backend/` (store persistence/masking/hot-apply, API semantics,
  agent event parsing + fallback, TTS client) - run with
  `python -m pytest tests/test_backend -v`
- Docs: `docs/SETTINGS_AND_AGENT.md`

### Backend Development Notes

**Path Management**:
- Backend adds parent directory to `sys.path` to import CLI modules
- Temporary projects stored in `backend/temp_projects/workflow_*`
- Permanent projects stored in `backend/projects/`
- Assets managed via `AssetManager` (`backend/utils/asset_manager.py`)

**Task Lifecycle**:
1. Frontend submits workflow request to `/api/v1/workflow/execute`
2. WorkflowService creates temp project and invokes ProjectRunner
3. TaskManager tracks progress via status callbacks
4. ProjectManager syncs task status back to project metadata
5. Frontend polls `/api/v1/tasks/{task_id}` for progress updates

**Async Patterns**:
- All service methods are `async def`
- Use `asyncio.gather()` for parallel operations
- Use `asyncio.Semaphore` for rate limiting
- TaskManager provides callback registration for status updates

**Logging**:
- Structured logging via `loguru` in CLI
- Custom logger setup in `backend/utils/logger.py`
- Request/response logging via middleware
- Log helpers in `backend/utils/log_helpers.py` truncate sensitive data (base64 images)

### Frontend Development Notes

**State Management**:
- No Redux/Zustand - uses React state and URL params
- Project state stored in backend, fetched on page load
- Real-time progress via polling (not WebSockets)

**Routing**:
- App Router (Next.js 14+) with TypeScript
- Dynamic routes: `[projectId]` for project-specific pages
- Server components for static content, client components for interactivity

**API Calls**:
- Centralized in `lib/api.ts`
- Type definitions in `lib/types.ts` and `lib/types/*.ts`
- Error handling with try-catch and user-friendly messages

**Styling**:
- Tailwind CSS with custom Apple-inspired design
- Component library in `components/ui/*`
- Responsive design with mobile-first approach

## Project Status

Current development status (see 开发计划.md):
- ✅ TODO 1: Environment setup and base architecture
- ✅ TODO 2: Script parsing and data models
- ✅ TODO 3: Image and video generation modules
- ✅ TODO 4: Video composition and post-processing
- ✅ TODO 5: Testing, deployment, and documentation

Key files demonstrate working implementation:
- `examples/complete_workflow_example.py` - Full workflow examples
- `agents/orchestrator_agent.py` - Main orchestration logic
- `models/script_models.py` - Complete data model with validation

## External Dependencies

### Required System Dependencies
- **Python 3.9+**
- **Node.js 18.0+** and **npm 9.0+** (for frontend)
- **FFmpeg 4.0+** - Must be installed separately and available in PATH

### Python Packages (requirements.txt)
- `pydantic` 2.5.0 - Data validation
- `httpx` 0.25.2 - HTTP client for API calls
- `aiohttp` 3.9.1 - Async HTTP operations
- `moviepy` >=2.0.0 - Video editing
- `loguru` 0.7.2 - Advanced logging
- `pytest` 7.4.3 + `pytest-asyncio` 0.21.1 - Testing
- `fastapi` + `uvicorn` - Web API framework (backend)

### Frontend Packages (frontend/package.json)
- `next` 14.2.0 - React framework
- `react` 18.3.0 + `react-dom` - UI library
- `typescript` 5.3.0 - Type safety
- `tailwindcss` 3.4.1 - Styling framework
- `js-yaml` 4.1.0 - YAML parsing

### External API Services
- **Nano Banana Pro** - Image generation (requires API key in `NANO_BANANA_API_KEY`)
- **Veo3** - Video generation (default, requires API key in `VEO3_API_KEY`)
- **Sora2** - Video generation (alternative, requires API key in `SORA2_API_KEY`)
  - OpenAI format API
  - Supports styles: anime, comic, nostalgic, thanksgiving, news, selfie
  - Supports character consistency via character_url
  - Duration constraints: 4, 8, 12 seconds (basic mode); 10, 15, 25 seconds (storyboard mode)
  - Service selection via `VIDEO_SERVICE_TYPE` env var or project config
- **Doubao / 火山引擎方舟** - Optional LLM services:
  - Script polishing (`DOUBAO_API_KEY`)
  - Character consistency judging (`JUDGE_LLM_API_KEY`)
- **Midjourney** - Optional alternative image service (see `docs/midjourney_integration.md`)

## File Structure Highlights

```
ai-movie-agent-guide/
├── cli.py                      # CLI entry point
├── init_project.py             # Project initialization script
├── requirements.txt            # Python dependencies
│
├── agents/                     # Core agent implementations
│   ├── base_agent.py           # BaseAgent + MessageBus + WorkflowStateManager + ErrorHandler
│   ├── orchestrator_agent.py   # Main coordinator with SimpleDramaGenerator
│   ├── script_parser_agent.py
│   ├── image_generator_agent.py
│   ├── video_generator_agent.py
│   └── video_composer_agent.py
│
├── backend/                    # FastAPI web backend
│   ├── main.py                 # FastAPI app initialization
│   ├── run_dev.py              # Development server runner
│   ├── config.py               # Pydantic settings
│   │
│   ├── api/                    # API routes
│   │   ├── router.py           # Main router combining v1 and OpenAI APIs
│   │   ├── v1/                 # REST API v1
│   │   │   ├── llm.py
│   │   │   ├── images.py
│   │   │   ├── videos.py
│   │   │   ├── tasks.py
│   │   │   └── workflow.py
│   │   ├── openai/             # OpenAI-compatible endpoints
│   │   │   ├── chat.py
│   │   │   ├── images.py
│   │   │   └── videos.py
│   │   └── routes/
│   │       └── projects.py     # Project CRUD
│   │
│   ├── core/                   # Core backend services
│   │   ├── task_manager.py     # Async task execution and tracking
│   │   ├── workflow_service.py # Bridges FastAPI and CLI generation
│   │   ├── project_manager.py  # Project persistence
│   │   ├── models.py           # Pydantic models for API
│   │   └── exceptions.py       # Custom exception classes
│   │
│   ├── middleware/             # FastAPI middleware
│   │   ├── logging.py
│   │   └── error_handler.py
│   │
│   └── utils/                  # Backend utilities
│       ├── logger.py
│       ├── asset_manager.py
│       └── log_helpers.py
│
├── frontend/                   # Next.js web frontend
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   │
│   └── src/
│       ├── app/                # App Router pages
│       │   ├── page.tsx        # Home page
│       │   ├── layout.tsx      # Root layout
│       │   ├── projects/
│       │   │   ├── new/page.tsx
│       │   │   └── [projectId]/page.tsx
│       │   └── workflow/
│       │       └── [projectId]/page.tsx
│       │
│       ├── components/         # React components
│       │   ├── steps/          # Step-based workflow components
│       │   └── ui/             # Reusable UI components
│       │
│       └── lib/                # Utilities and types
│           ├── api.ts          # API client
│           ├── types.ts        # TypeScript type definitions
│           └── types/          # Additional type definitions
│
├── models/                     # Data models
│   ├── script_models.py        # Script, Scene, Character, Dialogue models
│   └── config_models.py        # Configuration models
│
├── services/                   # External API wrappers
│   ├── nano_banana_service.py
│   ├── veo3_service.py
│   ├── sora2_service.py
│   ├── video_service_factory.py
│   └── doubao_service.py
│
├── utils/                      # Shared utilities (CLI)
│   ├── retry.py                # @async_retry decorator
│   ├── concurrency.py          # ConcurrencyLimiter, RateLimiter, ResultCache
│   ├── checkpoint.py           # CheckpointManager
│   ├── progress_monitor.py     # Progress tracking
│   ├── task_queue.py           # Async task queue
│   └── video_utils.py          # FFmpeg wrapper
│
├── config/                     # Configuration (CLI)
│   └── settings.py             # Pydantic settings (loads from .env)
│
├── core/                       # Core modules (CLI)
│   ├── project_manager.py      # CLI project manager
│   ├── config_loader.py        # YAML config loader
│   ├── runner.py               # Project execution runner
│   ├── validators.py           # Validation logic
│   └── errors.py               # Error definitions
│
├── projects/                   # User projects (CLI)
│   └── [project_name]/
│       ├── config.yaml
│       ├── script.txt
│       ├── characters/
│       └── outputs/
│
├── examples/                   # Example code
│   ├── complete_workflow_example.py
│   └── sample_scripts/
│
├── tests/                      # Test suite
│   ├── test_agents/
│   ├── test_services/
│   ├── test_integration/
│   └── test_performance/
│
└── docs/                       # Documentation
    ├── CHARACTER_CONSISTENCY_JUDGING.md
    ├── MIDJOURNEY_INTEGRATION_STATUS.md
    └── ...
```

## Project Index

This project has a pre-generated index for quick codebase understanding.

- **Location:** `.claude-index/index.md`
- **Last Updated:** 2026-10-10
- **Contents:** Project overview, feature map, file index, exported symbols, module dependencies

**Usage:** Read `.claude-index/index.md` to quickly understand the project structure before making changes. The index provides a navigation map of the codebase without needing to explore every file.

**Regenerate:** Say "regenerate index" or "更新索引" to update the index after major changes.

## Clean Code Guidelines

<!-- project-indexer:cleancode:begin v1.1.0 -->
> 本节由 `project-indexer` 自动维护，灵感取自谷歌风格，并按本项目主要语言收敛阈值。请勿手工编辑 markers 之间的内容，需要刷新时请运行「regenerate index」。

### 一、概述

本节是本项目在使用 AI 辅助开发时必须遵守的代码规范。在写或改动任何代码之前，先把下列条目读完一遍，再动键盘。规则的目的不是束缚发挥，而是让人类与 agent 写出的代码在阈值上保持可比的下限，避免出现千行文件与几百行方法，避免命名混乱、错误吞咽、测试缺失这些会在后续维护中迅速发酵的问题。所有阈值都允许根据项目实际情况调整，但调整必须在 `.claude-index/config.md` 中显式记录，并在评审中说明理由，不要靠默认值偷偷放宽。

### 二、文件与函数尺寸

- 单文件不超过 **800** 行，超过即按职责拆分到新模块。
- 单方法不超过 **50** 行，写到一半感觉膨胀就先抽函数。
- 函数形参不超过 **5** 个，多了请改用配置对象、命名参数或聚合结构体，禁止靠位置堆参数。
- 圈复杂度不超过 **10**，分支累积过多必须拆函数或引入查找表。
- 单行长度不超过 **80** 列，超长就换行或抽变量名。判定标准很简单：阈值超了就是技术债，提交前自查并修正。

### 三、命名

- 函数以动词开头表达动作，例如 `loadConfig`、`parseToken`；查询类用名词或 `get` / `find`。
- 返回布尔值的函数与变量以 `is`、`has`、`should`、`can` 起头，便于阅读条件表达式。
- 常量使用大写蛇形，模块名短小且语义化，避免堆叠首字母缩写。
- 不缩写领域词，宁可名字长五个字母也要让读者一眼看懂含义。
- 类与接口使用大驼峰命名，方法与变量使用小驼峰或语言推荐的蛇形写法，保持整个仓库风格一致。
- 避免使用 `data`、`info`、`temp`、`obj` 这类无信息量的名字；给出具体的领域名词。

### 四、注释与文档

- 注释只解释「为什么」，不复述「做什么」，代码本身就是「做什么」的真相。
- 所有公开 API 必须写 docstring，标注参数、返回值与可能抛出的异常。
- 删除一切僵尸注释与被注释掉的旧代码；保留 `TODO` 必须带责任人与日期。
- 行级注释稀缺即珍贵，不要在每行上方堆一句无信息量的话。
- 复杂业务规则、踩坑记录、临时性 workaround 必须在注释中写清楚原因与可回退条件。

### 五、错误处理

- 错误显式传播，不要默默吞异常或返回 `null` 假装一切正常。
- 外部输入在边界处一次性校验，进入内部后信任内部数据，禁止层层重复校验。
- 不要为「理论上不会发生」的分支写防御性 `try/except`，那只是噪音。
- 错误信息必须包含定位线索：发生在哪、关键参数是什么、下游应如何处理。
- 在 IO、网络、子进程等不可控边界，使用带超时与重试的结构化封装，而非裸调用。
- 捕获异常时尽量缩小作用域，只处理你确实有办法应对的错误类型，其他原样向上抛出。
- 对外暴露的错误码或异常类必须稳定，更名等同于破坏性变更，需要在变更日志中显式标注。

### 六、复杂度与嵌套

- 嵌套深度不超过 **4** 层，深嵌套是函数过长的前兆。
- 优先使用早返回（guard clause）取代 `else` 阶梯。
- 单个表达式里出现超过三个布尔条件，立刻抽成命名清晰的辅助函数。
- 循环里若出现复杂条件分支，改写为查找表或策略对象往往更易读。
- 一个函数只做一件事；当解释函数职责时需要用「并」「同时」「再」这类连词，就是应该拆分的信号。

### 七、测试

- 修 bug 必须先写一个能稳定复现该 bug 的测试用例，再动业务代码。
- 公开行为都要有单元测试覆盖正常路径与至少一条异常路径。
- 测试名描述被验证的行为而非实现细节，例如 `rejects_expired_token`。
- 不允许 mock 数据库迁移、鉴权签名等高风险路径，必须使用真实集成测试。
- 单测应快速且可重复运行；外部依赖通过桩或本地容器隔离，禁止依赖共享环境状态。
- 任何被发现的回归 bug 都要补上对应的测试，把过去的坑变成未来的护栏。

### 八、代码评审清单

提交前对照以下 8 条自查，任何一条不满足都视为未完成：

1. 命名是否自解释，是否避免无意义缩写。
2. 文件、方法、参数、嵌套、圈复杂度是否都在阈值内。
3. 错误是否显式传播，边界校验是否到位。
4. 注释是否只解释「为什么」，是否还有僵尸代码或孤儿 TODO。
5. 测试是否覆盖正常路径与异常路径，是否能稳定复现已修复的 bug。
6. 是否引入新依赖，依赖是否必要、是否有安全或许可证风险。
7. 是否泄露密钥、个人数据、内部链接等敏感信息。
8. 是否与现有架构与命名风格一致，是否制造新的孤岛。

### 九、语言特有提示

当前项目主要语言：**Python, TypeScript**。

- Python: PEP 8 + Google docstrings.
- TypeScript: Prefer `interface` over `type` for public APIs.

### 十、元信息

模板版本与上方 markers 中的版本一致。说「regenerate index」或「更新索引」可重新生成本节内容；说「disable cleancode」可移除本节。
<!-- project-indexer:cleancode:end -->
