'use client';

/**
 * Settings Center page.
 *
 * Configure text / voice / video / image / agent model services at runtime.
 * Changes are persisted by the backend and hot-applied without restart.
 * The Agent tab hosts the AI configuration assistant (AragonAgent).
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '@/components/ui';
import { Checkbox } from '@/components/ui/ConfigPanel';
import ProviderCard from '@/components/settings/ProviderCard';
import SettingsChatPanel from '@/components/settings/SettingsChatPanel';
import { apiClient } from '@/lib/api';
import type {
  ModelSettings,
  ConnectionTestResult,
  AgentStatus,
} from '@/lib/api';
import { logger } from '@/lib/logger';
import { invalidateActiveImageService } from '@/lib/imageService';

type Category = 'text' | 'voice' | 'video' | 'image' | 'agent';
type Draft = Record<string, unknown>;

const CATEGORIES: Array<{ key: Category; label: string }> = [
  { key: 'text', label: '文字模型' },
  { key: 'voice', label: '语音模型' },
  { key: 'video', label: '视频模型' },
  { key: 'image', label: '图像模型' },
  { key: 'agent', label: 'Agent 助手' },
];

/** Ali Coding Plan (Token Plan) one-click preset values. */
const ALI_TOKEN_PLAN_URL =
  'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1';

const ALI_CODING_PLAN_PRESET = {
  text: {
    fast_llm: { api_url: ALI_TOKEN_PLAN_URL, model: 'qwen3.8-max' },
    judge_llm: { api_url: ALI_TOKEN_PLAN_URL, model: 'qwen3.8-max' },
  },
  voice: {
    enabled: true,
    // 该网关没有一次性 HTTP 合成接口，auto 会把请求路由到 DashScope 原生接口
    provider: 'auto',
    base_url: ALI_TOKEN_PLAN_URL,
    model: 'qwen-audio-3.0-tts-plus',
    default_voice: 'Cherry',
  },
  video: {
    service_type: 'ali_token_plan',
    ali_token_plan: {
      base_url: ALI_TOKEN_PLAN_URL,
      endpoint: '/api/v1/services/aigc/video-generation/video-synthesis',
      model: 'happyhorse-1.1-i2v',
      t2v_model: 'happyhorse-1.1-t2v',
      r2v_model: 'happyhorse-1.1-r2v',
      default_size: '1280x720',
      default_duration: 5,
    },
  },
  image: {
    service_type: 'ali_token_plan',
    ali_token_plan: {
      base_url: ALI_TOKEN_PLAN_URL,
      endpoint: '/api/v1/services/aigc/multimodal-generation/generation',
      model: 'wan2.7-image-pro',
    },
  },
} as const;

export default function SettingsPage() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [dirty, setDirty] = useState<Record<string, boolean>>({});
  const [savingCat, setSavingCat] = useState<string | null>(null);
  const [testingCat, setTestingCat] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, ConnectionTestResult[]>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // ---------------- load ----------------

  const initDrafts = (s: ModelSettings): Record<string, Draft> => {
    const stripKeys = (obj: Record<string, unknown>): Draft => {
      const out: Draft = {};
      for (const [k, v] of Object.entries(obj)) {
        if (v && typeof v === 'object' && !Array.isArray(v)) {
          out[k] = stripKeys(v as Record<string, unknown>);
        } else if (k === 'api_key' || k.endsWith('_api_key')) {
          // write-only: untouched until the user types. Covers api_key AND
          // nested keys such as voice.native_api_key, which the GET response
          // returns masked - sending that mask back would overwrite the key.
          out[k] = undefined;
        } else {
          out[k] = v;
        }
      }
      return out;
    };
    const out: Record<string, Draft> = {};
    for (const cat of ['text', 'voice', 'video', 'image', 'agent'] as Category[]) {
      out[cat] = stripKeys(s[cat] as unknown as Record<string, unknown>);
    }
    return out;
  };

  const refresh = useCallback(async (withStatus = true) => {
    try {
      const result = await apiClient.settings.get();
      setSettings(result.settings);
      setDrafts(initDrafts(result.settings));
      setDirty({});
      setLoadError(null);
      if (withStatus) {
        try {
          setAgentStatus(await apiClient.settings.agentStatus());
        } catch {
          setAgentStatus(null);
        }
      }
    } catch (err) {
      logger.error('SettingsPage', 'Failed to load settings', err);
      setLoadError(err instanceof Error ? err.message : '加载设置失败');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // ---------------- mutations ----------------

  const setField = (
    category: Category,
    path: string, // 'veo3.base_url' or 'service_type'
    value: unknown
  ) => {
    setDrafts((prev) => {
      const cat = { ...(prev[category] ?? {}) };
      const parts = path.split('.');
      let node = cat;
      for (const part of parts.slice(0, -1)) {
        node[part] = { ...(node[part] as Draft) };
        node = node[part] as Draft;
      }
      node[parts[parts.length - 1]] = value;
      return { ...prev, [category]: cat };
    });
    setDirty((prev) => ({ ...prev, [category]: true }));
    setNotice(null);
  };

  const getField = (category: Category, path: string): unknown => {
    let node = drafts[category] as unknown;
    for (const part of path.split('.')) {
      if (node == null) return undefined;
      node = (node as Draft)[part];
    }
    return node;
  };

  /** Deep-merge a preset onto one category draft; never touches api_key. */
  const mergeDraft = (base: Draft, overlay: Record<string, unknown>): Draft => {
    const out: Draft = { ...base };
    for (const [k, v] of Object.entries(overlay)) {
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        out[k] = mergeDraft((out[k] as Draft) ?? {}, v as Record<string, unknown>);
      } else if (k !== 'api_key' && !k.endsWith('_api_key')) {
        // *_api_key is write-only: keep whatever the user already typed/stored
        out[k] = v;
      }
    }
    return out;
  };

  const applyAliCodingPlanPreset = () => {
    setDrafts((prev) => {
      const next = { ...prev };
      for (const [cat, preset] of Object.entries(ALI_CODING_PLAN_PRESET)) {
        next[cat] = mergeDraft(
          (prev[cat] ?? {}) as Draft,
          preset as unknown as Record<string, unknown>
        );
      }
      return next;
    });
    setDirty({ text: true, voice: true, video: true, image: true });
    setNotice('已填入 Ali Coding Plan 预设（API Key 使用后端 .env 默认值），请逐类保存生效');
  };

  const saveCategory = async (category: Category) => {
    setSavingCat(category);
    setNotice(null);
    try {
      const result = await apiClient.settings.update({
        [category]: drafts[category],
      });
      setSettings(result.settings);
      setDrafts((prev) => ({
        ...prev,
        ...initDrafts(result.settings),
      }));
      setDirty((prev) => ({ ...prev, [category]: false }));
      // The workflow steps resolve the active image service from these settings;
      // drop the cached value so the change takes effect immediately.
      invalidateActiveImageService();
      setNotice('已保存并即时生效（无需重启后端）');
      if (category === 'agent') {
        setAgentStatus(await apiClient.settings.agentStatus().catch(() => null));
      }
    } catch (err) {
      logger.error('SettingsPage', `Failed to save ${category}`, err);
      setNotice(`保存失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSavingCat(null);
    }
  };

  const testCategory = async (category: Category) => {
    setTestingCat(category);
    try {
      const results = await apiClient.settings.test(category);
      setTestResults((prev) => ({ ...prev, [category]: results }));
    } catch (err) {
      logger.error('SettingsPage', `Test ${category} failed`, err);
      setTestResults((prev) => ({
        ...prev,
        [category]: [
          {
            category,
            target: '',
            success: false,
            latency_ms: null,
            message: err instanceof Error ? err.message : String(err),
            detail: null,
            verified: 'full',
          },
        ],
      }));
    } finally {
      setTestingCat(null);
    }
  };

  const resultFor = (category: Category, target: string) =>
    (testResults[category] ?? []).find((r) => r.target === target) ?? null;

  const secretPlaceholder = (maskedKey: string | null | undefined) =>
    maskedKey ?? '';

  // ---------------- render helpers ----------------

  const SaveBar = ({ category }: { category: Category }) => (
    <div className="flex items-center gap-3 mt-2">
      <Button
        loading={savingCat === category}
        disabled={!dirty[category]}
        onClick={() => saveCategory(category)}
      >
        保存{dirty[category] ? '' : '（无变更）'}
      </Button>
      <Button
        variant="secondary"
        loading={testingCat === category}
        onClick={() => testCategory(category)}
      >
        测试连接
      </Button>
      {notice && dirty[category] === false && (
        <span className="text-sm text-success-text">{notice}</span>
      )}
    </div>
  );

  const ToggleRow = ({
    category,
    path,
    label,
    description,
  }: {
    category: Category;
    path: string;
    label: string;
    description: string;
  }) => (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm font-medium text-text-primary">{label}</p>
        <p className="text-xs text-text-tertiary">{description}</p>
      </div>
      <Checkbox
        label={label}
        checked={Boolean(getField(category, path))}
        onChange={(v) => setField(category, path, v)}
      />
    </div>
  );

  // ---------------- load states ----------------

  if (loadError && !settings) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 px-8 py-8">
          <div className="max-w-3xl mx-auto card-apple p-8 text-center">
            <div className="text-5xl mb-4">⚠️</div>
            <h1 className="text-2xl font-semibold text-text-primary mb-2">无法加载设置</h1>
            <p className="text-text-secondary mb-6">{loadError}</p>
            <Link href="/" className="btn-apple btn-apple-secondary px-5 py-2.5">
              返回首页
            </Link>
          </div>
        </main>
      </div>
    );
  }

  if (!settings || !drafts.text) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="spinner-apple w-10 h-10" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 px-6 py-8 overflow-y-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-[-0.02em] text-text-primary mb-1">设置中心</h1>
              <p className="text-text-secondary">
                随时配置文字 / 语音 / 视频 / 图像 / Agent 模型服务的 URL、凭证与模型，保存后即时生效
              </p>
            </div>
            <Button
              variant="secondary"
              onClick={applyAliCodingPlanPreset}
              title="一键填入阿里云 Token Plan 网关地址与各模型默认值（API Key 沿用已保存配置）"
            >
              ⚡ 使用 Ali Coding Plan
            </Button>
          </div>

          {notice && (
            <div className="mb-4 p-3 rounded-apple-md bg-success-soft border border-success-border text-success-text text-sm">
              {notice}
            </div>
          )}

          <Tabs defaultValue="text">
            <TabsList>
              {CATEGORIES.map((c) => (
                <TabsTrigger key={c.key} value={c.key}>
                  {c.label}
                  {dirty[c.key] && <span className="ml-1 text-apple-orange">•</span>}
                </TabsTrigger>
              ))}
            </TabsList>

            {/* ==================== TEXT ==================== */}
            <TabsContent value="text">
              <ProviderCard
                title="快速 LLM"
                subtitle="用于剧本润色与提示词优化（OpenAI 兼容接口）"
                fields={[
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'api_url', label: 'API URL', placeholder: 'https://.../v1' },
                  { key: 'model', label: '模型', placeholder: 'qwen-max-latest' },
                ]}
                values={{
                  api_key: getField('text', 'fast_llm.api_key'),
                  api_url: getField('text', 'fast_llm.api_url'),
                  model: getField('text', 'fast_llm.model'),
                }}
                maskedKey={secretPlaceholder(settings.text.fast_llm.api_key)}
                onChange={(k, v) => setField('text', `fast_llm.${k}`, v)}
                testing={testingCat === 'text'}
                testResult={resultFor('text', 'fast_llm')}
              />
              <ProviderCard
                title="评审 LLM"
                subtitle="多模态模型，用于角色一致性评分（需支持图片输入）"
                fields={[
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'api_url', label: 'API URL', placeholder: 'https://.../v3' },
                  { key: 'model', label: '模型', placeholder: 'doubao-seed-1-6-251015' },
                ]}
                values={{
                  api_key: getField('text', 'judge_llm.api_key'),
                  api_url: getField('text', 'judge_llm.api_url'),
                  model: getField('text', 'judge_llm.model'),
                }}
                maskedKey={secretPlaceholder(settings.text.judge_llm.api_key)}
                onChange={(k, v) => setField('text', `judge_llm.${k}`, v)}
                testing={testingCat === 'text'}
                testResult={resultFor('text', 'judge_llm')}
              />
              <Card className="mb-4">
                <ToggleRow
                  category="text"
                  path="enable_prompt_optimization"
                  label="启用提示词优化"
                  description="生成图片/视频前用快速 LLM 优化提示词"
                />
                <ToggleRow
                  category="text"
                  path="enable_character_consistency_judge"
                  label="启用角色一致性评分"
                  description="用评审 LLM 对候选图打分，选择最一致的一张"
                />
              </Card>
              <SaveBar category="text" />
            </TabsContent>

            {/* ==================== VOICE ==================== */}
            <TabsContent value="voice">
              <ProviderCard
                title="语音合成 (TTS)"
                subtitle="Ali Token Plan 网关虽然列出 qwen-audio-3.0-tts-plus，但没有可用的 HTTP 合成接口（/audio/speech 返回 InvalidParameter）。请在下表选择通道：改用下方 DashScope 原生鉴权，或换别的 OpenAI 兼容 TTS 网关。"
                fields={[
                  {
                    key: 'provider',
                    label: 'TTS 通道',
                    type: 'select',
                    options: [
                      { value: 'auto', label: '自动（DashScope 主机/Token Plan 走原生）' },
                      { value: 'openai_compatible', label: 'OpenAI 兼容 /audio/speech' },
                      { value: 'dashscope_native', label: 'DashScope 原生合成' },
                      { value: 'volc_tts2', label: '火山引擎 TTS 2.0（豆包语音合成）' },
                    ],
                  },
                  { key: 'base_url', label: 'Base URL', placeholder: 'https://api.openai.com/v1' },
                  { key: 'api_key', label: 'API Key（兼容网关）', secret: true },
                  { key: 'model', label: '模型', placeholder: 'tts-1 / tts-1-hd' },
                  { key: 'default_voice', label: '默认音色', placeholder: 'alloy' },
                  {
                    key: 'default_format',
                    label: '音频格式',
                    type: 'select',
                    options: ['mp3', 'opus', 'aac', 'flac', 'wav', 'pcm'].map((v) => ({
                      value: v,
                      label: v,
                    })),
                  },
                  { key: 'default_speed', label: '语速 (0.25-4.0)', type: 'number' },
                ]}
                values={{
                  provider: getField('voice', 'provider'),
                  base_url: getField('voice', 'base_url'),
                  api_key: getField('voice', 'api_key'),
                  model: getField('voice', 'model'),
                  default_voice: getField('voice', 'default_voice'),
                  default_format: getField('voice', 'default_format'),
                  default_speed: getField('voice', 'default_speed'),
                }}
                maskedKey={secretPlaceholder(settings.voice.api_key)}
                onChange={(k, v) => setField('voice', k, v)}
                testing={testingCat === 'voice'}
                testResult={resultFor('voice', 'tts')}
              />

              <ProviderCard
                title="DashScope 原生语音合成"
                subtitle="TTS_PROVIDER=dashscope_native 时使用：POST {base}/api/v1/services/aigc/multimodal-generation/generation（模型 qwen-tts / cosyvoice-v2）。Token Plan 网关没有该通道，需要单独的 DashScope Key。"
                fields={[
                  { key: 'native_base_url', label: 'Base URL', placeholder: 'https://dashscope.aliyuncs.com' },
                  { key: 'native_api_key', label: 'DashScope API Key', secret: true },
                  { key: 'native_model', label: '模型', placeholder: 'qwen-tts / cosyvoice-v2' },
                  { key: 'native_voice', label: '音色', placeholder: 'Cherry / longxiaochun_v2' },
                ]}
                values={{
                  native_base_url: getField('voice', 'native_base_url'),
                  native_api_key: getField('voice', 'native_api_key'),
                  native_model: getField('voice', 'native_model'),
                  native_voice: getField('voice', 'native_voice'),
                }}
                maskedKey={secretPlaceholder(settings.voice.native_api_key)}
                onChange={(k, v) => setField('voice', k, v)}
              />
              <Card className="mb-4">
                <ToggleRow
                  category="voice"
                  path="enabled"
                  label="启用语音合成"
                  description="启用后可通过 POST /api/v1/tts/generate 生成配音"
                />
              </Card>
              <SaveBar category="voice" />
            </TabsContent>

            {/* ==================== VIDEO ==================== */}
            <TabsContent value="video">
              <Card className="mb-4">
                <label className="block text-sm font-medium text-text-primary mb-2">
                  默认视频服务
                </label>
                <div className="flex gap-2 flex-wrap">
                  {(['ali_token_plan', 'doubao', 'veo3', 'sora2'] as const).map((svc) => (
                    <button
                      key={svc}
                      type="button"
                      onClick={() => setField('video', 'service_type', svc)}
                      className={`px-4 py-2 rounded-apple-md border-2 text-sm font-medium transition-colors ${
                        getField('video', 'service_type') === svc
                          ? 'border-accent bg-accent-soft text-accent-text'
                          : 'border-hairline text-text-secondary hover:text-text-primary'
                      }`}
                    >
                      {svc === 'veo3' ? 'Veo3' : svc === 'sora2' ? 'Sora2' : 'Ali Coding Plan'}
                    </button>
                  ))}
                </div>
              </Card>

              <ProviderCard
                title="Veo3"
                subtitle="图生视频（提交 + 轮询）"
                badge={getField('video', 'service_type') === 'veo3' ? '当前使用' : undefined}
                fields={[
                  { key: 'base_url', label: 'Base URL' },
                  { key: 'endpoint', label: 'Endpoint', placeholder: '/v1/videos' },
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'model', label: '模型', placeholder: 'veo_3_1' },
                ]}
                values={{
                  base_url: getField('video', 'veo3.base_url'),
                  endpoint: getField('video', 'veo3.endpoint'),
                  api_key: getField('video', 'veo3.api_key'),
                  model: getField('video', 'veo3.model'),
                }}
                maskedKey={secretPlaceholder(settings.video.veo3.api_key)}
                onChange={(k, v) => setField('video', `veo3.${k}`, v)}
                testing={testingCat === 'video'}
                testResult={resultFor('video', 'veo3')}
              />

              <ProviderCard
                title="Sora2"
                subtitle="图生视频（OpenAI 格式，支持 4/8/12s 与分镜）"
                badge={getField('video', 'service_type') === 'sora2' ? '当前使用' : undefined}
                fields={[
                  { key: 'base_url', label: 'Base URL' },
                  { key: 'endpoint', label: 'Endpoint', placeholder: '/v1/videos' },
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'model', label: '模型', placeholder: 'sora-2 / sora-2-pro' },
                  { key: 'default_size', label: '默认分辨率', placeholder: '1280x720' },
                  { key: 'default_duration', label: '默认时长（秒）', type: 'number' },
                ]}
                values={{
                  base_url: getField('video', 'sora2.base_url'),
                  endpoint: getField('video', 'sora2.endpoint'),
                  api_key: getField('video', 'sora2.api_key'),
                  model: getField('video', 'sora2.model'),
                  default_size: getField('video', 'sora2.default_size'),
                  default_duration: getField('video', 'sora2.default_duration'),
                }}
                maskedKey={secretPlaceholder(settings.video.sora2.api_key)}
                onChange={(k, v) => setField('video', `sora2.${k}`, v)}
                testing={testingCat === 'video'}
                testResult={resultFor('video', 'sora2')}
              />

              <ProviderCard
                title="Ali Coding Plan (Token Plan)"
                subtitle="阿里云 Token Plan 网关（DashScope 原生异步任务，happyhorse-1.1 系列：图生视频/文生视频/参考生视频）"
                badge={getField('video', 'service_type') === 'ali_token_plan' ? '当前使用' : undefined}
                fields={[
                  { key: 'base_url', label: 'Base URL', placeholder: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1' },
                  { key: 'endpoint', label: 'Endpoint', placeholder: '/api/v1/services/aigc/video-generation/video-synthesis' },
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'model', label: '图生视频模型 (i2v)', placeholder: 'happyhorse-1.1-i2v' },
                  { key: 't2v_model', label: '文生视频模型 (t2v)', placeholder: 'happyhorse-1.1-t2v' },
                  { key: 'r2v_model', label: '参考生视频模型 (r2v)', placeholder: 'happyhorse-1.1-r2v' },
                  { key: 'default_size', label: '默认分辨率', placeholder: '1280x720' },
                  { key: 'default_duration', label: '默认时长（秒）', type: 'number' },
                  {
                    key: 'watermark',
                    label: '成品水印 (parameters.watermark)',
                    type: 'select',
                    options: [
                      { value: 'false', label: '关闭（无水印，默认）' },
                      { value: 'true', label: '开启（带 refiner_watermark 标记）' },
                    ],
                    hint: '以 parameters.watermark 提交给网关；关闭后成品不再带 refiner_watermark 变体',
                  },
                ]}
                values={{
                  base_url: getField('video', 'ali_token_plan.base_url'),
                  endpoint: getField('video', 'ali_token_plan.endpoint'),
                  api_key: getField('video', 'ali_token_plan.api_key'),
                  model: getField('video', 'ali_token_plan.model'),
                  t2v_model: getField('video', 'ali_token_plan.t2v_model'),
                  r2v_model: getField('video', 'ali_token_plan.r2v_model'),
                  default_size: getField('video', 'ali_token_plan.default_size'),
                  default_duration: getField('video', 'ali_token_plan.default_duration'),
                  watermark: String(
                    getField('video', 'ali_token_plan.watermark') ?? false
                  ),
                }}
                maskedKey={secretPlaceholder(settings.video.ali_token_plan?.api_key)}
                onChange={(k, v) =>
                  setField(
                    'video',
                    `ali_token_plan.${k}`,
                    // <Select> only yields strings; the backend expects a boolean
                    k === 'watermark' ? v === 'true' : v
                  )
                }
                testing={testingCat === 'video'}
                testResult={resultFor('video', 'ali_token_plan')}
              />
              <ProviderCard
                title="豆包 Seedance（火山方舟）"
                subtitle="火山方舟 Ark 异步视频任务：图生视频 / 文生视频。非 OpenAI 兼容接口，分辨率 / 时长 / 比例为 JSON 字段。"
                badge={getField('video', 'service_type') === 'doubao' ? '当前使用' : undefined}
                fields={[
                  { key: 'api_key', label: 'Ark API Key', secret: true, hint: '火山方舟控制台 → API Key 管理（UUID 形式）' },
                  { key: 'model', label: '图生视频模型 (i2v)', placeholder: 'doubao-seedance-2-0-260128' },
                  { key: 't2v_model', label: '文生视频模型 (t2v)', placeholder: 'doubao-seedance-2-0-260128' },
                  {
                    key: 'default_resolution',
                    label: '默认分辨率',
                    type: 'select',
                    options: [
                      { value: '480p', label: '480p' },
                      { value: '720p', label: '720p' },
                      { value: '1080p', label: '1080p' },
                    ],
                  },
                  { key: 'default_ratio', label: '画面比例', placeholder: '16:9' },
                  { key: 'default_duration', label: '默认时长（秒，4-15）', type: 'number' },
                  { key: 'base_url', label: 'Base URL', placeholder: 'https://ark.cn-beijing.volces.com/api/v3' },
                  { key: 'endpoint', label: 'Endpoint', placeholder: '/contents/generations/tasks' },
                ]}
                values={{
                  base_url: getField('video', 'doubao.base_url'),
                  endpoint: getField('video', 'doubao.endpoint'),
                  api_key: getField('video', 'doubao.api_key'),
                  model: getField('video', 'doubao.model'),
                  t2v_model: getField('video', 'doubao.t2v_model'),
                  default_resolution: getField('video', 'doubao.default_resolution'),
                  default_ratio: getField('video', 'doubao.default_ratio'),
                  default_duration: getField('video', 'doubao.default_duration'),
                }}
                maskedKey={secretPlaceholder(settings.video.doubao?.api_key)}
                onChange={(k, v) => setField('video', `doubao.${k}`, v)}
                testing={testingCat === 'video'}
                testResult={resultFor('video', 'doubao')}
              />
              <SaveBar category="video" />
            </TabsContent>

            {/* ==================== IMAGE ==================== */}
            <TabsContent value="image">
              <Card className="mb-4">
                <label className="block text-sm font-medium text-text-primary mb-2">
                  默认图像服务
                </label>
                <div className="flex gap-2 flex-wrap">
                  {(['ali_token_plan', 'doubao', 'nano_banana', 'midjourney'] as const).map((svc) => (
                    <button
                      key={svc}
                      type="button"
                      onClick={() => setField('image', 'service_type', svc)}
                      className={`px-4 py-2 rounded-apple-md border-2 text-sm font-medium transition-colors ${
                        getField('image', 'service_type') === svc
                          ? 'border-accent bg-accent-soft text-accent-text'
                          : 'border-hairline text-text-secondary hover:text-text-primary'
                      }`}
                    >
                      {svc === 'nano_banana'
                        ? 'Nano Banana'
                        : svc === 'doubao'
                          ? '豆包'
                          : svc === 'ali_token_plan'
                            ? 'Ali Coding Plan'
                            : 'Midjourney'}
                    </button>
                  ))}
                </div>
              </Card>

              <ProviderCard
                title="豆包 Doubao"
                subtitle="火山引擎方舟图像生成（文生图 + 图生图）"
                badge={getField('image', 'service_type') === 'doubao' ? '当前使用' : undefined}
                fields={[
                  { key: 'base_url', label: 'Base URL' },
                  { key: 'endpoint', label: 'Endpoint', placeholder: '/api/v3/images/generations' },
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'model', label: '模型', placeholder: 'doubao-seedream-4-5-251128' },
                ]}
                values={{
                  base_url: getField('image', 'doubao.base_url'),
                  endpoint: getField('image', 'doubao.endpoint'),
                  api_key: getField('image', 'doubao.api_key'),
                  model: getField('image', 'doubao.model'),
                }}
                maskedKey={secretPlaceholder(settings.image.doubao.api_key)}
                onChange={(k, v) => setField('image', `doubao.${k}`, v)}
                testing={testingCat === 'image'}
                testResult={resultFor('image', 'doubao')}
              />

              <ProviderCard
                title="Nano Banana Pro"
                subtitle="OpenAI 兼容图像生成"
                badge={getField('image', 'service_type') === 'nano_banana' ? '当前使用' : undefined}
                fields={[
                  { key: 'base_url', label: 'Base URL' },
                  { key: 'endpoint', label: 'Endpoint', placeholder: '/v1/images/generations' },
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'model', label: '模型', placeholder: 'gemini-3-pro-image-preview' },
                ]}
                values={{
                  base_url: getField('image', 'nano_banana.base_url'),
                  endpoint: getField('image', 'nano_banana.endpoint'),
                  api_key: getField('image', 'nano_banana.api_key'),
                  model: getField('image', 'nano_banana.model'),
                }}
                maskedKey={secretPlaceholder(settings.image.nano_banana.api_key)}
                onChange={(k, v) => setField('image', `nano_banana.${k}`, v)}
                testing={testingCat === 'image'}
                testResult={resultFor('image', 'nano_banana')}
              />

              <ProviderCard
                title="Midjourney 代理"
                subtitle="Midjourney Proxy（提交 + 轮询 + 自动放大）"
                badge={getField('image', 'service_type') === 'midjourney' ? '当前使用' : undefined}
                fields={[
                  { key: 'base_url', label: 'Base URL' },
                  { key: 'api_key', label: 'API Key', secret: true },
                  {
                    key: 'bot_type',
                    label: 'Bot 类型',
                    type: 'select',
                    options: [
                      { value: 'MID_JOURNEY', label: 'MID_JOURNEY' },
                      { value: 'NIJI_JOURNEY', label: 'NIJI_JOURNEY' },
                    ],
                  },
                  { key: 'poll_interval', label: '轮询间隔（秒）', type: 'number' },
                  { key: 'max_poll_attempts', label: '最大轮询次数', type: 'number' },
                ]}
                values={{
                  base_url: getField('image', 'midjourney.base_url'),
                  api_key: getField('image', 'midjourney.api_key'),
                  bot_type: getField('image', 'midjourney.bot_type'),
                  poll_interval: getField('image', 'midjourney.poll_interval'),
                  max_poll_attempts: getField('image', 'midjourney.max_poll_attempts'),
                }}
                maskedKey={secretPlaceholder(settings.image.midjourney.api_key)}
                onChange={(k, v) => setField('image', `midjourney.${k}`, v)}
                testing={testingCat === 'image'}
                testResult={resultFor('image', 'midjourney')}
              />

              <ProviderCard
                title="Ali Coding Plan (Token Plan)"
                subtitle="阿里云 Token Plan 网关（DashScope 原生接口，wan2.7-image-pro 文生图 + 参考图生图）"
                badge={getField('image', 'service_type') === 'ali_token_plan' ? '当前使用' : undefined}
                fields={[
                  { key: 'base_url', label: 'Base URL', placeholder: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1' },
                  { key: 'endpoint', label: 'Endpoint', placeholder: '/api/v1/services/aigc/multimodal-generation/generation' },
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'model', label: '模型', placeholder: 'wan2.7-image-pro' },
                ]}
                values={{
                  base_url: getField('image', 'ali_token_plan.base_url'),
                  endpoint: getField('image', 'ali_token_plan.endpoint'),
                  api_key: getField('image', 'ali_token_plan.api_key'),
                  model: getField('image', 'ali_token_plan.model'),
                }}
                maskedKey={secretPlaceholder(settings.image.ali_token_plan?.api_key)}
                onChange={(k, v) => setField('image', `ali_token_plan.${k}`, v)}
                testing={testingCat === 'image'}
                testResult={resultFor('image', 'ali_token_plan')}
              />
              <SaveBar category="image" />
            </TabsContent>

            {/* ==================== AGENT ==================== */}
            <TabsContent value="agent">
              <div className="mb-4">
                <SettingsChatPanel
                  agentStatus={agentStatus}
                  onSettingsUpdated={(s) => {
                    setSettings(s);
                    setDrafts(initDrafts(s));
                    setDirty({});
                    setNotice('配置已被 AI 助手更新并即时生效');
                  }}
                />
              </div>

              <ProviderCard
                title="Agent 大模型"
                subtitle="驱动 AI 配置助手的大模型（OpenAI 兼容端点 / Anthropic / Google）"
                fields={[
                  {
                    key: 'provider',
                    label: '提供方',
                    type: 'select',
                    options: [
                      { value: 'openai', label: 'OpenAI 兼容（DeepSeek/Qwen/硅基流动…）' },
                      { value: 'anthropic', label: 'Anthropic' },
                      { value: 'google', label: 'Google' },
                    ],
                  },
                  { key: 'base_url', label: 'Base URL（OpenAI 兼容端点必填，官方 API 留空）', placeholder: 'https://api.deepseek.com/v1' },
                  { key: 'api_key', label: 'API Key', secret: true },
                  { key: 'model', label: '模型', placeholder: 'gpt-4o / deepseek-chat / qwen-max' },
                  { key: 'max_turns', label: '单次对话最大轮次', type: 'number' },
                  { key: 'timeout_seconds', label: '单次对话超时（秒）', type: 'number' },
                  { key: 'aragon_cli_path', label: 'aragon CLI 路径', placeholder: 'aragon' },
                ]}
                values={{
                  provider: getField('agent', 'provider'),
                  base_url: getField('agent', 'base_url'),
                  api_key: getField('agent', 'api_key'),
                  model: getField('agent', 'model'),
                  max_turns: getField('agent', 'max_turns'),
                  timeout_seconds: getField('agent', 'timeout_seconds'),
                  aragon_cli_path: getField('agent', 'aragon_cli_path'),
                }}
                maskedKey={secretPlaceholder(settings.agent.api_key)}
                onChange={(k, v) => setField('agent', k, v)}
                testing={testingCat === 'agent'}
                testResult={resultFor('agent', 'agent_llm')}
              />

              <Card className="mb-4">
                <ToggleRow
                  category="agent"
                  path="enabled"
                  label="启用 Agent 协助配置"
                  description="保存后在上方聊天面板与助手对话"
                />
                {agentStatus && (
                  <div className="mt-2 p-3 rounded-apple-md bg-background-deep border border-hairline text-sm text-text-secondary">
                    <p>
                      aragon CLI：
                      {agentStatus.aragon_installed
                        ? `已安装${agentStatus.aragon_version ? `（v${agentStatus.aragon_version}）` : ''}`
                        : '未安装（降级为纯 LLM 建议模式，安装命令：npm i -g @aragon-agent/cli）'}
                    </p>
                    <p className="mt-1">{agentStatus.message}</p>
                  </div>
                )}
              </Card>
              <SaveBar category="agent" />
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}
