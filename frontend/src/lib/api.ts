/**
 * Centralized API client.
 *
 * All backend payloads use snake_case; responses are returned as-is.
 * Non-2xx responses throw APIException with the server's error envelope.
 */

import {
  Project,
  CreateProjectRequest,
  TaskStatusResponse,
  APIException,
} from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export function getApiBase(): string {
  return API_BASE;
}

// ======================================================================
// Core fetch wrapper
// ======================================================================

interface RequestOptions {
  method?: string;
  body?: unknown;
  timeoutMs?: number;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, timeoutMs = 60_000 } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    clearTimeout(timer);
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new APIException(`Request timed out after ${timeoutMs / 1000}s: ${path}`, 'TIMEOUT', null, true);
    }
    throw new APIException(
      `Network error: cannot reach backend at ${API_BASE}`,
      'NETWORK_ERROR',
      e,
      true
    );
  }
  clearTimeout(timer);

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    throw toApiException(response.status, payload, path);
  }

  return payload as T;
}

function toApiException(status: number, payload: unknown, path: string): APIException {
  let message = `Request failed with status ${status}`;
  let code = `HTTP_${status}`;
  let details: unknown = payload;
  let retryable = status >= 500;

  if (payload && typeof payload === 'object') {
    const obj = payload as Record<string, unknown>;
    // FastAPI HTTPException: {detail}
    const detail = obj.detail ?? obj.message ?? obj.error;
    if (typeof detail === 'string') {
      message = detail;
    } else if (detail && typeof detail === 'object') {
      const d = detail as Record<string, unknown>;
      message = typeof d.message === 'string' ? d.message : message;
      if (typeof d.error_code === 'string') code = d.error_code;
      if (typeof d.retryable === 'boolean') retryable = d.retryable;
    }
    if (typeof obj.code === 'string') code = obj.code;
  } else if (typeof payload === 'string' && payload) {
    message = payload;
  }

  return new APIException(`${message} (${path})`, code, details, retryable);
}

// ======================================================================
// Projects
// ======================================================================

interface ProjectListResponse {
  projects: Project[];
  total: number;
}
interface ProjectResponse {
  project: Project;
}

// ======================================================================
// Settings Center (runtime model configuration)
// ======================================================================

export type SettingsCategory = 'text' | 'voice' | 'video' | 'image' | 'agent';

export interface ConnectionTestResult {
  category: SettingsCategory;
  target: string;
  success: boolean;
  latency_ms: number | null;
  message: string;
  detail: string | null;
  verified: 'full' | 'partial';
}

export interface AgentStatus {
  aragon_installed: boolean;
  aragon_version: string | null;
  aragon_path: string | null;
  agent_configured: boolean;
  agent_enabled: boolean;
  mode: 'aragon' | 'llm_fallback' | 'unavailable';
  message: string;
}

export interface ModelSettings {
  text: {
    fast_llm: ProviderConfig;
    judge_llm: ProviderConfig;
    enable_prompt_optimization: boolean;
    enable_character_consistency_judge: boolean;
  };
  voice: VoiceConfig;
  video: {
    service_type: 'veo3' | 'sora2' | 'ali_token_plan';
    veo3: ProviderConfig & { skip_upload: boolean };
    sora2: ProviderConfig & {
      default_size: string;
      default_duration: number;
      default_style: string | null;
      watermark: boolean;
      private: boolean;
    };
    ali_token_plan: ProviderConfig & {
      t2v_model: string;
      r2v_model: string;
      default_size: string;
      default_duration: number;
    };
  };
  image: {
    service_type: 'doubao' | 'nano_banana' | 'midjourney' | 'ali_token_plan';
    doubao: ProviderConfig & { watermark: boolean };
    nano_banana: ProviderConfig;
    midjourney: ProviderConfig & {
      bot_type: string;
      poll_interval: number;
      max_poll_attempts: number;
      auto_upscale: boolean;
      upscale_index: number;
    };
    ali_token_plan: ProviderConfig;
  };
  agent: {
    enabled: boolean;
    provider: 'openai' | 'anthropic' | 'google';
    api_key: string | null;
    base_url: string | null;
    model: string;
    max_turns: number;
    timeout_seconds: number;
    aragon_cli_path: string;
  };
}

export interface ProviderConfig {
  api_key: string | null;
  api_url?: string;
  base_url?: string;
  endpoint?: string;
  model: string;
}

export interface VoiceConfig {
  enabled: boolean;
  api_key: string | null;
  base_url: string;
  model: string;
  default_voice: string;
  default_format: string;
  default_speed: number;
}

/** Normalized agent-chat SSE event (see backend settings.py endpoint docs). */
export interface AgentChatEvent {
  type:
    | 'meta'
    | 'status'
    | 'system'
    | 'text_delta'
    | 'tool_call'
    | 'tool_result'
    | 'assistant'
    | 'result'
    | 'settings_updated'
    | 'error';
  session_id?: string;
  mode?: string | null;
  message?: string;
  text?: string;
  note?: string;
  id?: string;
  name?: string;
  input?: Record<string, unknown>;
  preview?: string;
  is_error?: boolean;
  stop_reason?: string;
  usage?: Record<string, number>;
  settings?: ModelSettings;
  suggested_patch?: Record<string, unknown>;
  detail?: string;
}

const settingsApi = {
  async get(): Promise<{ settings: ModelSettings; settings_file: string }> {
    return request('/api/v1/settings');
  },

  async update(patch: Record<string, unknown>): Promise<{ settings: ModelSettings; settings_file: string }> {
    return request('/api/v1/settings', { method: 'PUT', body: patch });
  },

  async test(category: SettingsCategory): Promise<ConnectionTestResult[]> {
    return request(`/api/v1/settings/test/${category}`, { method: 'POST' });
  },

  async agentStatus(): Promise<AgentStatus> {
    return request('/api/v1/settings/agent/status');
  },

  /**
   * Stream one configuration-agent turn (SSE over fetch).
   * Returns when the stream completes ([DONE]).
   */
  async chat(
    body: { message: string; session_id?: string },
    onEvent: (event: AgentChatEvent) => void,
    options?: { signal?: AbortSignal }
  ): Promise<void> {
    const response = await fetch(`${API_BASE}/api/v1/settings/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: options?.signal,
    });

    if (!response.ok || !response.body) {
      const text = await response.text().catch(() => '');
      throw toApiException(response.status, text || null, '/api/v1/settings/agent/chat');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() ?? '';
      for (const chunk of chunks) {
        const dataLine = chunk
          .split('\n')
          .find((l) => l.startsWith('data: '));
        if (!dataLine) continue;
        const payload = dataLine.slice('data: '.length).trim();
        if (payload === '[DONE]') return;
        try {
          onEvent(JSON.parse(payload) as AgentChatEvent);
        } catch {
          // ignore malformed events
        }
      }
    }
  },
};

// ======================================================================
// The client
// ======================================================================

export const apiClient = {
  // ---- projects ----
  async listProjects(): Promise<Project[]> {
    const data = await request<ProjectListResponse>('/api/v1/projects');
    return data.projects ?? [];
  },

  async getProject(projectId: string): Promise<Project> {
    const data = await request<ProjectResponse>(`/api/v1/projects/${projectId}`);
    return data.project;
  },

  async createProject(body: CreateProjectRequest): Promise<Project> {
    const data = await request<ProjectResponse>('/api/v1/projects', {
      method: 'POST',
      body,
    });
    return data.project;
  },

  async deleteProject(projectId: string): Promise<void> {
    await request<void>(`/api/v1/projects/${projectId}`, { method: 'DELETE' });
  },

  getProjectThumbnailUrl(projectId: string): string {
    return `${API_BASE}/api/v1/projects/${projectId}/thumbnail`;
  },

  // ---- llm ----
  async chat(body: {
    messages: Array<{ role: string; content: string }>;
    model?: string;
    temperature?: number;
    max_tokens?: number;
  }): Promise<{
    choices: Array<{ message: { role: string; content: string }; finish_reason?: string }>;
    usage?: Record<string, number>;
  }> {
    return request('/api/v1/llm/chat', { method: 'POST', body, timeoutMs: 300_000 });
  },

  // ---- images ----
  async generateImage(body: {
    prompt: string;
    service?: string;
    width?: number;
    height?: number;
    quality?: string;
    style?: string;
    negative_prompt?: string;
    seed?: number;
    optimize_prompt?: boolean;
  }): Promise<{ image_url?: string | null; image_b64?: string | null; service: string; duration?: number }> {
    return request('/api/v1/images/generate', {
      method: 'POST',
      body,
      timeoutMs: 300_000,
    });
  },

  // ---- workflows ----
  async startWorkflow(body: {
    script: string;
    video_type?: string;
    video_subtype?: string;
    character_images?: Record<string, string>;
    scene_images?: Record<string, string>;
    config?: Record<string, unknown>;
  }): Promise<{ task_id: string; status: string; message?: string }> {
    return request('/api/v1/workflow/generate', { method: 'POST', body });
  },

  async startQuickModeWorkflow(body: {
    mode: 'quick';
    scenes: Array<{
      scene_id: string;
      image: string;
      duration: number;
      prompt?: string;
      camera_motion?: string;
      motion_strength?: number;
    }>;
    config?: Record<string, unknown>;
  }): Promise<{ task_id: string; status: string; message?: string }> {
    return request('/api/v1/workflow/quick-generate', { method: 'POST', body });
  },

  // ---- tasks ----
  async getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
    return request(`/api/v1/tasks/${taskId}`);
  },

  async cancelTask(taskId: string): Promise<void> {
    await request<void>(`/api/v1/tasks/${taskId}`, { method: 'DELETE' });
  },

  /**
   * Poll a task until it reaches a terminal state.
   * - Calls onProgress on every status update.
   * - Resolves with the final COMPLETED status.
   * - Throws APIException when the task fails, is cancelled, or times out.
   */
  async pollTaskUntilComplete(
    taskId: string,
    onProgress?: (status: TaskStatusResponse) => void,
    timeoutMs: number = 4 * 60 * 60 * 1000,
    pollIntervalMs: number = 2000
  ): Promise<TaskStatusResponse> {
    const deadline = Date.now() + timeoutMs;
    // The backend composes the final video on the same event loop that serves
    // /api/v1/tasks/..., so an individual status request can stall for minutes.
    // A stalled poll is NOT a failed generation - retry it a bounded number of
    // times instead of tearing down a workflow that is still running.
    const maxConsecutivePollErrors = 15;
    let consecutivePollErrors = 0;

    for (;;) {
      let status: TaskStatusResponse;
      try {
        status = await request<TaskStatusResponse>(`/api/v1/tasks/${taskId}`, {
          timeoutMs: 180_000,
        });
        consecutivePollErrors = 0;
      } catch (err) {
        const transient = err instanceof APIException && err.retryable === true;
        if (!transient || ++consecutivePollErrors > maxConsecutivePollErrors) {
          throw err;
        }
        console.warn(
          `[api] task ${taskId} status poll stalled (${consecutivePollErrors}/${maxConsecutivePollErrors}), retrying`
        );
        if (Date.now() > deadline) {
          throw new APIException(
            `Task polling timed out after ${Math.round(timeoutMs / 1000)}s`,
            'TIMEOUT',
            null,
            true
          );
        }
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
        continue;
      }

      onProgress?.(status);

      if (status.status === 'completed') return status;

      if (status.status === 'failed') {
        const errMessage =
          (status.error && (status.error.message || status.error.error_type)) ||
          'Task failed';
        throw new APIException(
          `Task failed: ${errMessage}`,
          'TASK_FAILED',
          status.error,
          false
        );
      }
      if (status.status === 'cancelled') {
        throw new APIException('Task was cancelled', 'TASK_CANCELLED', status.error, false);
      }

      if (Date.now() > deadline) {
        throw new APIException(
          `Task polling timed out after ${Math.round(timeoutMs / 1000)}s`,
          'TIMEOUT',
          null,
          true
        );
      }

      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }
  },

  // ---- settings center ----
  settings: settingsApi,
};

export { apiClient as default, APIException };
