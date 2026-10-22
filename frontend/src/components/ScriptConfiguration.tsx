'use client';

import React, { useState } from 'react';
import {
  ConfigPanel,
  ConfigRow,
  Checkbox,
  NumberInput,
  Select,
  GenreCard,
} from '@/components/ui/ConfigPanel';
import { Input } from '@/components/ui/Input';
import {
  ScriptGenerationConfig,
  DramaGenre,
  GENRE_LABELS,
  validateScriptConfig,
} from '@/lib/types/scriptConfig';
import { logger } from '@/lib/logger';

interface ScriptConfigurationProps {
  config: ScriptGenerationConfig;
  onChange: (config: ScriptGenerationConfig) => void;
  onValidationChange?: (isValid: boolean, errors: string[]) => void;
}

export const ScriptConfiguration: React.FC<ScriptConfigurationProps> = ({
  config,
  onChange,
  onValidationChange,
}) => {
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Validate configuration whenever it changes
  React.useEffect(() => {
    const validation = validateScriptConfig(config);
    onValidationChange?.(validation.isValid, validation.errors);
  }, [config, onValidationChange]);

  const updateConfig = (updates: Partial<ScriptGenerationConfig>) => {
    const newConfig = { ...config, ...updates };
    logger.debug('ScriptConfiguration', 'Config updated', { updates, newConfig });
    onChange(newConfig);
  };

  const genres: DramaGenre[] = [
    'slice_of_life',
    'shuang_ju',
    'comedy',
    'romance',
    'suspense',
    'action',
    'fantasy',
    'sci_fi',
    'horror',
    'other',
  ];

  return (
    <div className="space-y-6">
      {/* Genre Selection */}
      <ConfigPanel
        title="剧情类型 / Drama Genre"
        description="选择你想要生成的短剧类型"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {genres.map((genre) => (
            <GenreCard
              key={genre}
              genre={genre}
              label={GENRE_LABELS[genre].zh}
              description={GENRE_LABELS[genre].description}
              selected={config.genre === genre}
              onClick={() => updateConfig({ genre })}
            />
          ))}
        </div>

        {/* Custom genre input */}
        {config.genre === 'other' && (
          <div className="mt-4">
            <Input
              label="自定义剧情类型 / Custom Genre"
              placeholder="请描述你想要的剧情类型..."
              value={config.genreCustom || ''}
              onChange={(e) => updateConfig({ genreCustom: e.target.value })}
              helperText="例如：职场励志、校园青春、家庭伦理等"
            />
          </div>
        )}
      </ConfigPanel>

      {/* Character and Scene Settings */}
      <ConfigPanel
        title="角色与场景设置 / Character & Scene Settings"
        description="配置剧本的基本结构"
      >
        <ConfigRow
          label="人物个数 / Character Count"
          description="剧本中的主要角色数量 (1-10)"
          required
        >
          <NumberInput
            value={config.characterCount}
            onChange={(value) => updateConfig({ characterCount: value })}
            min={1}
            max={10}
            step={1}
          />
        </ConfigRow>

        <ConfigRow
          label="场景数 / Scene Count"
          description="剧本包含的主要场景数量 (1-20)"
          required
        >
          <NumberInput
            value={config.sceneCount}
            onChange={(value) => updateConfig({ sceneCount: value })}
            min={1}
            max={20}
            step={1}
          />
        </ConfigRow>

        <ConfigRow
          label="子场景数 / Sub-scenes per Scene"
          description="每个主场景包含的子场景数量 (0-5)"
        >
          <NumberInput
            value={config.subSceneCount}
            onChange={(value) => updateConfig({ subSceneCount: value })}
            min={0}
            max={5}
            step={1}
          />
        </ConfigRow>
      </ConfigPanel>

      {/* Content Safety Settings */}
      <ConfigPanel
        title="内容安全设置 / Content Safety"
        description="确保生成的内容符合规范"
      >
        <div className="space-y-3">
          <Checkbox
            label="不出现公众人物 / No Public Figures"
            description="避免生成真实公众人物的形象和名字"
            checked={config.noPublicFigures}
            onChange={(checked) => updateConfig({ noPublicFigures: checked })}
          />

          <Checkbox
            label="不出现未成年 / No Minors"
            description="避免生成未成年角色"
            checked={config.noMinors}
            onChange={(checked) => updateConfig({ noMinors: checked })}
          />

          <Checkbox
            label="不出现暴力内容 / No Violence"
            description="避免生成暴力、血腥场景"
            checked={config.noViolence}
            onChange={(checked) => updateConfig({ noViolence: checked })}
          />

          <Checkbox
            label="不出现敏感话题 / No Sensitive Topics"
            description="避免政治、宗教等敏感话题"
            checked={config.noSensitiveTopics}
            onChange={(checked) => updateConfig({ noSensitiveTopics: checked })}
          />
        </div>
      </ConfigPanel>

      {/* Advanced Settings (Collapsible) */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-2 text-accent hover:text-accent-strong transition-colors"
        >
          <svg
            className={`w-5 h-5 transition-transform ${showAdvanced ? 'rotate-90' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-apple-body font-medium">
            {showAdvanced ? '隐藏高级设置' : '显示高级设置'} / Advanced Settings
          </span>
        </button>

        {showAdvanced && (
          <div className="mt-4">
            <ConfigPanel
              title="高级设置 / Advanced Settings"
              description="微调剧本的风格和节奏"
            >
              <ConfigRow
                label="目标受众 / Target Audience"
                description="剧本的目标观众群体"
              >
                <Select
                  value={config.targetAudience || 'general'}
                  onChange={(value) =>
                    updateConfig({ targetAudience: value as 'general' | 'youth' | 'adult' })
                  }
                  options={[
                    { value: 'general', label: '全年龄 / General' },
                    { value: 'youth', label: '青少年 / Youth' },
                    { value: 'adult', label: '成人 / Adult' },
                  ]}
                  className="w-48"
                />
              </ConfigRow>

              <ConfigRow
                label="剧情节奏 / Pacing"
                description="故事发展的快慢节奏"
              >
                <Select
                  value={config.pacing || 'medium'}
                  onChange={(value) =>
                    updateConfig({ pacing: value as 'slow' | 'medium' | 'fast' })
                  }
                  options={[
                    { value: 'slow', label: '慢节奏 / Slow' },
                    { value: 'medium', label: '中等 / Medium' },
                    { value: 'fast', label: '快节奏 / Fast' },
                  ]}
                  className="w-48"
                />
              </ConfigRow>

              <ConfigRow
                label="整体基调 / Tone"
                description="剧本的情感基调"
              >
                <Select
                  value={config.tone || 'lighthearted'}
                  onChange={(value) =>
                    updateConfig({ tone: value as 'serious' | 'lighthearted' | 'dramatic' })
                  }
                  options={[
                    { value: 'lighthearted', label: '轻松 / Lighthearted' },
                    { value: 'serious', label: '严肃 / Serious' },
                    { value: 'dramatic', label: '戏剧化 / Dramatic' },
                  ]}
                  className="w-48"
                />
              </ConfigRow>
            </ConfigPanel>
          </div>
        )}
      </div>
    </div>
  );
};

export default ScriptConfiguration;
