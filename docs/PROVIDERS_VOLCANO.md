# 火山引擎（豆包）接入说明

本仓库新增两个火山引擎服务，与原有的阿里 Token Plan / Veo3 / Sora2 / DashScope 并存，
在设置中心与桌面端首次配置向导里都能直接选择。

| 能力 | 服务类型 / 通道 | 协议 | 凭证 |
| --- | --- | --- | --- |
| 视频生成 | `VIDEO_SERVICE_TYPE=doubao`（豆包 Seedance） | 火山方舟 Ark 异步任务 `POST /api/v3/contents/generations/tasks` + 轮询 | 方舟 API Key（UUID 形式） |
| 语音合成 | `TTS_PROVIDER=volc_tts2`（火山 TTS 2.0） | v3 双向 WebSocket `wss://openspeech.bytedance.com/api/v3/tts/bidirection` | 语音技术 API Key（UUID 形式） |

图像仍可使用阿里 `ali_token_plan`，也可以切到 `image.service_type=doubao`（同一个方舟 Key）。

---

## 1. 豆包 Seedance 视频（`services/doubao_video_service.py`）

```
POST {base}/contents/generations/tasks
{
  "model": "doubao-seedance-2-0-260128",
  "content": [
    {"type": "text", "text": "<运动/镜头描述>"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
  ],
  "resolution": "720p",      // 480p / 720p / 1080p
  "duration": 5,             // 4 5 6 8 10 12 15（其他值自动吸附）
  "ratio": "16:9"
}
-> {"id": "cgt-..."}
GET {base}/contents/generations/tasks/{id}   // queued / running / succeeded / failed
-> {"content": {"video_url": "https://..."}}
```

要点：

- `resolution` / `duration` / `ratio` 必须是 **JSON 字段**，拼进 prompt 文本会被忽略。
- 本地首帧自动转 base64 data URI；只接受一张首帧，多余的场景连续性参考帧会记录 warning 后忽略。
- `content` 在响应里是对象（也可能历史上是数组），解析两种都兼容。
- 时长不足 4s 或不在允许集合时按最近值吸附并记录 warning。

### 内容安全（务必知道）

方舟会对输入图片做真人检测。用「上一镜头视频截帧」做首帧时，很容易触发：

```
400 InputImageSensitiveContentDetected.PrivacyInformation
The request failed because the input image 'content[1]' may contain real person
```

这不是配置问题，重试无意义（服务层已标记为不可重试并给出可执行建议）。可选方案：

1. 关闭场景连续性参考帧：`ENABLE_SCENE_CONTINUITY=false`、`ENABLE_SMART_CONTINUITY_JUDGE=false`
   （每个镜头用自己的场景图，实测可正常生成）。
2. 把 `visual_style` / 提示词调成插画、动画、强风格化，避免「照片级真人」。

## 2. 火山 TTS 2.0（`services/volc_tts_service.py`）

该网关**没有**一次性 HTTP 合成接口（`/api/v1/tts` 对现代 API Key 返回
`401 load grant: requested grant not found`），只能走 v3 双向 WebSocket：

```
StartConnection -> ConnectionStarted
StartSession(req_params.speaker, audio_params{format,sample_rate}) -> SessionStarted
TaskRequest(text) + FinishSession -> AudioOnlyServer 帧 ... SessionFinished
```

配置项（设置中心「语音合成」→ 通道选「火山引擎 TTS 2.0」）：

| 字段 | 说明 |
| --- | --- |
| `voice.volc_api_key` | 语音技术 API Key（`X-Api-Key`） |
| `voice.volc_resource_id` | `seed-tts-2.0`（标准 2.0 音色）/ `volc.megatts.timbre`（复刻音色） |
| `voice.volc_voice` | `speaker`，例如 `zh_female_xiaohe_uranus_bigtts`、`zh_male_shaonianzixin_uranus_bigtts` |

常见错误（服务层已翻译成中文提示）：

| 报错 | 原因 / 处理 |
| --- | --- |
| `resource ID is mismatched with speaker related resource` | 音色不属于该资源：换成 `*_uranus_bigtts` 等已授权音色，或把资源改为 `volc.megatts.timbre` |
| `requested resource not granted` | 该 Key 未授权此服务，需要在控制台为 Key 绑定 |
| 返回 0 字节音频 | 音色未激活 / 资源不匹配 |

## 3. 环境变量一览

```dotenv
# 视频：豆包 Seedance（火山方舟）
VIDEO_SERVICE_TYPE=doubao
DOUBAO_VIDEO_API_KEY=<ark uuid key>
DOUBAO_VIDEO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_VIDEO_ENDPOINT=/contents/generations/tasks
DOUBAO_VIDEO_MODEL=doubao-seedance-2-0-260128
DOUBAO_VIDEO_T2V_MODEL=doubao-seedance-2-0-260128
DOUBAO_VIDEO_DEFAULT_RESOLUTION=720p
DOUBAO_VIDEO_DEFAULT_RATIO=16:9
DOUBAO_VIDEO_DEFAULT_DURATION=5
DOUBAO_VIDEO_WATERMARK=false

# 语音：火山 TTS 2.0
TTS_PROVIDER=volc_tts2
TTS_VOLC_API_KEY=<volcano speech uuid key>
TTS_VOLC_RESOURCE_ID=seed-tts-2.0
TTS_VOLC_VOICE=zh_female_xiaohe_uranus_bigtts
TTS_VOLC_SPEED=1.0
TTS_VOLC_SAMPLE_RATE=24000
```

`websockets>=12.0` 已加入 `requirements.txt`，桌面端便携运行时也已内置。

## 4. 自动化验证

```bat
:: 用真实凭证跑一条 2 场景 x 5s 的短剧，产出 mp4 并用 ffprobe 校验
set DOUBAO_VIDEO_API_KEY=...
set TTS_VOLC_API_KEY=...
venv\Scripts\python.exe scripts\e2e_volcano_short_drama.py
```

脚本会：起后端 → 通过 Settings Center API 写入配置 → 逐项连接测试 →
提交工作流 → 轮询 → 下载成片 → `ffprobe` 校验（时长 8-13s、含音轨、有视频流）→
把报告与成片存到 `build/desktop/e2e/<timestamp>/`。
---

## 5. 本次验证中发现并修复的问题

1. **旁白从未进入成片**（`agents/video_generator_agent.py`）：视频生成 Agent 的返回值里只有 `dialogues`，但
   `VideoComposerAgent._scene_speech_text()` 读的是 `result["narrations"]`，因此即使 TTS 配置正确也会静默跳过配音。
   已在普通场景、层级场景（sub_scene）两条返回路径上补齐 `narrations`，成片现在会带上旁白音轨。
2. **Ark 真人内容过滤**：用上一镜头截帧做首帧会触发
   `InputImageSensitiveContentDetected.PrivacyInformation`。服务层已把这类错误标记为不可重试并给出可选方案；
   自动化脚本改用插画风格静帧 + 关闭场景连续性，稳定通过。
3. **首次配置向导 / 设置中心**已同步支持新服务：视频服务商列表新增「豆包 Seedance」，语音通道新增「火山 TTS 2.0」
   （含资源 ID 与音色字段）。

