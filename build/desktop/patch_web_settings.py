"""Patch frontend settings page: 豆包 Seedance video card + 火山 TTS 2.0 voice card."""

from pathlib import Path

path = Path("frontend/src/app/settings/page.tsx")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"


def must_replace(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"MISSING {label}:\n{old[:300]}")
    text = text.replace(old, new, 1)
    print(f"ok {label}")


# ---- 1. video service selector: add doubao --------------------------------
must_replace(
    "{(['veo3', 'sora2', 'ali_token_plan'] as const).map((svc) => (",
    "{(['ali_token_plan', 'doubao', 'veo3', 'sora2'] as const).map((svc) => (",
    "video service chips",
)

must_replace(
    "                          : svc === 'ali_token_plan'\n",
    "                          : svc === 'ali_token_plan'\n",
    "noop",
) if False else None

# ---- 2. video providers: append the Doubao Seedance card before SaveBar ----
video_anchor = (
    "                  testResult={resultFor('video', 'ali_token_plan')}" + NL
    + "                />" + NL
    + '                <SaveBar category="video" />'
)
video_card = (
    "                  testResult={resultFor('video', 'ali_token_plan')}" + NL
    + "                />" + NL
    + "                <ProviderCard" + NL
    + '                  title="豆包 Seedance（火山方舟）"' + NL
    + '                  subtitle="火山方舟 Ark 异步视频任务：图生视频 / 文生视频。非 OpenAI 兼容接口，分辨率/时长/比例为 JSON 字段。"' + NL
    + "                  badge={getField('video', 'service_type') === 'doubao' ? '当前使用' : undefined}" + NL
    + "                  fields={[" + NL
    + "                    { key: 'api_key', label: 'Ark API Key', secret: true, hint: '火山方舟控制台 → API Key 管理（UUID 形式）' }," + NL
    + "                    { key: 'model', label: '图生视频模型 (i2v)', placeholder: 'doubao-seedance-2-0-260128' }," + NL
    + "                    { key: 't2v_model', label: '文生视频模型 (t2v)', placeholder: 'doubao-seedance-2-0-260128' }," + NL
    + "                    {" + NL
    + "                      key: 'default_resolution'," + NL
    + "                      label: '默认分辨率'," + NL
    + "                      type: 'select'," + NL
    + "                      options: [" + NL
    + "                        { value: '480p', label: '480p' }," + NL
    + "                        { value: '720p', label: '720p' }," + NL
    + "                        { value: '1080p', label: '1080p' }," + NL
    + "                      ]," + NL
    + "                    }," + NL
    + "                    { key: 'default_ratio', label: '画面比例', placeholder: '16:9' }," + NL
    + "                    { key: 'default_duration', label: '默认时长（秒，4-15）', type: 'number' }," + NL
    + "                    { key: 'base_url', label: 'Base URL', placeholder: 'https://ark.cn-beijing.volces.com/api/v3' }," + NL
    + "                    { key: 'endpoint', label: 'Endpoint', placeholder: '/contents/generations/tasks' }," + NL
    + "                  ]}" + NL
    + "                  values={{" + NL
    + "                    base_url: getField('video', 'doubao.base_url')," + NL
    + "                    endpoint: getField('video', 'doubao.endpoint')," + NL
    + "                    api_key: getField('video', 'doubao.api_key')," + NL
    + "                    model: getField('video', 'doubao.model')," + NL
    + "                    t2v_model: getField('video', 'doubao.t2v_model')," + NL
    + "                    default_resolution: getField('video', 'doubao.default_resolution')," + NL
    + "                    default_ratio: getField('video', 'doubao.default_ratio')," + NL
    + "                    default_duration: getField('video', 'doubao.default_duration')," + NL
    + "                  }}" + NL
    + "                  maskedKey={secretPlaceholder(settings.video.doubao?.api_key)}" + NL
    + "                  onChange={(k, v) => setField('video', `doubao.${k}`, v)}" + NL
    + "                  testing={testingCat === 'video'}" + NL
    + "                  testResult={resultFor('video', 'doubao')}" + NL
    + "                />" + NL
    + '                <SaveBar category="video" />'
)
must_replace(video_anchor, video_card, "doubao video card")

# ---- 3. voice provider options -------------------------------------------
must_replace(
    "                      { value: 'dashscope_native', label: 'DashScope 原生合成' },",
    "                      { value: 'dashscope_native', label: 'DashScope 原生合成' }," + NL
    + "                      { value: 'volc_tts2', label: '火山引擎 TTS 2.0（豆包）' },",
    "voice provider option",
)
