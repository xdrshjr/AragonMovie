/**
 * New Project Creation Page
 *
 * Allows users to create a new video generation project by selecting:
 * - Video type (news_broadcast, anime, movie, short_drama)
 * - Generation mode (full or quick)
 * - Project name and description
 */

'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/lib/api';
import { VideoType, GenerationMode } from '@/lib/types';
import { logger } from '@/lib/logger';
import { Input, Textarea } from '@/components/ui';

const videoTypeOptions: Array<{
  value: VideoType;
  label: string;
  description: string;
  icon: string;
}> = [
  {
    value: 'news_broadcast',
    label: 'News Broadcast',
    description: 'Professional news-style videos with anchors and reports',
    icon: '📰',
  },
  {
    value: 'anime',
    label: 'Anime',
    description: 'Animated style videos with manga aesthetics',
    icon: '🎌',
  },
  {
    value: 'movie',
    label: 'Movie',
    description: 'Cinematic videos with dramatic storytelling',
    icon: '🎬',
  },
  {
    value: 'short_drama',
    label: 'Short Drama',
    description: 'Quick dramatic scenes with emotional narratives',
    icon: '🎭',
  },
];

const modeOptions: Array<{
  value: GenerationMode;
  label: string;
  description: string;
  icon: string;
}> = [
  {
    value: 'full',
    label: 'Full Mode',
    description: 'Complete workflow: script → characters → scenes → video',
    icon: '🎯',
  },
  {
    value: 'quick',
    label: 'Quick Mode',
    description: 'Fast generation: upload images → generate video',
    icon: '⚡',
  },
];

export default function NewProjectPage() {
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [projectName, setProjectName] = useState('');
  const [projectDescription, setProjectDescription] = useState('');
  const [selectedVideoType, setSelectedVideoType] = useState<VideoType | null>(null);
  const [selectedMode, setSelectedMode] = useState<GenerationMode | null>(null);

  const handleCreate = async () => {
    // Validation
    if (!projectName.trim()) {
      setError('Please enter a project name');
      return;
    }

    if (!selectedVideoType) {
      setError('Please select a video type');
      return;
    }

    if (!selectedMode) {
      setError('Please select a generation mode');
      return;
    }

    setIsCreating(true);
    setError(null);

    try {
      logger.info('NewProjectPage', 'Creating new project', {
        name: projectName,
        videoType: selectedVideoType,
        mode: selectedMode,
      });

      const project = await apiClient.createProject({
        name: projectName,
        description: projectDescription || undefined,
        video_type: selectedVideoType,
        mode: selectedMode,
      });

      logger.info('NewProjectPage', 'Project created successfully', { projectId: project.id });

      // Navigate to the workflow page with project info in URL params
      const params = new URLSearchParams({
        projectId: project.id,
        videoType: selectedVideoType,
        mode: selectedMode,
      });
      router.push(`/workflow/${project.id}?${params.toString()}`);
    } catch (err) {
      logger.error('NewProjectPage', 'Failed to create project', err);
      setError(err instanceof Error ? err.message : 'Failed to create project');
      setIsCreating(false);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 glass-effect glow-top border-b border-hairline">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link
                href="/"
                className="text-text-secondary hover:text-text-primary transition-colors"
              >
                ← Back
              </Link>
              <h1 className="text-2xl font-semibold tracking-[-0.02em] text-text-primary">
                Create New Project
              </h1>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-6 py-12">
        <div className="space-y-8">
          {/* Project Details */}
          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-4">
              Project Details
            </h2>
            <div className="space-y-4">
              {/* Project Name — labelled so getByLabel() / a11y works */}
              <Input
                label="Project Name *"
                type="text"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="My Awesome Video"
                className="w-full"
                maxLength={200}
              />

              {/* Project Description */}
              <Textarea
                label="Description (Optional)"
                value={projectDescription}
                onChange={(e) => setProjectDescription(e.target.value)}
                placeholder="A brief description of your video project..."
                className="min-h-[100px] resize-y"
                maxLength={1000}
              />
            </div>
          </section>

          {/* Video Type Selection */}
          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-4">
              Video Type *
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {videoTypeOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setSelectedVideoType(option.value)}
                  className={`
                    card-apple p-6 text-left transition-all duration-200
                    ${selectedVideoType === option.value
                      ? 'ring-2 ring-accent bg-accent-soft'
                      : 'border-hairline hover:border-accent-border hover:shadow-apple-md'
                    }
                  `}
                >
                  <div className="flex items-start gap-4">
                    <div className="text-4xl">{option.icon}</div>
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-text-primary mb-1">
                        {option.label}
                      </h3>
                      <p className="text-sm text-text-secondary">
                        {option.description}
                      </p>
                    </div>
                    {selectedVideoType === option.value && (
                      <div className="text-accent text-xl">✓</div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Generation Mode Selection */}
          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-4">
              Generation Mode *
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {modeOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setSelectedMode(option.value)}
                  className={`
                    card-apple p-6 text-left transition-all duration-200
                    ${selectedMode === option.value
                      ? 'ring-2 ring-accent bg-accent-soft'
                      : 'border-hairline hover:border-accent-border hover:shadow-apple-md'
                    }
                  `}
                >
                  <div className="flex items-start gap-4">
                    <div className="text-4xl">{option.icon}</div>
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-text-primary mb-1">
                        {option.label}
                      </h3>
                      <p className="text-sm text-text-secondary">
                        {option.description}
                      </p>
                    </div>
                    {selectedMode === option.value && (
                      <div className="text-accent text-xl">✓</div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Error Message */}
          {error && (
            <div className="card-apple p-4 bg-error-soft border-error-border">
              <p className="text-sm text-error-text">{error}</p>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-4 pt-6 border-t border-hairline">
            <Link
              href="/"
              className="btn-apple btn-apple-secondary px-6 py-3"
            >
              Cancel
            </Link>
            <button
              onClick={handleCreate}
              disabled={isCreating}
              className="btn-apple btn-apple-primary px-6 py-3 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCreating ? (
                <span className="flex items-center gap-2">
                  <span className="spinner-apple w-4 h-4" />
                  Creating...
                </span>
              ) : (
                'Create Project'
              )}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
