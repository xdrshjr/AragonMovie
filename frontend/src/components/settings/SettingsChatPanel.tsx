'use client';

/**
 * Configuration-agent chat panel.
 *
 * Streams SSE events from POST /api/v1/settings/agent/chat:
 *  - aragon mode: the agent can actually edit the settings file
 *    (tool_call / tool_result cards show what it touched)
 *  - llm_fallback mode: advice only, with an "apply patch" button
 *  - settings_updated: the parent form refreshes automatically
 */

import React, { useRef, useState } from 'react';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import { apiClient, AgentStatus } from '@/lib/api';
import type { ModelSettings } from '@/lib/api';
import { logger } from '@/lib/logger';

interface ChatMessage {
  role: 'user' | 'assistant' | 'tool' | 'system';
  text: string;
  toolName?: string;
  toolPreview?: string;
  isError?: boolean;
  pending?: boolean;
}

interface SettingsChatPanelProps {
  agentStatus: AgentStatus | null;
  onSettingsUpdated: (settings: ModelSettings) => void;
}

const MODE_LABELS: Record<string, { text: string; cls: string }> = {
  aragon: { text: 'AragonAgent · 可自动修改配置', cls: 'bg-success-soft border border-success-border text-success-text' },
  llm_fallback: { text: '降级模式 · 仅提供建议', cls: 'bg-warning-soft border border-warning-border text-warning-text' },
  unavailable: { text: '未配置', cls: 'bg-error-soft border border-error-border text-error-text' },
};

export default function SettingsChatPanel({
  agentStatus,
  onSettingsUpdated,
}: SettingsChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [sessionKey, setSessionKey] = useState<string | undefined>(undefined);
  const [suggestedPatch, setSuggestedPatch] = useState<Record<string, unknown> | null>(null);
  const [applying, setApplying] = useState(false);
  const [patchApplied, setPatchApplied] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const mode = agentStatus?.mode ?? 'unavailable';
  const modeInfo = MODE_LABELS[mode] ?? MODE_LABELS.unavailable;
  const unavailable = mode === 'unavailable';

  const pushMessage = (msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming || unavailable) return;

    setInput('');
    setSuggestedPatch(null);
    setPatchApplied(false);
    setBanner(null);
    pushMessage({ role: 'user', text });

    // Placeholder assistant message that accumulates text deltas
    let assistantIndex = -1;
    setMessages((prev) => {
      assistantIndex = prev.length;
      return [...prev, { role: 'assistant', text: '', pending: true }];
    });

    const appendDelta = (delta: string) => {
      setMessages((prev) =>
        prev.map((m, i) =>
          i === assistantIndex ? { ...m, text: m.text + delta } : m
        )
      );
    };
    const finalize = (full: string) => {
      setMessages((prev) =>
        prev.map((m, i) =>
          i === assistantIndex ? { ...m, text: full, pending: false } : m
        )
      );
    };

    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);

    try {
      await apiClient.settings.chat(
        { message: text, session_id: sessionKey },
        (event) => {
          switch (event.type) {
            case 'meta':
              if (event.session_id) setSessionKey(event.session_id);
              if (event.type === 'meta' && event.mode === 'llm_fallback') {
                // note carried by the following status event
              }
              break;
            case 'status':
              pushMessage({ role: 'system', text: event.message ?? '' });
              break;
            case 'text_delta':
              appendDelta(event.text ?? '');
              break;
            case 'tool_call':
              pushMessage({
                role: 'tool',
                text: `调用工具 ${event.name}`,
                toolName: event.name,
                pending: true,
              });
              break;
            case 'tool_result':
              setMessages((prev) => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i--) {
                  if (next[i].role === 'tool' && next[i].pending) {
                    next[i] = {
                      ...next[i],
                      text: `工具 ${next[i].toolName} 完成`,
                      toolPreview: event.preview,
                      pending: false,
                      isError: event.is_error,
                    };
                    break;
                  }
                }
                return next;
              });
              break;
            case 'assistant':
              finalize(event.text ?? '');
              break;
            case 'result':
              setMessages((prev) =>
                prev.map((m, i) => (i === assistantIndex ? { ...m, pending: false } : m))
              );
              if (event.suggested_patch) {
                setSuggestedPatch(event.suggested_patch);
              }
              break;
            case 'settings_updated':
              if (event.settings) {
                onSettingsUpdated(event.settings);
                setBanner('助手已更新配置并即时生效，表单已刷新');
              }
              break;
            case 'error':
              pushMessage({ role: 'system', text: `出错了：${event.message ?? '未知错误'}`, isError: true });
              break;
          }
        },
        { signal: controller.signal }
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        pushMessage({ role: 'system', text: '已停止生成' });
      } else {
        logger.error('SettingsChatPanel', 'Agent chat failed', err);
        pushMessage({
          role: 'system',
          text: `请求失败：${err instanceof Error ? err.message : String(err)}`,
          isError: true,
        });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      setMessages((prev) => prev.map((m) => ({ ...m, pending: false })));
    }
  };

  const handleApplyPatch = async () => {
    if (!suggestedPatch) return;
    setApplying(true);
    try {
      const result = await apiClient.settings.update(suggestedPatch);
      onSettingsUpdated(result.settings);
      setPatchApplied(true);
      setBanner('建议配置已应用并即时生效');
    } catch (err) {
      logger.error('SettingsChatPanel', 'Apply patch failed', err);
      setBanner(`应用失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setApplying(false);
    }
  };

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">AI 配置助手</h3>
          <p className="text-sm text-text-secondary mt-0.5">
            告诉它你想切换哪个服务、填什么 Key，让它帮你完成配置
          </p>
        </div>
        <span className={`px-3 py-1 rounded-full text-xs font-medium ${modeInfo.cls}`}>
          {modeInfo.text}
        </span>
      </div>

      {unavailable && (
        <div className="mb-3 p-3 rounded-apple-md bg-background-deep border border-hairline text-sm text-text-secondary">
          {agentStatus?.message ?? '请先在下方配置 Agent 大模型'}
          {agentStatus && !agentStatus.aragon_installed && (
            <span className="block mt-1 text-xs">
              提示：安装 AragonAgent 后可解锁自动配置能力：
              <code className="mx-1 px-1 bg-surface-hover border border-hairline rounded">npm i -g @aragon-agent/cli</code>
              （需要 Node.js ≥ 18）
            </span>
          )}
        </div>
      )}

      {banner && (
        <div className="mb-3 p-2 rounded-apple-md bg-success-soft border border-success-border text-success-text text-sm">
          {banner}
        </div>
      )}

      {/* Messages */}
      <div className="space-y-3 mb-4 max-h-[420px] overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-sm text-text-tertiary text-center py-8">
            例如：「帮我把视频服务切换到 sora2，模型用 sora-2-pro，这是我的 Key：sk-xxx」
          </p>
        )}
        {messages.map((msg, i) => {
          if (msg.role === 'tool') {
            return (
              <div
                key={i}
                className={`text-xs px-3 py-2 rounded-apple-md border ${
                  msg.isError
                    ? 'border-error-border bg-error-soft text-error-text'
                    : 'border-hairline bg-surface text-text-secondary'
                }`}
              >
                <span className="font-medium">
                  {msg.isError ? '✗' : '🔧'} {msg.text}
                </span>
                {msg.toolPreview && (
                  <span className="block mt-1 opacity-75 break-all">{msg.toolPreview}</span>
                )}
              </div>
            );
          }
          if (msg.role === 'system') {
            return (
              <div
                key={i}
                className={`text-xs px-3 py-2 rounded-apple-md ${
                  msg.isError
                    ? 'bg-error-soft text-error-text'
                    : 'bg-surface-elevated text-text-secondary'
                }`}
              >
                {msg.text}
              </div>
            );
          }
          const isUser = msg.role === 'user';
          return (
            <div key={i} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] px-4 py-2.5 rounded-apple-lg text-sm whitespace-pre-wrap break-words ${
                  isUser
                    ? 'bg-accent text-[#0A0A0B]'
                    : 'bg-surface-elevated text-text-primary'
                }`}
              >
                {msg.text || (msg.pending ? '思考中…' : '')}
                {msg.pending && msg.text && (
                  <span className="inline-block w-1.5 h-4 ml-0.5 bg-text-tertiary animate-pulse align-middle" />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {suggestedPatch && !patchApplied && (
        <div className="mb-3 p-3 rounded-apple-md bg-accent-soft border border-accent-border">
          <p className="text-sm text-text-primary mb-2">助手给出了配置建议，是否应用？</p>
          <Button size="sm" loading={applying} onClick={handleApplyPatch}>
            应用建议配置
          </Button>
        </div>
      )}

      {/* Composer */}
      <div className="flex gap-2">
        <textarea
          className="input-apple flex-1 resize-none"
          rows={2}
          value={input}
          placeholder={unavailable ? '请先配置 Agent 大模型' : '描述你想修改的配置…'}
          disabled={unavailable || streaming}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        {streaming ? (
          <Button variant="secondary" onClick={() => abortRef.current?.abort()}>
            停止
          </Button>
        ) : (
          <Button disabled={unavailable || !input.trim()} onClick={handleSend}>
            发送
          </Button>
        )}
      </div>
    </Card>
  );
}
