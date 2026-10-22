'use strict';

/**
 * Thin HTTP bridge to the backend Settings Center.
 *
 * The renderer never talks to the API directly: the setup wizard runs with
 * contextIsolation and does every call through IPC, which keeps credentials out
 * of renderer network logs and avoids CORS/file:// origin issues.
 */
const { scoped } = require('./logger');

const log = scoped('settings-api');

async function request(baseUrl, path, { method = 'GET', body, timeoutMs = 120_000 } = {}) {
  if (!baseUrl) throw new Error('后端服务尚未就绪');
  const url = `${baseUrl.replace(/\/+$/, '')}${path}`;
  const started = Date.now();
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    log.error(`${method} ${url} failed: ${error.message}`);
    throw new Error(`无法连接本地服务：${error.message}`);
  }
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const detail =
      (data && (data.detail || data.message)) || (typeof data === 'string' ? data : '') || response.statusText;
    log.error(`${method} ${url} -> ${response.status}: ${String(detail).slice(0, 300)}`);
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  log.info(`${method} ${path} -> ${response.status} (${Date.now() - started}ms)`);
  return data;
}

function hasKey(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function pickServiceKey(category, settings) {
  if (!settings) return null;
  if (category === 'image') {
    const service = settings.image?.service_type || 'ali_token_plan';
    return { service, key: settings.image?.[service]?.api_key };
  }
  if (category === 'video') {
    const service = settings.video?.service_type || 'ali_token_plan';
    return { service, key: settings.video?.[service]?.api_key };
  }
  if (category === 'voice') {
    const voice = settings.voice || {};
    if (voice.provider === 'dashscope_native') {
      return { service: 'dashscope_native', key: voice.native_api_key || voice.api_key };
    }
    return { service: voice.provider || 'auto', key: voice.api_key || voice.native_api_key };
  }
  return null;
}

/**
 * A machine is "configured" when every credential the pipeline truly needs is
 * present. Voice is optional (silent videos are legitimate), but when the user
 * enabled it we insist on a key.
 */
function evaluate(settings) {
  const missing = [];
  const categories = {
    text: { configured: false, detail: '' },
    image: { configured: false, detail: '' },
    video: { configured: false, detail: '' },
    voice: { configured: false, detail: '' },
  };

  const llmKey = settings?.text?.fast_llm?.api_key;
  categories.text.configured = hasKey(llmKey);
  categories.text.detail = settings?.text?.fast_llm?.model || '';
  if (!categories.text.configured) missing.push('LLM 文本模型');

  for (const category of ['image', 'video']) {
    const picked = pickServiceKey(category, settings);
    const ok = hasKey(picked?.key);
    categories[category].configured = ok;
    categories[category].detail = picked?.service || '';
    if (!ok) missing.push(category === 'image' ? '图像生成' : '视频生成');
  }

  const voiceEnabled = Boolean(settings?.voice?.enabled);
  const voicePicked = pickServiceKey('voice', settings);
  const voiceOk = !voiceEnabled || hasKey(voicePicked?.key);
  categories.voice.configured = voiceOk;
  categories.voice.detail = voiceEnabled ? voicePicked?.service || '' : '未启用';
  if (voiceEnabled && !hasKey(voicePicked?.key)) missing.push('语音合成');

  return {
    configured: missing.length === 0,
    missing,
    categories,
  };
}

class SettingsBridge {
  constructor(runtime) {
    this.runtime = runtime;
  }

  get baseUrl() {
    // Set by the service manager once the backend is up.
    return this.runtime.backendUrl;
  }

  async getSettings() {
    return request(this.baseUrl, '/api/v1/settings');
  }

  async update(category, payload) {
    const body = { [category]: payload };
    return request(this.baseUrl, '/api/v1/settings', { method: 'PUT', body });
  }

  async test(category) {
    return request(this.baseUrl, `/api/v1/settings/test/${category}`, {
      method: 'POST',
      timeoutMs: 180_000,
    });
  }

  async saveAndTest(category, payload) {
    if (payload) {
      await this.update(category, payload);
    }
    const results = await this.test(category);
    const settings = await this.getSettings();
    return { results, settings, status: evaluate(settings.settings) };
  }
}

module.exports = { SettingsBridge, evaluate, hasKey, pickServiceKey };
