# Index Configuration

## Excluded Directories
- node_modules
- .git
- dist
- build
- __pycache__
- .venv
- venv
- vendor
- coverage
- .next
- .nuxt
- .cache
- target
- bin
- obj
- output
- logs
- .pytest_cache

## Priority Directories
- agents/
- backend/
- frontend/src/
- services/
- core/
- utils/
- models/

## Tech Stack
- Frontend: Next.js 14.2 (App Router) + React 18.3 + TypeScript 5.3 + Tailwind CSS 3.4 + js-yaml
- Backend: FastAPI + Uvicorn (backend/) plus Python CLI pipeline (repo root)
- Language: Python (~55%, 146 files), TypeScript/TSX (~18%, 47 files)
- Default model provider: Ali Token Plan / DashScope (`ali_token_plan`) for text, image and video
- Tests: pytest + pytest-asyncio (unit/integration), Playwright + pytest-playwright (tests/e2e)

## Index Settings
- Generated: 2026-10-20
- Project Root: E:\TAKO-PROJECTS\AragonMovie
- Index Version: 1.0
- Environments Configured: No
- Source Commit: 2bbe4dd (2026-10-20)

## Clean Code Settings
- Enabled: Yes
- Preset: strict
- MAX_FILE_LINES: 800
- MAX_METHOD_LINES: 50
- MAX_FUNCTION_PARAMS: 5
- MAX_CYCLOMATIC: 10
- MAX_LINE_LENGTH: 80
- MAX_NESTING_DEPTH: 4
