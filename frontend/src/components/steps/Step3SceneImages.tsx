'use client';

import React, { useState, useEffect } from 'react';
import { Card, Button, Input, ImageGrid, LoadingAnimation } from '@/components/ui';
import { apiClient } from '@/lib/api';
import { logger } from '@/lib/logger';
import { processImageResults } from '@/lib/imageHelpers';
import { resolveActiveImageService } from '@/lib/imageService';
import { Scene, APIException } from '@/lib/types';
import { parseYamlScript, extractScenesFromParsedScript } from '@/lib/yamlParser';

interface Step3SceneImagesProps {
  polishedScript: string;
  onNext: (scenes: Scene[]) => void;
  onBack: () => void;
  initialScenes?: Scene[];
}

export const Step3SceneImages: React.FC<Step3SceneImagesProps> = ({
  polishedScript,
  onNext,
  onBack,
  initialScenes = [],
}) => {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [generatingFor, setGeneratingFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Extract scenes when component mounts or script changes
  useEffect(() => {
    if (initialScenes.length > 0) {
      setScenes(initialScenes);
    } else {
      const extracted = extractScenesFromScript(polishedScript);
      setScenes(extracted);
    }
  }, [polishedScript, initialScenes]);

  function extractScenesFromScript(script: string): Scene[] {
    logger.info('Step3SceneImages', 'Starting scene extraction', {
      scriptLength: script.length,
    });

    // Parse YAML
    const parseResult = parseYamlScript(script);
    
    if (!parseResult.success || !parseResult.data) {
      logger.error('Step3SceneImages', 'Failed to parse script', {
        error: parseResult.error,
      });
      return createDefaultScene();
    }

    // Extract scenes
    const extractedScenes = extractScenesFromParsedScript(parseResult.data);
    
    if (extractedScenes.length === 0) {
      logger.warn('Step3SceneImages', 'No scenes found, using default');
      return createDefaultScene();
    }

    // Convert to Scene type
    const scenes = extractedScenes.map(scene => ({
      id: scene.id,
      description: scene.description,
      location: scene.location,
      time: scene.time,
      mode: 'generate' as const,
      imageCount: 3,
      generatedImages: [],
      selectedImage: null,
    }));

    logger.info('Step3SceneImages', `Successfully extracted ${scenes.length} scenes`, {
      sceneIds: scenes.map(s => s.id),
    });

    return scenes;
  }

  function createDefaultScene(): Scene[] {
    return [{
      id: 'scene_001',
      description: 'Main scene from the script',
      location: 'General setting',
      time: 'Day',
      mode: 'generate',
      imageCount: 3,
      generatedImages: [],
      selectedImage: null,
    }];
  }

  const handleGenerateImages = async (sceneId: string) => {
    const scene = scenes.find((s) => s.id === sceneId);
    if (!scene) return;

    logger.info('Step3SceneImages', `Generating images for scene: ${scene.description}`, {
      count: scene.imageCount,
    });

    setGeneratingFor(sceneId);
    setError(null);

    try {
      // Use the image service actually configured in the backend
      // (.env IMAGE_SERVICE_TYPE / settings center) instead of hardcoding one.
      const imageService = await resolveActiveImageService();
      logger.info('Step3SceneImages', `Using image service: ${imageService ?? 'backend default'}`);

      const imagePromises = Array.from({ length: scene.imageCount }).map(() =>
        apiClient.generateImage({
          prompt: `${scene.location}, ${scene.time}, ${scene.description}, cinematic lighting, high quality, establishing shot`,
          service: imageService,
          width: 1920,
          height: 1080,
          optimize_prompt: true,
        })
      );

      const results = await Promise.all(imagePromises);
      
      // Process image URLs, handling both URL and base64 responses
      const imageUrls = processImageResults(results);
      
      if (imageUrls.length === 0) {
        throw new Error('No valid images were generated. Please try again.');
      }

      setScenes((prev) =>
        prev.map((s) =>
          s.id === sceneId
            ? { ...s, generatedImages: imageUrls, selectedImage: imageUrls[0] }
            : s
        )
      );

      logger.info('Step3SceneImages', `Generated ${imageUrls.length} images for scene ${sceneId}`, {
        requested: scene.imageCount,
        received: imageUrls.length,
      });
    } catch (err) {
      logger.error('Step3SceneImages', `Failed to generate images for scene ${sceneId}`, err);
      
      if (err instanceof APIException) {
        setError(`Failed to generate images: ${err.message}`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    } finally {
      setGeneratingFor(null);
    }
  };

  const handleImageSelect = (sceneId: string, imageUrl: string) => {
    setScenes((prev) =>
      prev.map((s) => (s.id === sceneId ? { ...s, selectedImage: imageUrl } : s))
    );
    logger.debug('Step3SceneImages', `Selected image for scene ${sceneId}`);
  };

  const handleFileUpload = async (sceneId: string, file: File) => {
    logger.info('Step3SceneImages', `Uploading image for scene ${sceneId}`);

    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      setScenes((prev) =>
        prev.map((s) =>
          s.id === sceneId
            ? {
                ...s,
                generatedImages: [dataUrl, ...s.generatedImages],
                selectedImage: dataUrl,
              }
            : s
        )
      );
    };
    reader.readAsDataURL(file);
  };

  const handleNext = () => {
    // Allow proceeding with partial or no scene images
    // Backend will automatically generate images for scenes without custom images
    const scenesWithImages = scenes.filter((s) => s.selectedImage);
    const scenesWithoutImages = scenes.filter((s) => !s.selectedImage);
    
    if (scenesWithoutImages.length > 0) {
      logger.info(
        'Step3SceneImages', 
        `Proceeding with ${scenesWithImages.length} custom scene images, ${scenesWithoutImages.length} will be auto-generated by backend`,
        {
          customScenes: scenesWithImages.map(s => s.id),
          autoGenScenes: scenesWithoutImages.map(s => s.id)
        }
      );
    } else {
      logger.info('Step3SceneImages', 'Proceeding with all custom scene images');
    }

    // Pass all scenes, backend will generate missing ones
    onNext(scenes);
  };

  return (
    <div className="space-y-6">
      <Card>
        <div className="space-y-3">
          <h3 className="text-lg font-semibold text-text-primary">Scene Images Setup</h3>
          <p className="text-apple-body text-text-secondary">
            For each scene, you can generate or upload custom images. If you skip a scene, 
            the system will automatically generate it based on your script context.
          </p>
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            <span>Found {scenes.length} scene{scenes.length !== 1 ? 's' : ''} in your script</span>
          </div>
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-apple-sm">
            <p className="text-sm text-blue-800 dark:text-blue-300">
              💡 <strong>Tip:</strong> You can skip scenes you don't want to customize. The AI will automatically 
              generate high-quality images for them based on your script's context, characters, and style.
            </p>
          </div>
        </div>
      </Card>

      {/* Scene Cards */}
      <div className="space-y-6">
        {scenes.map((scene) => (
          <Card
            key={scene.id}
            title={scene.id}
            subtitle={`${scene.location} - ${scene.time}`}
          >
            <div className="space-y-4">
              <div className="bg-bg-secondary p-3 rounded-apple-sm">
                <p className="text-sm text-text-primary font-medium mb-1">{scene.description}</p>
                <p className="text-xs text-text-secondary">
                  {scene.location} • {scene.time}
                  {!scene.selectedImage && (
                    <span className="ml-2 text-blue-600 dark:text-blue-400">
                      • Will auto-generate if skipped
                    </span>
                  )}
                </p>
              </div>

              {/* Mode Selection */}
              <div className="flex gap-4">
                <Button
                  variant={scene.mode === 'generate' ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() =>
                    setScenes((prev) =>
                      prev.map((s) =>
                        s.id === scene.id ? { ...s, mode: 'generate' } : s
                      )
                    )
                  }
                >
                  Auto Generate
                </Button>
                <Button
                  variant={scene.mode === 'upload' ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() =>
                    setScenes((prev) =>
                      prev.map((s) =>
                        s.id === scene.id ? { ...s, mode: 'upload' } : s
                      )
                    )
                  }
                >
                  Manual Upload
                </Button>
              </div>

              {/* Generate Mode */}
              {scene.mode === 'generate' && (
                <div className="space-y-3">
                  <div className="flex gap-4 items-end">
                    <Input
                      label="Number of Images"
                      type="number"
                      min="1"
                      max="5"
                      value={scene.imageCount}
                      onChange={(e) =>
                        setScenes((prev) =>
                          prev.map((s) =>
                            s.id === scene.id
                              ? { ...s, imageCount: parseInt(e.target.value, 10) }
                              : s
                          )
                        )
                      }
                      className="w-32"
                      helperText="Generate 1-5 variations"
                    />
                    <Button
                      onClick={() => handleGenerateImages(scene.id)}
                      loading={generatingFor === scene.id}
                      loadingText="Generating..."
                      disabled={generatingFor !== null}
                      size="md"
                    >
                      <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      Generate Images
                    </Button>
                  </div>
                  {scene.generatedImages.length === 0 && (
                    <p className="text-sm text-text-secondary italic">
                      Click "Generate Images" to create options, or skip and let AI auto-generate during video creation
                    </p>
                  )}
                </div>
              )}

              {/* Upload Mode */}
              {scene.mode === 'upload' && (
                <div className="space-y-3">
                  <div className="flex items-center gap-4">
                    <label className="flex-1">
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        id={`upload-${scene.id}`}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            handleFileUpload(scene.id, file);
                          }
                          // Reset input value to allow re-uploading the same file
                          e.target.value = '';
                        }}
                      />
                      <Button
                        as="span"
                        variant="secondary"
                        size="md"
                        className="cursor-pointer w-full sm:w-auto"
                      >
                        <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                        Choose Image File
                      </Button>
                    </label>
                  </div>
                  {scene.generatedImages.length === 0 && (
                    <p className="text-sm text-text-secondary italic">
                      Upload an image, or skip to let AI auto-generate during video creation
                    </p>
                  )}
                </div>
              )}

              {/* Loading State */}
              {generatingFor === scene.id && (
                <LoadingAnimation message="Generating scene images..." />
              )}

              {/* Image Grid */}
              {scene.generatedImages.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-medium text-text-primary">
                      Generated Images ({scene.generatedImages.length})
                    </h4>
                    {scene.selectedImage && (
                      <span className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        Image selected
                      </span>
                    )}
                  </div>
                  <ImageGrid
                    label={`${scene.id} 的场景图候选`}
                    testIdPrefix={`scene-${scene.id}-option`}
                    images={scene.generatedImages.map((url, i) => ({
                      id: url,
                      url,
                      selected: url === scene.selectedImage,
                      label: `${scene.id} 候选图 ${i + 1}`,
                    }))}
                    onSelect={(imageUrl) => handleImageSelect(scene.id, imageUrl)}
                    columns={3}
                    aspectRatio="16/9"
                  />
                  <p className="text-xs text-text-secondary italic">
                    Click an image to select it, or leave unselected to let AI auto-generate
                  </p>
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-apple-red rounded-apple-md p-4">
          <p className="text-apple-red text-sm">{error}</p>
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-between">
        <Button onClick={onBack} variant="secondary" size="lg">
          ← Back
        </Button>
        <Button onClick={handleNext} size="lg">
          Next: Generate Video →
        </Button>
      </div>
    </div>
  );
};

export default Step3SceneImages;

