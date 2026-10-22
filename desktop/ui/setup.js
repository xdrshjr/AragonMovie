'use strict';

/* =====================================================================
   AragonMovie · first-run setup wizard (renderer)
   Vanilla JS, no dependencies: the wizard must work offline, before the
   product UI is reachable, and never leak credentials to a network layer
   other than the privileged IPC bridge.
   ===================================================================== */

const shell = window.aragonShell || {};

const CATEGORY_LABELS = {
  text: 'LLM 文本模型',
  image: '图像生成',
  video: '视频生成',
  voice: '语音合成',
};

const STEPS = [
  {
    id: 'text',
    nav: 'LLM 文本模型',
    navSub: '剧本润色 / 镜头评审',
    title: 'LLM 文本模型',
    desc: '用于剧本润色、分镜优化与镜头评审。任何兼容 OpenAI Chat Completions 协议的接口都可以接入。',
  },
  {
    id: 'image',
    nav: '图像生成',
    navSub: '角色设定 / 分镜画面',
    title: '图像生成',
    desc: '生成角色多视图与每个镜头的首帧画面，视频模型会以它为参考生成动态镜头。',
  },
  {
    id: 'video',
    nav: '视频生成',
    navSub: '图生视频',
    title: '视频生成',
    desc: '把分镜画面转成动态镜头。选好服务商后填入对应凭证即可。',
  },
  {
    id: 'voice',
    nav: '语音合成',
    navSub: '旁白配音（可选）',
    title: '语音合成',
    desc: '为成片叠加旁白配音。此步骤可选，关闭后生成静音视频。',
  },
  {
    id: 'finish',
    nav: '完成',
    navSub: '检查并进入应用',
    title: '配置完成',
    desc: '确认各项服务的连接状态，然后进入工作台。凭证会保存在本机，下次启动无需重新配置。',
  },
];

/* ------------------------------------------------------------------ schema */

const TEXT_PRESETS = [
  {
    id: 'ali-token-plan',
    label: '阿里云 Token Plan',
    api_url: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
    model: 'qwen3.8-max',
  },
  {
    id: 'dashscope',
    label: 'DashScope 百炼',
    api_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-plus',
  },
  { id: 'deepseek', label: 'DeepSeek', api_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { id: 'openai', label: 'OpenAI', api_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  {
    id: 'siliconflow',
    label: 'SiliconFlow',
    api_url: 'https://api.siliconflow.cn/v1',
    model: 'Qwen/Qwen2.5-72B-Instruct',
  },
];

const IMAGE_PROVIDERS = [
  {
    value: 'ali_token_plan',
    label: '阿里云 Token Plan',
    note: '一个 Key 覆盖文本、图像与视频，最省事',
    fields: [
      { path: 'ali_token_plan.api_key', label: 'API Key', type: 'password', secret: true, required: true, full: true },
      { path: 'ali_token_plan.model', label: '图像模型', type: 'text', placeholder: 'wan2.7-image-pro' },
      {
        path: 'ali_token_plan.base_url',
        label: 'Base URL',
        type: 'text',
        advanced: true,
        placeholder: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
      },
      {
        path: 'ali_token_plan.endpoint',
        label: 'Endpoint',
        type: 'text',
        advanced: true,
        placeholder: '/api/v1/services/aigc/multimodal-generation/generation',
      },
    ],
  },
  {
    value: 'doubao',
    label: '豆包 Seedream',
    note: '火山方舟 Ark，速度与画质均衡',
    fields: [
      { path: 'doubao.api_key', label: 'API Key', type: 'password', secret: true, required: true, full: true },
      { path: 'doubao.model', label: '图像模型', type: 'text', placeholder: 'doubao-seedream-4-5-251128' },
      { path: 'doubao.base_url', label: 'Base URL', type: 'text', advanced: true, placeholder: 'https://ark.cn-beijing.volces.com' },
      { path: 'doubao.endpoint', label: 'Endpoint', type: 'text', advanced: true, placeholder: '/api/v3/images/generations' },
      { path: 'doubao.watermark', label: '生成水印', type: 'checkbox', advanced: true },
    ],
  },
  {
    value: 'nano_banana',
    label: 'Nano Banana Pro',
    note: 'Gemini 3 Pro Image，擅长人物一致性',
    fields: [
      { path: 'nano_banana.api_key', label: 'API Key', type: 'password', secret: true, required: true, full: true },
      { path: 'nano_banana.model', label: '图像模型', type: 'text', placeholder: 'gemini-3-pro-image-preview' },
      { path: 'nano_banana.base_url', label: 'Base URL', type: 'text', advanced: true },
      { path: 'nano_banana.endpoint', label: 'Endpoint', type: 'text', advanced: true, placeholder: '/v1/images/generations' },
    ],
  },
  {
    value: 'midjourney',
    label: 'Midjourney',
    note: '通过第三方代理提交任务',
    fields: [
      { path: 'midjourney.api_key', label: 'API Key', type: 'password', secret: true, required: true, full: true },
      { path: 'midjourney.base_url', label: 'Base URL', type: 'text', advanced: true, placeholder: 'https://api.kuai.host' },
      {
        path: 'midjourney.bot_type',
        label: 'Bot 类型',
        type: 'select',
        options: [
          { value: 'MID_JOURNEY', label: 'MID_JOURNEY' },
          { value: 'NIJI_JOURNEY', label: 'NIJI_JOURNEY' },
        ],
      },
      { path: 'midjourney.auto_upscale', label: '自动放大 2×2 网格', type: 'checkbox', advanced: true },
    ],
  },
];

const VIDEO_PROVIDERS = [
  {
    value: 'doubao',
    label: '豆包 Seedance',
    note: '火山方舟 Ark 视频生成（图生视频 / 文生视频），异步任务接口',
    fields: [
      { path: 'doubao.api_key', label: 'Ark API Key', type: 'password', secret: true, required: true, full: true },
      { path: 'doubao.model', label: '图生视频模型', type: 'text', placeholder: 'doubao-seedance-2-0-260128' },
      {
        path: 'doubao.default_resolution',
        label: '默认分辨率',
        type: 'select',
        options: [
          { value: '480p', label: '480p' },
          { value: '720p', label: '720p' },
          { value: '1080p', label: '1080p' },
        ],
      },
      { path: 'doubao.default_ratio', label: '画面比例', type: 'text', placeholder: '16:9' },
      { path: 'doubao.default_duration', label: '默认时长（秒，4-15）', type: 'number', min: 4, max: 15 },
      { path: 'doubao.t2v_model', label: '文生视频模型', type: 'text', advanced: true },
      { path: 'doubao.base_url', label: 'Base URL', type: 'text', advanced: true, placeholder: 'https://ark.cn-beijing.volces.com/api/v3' },
      { path: 'doubao.endpoint', label: 'Endpoint', type: 'text', advanced: true, placeholder: '/contents/generations/tasks' },
    ],
  },
  {
    value: 'ali_token_plan',
    label: '阿里云 Token Plan',
    note: 'happyhorse-1.1 图生视频，与文本/图像共用 Key',
    fields: [
      { path: 'ali_token_plan.api_key', label: 'API Key', type: 'password', secret: true, required: true, full: true },
      { path: 'ali_token_plan.model', label: '图生视频模型', type: 'text', placeholder: 'happyhorse-1.1-i2v' },
      { path: 'ali_token_plan.t2v_model', label: '文生视频模型', type: 'text', advanced: true },
      { path: 'ali_token_plan.r2v_model', label: '参考生视频模型', type: 'text', advanced: true },
      { path: 'ali_token_plan.default_size', label: '默认分辨率', type: 'text', advanced: true, placeholder: '1280x720' },
      { path: 'ali_token_plan.default_duration', label: '默认时长（秒）', type: 'number', advanced: true, min: 1, max: 60 },
      { path: 'ali_token_plan.watermark', label: '请求带水印版本', type: 'checkbox', advanced: true },
      { path: 'ali_token_plan.base_url', label: 'Base URL', type: 'text', advanced: true },
      { path: 'ali_token_plan.endpoint', label: 'Endpoint', type: 'text', advanced: true },
    ],
  },
  {
    value: 'veo3',
    label: 'Veo 3',
    note: 'Google Veo 3.1（通过代理网关）',
    fields: [
      { path: 'veo3.api_key', label: 'API Key', type: 'password', secret: true, required: true, full: true },
      { path: 'veo3.model', label: '视频模型', type: 'text', placeholder: 'veo_3_1' },
      { path: 'veo3.base_url', label: 'Base URL', type: 'text', advanced: true, placeholder: 'https://api.kuai.host' },
      { path: 'veo3.endpoint', label: 'Endpoint', type: 'text', advanced: true, placeholder: '/v1/videos' },
      { path: 'veo3.skip_upload', label: '跳过上传（直接传 base64）', type: 'checkbox', advanced: true },
    ],
  },
  {
    value: 'sora2',
    label: 'Sora 2',
    note: 'OpenAI Sora 2（通过代理网关）',
    fields: [
      { path: 'sora2.api_key', label: 'API Key', type: 'password', secret: true, required: true, full: true },
      { path: 'sora2.model', label: '视频模型', type: 'text', placeholder: 'sora-2' },
      { path: 'sora2.default_size', label: '默认分辨率', type: 'text', advanced: true, placeholder: '1280x720' },
      { path: 'sora2.default_duration', label: '默认时长（秒）', type: 'number', advanced: true, min: 4, max: 25 },
      { path: 'sora2.watermark', label: '生成水印', type: 'checkbox', advanced: true },
      { path: 'sora2.private', label: '私有任务', type: 'checkbox', advanced: true },
      { path: 'sora2.base_url', label: 'Base URL', type: 'text', advanced: true, placeholder: 'https://api.kuai.host' },
      { path: 'sora2.endpoint', label: 'Endpoint', type: 'text', advanced: true, placeholder: '/v1/videos' },
    ],
  },
];

const VOICE_PROVIDERS = [
  { value: 'volc_tts2', label: '火山 TTS 2.0', note: '豆包语音合成 2.0（v3 双向 WebSocket，seed-tts-2.0 资源）' },
  { value: 'auto', label: '自动识别', note: '按 Base URL 自动选择传输方式' },
  { value: 'openai_compatible', label: 'OpenAI 兼容', note: 'POST {base}/audio/speech' },
  { value: 'dashscope_native', label: 'DashScope 原生', note: 'qwen-tts / cosyvoice-v2' },
];

const SECRET_PATHS = {
  text: ['fast_llm.api_key', 'judge_llm.api_key'],
  image: ['ali_token_plan.api_key', 'doubao.api_key', 'nano_banana.api_key', 'midjourney.api_key'],
  video: ['ali_token_plan.api_key', 'veo3.api_key', 'sora2.api_key'],
  voice: ['api_key', 'native_api_key', 'volc_api_key'],
};

/* ------------------------------------------------------------------- state */

const state = {
  info: null,
  settings: null,
  status: null,
  drafts: {},
  results: {},
  testState: {},
  step: 'text',
  busy: false,
  advanced: {},
  sameJudge: true,
  mirrorAli: true,
  reconfigure: new URLSearchParams(location.search).get('mode') === 'reconfigure',
};

const els = {
  nav: document.getElementById('nav'),
  body: document.getElementById('step-body'),
  eyebrow: document.getElementById('step-eyebrow'),
  title: document.getElementById('step-title'),
  desc: document.getElementById('step-desc'),
  topStatus: document.getElementById('topbar-status'),
  footStatus: document.getElementById('foot-status'),
  footStatusText: document.getElementById('foot-status-text'),
  prev: document.getElementById('btn-prev'),
  test: document.getElementById('btn-test'),
  next: document.getElementById('btn-next'),
  toast: document.getElementById('toast'),
  brandSub: document.getElementById('brand-sub'),
  paths: document.getElementById('btn-paths'),
};

/* ----------------------------------------------------------------- helpers */

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function getPath(obj, path) {
  return path.split('.').reduce((node, key) => (node == null ? undefined : node[key]), obj);
}

function setPath(obj, path, value) {
  const parts = path.split('.');
  let node = obj;
  for (let i = 0; i < parts.length - 1; i += 1) {
    if (typeof node[parts[i]] !== 'object' || node[parts[i]] === null) node[parts[i]] = {};
    node = node[parts[i]];
  }
  node[parts[parts.length - 1]] = value;
  return obj;
}

function category() {
  return state.step === 'finish' ? null : state.step;
}

function draft(cat, path) {
  const bucket = state.drafts[cat];
  return bucket ? bucket[path] : undefined;
}

function setDraft(cat, path, value) {
  if (!state.drafts[cat]) state.drafts[cat] = {};
  state.drafts[cat][path] = value;
}

function currentValue(cat, path) {
  const drafted = draft(cat, path);
  if (drafted !== undefined) return drafted;
  const stored = getPath(state.settings && state.settings[cat], path);
  return stored === undefined || stored === null ? '' : stored;
}

function storedSecret(cat, path) {
  const stored = getPath(state.settings && state.settings[cat], path);
  return typeof stored === 'string' && stored.trim().length > 0 ? stored : '';
}

function serviceType(cat) {
  const drafted = draft(cat, 'service_type');
  if (drafted) return drafted;
  return (state.settings && state.settings[cat] && state.settings[cat].service_type) || 'ali_token_plan';
}

function voiceEnabled() {
  const drafted = draft('voice', 'enabled');
  if (drafted !== undefined) return Boolean(drafted);
  return Boolean(state.settings && state.settings.voice && state.settings.voice.enabled);
}

function voiceProvider() {
  const drafted = draft('voice', 'provider');
  if (drafted) return drafted;
  return (state.settings && state.settings.voice && state.settings.voice.provider) || 'auto';
}

function toast(message, type) {
  els.toast.textContent = message;
  els.toast.className = `toast show${type === 'error' ? ' error' : ''}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    els.toast.className = 'toast';
  }, type === 'error' ? 5200 : 2600);
}

function bus(cat) {
  return state.testState[cat] === 'busy';
}

/* ---------------------------------------------------------------- payloads */

function buildPayload(cat) {
  const base = JSON.parse(JSON.stringify((state.settings && state.settings[cat]) || {}));
  const bucket = state.drafts[cat] || {};
  for (const [path, value] of Object.entries(bucket)) setPath(base, path, value);

  // Write-only secrets: an untouched field keeps the stored key. Echoing the
  // masked value back is explicitly tolerated by the backend, so we simply pass
  // through whatever the settings tree already contains.
  if (cat === 'text' && state.sameJudge) {
    const fast = base.fast_llm || {};
    base.judge_llm = {
      ...(base.judge_llm || {}),
      api_url: fast.api_url,
      model: fast.model,
      api_key: fast.api_key,
    };
  }
  return base;
}

function validate(cat) {
  if (cat === 'text') {
    if (!String(currentValue('text', 'fast_llm.api_url')).trim()) return '请填写接口地址';
    if (!String(currentValue('text', 'fast_llm.model')).trim()) return '请填写模型 ID';
    if (!draft('text', 'fast_llm.api_key') && !storedSecret('text', 'fast_llm.api_key')) return '请填写 API Key';
  }
  if (cat === 'image' || cat === 'video') {
    const service = serviceType(cat);
    const path = `${service}.api_key`;
    if (!draft(cat, path) && !storedSecret(cat, path)) {
      return `请填写 ${service === 'ali_token_plan' ? '阿里云 Token Plan' : service} 的 API Key`;
    }
  }
  if (cat === 'voice' && voiceEnabled()) {
    const provider = voiceProvider();
    if (provider === 'volc_tts2') {
      if (!draft('voice', 'volc_api_key') && !storedSecret('voice', 'volc_api_key')) {
        return '请填写火山引擎语音合成 2.0 的 API Key';
      }
    } else {
      const needsNative = provider === 'dashscope_native';
      const keyPath = needsNative ? 'native_api_key' : 'api_key';
      const fallback = needsNative ? storedSecret('voice', 'api_key') : storedSecret('voice', 'native_api_key');
      if (!draft('voice', keyPath) && !storedSecret('voice', keyPath) && !fallback) {
        return needsNative ? '请填写 DashScope API Key' : '请填写语音服务 API Key';
      }
    }
  }
  return null;
}

/* ------------------------------------------------------------------- views */

function fieldHtml(cat, field) {
  const value = currentValue(cat, field.path);
  const stored = field.secret ? storedSecret(cat, field.path) : '';
  const label = `
    <label for="f-${cat}-${field.path.replace(/\./g, '-')}">
      ${escapeHtml(field.label)}
      ${field.required ? '<span class="req">*</span>' : '<span class="opt">可选</span>'}
    </label>`;

  const attrs = `id="f-${cat}-${field.path.replace(/\./g, '-')}" data-path="${field.path}" data-cat="${cat}" ${
    field.secret ? 'data-secret="1"' : ''
  }`;

  if (field.type === 'checkbox') {
    const on = value === true || value === 'true';
    return `
      <div class="field ${field.full ? 'full' : ''}">
        <div class="switch-row" style="padding:4px 0;border:0">
          <div class="switch ${on ? 'on' : ''}" data-toggle="${field.path}" data-cat="${cat}" role="switch" aria-checked="${on}" tabindex="0"></div>
          <div class="switch-text"><b>${escapeHtml(field.label)}</b></div>
        </div>
      </div>`;
  }

  if (field.type === 'select') {
    const options = (field.options || [])
      .map(
        (opt) =>
          `<option value="${escapeHtml(opt.value)}" ${
            String(opt.value) === String(value) ? 'selected' : ''
          }>${escapeHtml(opt.label)}</option>`
      )
      .join('');
    return `
      <div class="field ${field.full ? 'full' : ''}">
        ${label}
        <select ${attrs}>${options}</select>
      </div>`;
  }

  if (field.secret) {
    return `
      <div class="field ${field.full ? 'full' : ''}">
        ${label}
        <div class="secret-wrap">
          <input ${attrs} type="password" autocomplete="off" spellcheck="false"
            value="${escapeHtml(value)}"
            placeholder="${stored ? `已保存 ${escapeHtml(stored)}（留空保持不变）` : '粘贴 API Key'}" />
          <button class="secret-toggle" data-reveal="${field.path}" data-cat="${cat}" type="button">显示</button>
        </div>
        ${stored && !value ? `<div class="stored-key">已保存：<b>${escapeHtml(stored)}</b></div>` : ''}
      </div>`;
  }

  const type = field.type === 'number' ? 'number' : 'text';
  const extra =
    (field.min !== undefined ? `min="${field.min}" ` : '') + (field.max !== undefined ? `max="${field.max}" ` : '');
  return `
    <div class="field ${field.full ? 'full' : ''}">
      ${label}
      <input ${attrs} type="${type}" ${extra}spellcheck="false" autocomplete="off"
        value="${escapeHtml(value)}"
        placeholder="${escapeHtml(field.placeholder || '')}" />
      ${field.hint ? `<div class="hint">${escapeHtml(field.hint)}</div>` : ''}
    </div>`;
}

function providerFieldsHtml(cat, provider) {
  const normal = provider.fields.filter((f) => !f.advanced);
  const advanced = provider.fields.filter((f) => f.advanced);
  const open = Boolean(state.advanced[cat]);
  return `
    <div class="grid">${normal.map((f) => fieldHtml(cat, f)).join('')}</div>
    ${
      advanced.length
        ? `<button class="advanced-toggle" data-advanced="${cat}" type="button">
             ${open ? '收起' : '显示'}高级参数（Base URL / Endpoint / 分辨率等）
           </button>
           <div class="grid advanced ${open ? 'open' : ''}" style="margin-top:12px">
             ${advanced.map((f) => fieldHtml(cat, f)).join('')}
           </div>`
        : ''
    }`;
}

function segmentedHtml(cat, options, active) {
  return `<div class="segmented">${options
    .map(
      (opt) =>
        `<button class="seg ${opt.value === active ? 'active' : ''}" data-seg="${cat}" data-value="${opt.value}" type="button">${escapeHtml(
          opt.label
        )}</button>`
    )
    .join('')}</div>`;
}

function resultsHtml(cat) {
  const results = state.results[cat];
  if (!results || !results.length) return '';
  const rows = results
    .map((r) => {
      const ok = Boolean(r.success);
      return `
        <div class="result ${ok ? 'ok' : 'fail'}">
          <div class="result-icon">${ok ? '✓' : '!'}</div>
          <div class="result-main">
            <div class="result-head">
              <span class="result-target">${escapeHtml(r.target || cat)}</span>
              <span class="badge ${ok ? 'ok' : 'partial'}">${ok ? '连接成功' : '连接失败'}</span>
              <span class="badge">${r.verified === 'full' ? '真实请求' : '仅鉴权'}</span>
            </div>
            <div class="result-msg">${escapeHtml(r.message || '')}</div>
            ${r.detail ? `<div class="result-detail">${escapeHtml(String(r.detail).slice(0, 1200))}</div>` : ''}
          </div>
          <div class="result-meta">${r.latency_ms != null ? `${r.latency_ms} ms` : ''}</div>
        </div>`;
    })
    .join('');
  return `<div class="card"><div class="card-head"><div><div class="card-title">连接测试结果</div>
    <div class="card-sub">测试始终使用已保存的最新配置</div></div></div>
    <div class="results">${rows}</div></div>`;
}

function textStepHtml() {
  const cat = 'text';
  const activePreset = TEXT_PRESETS.find(
    (p) => p.api_url === currentValue(cat, 'fast_llm.api_url') && p.model === currentValue(cat, 'fast_llm.model')
  );
  const judgeKeyStored = storedSecret(cat, 'judge_llm.api_key');
  const isAliPlan = /aliyuncs\.com/i.test(String(currentValue(cat, 'fast_llm.api_url')));
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">接入方式</div>
          <div class="card-sub">选择常用服务商会自动填入接口地址与模型，也可以完全自定义</div>
        </div>
      </div>
      <div class="chips">
        ${TEXT_PRESETS.map(
          (p) =>
            `<button class="chip ${activePreset && activePreset.id === p.id ? 'active' : ''}" data-preset="${p.id}" type="button">${escapeHtml(
              p.label
            )}</button>`
        ).join('')}
      </div>
      <div class="grid" style="margin-top:16px">
        ${fieldHtml(cat, { path: 'fast_llm.api_url', label: '接口地址 (Base URL)', type: 'text', required: true, full: true, placeholder: 'https://…/v1' })}
        ${fieldHtml(cat, { path: 'fast_llm.model', label: '模型 ID', type: 'text', required: true, placeholder: 'qwen3.8-max' })}
        ${fieldHtml(cat, { path: 'fast_llm.api_key', label: 'API Key', type: 'password', secret: true, required: true })}
      </div>
    </div>

    ${
      isAliPlan
        ? `<div class="card">
            <div class="switch-row" style="border:0;padding:0">
              <div class="switch ${state.mirrorAli ? 'on' : ''}" data-toggle="__mirrorAli" role="switch" aria-checked="${state.mirrorAli}" tabindex="0"></div>
              <div class="switch-text">
                <b>同一 Key 同时用于图像与视频生成</b>
                <span>阿里云 Token Plan 的一个 Key 覆盖文本 / 图像 / 视频，勾选后无需在后续步骤重复粘贴</span>
              </div>
            </div>
          </div>`
        : ''
    }

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">镜头评审模型</div>
          <div class="card-sub">用于角色一致性与场景连续性打分（多模态模型效果最好）</div>
        </div>
      </div>
      <div class="switch-row" style="border:0;padding-top:0">
        <div class="switch ${state.sameJudge ? 'on' : ''}" data-toggle="__sameJudge" role="switch" aria-checked="${state.sameJudge}" tabindex="0"></div>
        <div class="switch-text">
          <b>复用上面的凭证</b>
          <span>${judgeKeyStored ? '当前已单独保存过评审 Key' : '关闭后可单独填写评审模型的地址与 Key'}</span>
        </div>
      </div>
      ${
        state.sameJudge
          ? ''
          : `<div class="grid" style="margin-top:10px">
              ${fieldHtml(cat, { path: 'judge_llm.api_url', label: '接口地址 (Base URL)', type: 'text', full: true })}
              ${fieldHtml(cat, { path: 'judge_llm.model', label: '模型 ID', type: 'text' })}
              ${fieldHtml(cat, { path: 'judge_llm.api_key', label: 'API Key', type: 'password', secret: true })}
            </div>`
      }
    </div>

    <div class="card">
      <div class="card-head"><div><div class="card-title">生成管线开关</div></div></div>
      ${fieldHtml(cat, { path: 'enable_prompt_optimization', label: '启用剧本润色与 Prompt 优化', type: 'checkbox' })}
      ${fieldHtml(cat, { path: 'enable_character_consistency_judge', label: '启用角色一致性评审（会增加一次多模态调用）', type: 'checkbox' })}
    </div>
    ${resultsHtml(cat)}`;
}

function providerStepHtml(cat, providers, title, sub) {
  const active = serviceType(cat);
  const provider = providers.find((p) => p.value === active) || providers[0];
  const aliDraft = draft('text', 'fast_llm.api_key');
  const reuseAli =
    active === 'ali_token_plan' && aliDraft && draft(cat, 'ali_token_plan.api_key') !== aliDraft
      ? `<button class="btn tiny ghost" data-reuse-ali="${cat}" type="button">复用 LLM 步骤的 Key</button>`
      : '';
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">${escapeHtml(title)}</div>
          <div class="card-sub">${escapeHtml(sub)}</div>
        </div>
        <div class="card-head-right">${reuseAli}</div>
      </div>
      ${segmentedHtml(cat, providers.map((p) => ({ value: p.value, label: p.label })), active)}
      <div class="hint" style="margin-top:10px">${escapeHtml(provider.note || '')}</div>
      <div style="margin-top:16px">${providerFieldsHtml(cat, provider)}</div>
    </div>
    ${resultsHtml(cat)}`;
}

function voiceStepHtml() {
  const cat = 'voice';
  const enabled = voiceEnabled();
  const provider = voiceProvider();
  const isVolc = provider === 'volc_tts2';
  const showNative = provider !== 'openai_compatible' && provider !== 'volc_tts2';
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">旁白配音</div>
          <div class="card-sub">关闭后生成的成片为静音视频</div>
        </div>
      </div>
      <div class="switch-row" style="border:0;padding-top:0">
        <div class="switch ${enabled ? 'on' : ''}" data-toggle="enabled" data-cat="voice" role="switch" aria-checked="${enabled}" tabindex="0"></div>
        <div class="switch-text"><b>启用语音合成</b><span>为每个镜头生成旁白并混合进时间线</span></div>
      </div>
    </div>

    <div class="card" ${enabled ? '' : 'style="opacity:.55"'}>
      <div class="card-head"><div><div class="card-title">服务传输方式</div>
        <div class="card-sub">Token Plan 网关没有一次性 HTTP 合成接口，选择「自动识别」会自动改走 DashScope 原生接口</div></div></div>
      ${segmentedHtml(cat, VOICE_PROVIDERS.map((p) => ({ value: p.value, label: p.label })), provider)}
      ${
        isVolc
          ? `<div class="banner" style="margin-top:14px">
               <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6"/><path d="M12 8v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="16.2" r="1" fill="currentColor"/></svg>
               <span>火山 TTS 2.0 使用 v3 双向 WebSocket 合成，凭证是火山引擎「大模型语音合成 2.0」的 API Key；音色需属于 <code>seed-tts-2.0</code> 资源（如 <code>zh_female_xiaohe_uranus_bigtts</code>）。</span>
             </div>
             <div class="grid" style="margin-top:16px">
               ${fieldHtml(cat, { path: 'volc_api_key', label: '火山 TTS 2.0 API Key', type: 'password', secret: true, required: true, full: true })}
               ${fieldHtml(cat, { path: 'volc_resource_id', label: '资源 ID', type: 'text', placeholder: 'seed-tts-2.0' })}
               ${fieldHtml(cat, { path: 'volc_voice', label: '音色 (speaker)', type: 'text', placeholder: 'zh_female_xiaohe_uranus_bigtts' })}
             </div>`
          : `<div class="grid" style="margin-top:16px">
               ${fieldHtml(cat, { path: 'api_key', label: 'API Key', type: 'password', secret: true, full: true })}
               ${fieldHtml(cat, { path: 'base_url', label: 'Base URL', type: 'text', full: true, placeholder: 'https://…/v1' })}
               ${fieldHtml(cat, { path: 'model', label: '语音模型', type: 'text', placeholder: 'qwen-audio-3.0-tts-plus' })}
               ${fieldHtml(cat, { path: 'default_voice', label: '默认音色', type: 'text', placeholder: 'Cherry' })}
               ${fieldHtml(cat, {
                 path: 'default_format',
                 label: '输出格式',
                 type: 'select',
                 options: ['mp3', 'opus', 'aac', 'flac', 'wav', 'pcm'].map((v) => ({ value: v, label: v })),
               })}
               ${fieldHtml(cat, { path: 'default_speed', label: '语速（0.25 – 4.0）', type: 'number' })}
             </div>`
      }
    </div>

    ${
      showNative
        ? `<div class="card" ${enabled ? '' : 'style="opacity:.55"'}>
            <div class="card-head"><div><div class="card-title">DashScope 原生合成</div>
              <div class="card-sub">Token Plan 的 Key 在 dashscope.aliyuncs.com 上无效，需要单独填写百炼 Key</div></div></div>
            <div class="banner">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6"/><path d="M12 8v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="16.2" r="1" fill="currentColor"/></svg>
              <span>如果只想用 Token Plan 的 Key，可保持「自动识别」并留空下面的 DashScope Key——此时管线会记录原因并跳过配音，而不是静默生成无声视频。</span>
            </div>
            <div class="grid" style="margin-top:16px">
              ${fieldHtml(cat, { path: 'native_api_key', label: 'DashScope API Key', type: 'password', secret: true, full: true })}
              ${fieldHtml(cat, { path: 'native_base_url', label: 'Native Base URL', type: 'text', full: true, placeholder: 'https://dashscope.aliyuncs.com' })}
              ${fieldHtml(cat, { path: 'native_model', label: 'Native 模型', type: 'text', placeholder: 'qwen-tts' })}
              ${fieldHtml(cat, { path: 'native_voice', label: 'Native 音色', type: 'text', placeholder: 'Cherry' })}
            </div>
          </div>`
        : ''
    }
    ${resultsHtml(cat)}`;
}

function finishStepHtml() {
  const categories = (state.status && state.status.categories) || {};
  const rows = ['text', 'image', 'video', 'voice']
    .map((cat) => {
      const info = categories[cat] || { configured: false, detail: '' };
      const tested = state.testState[cat] === 'ok';
      const powered = state.testState[cat] === 'fail';
      const ok = info.configured && !powered;
      const stateText = powered
        ? '测试未通过'
        : tested
        ? '已测试通过'
        : info.configured
        ? `已配置${info.detail ? ` · ${info.detail}` : ''}`
        : '待配置';
      return `
        <div class="summary-row">
          <div class="summary-ico ${ok ? 'ok' : info.configured ? '' : 'missing'}">${ok ? '✓' : info.configured ? '·' : '!'}</div>
          <div class="summary-text">
            <b>${CATEGORY_LABELS[cat]}</b>
            <span>${escapeHtml(stateText)}</span>
          </div>
          <div class="summary-action">
            <button class="btn tiny ghost" data-goto="${cat}" type="button">${info.configured ? '调整' : '去配置'}</button>
          </div>
        </div>`;
    })
    .join('');

  const ready = Boolean(state.status && state.status.configured);
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">服务清单</div>
          <div class="card-sub">${ready ? '所有必需凭证已就绪，可以进入工作台' : '还有必需凭证未填写，完成后才能开始生成'}</div>
        </div>
        <div class="card-head-right">
          <button class="btn tiny ghost" id="btn-test-all" type="button">全部测试</button>
        </div>
      </div>
      <div class="summary">${rows}</div>
    </div>

    <div class="card">
      <div class="card-head"><div><div class="card-title">数据与隐私</div>
        <div class="card-sub">凭证保存在本机用户目录，仅本地服务读取</div></div></div>
      <div class="hint" id="paths-hint">正在读取路径信息…</div>
    </div>`;
}

/* --------------------------------------------------------------- rendering */

function renderNav() {
  const categories = (state.status && state.status.categories) || {};
  els.nav.innerHTML = STEPS.map((step, index) => {
    const active = state.step === step.id;
    const cat = step.id === 'finish' ? null : step.id;
    const configured = cat ? Boolean(categories[cat] && categories[cat].configured) : Boolean(state.status && state.status.configured);
    const tested = cat && state.testState[cat] === 'ok';
    const dotClass = tested || configured ? 'ok' : 'pending';
    return `
      <button class="nav-item ${active ? 'active' : ''} ${configured ? 'done' : ''}" data-step="${step.id}" type="button">
        <span class="nav-index">${configured ? '✓' : index + 1}</span>
        <span class="nav-labels">
          <span class="nav-label">${escapeHtml(step.nav)}</span>
          <span class="nav-sub">${escapeHtml(step.navSub)}</span>
        </span>
        <span class="nav-state ${dotClass}"></span>
      </button>`;
  }).join('');
}

function renderTopStatus() {
  const cat = category();
  const categories = (state.status && state.status.categories) || {};
  let html = '';
  if (cat) {
    const configured = Boolean(categories[cat] && categories[cat].configured);
    const tested = state.testState[cat] === 'ok';
    const failed = state.testState[cat] === 'fail';
    const label = failed ? '测试未通过' : tested ? '已测试通过' : configured ? '已配置' : '待配置';
    const cls = failed ? 'partial' : configured ? 'ok' : '';
    html = `<span class="badge ${cls}">${label}</span>`;
  } else {
    const ready = state.status && state.status.configured;
    html = `<span class="badge ${ready ? 'ok' : 'partial'}">${ready ? '准备就绪' : '待完成'}</span>`;
  }
  els.topStatus.innerHTML = html;
}

function renderFoot() {
  const cat = category();
  const index = STEPS.findIndex((s) => s.id === state.step);
  els.prev.style.visibility = index === 0 ? 'hidden' : 'visible';
  els.test.style.display = cat ? 'inline-flex' : 'none';
  els.next.textContent = cat ? '下一步' : '进入工作台';

  const valid = cat ? !validate(cat) : Boolean(state.status && state.status.configured);
  els.next.disabled = state.busy || (cat ? false : !valid);
  els.test.disabled = state.busy;

  const busyCat = cat && bus(cat);
  els.test.classList.toggle('is-busy', Boolean(busyCat));
  els.test.innerHTML = `${busyCat ? '<span class="spinner"></span>' : ''}${busyCat ? '测试中…' : '保存并测试'}`;

  const status = els.footStatus;
  status.className = 'foot-status';
  if (!cat) {
    if (state.status && state.status.configured) {
      status.classList.add('ok');
      els.footStatusText.textContent = '必需凭证已配置完成';
    } else {
      status.classList.add('warn');
      els.footStatusText.textContent = `还有未完成项：${(state.status && state.status.missing || []).join('、') || '未知'}`;
    }
    return;
  }
  const error = validate(cat);
  const tested = state.testState[cat];
  if (cat === 'voice' && !voiceEnabled()) {
    status.classList.add('ok');
    els.footStatusText.textContent = '语音合成未启用，可随时回来开启';
  } else if (tested === 'ok') {
    status.classList.add('ok');
    els.footStatusText.textContent = '最近一次连接测试通过，配置已保存';
  } else if (tested === 'fail') {
    status.classList.add('warn');
    els.footStatusText.textContent = '最近一次连接测试未通过，请检查凭证或地址';
  } else if (error) {
    status.classList.add('warn');
    els.footStatusText.textContent = error;
  } else {
    els.footStatusText.textContent = '填写完成后点击「保存并测试」验证连接';
  }
}

function render() {
  const step = STEPS.find((s) => s.id === state.step) || STEPS[0];
  const index = STEPS.findIndex((s) => s.id === state.step);
  els.eyebrow.textContent = index + 1 <= 4 ? `步骤 ${index + 1} / 4` : '完成';
  els.title.textContent = step.title;
  els.desc.textContent = step.desc;
  els.brandSub.textContent = state.reconfigure ? '重新配置' : '初始配置';

  let html = '';
  if (state.step === 'text') html = textStepHtml();
  else if (state.step === 'image') html = providerStepHtml('image', IMAGE_PROVIDERS, '图像服务商', '角色参考图与分镜首帧都来自这里');
  else if (state.step === 'video') html = providerStepHtml('video', VIDEO_PROVIDERS, '视频服务商', '图生视频负责把静帧变成镜头');
  else if (state.step === 'voice') html = voiceStepHtml();
  else html = finishStepHtml();

  els.body.innerHTML = html;
  renderNav();
  renderTopStatus();
  renderFoot();

  if (state.step === 'finish') {
    shell
      .info()
      .then((info) => {
        const hint = document.getElementById('paths-hint');
        if (!hint) return;
        hint.innerHTML = `配置文件：<code>${escapeHtml(info.settingsFile || '—')}</code><br/>日志目录：<code>${escapeHtml(
          info.logDir || '—'
        )}</code>`;
      })
      .catch(() => {});
  }
}

/* ----------------------------------------------------------------- actions */

function goStep(id) {
  state.step = id;
  render();
}

async function refreshSettings() {
  const payload = await shell.getSettings();
  state.settings = payload.settings;
  state.status = payload.status;
}

async function runTest(cat) {
  const error = validate(cat);
  if (error) {
    toast(error, 'error');
    return;
  }
  state.testState[cat] = 'busy';
  renderFoot();
  try {
    const response = await shell.saveAndTest(cat, buildPayload(cat));
    state.results[cat] = response.results || [];
    state.settings = response.settings.settings;
    state.status = response.status;
    const allOk = (response.results || []).every((r) => r.success);
    state.testState[cat] = allOk ? 'ok' : 'fail';
    if (allOk) await mirrorAliKey(cat);
    state.drafts[cat] = {};
    render();
    toast(allOk ? `${CATEGORY_LABELS[cat]} 连接成功，配置已保存` : `${CATEGORY_LABELS[cat]} 测试未通过，请查看结果`, allOk ? 'ok' : 'error');
  } catch (err) {
    state.testState[cat] = 'fail';
    render();
    toast(err && err.message ? err.message : '测试失败', 'error');
  }
}

/**
 * Ali Token Plan uses one key for every modality. When the LLM step saves an
 * Ali key, copy it into the image/video provider configs so the user never has
 * to paste the same secret three times.
 */
async function mirrorAliKey(cat) {
  if (cat !== 'text' || !state.mirrorAli) return;
  const key = draft('text', 'fast_llm.api_key');
  const url = String(currentValue('text', 'fast_llm.api_url'));
  if (!key || !/aliyuncs\.com/i.test(url)) return;
  for (const target of ['image', 'video']) {
    try {
      const tree = JSON.parse(JSON.stringify((state.settings && state.settings[target]) || {}));
      tree.ali_token_plan = { ...(tree.ali_token_plan || {}), api_key: key };
      const response = await shell.saveCategory(target, tree);
      if (response && response.settings) state.settings = response.settings;
      if (response && response.status) state.status = response.status;
    } catch {
      /* mirroring is a convenience — never block onboarding on it */
    }
  }
}

async function testAll() {
  const categories = ['text', 'image', 'video', 'voice'];
  for (const cat of categories) {
    if (cat === 'voice' && !voiceEnabled()) continue;
    if (validate(cat)) continue;
    state.testState[cat] = 'busy';
    renderFoot();
    try {
      const response = await shell.saveAndTest(cat, buildPayload(cat));
      state.results[cat] = response.results || [];
      state.settings = response.settings.settings;
      state.status = response.status;
      const ok = (response.results || []).every((r) => r.success);
      state.testState[cat] = ok ? 'ok' : 'fail';
      if (ok) await mirrorAliKey(cat);
      state.drafts[cat] = {};
    } catch {
      state.testState[cat] = 'fail';
    }
  }
  render();
  toast('全部测试已完成');
}

async function completeSetup() {
  if (!state.status || !state.status.configured) {
    toast('必需凭证尚未配置完成', 'error');
    return;
  }
  els.next.disabled = true;
  try {
    await shell.completeSetup();
  } catch (error) {
    toast(error.message || '进入应用失败', 'error');
    els.next.disabled = false;
  }
}

/* -------------------------------------------------------------- event wiring */

els.nav.addEventListener('click', (event) => {
  const button = event.target.closest('[data-step]');
  if (button) goStep(button.dataset.step);
});

els.body.addEventListener('input', (event) => {
  const input = event.target.closest('[data-path]');
  if (!input) return;
  const cat = input.dataset.cat;
  let value = input.value;
  if (input.type === 'number') value = value === '' ? '' : Number(value);
  setDraft(cat, input.dataset.path, value);
  renderFoot();
});

els.body.addEventListener('change', (event) => {
  const input = event.target.closest('select[data-path]');
  if (!input) return;
  setDraft(input.dataset.cat, input.dataset.path, input.value);
  renderFoot();
});

els.body.addEventListener('click', (event) => {
  const reveal = event.target.closest('[data-reveal]');
  if (reveal) {
    const input = reveal.parentElement.querySelector('input');
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    reveal.textContent = showing ? '显示' : '隐藏';
    return;
  }

  const toggle = event.target.closest('[data-toggle]');
  if (toggle) {
    const key = toggle.dataset.toggle;
    if (key === '__sameJudge') {
      state.sameJudge = !state.sameJudge;
    } else if (key === '__mirrorAli') {
      state.mirrorAli = !state.mirrorAli;
    } else {
      const cat = toggle.dataset.cat;
      const current = Boolean(currentValue(cat, key));
      setDraft(cat, key, !current);
    }
    render();
    return;
  }

  const seg = event.target.closest('[data-seg]');
  if (seg) {
    const cat = seg.dataset.seg;
    if (cat === 'voice') setDraft(cat, 'provider', seg.dataset.value);
    else setDraft(cat, 'service_type', seg.dataset.value);
    render();
    return;
  }

  const advanced = event.target.closest('[data-advanced]');
  if (advanced) {
    const cat = advanced.dataset.advanced;
    state.advanced[cat] = !state.advanced[cat];
    render();
    return;
  }

  const preset = event.target.closest('[data-preset]');
  if (preset) {
    const found = TEXT_PRESETS.find((p) => p.id === preset.dataset.preset);
    if (found) {
      setDraft('text', 'fast_llm.api_url', found.api_url);
      setDraft('text', 'fast_llm.model', found.model);
      render();
    }
    return;
  }

  const reuse = event.target.closest('[data-reuse-ali]');
  if (reuse) {
    const cat = reuse.dataset.reuseAli;
    const key = draft('text', 'fast_llm.api_key');
    if (key) {
      setDraft(cat, 'ali_token_plan.api_key', key);
      render();
      toast('已复用 LLM 步骤的 Key');
    } else {
      toast('LLM 步骤中还没有输入 Key', 'error');
    }
    return;
  }

  const goto = event.target.closest('[data-goto]');
  if (goto) {
    goStep(goto.dataset.goto);
    return;
  }

  if (event.target.closest('#btn-test-all')) {
    testAll();
  }
});

els.body.addEventListener('keydown', (event) => {
  const toggle = event.target.closest('[data-toggle]');
  if (toggle && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault();
    toggle.click();
  }
});

els.prev.addEventListener('click', () => {
  const index = STEPS.findIndex((s) => s.id === state.step);
  if (index > 0) goStep(STEPS[index - 1].id);
});

els.test.addEventListener('click', () => {
  const cat = category();
  if (cat) runTest(cat);
});

els.next.addEventListener('click', async () => {
  const index = STEPS.findIndex((s) => s.id === state.step);
  if (state.step === 'finish') {
    completeSetup();
    return;
  }
  const cat = category();
  const error = cat ? validate(cat) : null;
  if (error) {
    toast(error, 'error');
    return;
  }
  // Persist unsaved edits (e.g. "voice disabled") before advancing so the
  // final summary reflects what the backend will actually use.
  if (cat && Object.keys(state.drafts[cat] || {}).length > 0) {
    els.next.disabled = true;
    try {
      const response = await shell.saveCategory(cat, buildPayload(cat));
      if (response && response.settings) state.settings = response.settings;
      if (response && response.status) state.status = response.status;
      state.drafts[cat] = {};
    } catch (err) {
      toast(err && err.message ? err.message : '保存失败', 'error');
      els.next.disabled = false;
      return;
    }
  }
  if (index < STEPS.length - 1) goStep(STEPS[index + 1].id);
});

els.paths.addEventListener('click', async () => {
  const result = await shell.openPath('data');
  if (result && result.ok === false) toast(result.message || '无法打开目录', 'error');
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    els.next.click();
  }
});

shell.onServiceError &&
  shell.onServiceError((payload) => {
    toast(payload.message || '本地服务异常', 'error');
  });

/* --------------------------------------------------------------------- boot */

async function boot() {
  try {
    state.info = await shell.info();
    await refreshSettings();
    // Jump straight to the first category that still needs credentials.
    const order = ['text', 'image', 'video', 'voice'];
    if (state.reconfigure) {
      state.step = 'text';
    } else {
      const missing = order.find(
        (cat) => state.status && state.status.categories && !state.status.categories[cat].configured
      );
      state.step = missing || 'finish';
    }
    render();
  } catch (error) {
    els.body.innerHTML = `<div class="card"><div class="card-title">无法读取配置</div>
      <div class="hint warn" style="margin-top:8px">${escapeHtml(error && error.message ? error.message : String(error))}</div>
      <div class="hint" style="margin-top:10px">请返回启动窗口重试，或打开日志目录查看详情。</div></div>`;
  }
}

boot();
