'use client';

/**
 * Generic provider configuration card.
 *
 * Renders URL / API key / model fields for one external service, with
 * write-only key semantics: when a key is already stored, the input is
 * empty with a masked placeholder and only a freshly typed value is sent.
 */

import React, { useState } from 'react';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import { Select } from '@/components/ui/ConfigPanel';
import type { ConnectionTestResult } from '@/lib/api';

export interface FieldDef {
  key: string;
  label: string;
  placeholder?: string;
  type?: 'text' | 'password' | 'number' | 'select';
  options?: Array<{ value: string; label: string }>;
  hint?: string;
  /** mark as the secret field handled with write-only semantics */
  secret?: boolean;
}

export interface ProviderCardProps {
  title: string;
  subtitle?: string;
  badge?: string;
  fields: FieldDef[];
  values: Record<string, unknown>;
  /** masked representation of the stored key ('' when unset) */
  maskedKey?: string;
  onChange: (key: string, value: string) => void;
  onTest?: () => void;
  testing?: boolean;
  testResult?: ConnectionTestResult | null;
}

export default function ProviderCard({
  title,
  subtitle,
  badge,
  fields,
  values,
  maskedKey,
  onChange,
  onTest,
  testing = false,
  testResult = null,
}: ProviderCardProps) {
  const [showSecret, setShowSecret] = useState(false);

  return (
    <Card className="mb-4">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
            {badge && (
              <span className="px-2 py-0.5 rounded-full bg-apple-blue/10 text-apple-blue text-xs font-medium">
                {badge}
              </span>
            )}
          </div>
          {subtitle && <p className="text-sm text-text-secondary mt-1">{subtitle}</p>}
        </div>
        {onTest && (
          <Button variant="secondary" size="sm" loading={testing} onClick={onTest}>
            测试连接
          </Button>
        )}
      </div>

      <div className="space-y-4">
        {fields.map((field) => {
          if (field.secret) {
            const stored = (maskedKey ?? '') !== '';
            return (
              <div key={field.key}>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-sm font-medium text-text-primary">
                    API Key
                    {stored && (
                      <span className="ml-2 text-xs text-text-tertiary">
                        已保存 {maskedKey}
                      </span>
                    )}
                  </label>
                  {(values[field.key] as string) && (
                    <button
                      type="button"
                      className="text-xs text-apple-blue hover:underline"
                      onClick={() => onChange(field.key, '')}
                    >
                      清除
                    </button>
                  )}
                </div>
                <div className="flex gap-2">
                  <input
                    type={showSecret ? 'text' : 'password'}
                    className="input-apple flex-1"
                    value={(values[field.key] as string) ?? ''}
                    placeholder={
                      stored ? '留空保持已保存的 Key 不变' : 'sk-...'
                    }
                    onChange={(e) => onChange(field.key, e.target.value)}
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    className="px-3 rounded-apple-md border border-[var(--color-border)] text-sm text-text-secondary hover:text-text-primary"
                    onClick={() => setShowSecret((v) => !v)}
                  >
                    {showSecret ? '隐藏' : '显示'}
                  </button>
                </div>
                {field.hint && <p className="text-xs text-text-tertiary mt-1">{field.hint}</p>}
              </div>
            );
          }

          if (field.type === 'select' && field.options) {
            return (
              <div key={field.key}>
                <label className="block text-sm font-medium text-text-primary mb-1">
                  {field.label}
                </label>
                <Select
                  options={field.options}
                  value={String(values[field.key] ?? '')}
                  onChange={(v: string) => onChange(field.key, v)}
                />
                {field.hint && <p className="text-xs text-text-tertiary mt-1">{field.hint}</p>}
              </div>
            );
          }

          return (
            <Input
              key={field.key}
              label={field.label}
              type={field.type === 'number' ? 'number' : 'text'}
              value={String(values[field.key] ?? '')}
              placeholder={field.placeholder}
              helperText={field.hint}
              onChange={(e) => onChange(field.key, e.target.value)}
            />
          );
        })}
      </div>

      {testResult && (
        <div
          className={`mt-4 p-3 rounded-apple-md text-sm ${
            testResult.success
              ? 'bg-apple-green/10 text-apple-green'
              : 'bg-apple-red/10 text-apple-red'
          }`}
        >
          <div className="flex items-center gap-2">
            <span>{testResult.success ? '✓' : '✗'}</span>
            <span className="font-medium">
              {testResult.target || title}
              {testResult.latency_ms != null && ` · ${testResult.latency_ms}ms`}
              {testResult.verified === 'partial' && ' · 部分验证'}
            </span>
          </div>
          <p className="mt-1 opacity-90">{testResult.message}</p>
          {testResult.detail && (
            <details className="mt-1">
              <summary className="cursor-pointer text-xs opacity-75">详细信息</summary>
              <pre className="mt-1 text-xs whitespace-pre-wrap break-all opacity-75">
                {testResult.detail}
              </pre>
            </details>
          )}
        </div>
      )}
    </Card>
  );
}
