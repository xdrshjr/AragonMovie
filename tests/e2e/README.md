# UI 自动化测试（Playwright + pytest）

用真实浏览器驱动 AragonMovie 的 Web 界面，走完 **Step0 → Step5 完整生成工作流**，
最后由后端调用阿里云 Token Plan 网关（文本 / 图像 / 视频模型）产出 **1 分钟以内** 的短剧视频，
并断言视频可下载、可播放、时长与分辨率符合预期。

```
tests/e2e/
├── conftest.py                    # fixtures：前端/后端地址、artifacts 目录、后端 REST 客户端
├── e2e_support.py                 # BackendApi（健康检查/出图/下载）、ffprobe 时长探测
├── fixtures/short_drama_1min.yaml # 测试用剧本：1 角色 × 3 场景 × 8s ≈ 24s
├── test_ui_full_workflow.py       # 冒烟用例 + 全流程用例
└── artifacts/                     # 运行产物：分步截图、视频、报告（自动创建）
```

## 1. 前置条件

```bat
:: 后端依赖（venv 里的 Python 3.12）
venv\Scripts\python.exe -m pip install -r requirements.txt playwright pytest-playwright fastapi uvicorn
venv\Scripts\python.exe -m playwright install chromium

:: 前端依赖
cd frontend
npm install
cd ..

:: .env 里已经配置好 Token Plan 凭证（ALI_TOKEN_PLAN_API_KEY / FAST_LLM_* / TTS_*）
```

## 2. 启动前后端

```bat
:: 终端 1 —— 后端 http://localhost:8000
venv\Scripts\python.exe backend\run_dev.py

:: 终端 2 —— 前端 http://localhost:3000
cd frontend
npm run dev
```

也可以直接跑仓库自带的 `start-dev.ps1`。

## 3. 运行测试

```bat
:: 只跑便宜的冒烟用例（首页渲染，不消耗生成额度）
venv\Scripts\python.exe -m pytest tests/e2e -v -s -k home

:: 完整工作流（会真实调用图像 + 视频模型，约 5~15 分钟）
venv\Scripts\python.exe -m pytest tests/e2e -v -s -m e2e

:: 想看浏览器实际操作过程
venv\Scripts\python.exe -m pytest tests/e2e -v -s -m e2e --headed --slowmo 200
```

可选环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `E2E_FRONTEND_URL` | `http://localhost:3000` | 被测前端地址 |
| `E2E_BACKEND_URL` | `http://localhost:8000` | 被测后端地址 |
| `E2E_GENERATION_TIMEOUT_S` | `3000` | 等待视频生成完成的上限 |
| `E2E_MAX_DURATION_S` | `60` | 产物时长上限（断言用） |
| `E2E_PROJECT_NAME` | `E2E 城市微光` | 新建项目名称 |
| `E2E_ARTIFACTS_DIR` | `tests/e2e/artifacts` | 截图/视频/报告输出目录 |

## 4. 用例做了什么

1. **首页**：等待「My Projects」标题，确认「+ New Project」入口可见。
2. **新建项目**：填项目名 / 描述，选 *Short Drama* + *Full Mode*，点 *Create Project*，
   校验跳转到 `/workflow/<id>?videoType=short_drama&mode=full`。
3. **Step0**：选视频类型「短剧」→ 子类型「现代都市」→ 连续性配置出现 → 「继续到剧本输入 →」。
4. **Step1**：切到 *Direct YAML Input*，粘贴 `fixtures/short_drama_1min.yaml`，
   校验无报错后点 *Next: Character Images →*。
5. **Step2**：先用后端 `POST /api/v1/images/generate`（`service=ali_token_plan`，
   即 wan 图像模型）生成角色参考图，再通过 UI 的 *Manual Upload* 上传，
   等待「Image selected」后进入下一步。
   > 说明：Step2/Step3 的 *Auto Generate* 按钮在前端硬编码 `service: 'doubao'`，
   > 本项目只配置了 Token Plan 凭证，因此自动化走「上传」路径，图像仍由 Token Plan 生成。
6. **Step3**：保留 *Auto Generate* 模式不放图，场景图由后端用 Token Plan 图像模型自动补齐，
   点 *Next: Generate Video →*。
7. **Step4**：轮询进度（阶段 / 百分比打印到控制台），直到出现成功提示或失败横幅。
8. **Step5**：断言「Video Generated Successfully!」、读取 `<video src>` 下载 mp4，
   用 ffprobe 断言 **时长 ≤ 60s**、分辨率 ≥ 640。

## 5. 产物

`tests/e2e/artifacts/` 下会得到：

- `NN_*.png`：每一步的全页截图（新建项目、Step0~Step5）
- `character_reference.png`：Token Plan 生成的角色参考图
- `aragonmovie_e2e_output.mp4`：最终短剧视频
- `e2e_report.json` / `e2e_summary.json`：每步耗时、视频信息、浏览器控制台尾部日志
- 失败时额外写 `FAILED_*.png/.html/.logviewer.txt`（页面快照 + 生成日志面板内容）

## 6. 常见问题

- **首页一直空白/超时**：Next.js 首次编译较慢，用例已放宽到 180s；确认 `npm run dev` 已在 3000 端口就绪。
- **Step4 报 `Generation failed`**：先看 `FAILED_*.logviewer.txt`，多半是网关限流或模型额度；
  也可直接 `curl http://localhost:8000/health` 与 `POST /api/v1/settings/test/text` 排查凭证。
- **`ffprobe not found`**：安装 FFmpeg 并加入 PATH。
- **视频超过 60s**：调小剧本里每个 `scene.duration` 或减少场景数（`fixtures/short_drama_1min.yaml`）。
