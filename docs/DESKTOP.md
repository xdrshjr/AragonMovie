# AragonMovie 桌面端（Electron）

把现有的「Python 多智能体生成管线 + FastAPI 后端 + Next.js 前端」封装成一个**免安装环境**的
Windows 桌面应用：用户机器上不需要 Python、Node.js 或 ffmpeg。

- 首次启动：引导用户填写 LLM / 图像 / 视频 / 语音凭证，并**逐项真实连接测试**
- 之后启动：读取本机已保存的配置，**直接进入工作台**
- 视觉：全局灰黑色系（near-black 画布 + 发丝边框 + 克制的靛蓝强调色）

---

## 1. 架构

```
┌────────────────────────── AragonMovie.exe (Electron) ──────────────────────────┐
│  main 进程  src/main.js                                                        │
│   ├─ 启动/守护子进程（services.js）：动态分配回环端口，崩溃即上报                │
│   ├─ 首启动判定（desktop-state.json + /api/v1/settings 的凭证完整性）           │
│   └─ 窗口：splash → setup(首次) / main(产品 UI)                                 │
│                                                                                │
│  renderer                                                                      │
│   ├─ ui/splash.html        启动进度 / 失败重试                                  │
│   ├─ ui/setup.html|.css|.js  首次运行配置向导（IPC 调后端，渲染层不直连网络）     │
│   └─ http://127.0.0.1:<web>  Next.js 14 standalone 产品界面                     │
│        └─ window.aragonDesktop.apiBase ← preload 注入的运行时后端地址           │
└────────────────────────────────────────────────────────────────────────────────┘
        │ spawn                                        │ spawn (ELECTRON_RUN_AS_NODE)
        ▼                                              ▼
resources/python/python.exe -m uvicorn          node server.js（Next standalone）
  backend.main:app（便携 CPython 3.12）           端口动态分配
  PATH 前置 resources/app/bin（ffmpeg/ffprobe）
  IMAGEIO_FFMPEG_EXE → resources/app/bin/ffmpeg.exe
```

关键点：

| 关注点 | 做法 |
| --- | --- |
| 免依赖 | `build/desktop/build-python-runtime.ps1` 生成便携 CPython 3.12（embeddable）＋ 从 venv 精简出的 site-packages |
| 前端托管 | `next build` 的 `output: 'standalone'` 产物由 Electron 自带 Node 运行，无需安装 Node |
| 端口冲突 | 两个服务都用 `127.0.0.1` + 系统分配的空闲端口；后端地址通过 preload 注入，前端运行时解析（`frontend/src/lib/api.ts#getApiBase`） |
| 媒体处理 | 打包 ffmpeg 8.1.1 / ffprobe；同时删除 `imageio_ffmpeg` 自带的重复 ffmpeg（省 ~84 MB），通过 `IMAGEIO_FFMPEG_EXE` 指向同一份 |
| 凭证安全 | 只通过 IPC 走后端 API；密钥落盘在用户目录的 `backend/data/model_settings.json`（后端写只读语义、UI 永远只拿到掩码） |
| 生命周期 | 退出/崩溃时 `taskkill /T` 结束整棵子进程树；单实例锁；`before-quit` 清理 |

---

## 2. 首次启动体验

1. **Splash**（无边框深色窗口）：工作区准备 → 本地生成服务 → 界面服务 → 就绪；失败时显示原因、日志入口与「重试」。
2. **配置向导**（左栏 4 步 + 完成页）：
   - **LLM 文本模型**：常用服务商预设（阿里云 Token Plan / DashScope / DeepSeek / OpenAI / SiliconFlow）、评审模型是否复用同一凭证；若 Base URL 是阿里云网关，可勾选「同一 Key 同时用于图像与视频生成」。
   - **图像生成**：阿里云 Token Plan / 豆包 Seedream / Nano Banana Pro / Midjourney，高级参数（Base URL、Endpoint、水印等）折叠。
   - **视频生成**：阿里云 Token Plan / Veo 3 / Sora 2。
   - **语音合成**（可选）：自动识别 / OpenAI 兼容 / DashScope 原生，附 Token Plan 网关无 HTTP 合成接口的说明。
3. 每一步都可以 **保存并测试**：先 `PUT /api/v1/settings`，再 `POST /api/v1/settings/test/{category}`，逐 target 展示成功/失败、延迟、真实请求 or 仅鉴权、以及可展开的错误详情。
4. **完成页**：四项服务状态汇总 + 「全部测试」；必需凭证齐全后「进入工作台」；点击后写入 `desktop-state.json` 并打开产品窗口。

已保存的密钥会以 `sk-s****vtig` 形式回显为占位符：留空 = 保持不变，输入 = 覆盖（后端 write-only 语义）。

## 3. 后续启动

启动时判定「已配置」= `desktop-state.json` 里有 `onboardedAt`，且后端设置中 LLM / 图像 / 视频（以及启用时的语音）都已存在密钥。
满足则**跳过向导直接进入产品界面**；任意一项缺失（例如换了服务商但没填 Key）会重新打开向导，并自动定位到缺失的那一步。

菜单「应用 → 重新运行初始配置…」可随时回到向导（会预填已保存的配置）。

---

## 4. 开发

```bat
cd desktop
npm install
npm run build:app      :: 复制 Python 管线到 build\desktop\app（不含 .env / 用户数据）
npm run build:web      :: next build + 组装 standalone 到 build\desktop\web
npm run build:python   :: 生成便携 CPython + 打包 ffmpeg/ffprobe
npm start              :: 用 venv python + build\desktop\web 启动桌面端
```

`desktop\scripts\run-dev.ps1` 是更完整的开发启动器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File desktop\scripts\run-dev.ps1
powershell ... -Clean               # 清空工作区与 %APPDATA%\AragonMovie，模拟首次启动
powershell ... -ScrubCredentials    # 清掉构建机上全局导出的 *_API_KEY，模拟真实用户环境
```

可用环境变量（`desktop/src/paths.js`）：

| 变量 | 作用 |
| --- | --- |
| `ARAGON_PYTHON` | 指定 Python 解释器 |
| `ARAGON_APP_SOURCE` / `ARAGON_APP_HOME` | Python 管线源码目录 / 运行目录 |
| `ARAGON_WEB_SOURCE` / `ARAGON_WEB_HOME` | 前端产物目录 / 运行目录 |
| `ARAGON_FFMPEG_DIR` | ffmpeg/ffprobe 所在目录 |
| `ARAGON_BACKEND_URL` / `ARAGON_WEB_URL` | 直接复用已在运行的服务（跳过 spawn） |

端到端验证（需要应用以 `--remote-debugging-port=9222` 启动）：

```bat
venv\Scripts\python.exe desktop\tests\e2e_wizard.py first-run
venv\Scripts\python.exe desktop\tests\e2e_wizard.py relaunch
```

截图写入 `%APPDATA%\AragonMovie\captures\`（由 Electron `capturePage` 生成，避免无显示环境下 CDP 截图卡死）。

## 5. 打包

```bat
cd desktop
npm run build:all      :: app + web + python 运行时
node scripts\dist.js   :: electron-builder → release\AragonMovie-<version>-Setup.exe
node scripts\dist.js --dir        :: 只出 win-unpacked（快速冒烟）
node scripts\dist.js --portable   :: 额外产出绿色版
node scripts\dist.js --skip-web --skip-python  :: 复用已有构建产物
```

产物：`desktop\release\AragonMovie-1.0.0-Setup.exe`（NSIS，按用户安装，无需管理员；可选安装目录；创建桌面/开始菜单快捷方式）。

安装包体积主要来自：便携 CPython + 依赖（~145 MB）、ffmpeg + ffprobe（~190 MB）、Electron（~200 MB）、Next standalone（~20 MB）。

## 6. 数据与日志

| 内容 | 路径 |
| --- | --- |
| 桌面端状态（是否完成引导） | `%APPDATA%\AragonMovie\desktop-state.json` |
| 凭证与模型配置（明文 JSON） | `%APPDATA%\AragonMovie\workspace\app\backend\data\model_settings.json` |
| 项目 / 临时工程 / 输出 | `%APPDATA%\AragonMovie\workspace\app\{backend\projects,backend\temp_projects,output}` |
| 日志 | `%APPDATA%\AragonMovie\logs\{desktop,backend,web}.log` |
| 验证截图 | `%APPDATA%\AragonMovie\captures\` |

「应用」菜单可以直接打开数据目录、日志目录和配置文件。删除 `%APPDATA%\AragonMovie` 即可恢复出厂状态。

## 7. 故障排查

| 现象 | 处理 |
| --- | --- |
| Splash 停在「本地生成服务」 | 看 `logs\backend.log`；多为杀毒软件拦截便携 Python 或端口被占用（会自动换端口，不需要手动改） |
| 界面空白 / 报 `NEXT` 错误 | 看 `logs\web.log`；确认 `build\desktop\web\server.js` 存在（重新 `npm run build:web`） |
| 连接测试 401 / 403 | Key 与服务商不匹配；语音若用 Token Plan 的 Key，需切到 DashScope 原生并填百炼 Key |
| 打包时报缺少 ffmpeg | `winget install --id Gyan.FFmpeg -e` 后重跑 `npm run build:python`（脚本会解析 WinGet 包内的真实二进制） |
| 安装后首次启动没有弹向导 | 机器上存在全局 `*_API_KEY` 环境变量，后端会直接读到并视为已配置 |

## 8. 已知限制

- 仅构建 x64 Windows；未做代码签名（首次运行可能出现 SmartScreen 提示）。
- 便携 Python 的 `python312._pth` 会使解释器进入 isolated 模式，`PYTHONPATH` 无效，因此启动参数显式带上 `--app-dir`。
- 升级安装不会删除 `%APPDATA%\AragonMovie`，用户凭证与项目数据得以保留；`resources` 里的 Python 代码会在启动时覆盖式同步到工作区（跳过 `backend/data`、`backend/projects`、`backend/temp_projects`、`logs`、`output`、`bin`）。
