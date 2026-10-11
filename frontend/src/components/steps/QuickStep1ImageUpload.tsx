'use client';

import { useState, useCallback, useRef } from 'react';
import { QuickModeScene } from '@/lib/types';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import { logger } from '@/lib/logger';

interface QuickStep1ImageUploadProps {
  onNext: (scenes: QuickModeScene[]) => void;
  initialScenes?: QuickModeScene[];
}

export default function QuickStep1ImageUpload({
  onNext,
  initialScenes = [],
}: QuickStep1ImageUploadProps) {
  const [scenes, setScenes] = useState<QuickModeScene[]>(initialScenes);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Convert File to base64
  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  // Validate and process uploaded files
  const processFiles = useCallback(async (files: FileList | File[]) => {
    setError(null);
    const fileArray = Array.from(files);

    // Validate file types
    const invalidFiles = fileArray.filter(
      (file) => !file.type.startsWith('image/')
    );
    if (invalidFiles.length > 0) {
      setError('只支持图片文件 (PNG, JPG, JPEG, WebP)');
      return;
    }

    // Validate file sizes (max 10MB per file)
    const oversizedFiles = fileArray.filter((file) => file.size > 10 * 1024 * 1024);
    if (oversizedFiles.length > 0) {
      setError('图片文件不能超过 10MB');
      return;
    }

    // Validate total count (max 50 scenes)
    if (scenes.length + fileArray.length > 50) {
      setError('最多支持 50 个场景');
      return;
    }

    logger.info('QuickStep1', `Processing ${fileArray.length} files`);

    try {
      // Process files and create scene objects
      const newScenes: QuickModeScene[] = await Promise.all(
        fileArray.map(async (file, index) => {
          const sceneNumber = scenes.length + index + 1;
          const sceneId = `scene_${String(sceneNumber).padStart(3, '0')}`;
          const base64 = await fileToBase64(file);

          return {
            id: sceneId,
            imageFile: file,
            imagePreview: base64,
            imageBase64: base64.split(',')[1], // Remove data:image/...;base64, prefix
            duration: 5, // Default duration
            prompt: '',
            cameraMotion: undefined,
            motionStrength: 0.6,
          };
        })
      );

      setScenes([...scenes, ...newScenes]);
      logger.info('QuickStep1', `Added ${newScenes.length} scenes, total: ${scenes.length + newScenes.length}`);
    } catch (err) {
      logger.error('QuickStep1', 'Failed to process files', err);
      setError('处理图片失败，请重试');
    }
  }, [scenes]);

  // Handle file input change
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files);
    }
  };

  // Handle drag and drop
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  };

  // Remove a scene
  const handleRemoveScene = (sceneId: string) => {
    setScenes(scenes.filter((s) => s.id !== sceneId));
    logger.info('QuickStep1', `Removed scene: ${sceneId}`);
  };

  // Handle next button
  const handleNext = () => {
    if (scenes.length === 0) {
      setError('请至少上传一张图片');
      return;
    }

    logger.info('QuickStep1', `Proceeding with ${scenes.length} scenes`);
    onNext(scenes);
  };

  return (
    <div className="max-w-6xl mx-auto">
      <Card title="上传场景图片" subtitle="支持拖拽上传，图片将按顺序生成视频">
        {/* Upload Area */}
        <div
          className={`
            border-2 border-dashed rounded-apple-lg p-12 text-center transition-all duration-300
            ${
              isDragging
                ? 'border-primary bg-blue-50 dark:bg-blue-900/20'
                : 'border-gray-300 dark:border-gray-600 hover:border-primary'
            }
          `}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className="flex flex-col items-center gap-4">
            <div className="text-6xl">📸</div>
            <div>
              <p className="text-lg font-medium text-text-primary mb-2">
                拖拽图片到此处，或点击选择文件
              </p>
              <p className="text-sm text-text-secondary">
                支持 PNG, JPG, JPEG, WebP 格式，单个文件最大 10MB
              </p>
              <p className="text-sm text-text-tertiary mt-1">
                图片命名建议：scene_001.png, scene_002.png, ...
              </p>
            </div>
            <Button
              variant="primary"
              onClick={() => fileInputRef.current?.click()}
            >
              选择图片
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleFileChange}
              className="hidden"
            />
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-apple-md">
            <p className="text-sm text-red-800 dark:text-red-200">⚠️ {error}</p>
          </div>
        )}

        {/* Scene List */}
        {scenes.length > 0 && (
          <div className="mt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-text-primary">
                已上传场景 ({scenes.length}/50)
              </h3>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setScenes([])}
              >
                清空全部
              </Button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {scenes.map((scene, index) => (
                <div
                  key={scene.id}
                  className="relative group bg-background rounded-apple-lg overflow-hidden border border-gray-200 dark:border-gray-700 hover:shadow-apple-md transition-all duration-300"
                >
                  {/* Scene Number Badge */}
                  <div className="absolute top-2 left-2 z-10 bg-primary text-white text-xs font-bold px-2 py-1 rounded-apple-sm">
                    {index + 1}
                  </div>

                  {/* Remove Button */}
                  <button
                    onClick={() => handleRemoveScene(scene.id)}
                    className="absolute top-2 right-2 z-10 bg-red-500 text-white w-6 h-6 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center hover:bg-red-600"
                    title="删除"
                  >
                    ×
                  </button>

                  {/* Image Preview */}
                  <div className="aspect-video bg-gray-100 dark:bg-gray-800">
                    <img
                      src={scene.imagePreview}
                      alt={scene.id}
                      className="w-full h-full object-cover"
                    />
                  </div>

                  {/* Scene Info */}
                  <div className="p-2">
                    <p className="text-xs font-medium text-text-primary truncate">
                      {scene.id}
                    </p>
                    <p className="text-xs text-text-tertiary">
                      {scene.imageFile?.name || 'Unknown'}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {/* Info Box */}
            <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-apple-md">
              <p className="text-sm text-blue-800 dark:text-blue-200">
                💡 <strong>提示：</strong>
                图片将按当前顺序生成视频。下一步可以为每个场景配置时长和提示词。
              </p>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 mt-6">
          <Button
            variant="primary"
            onClick={handleNext}
            disabled={scenes.length === 0}
          >
            下一步：配置场景
          </Button>
        </div>
      </Card>
    </div>
  );
}
