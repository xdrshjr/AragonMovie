# 设置中心与 Agent 协助配置

> 本文档介绍 AragonMovie 的运行时"模型配置中心"：用户可以在 Web 设置页
> **随时**配置 文字 / 语音 / 视频 / 图像 / Agent 五类模型服务的 URL、API Key、
> 模型名等参数，保存后**即时生效（无需重启后端）**；并支持基于
> [AragonAgent](https://github.com/xdrshjr/AragonAgent) 的 **AI 配置助手**，
> 通过对话让 Agent 直接帮你完成配置。

## 总览

```
前端 /settings 页面
   │  (REST + SSE)
   ▼
后端 /api/v1/settings*
   │
   ├─ SettingsStore ──► backend/data/model_settings.json（持久化，含真实 Key）
   │       │
   │       └─ apply_to_runtime()：写入 backend.config.settings + config.settings
   │           两个单例，并失效 service_wrapper 缓存 → 新请求即用新配置
   │
   └─ AgentAssist ──► aragon exec 子进程（stream-json / strict 工具白名单）
           │            │
           │            └─ 编辑 model_settings.json → 后端检测变更 → 热加载
           └─ 未安装 aragon 时：LLM 降级（单轮建议 + JSON 补丁，用户一键应用）
```

## 配置层级

1. **`.env` 提供默认值**（pydantic-settings 启动时加载，行为与之前完全一致）。
2. **`backend/data/model_settings.json` 提供运行时覆盖**（设置页或 Agent 写入），
   启动时与每次更新后热应用到全局。
3. 该文件**包含明文 API Key**，已被 `.gitignore` 排除（`backend/data/`），
   请勿提交或外传；读取接口一律返回掩码（`sk-1****wxyz`）。

## 五类服务

| 类别 | 服务 | 关键字段 |
| --- | --- | --- |
| 文字 | 快速 LLM（剧本润色/提示词优化）、评审 LLM（多模态一致性评分） | api_url / api_key / model + 启用开关 |
| 语音 | TTS（OpenAI 兼容 `/audio/speech`） | base_url / api_key / model / 音色 / 格式 / 语速 |
| 视频 | Veo3、Sora2（运行时可切换） | base_url / endpoint / api_key / model + 各自默认参数 |
| 图像 | 豆包、Nano Banana、Midjourney（运行时可切换） | base_url / endpoint / api_key / model |
| Agent | 驱动 AI 配置助手的大模型 | provider / base_url / api_key / model / aragon CLI 路径 |

## REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/settings` | 全量设置（Key 已掩码） |
| PUT | `/api/v1/settings` | 部分更新，持久化 + 热生效 |
| POST | `/api/v1/settings/test/{category}` | 连接测试（text/voice/video/image/agent） |
| GET | `/api/v1/settings/agent/status` | aragon CLI 检测 + 助手模式 |
| POST | `/api/v1/settings/agent/chat` | AI 配置助手（SSE 流式） |
| POST | `/api/v1/tts/generate` | 语音合成（返回音频字节） |

### Write-only Key 语义

`PUT` 请求中每个 `api_key` 字段：

- **省略 / null** → 保留已保存的 Key（默认行为，前端只在用户输入新值时才发送）；
- **空字符串 `""`** → 清除该 Key；
- **其他字符串** → 替换为新 Key。

前端回显掩码值（如 `sk-1****wxyz`）仅作提示，原样回传也会被识别为"未修改"。

### 连接测试语义

- `verified: "full"`：发起了真实请求并成功（LLM 小对话、TTS 短合成）。
- `verified: "partial"`：仅验证可达性 / 认证未被拒绝（多数视频、图像网关
  没有廉价的探测端点，结果会明确标注"部分验证"，不冒充已验证生成）。

## Agent 协助配置（基于 AragonAgent）

### 模式

| 模式 | 条件 | 能力 |
| --- | --- | --- |
| `aragon`（主模式） | 已安装 aragon CLI 且已配置 Agent 大模型 | 助手拥有文件工具（read_file / write_file / edit_file / list_dir / glob / grep），可直接读写 `backend/data/model_settings.json` 完成配置 |
| `llm_fallback`（降级） | 未安装 aragon，但 Agent 提供方为 OpenAI 兼容 | 单轮对话给建议，并输出 JSON 补丁，前端提供"应用建议配置"一键应用 |
| `unavailable` | 未配置 Agent 大模型 | 提示先在 Agent 页配置 |

### 安装 AragonAgent（解锁主模式）

```bash
# 需要 Node.js >= 18
npm i -g @aragon-agent/cli
aragon --version   # 验证
```

也可在设置页 Agent 标签中指定 `aragon` CLI 的自定义路径。

### 安全边界

- 子进程以 `--permission-mode strict --allow-tool read_file,write_file,edit_file,list_dir,glob,grep`
  运行：**没有 bash**，不能执行任意命令；
- 系统提示词约束其只允许修改 `model_settings.json` 一个文件；
- 每轮结束后后端重新校验该文件（JSON Schema 校验失败则拒绝应用并保留旧配置），
  校验通过则热加载并向前端推送 `settings_updated` 事件刷新表单；
- 会话（`--session-id` / `--resume`）支持多轮连续对话；超时与取消会终止子进程。

### SSE 事件流（POST /api/v1/settings/agent/chat）

`data:` 行内为 JSON，`[DONE]` 结束。事件类型：`meta`（会话/模式）、`status`（提示）、
`system`（aragon init）、`text_delta`（流式回答）、`tool_call` / `tool_result`（工具卡片）、
`assistant`（整轮回答）、`result`（含 `suggested_patch`，降级模式）、`settings_updated`
（助手改了配置）、`error`。未知事件类型请忽略——这是前向兼容契约。

## 前端

- 入口：页面右上角齿轮图标 → `/settings`；
- 五个标签页对应五类服务；每个服务一张卡片（URL / Key / 模型 + 测试连接 + 状态徽标）；
- 保存仅提交该类别；保存后提示"即时生效"；
- Agent 标签页内置聊天面板：流式回答、工具调用卡片、`settings_updated` 自动刷新、
  降级模式的"应用建议配置"按钮、aragon 未安装时的安装引导。

## 相关代码

| 位置 | 说明 |
| --- | --- |
| `backend/core/settings_models.py` | 五类设置的 Pydantic 模型（含 write-only 语义） |
| `backend/core/settings_store.py` | 持久化 + 双单例热应用 + 掩码 + 外部变更重载 |
| `backend/core/settings_tester.py` | 五类连接测试器 |
| `backend/core/agent_assist.py` | aragon exec 运行器 + LLM 降级 + 会话/事件流 |
| `backend/api/v1/settings.py` | Settings REST + SSE 端点 |
| `backend/api/v1/tts.py`、`services/tts_service.py` | TTS 服务与 API |
| `backend/core/service_wrapper.py` | `reset_runtime_services()` 热重建 |
| `frontend/src/app/settings/page.tsx` | 设置中心页面 |
| `frontend/src/components/settings/*` | ProviderCard、SettingsChatPanel |
| `frontend/src/lib/api.ts` | apiClient（含 settings API 与 SSE 客户端） |

## 测试

```bash
python -m pytest tests/test_backend -v
# 45 个用例：store 持久化/掩码/热应用、API 语义、agent 事件解析/降级、TTS 客户端
```
