'use client';

import { useState } from 'react';
import { QuickModeScene } from '@/lib/types';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import { logger } from '@/lib/logger';

interface QuickStep2SceneConfigProps {
  scenes: QuickModeScene[];
  onNext: (configuredScenes: QuickModeScene[]) => void;
  onBack: () => void;
}

export default function QuickStep2SceneConfig({
  scenes: initialScenes,
  onNext,
  onBack,
}: QuickStep2SceneConfigProps) {
  const [scenes, setScenes] = useState<QuickModeScene[]>(initialScenes);
  const [batchMode, setBatchMode] = useState(false);
  const [batchConfig, setBatchConfig] = useState({
    duration: 5,
    prompt: '',
    cameraMotion: '' as '' | 'static' | 'pan' | 'tilt' | 'zoom',
    motionStrength: 0.6,
  });

  // Update a single scene
  const updateScene = (sceneId: string, updates: Partial<QuickModeScene>) => {
    setScenes(
      scenes.map((scene) =>
        scene.id === sceneId ? { ...scene, ...updates } : scene
      )
    );
  };

  // Apply batch configuration to all scenes
  const applyBatchConfig = () => {
    setScenes(
      scenes.map((scene) => ({
        ...scene,
        duration: batchConfig.duration,
        prompt: batchConfig.prompt,
        cameraMotion: batchConfig.cameraMotion || undefined,
        motionStrength: batchConfig.motionStrength,
      }))
    );
    logger.info('QuickStep2', 'Applied batch configuration to all scenes');
  };

  // Handle next button
  const handleNext = () => {
    logger.info('QuickStep2', `Proceeding with ${scenes.length} configured scenes`);
    onNext(scenes);
  };

  return (
    <div className="max-w-6xl mx-auto">
      <Card
        title="配置场景参数"
        subtitle="为每个场景设置时长、提示词和镜头运动"
      >
        {/* Batch Configuration Toggle */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-text-primary">
              场景列表 ({scenes.length})
            </h3>
            <p className="text-sm text-text-secondary mt-1">
              可以单独配置每个场景，或使用批量配置
            </p>
          </div>
          <Button
            variant={batchMode ? 'primary' : 'secondary'}
            onClick={() => setBatchMode(!batchMode)}
          >
            {batchMode ? '✓ 批量配置' : '批量配置'}
          </Button>
        </div>

        {/* Batch Configuration Panel */}
        {batchMode && (
          <div className="mb-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-apple-lg border border-blue-200 dark:border-blue-800">
            <h4 className="text-md font-semibold text-blue-900 dark:text-blue-100 mb-4">
              批量配置 - 应用到所有场景
            </h4>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Duration */}
              <div>
                <label className="block text-sm font-medium text-text-primary mb-2">
                  时长 (秒)
                </label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={batchConfig.duration}
                  onChange={(e) =>
                    setBatchConfig({ ...batchConfig, duration: parseInt(e.target.value) })
                  }
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-text-tertiary mt-1">
                  <span>1s</span>
                  <span className="font-semibold text-primary">{batchConfig.duration}s</span>
                  <span>10s</span>
                </div>
              </div>

              {/* Camera Motion */}
              <div>
                <label className="block text-sm font-medium text-text-primary mb-2">
                  镜头运动
                </label>
                <select
                  value={batchConfig.cameraMotion}
                  onChange={(e) =>
                    setBatchConfig({
                      ...batchConfig,
                      cameraMotion: e.target.value as any,
                    })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-apple-md bg-background text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="">无 (自动)</option>
                  <option value="static">静止</option>
                  <option value="pan">平移</option>
                  <option value="tilt">俯仰</option>
                  <option value="zoom">缩放</option>
                </select>
              </div>

              {/* Motion Strength */}
              <div>
                <label className="block text-sm font-medium text-text-primary mb-2">
                  运动强度
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={batchConfig.motionStrength}
                  onChange={(e) =>
                    setBatchConfig({
                      ...batchConfig,
                      motionStrength: parseFloat(e.target.value),
                    })
                  }
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-text-tertiary mt-1">
                  <span>0.0</span>
                  <span className="font-semibold text-primary">
                    {batchConfig.motionStrength.toFixed(1)}
                  </span>
                  <span>1.0</span>
                </div>
              </div>

              {/* Prompt */}
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-text-primary mb-2">
                  提示词 (可选)
                </label>
                <textarea
                  value={batchConfig.prompt}
                  onChange={(e) =>
                    setBatchConfig({ ...batchConfig, prompt: e.target.value })
                  }
                  placeholder="例如：镜头缓慢向右平移，展现场景全貌"
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-apple-md bg-background text-text-primary focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                />
              </div>
            </div>

            <div className="mt-4 flex justify-end">
              <Button variant="primary" onClick={applyBatchConfig}>
                应用到全部场景
              </Button>
            </div>
          </div>
        )}

        {/* Scene List */}
        <div className="space-y-4">
          {scenes.map((scene, index) => (
            <div
              key={scene.id}
              className="p-4 bg-background rounded-apple-lg border border-gray-200 dark:border-gray-700"
            >
              <div className="flex gap-4">
                {/* Image Preview */}
                <div className="flex-shrink-0">
                  <div className="w-32 h-20 bg-gray-100 dark:bg-gray-800 rounded-apple-md overflow-hidden">
                    <img
                      src={scene.imagePreview}
                      alt={scene.id}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <p className="text-xs text-center text-text-tertiary mt-1">
                    场景 {index + 1}
                  </p>
                </div>

                {/* Configuration */}
                <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Duration */}
                  <div>
                    <label className="block text-sm font-medium text-text-primary mb-2">
                      时长: {scene.duration}秒
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="10"
                      value={scene.duration}
                      onChange={(e) =>
                        updateScene(scene.id, { duration: parseInt(e.target.value) })
                      }
                      className="w-full"
                    />
                  </div>

                  {/* Camera Motion */}
                  <div>
                    <label className="block text-sm font-medium text-text-primary mb-2">
                      镜头运动
                    </label>
                    <select
                      value={scene.cameraMotion || ''}
                      onChange={(e) =>
                        updateScene(scene.id, {
                          cameraMotion: e.target.value as any || undefined,
                        })
                      }
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-apple-md bg-background text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    >
                      <option value="">无 (自动)</option>
                      <option value="static">静止</option>
                      <option value="pan">平移</option>
                      <option value="tilt">俯仰</option>
                      <option value="zoom">缩放</option>
                    </select>
                  </div>

                  {/* Prompt */}
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-text-primary mb-2">
                      提示词 (可选)
                    </label>
                    <textarea
                      value={scene.prompt}
                      onChange={(e) =>
                        updateScene(scene.id, { prompt: e.target.value })
                      }
                      placeholder="描述这个场景的镜头运动和氛围..."
                      rows={2}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-apple-md bg-background text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                    />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Info Box */}
        <div className="mt-6 p-4 bg-green-50 dark:bg-green-900/20 rounded-apple-md">
          <p className="text-sm text-green-800 dark:text-green-200">
            ✓ <strong>配置完成：</strong>
            {scenes.length} 个场景已准备就绪，总时长约{' '}
            {scenes.reduce((sum, s) => sum + s.duration, 0)} 秒
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-between gap-3 mt-6">
          <Button variant="secondary" onClick={onBack}>
            返回
          </Button>
          <Button variant="primary" onClick={handleNext}>
            开始生成视频
          </Button>
        </div>
      </Card>
    </div>
  );
}
