/**
 * Project Detail Page
 *
 * Displays project workflow based on project status:
 * - completed: Show result preview
 * - processing/pending: Show workflow with current progress
 * - failed: Show error message with retry option
 */

'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import { apiClient, getApiBase } from '@/lib/api';
import { Project } from '@/lib/types';
import { logger } from '@/lib/logger';

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch project data
  useEffect(() => {
    const fetchProject = async () => {
      try {
        logger.info('ProjectDetailPage', `Fetching project: ${projectId}`);
        const fetchedProject = await apiClient.getProject(projectId);
        setProject(fetchedProject);
        setError(null);
      } catch (err) {
        logger.error('ProjectDetailPage', 'Failed to fetch project', err);
        setError(err instanceof Error ? err.message : 'Failed to load project');
      } finally {
        setIsLoading(false);
      }
    };

    if (projectId) {
      fetchProject();
    }
  }, [projectId]);

  // Auto-refresh for in-progress projects
  useEffect(() => {
    if (!project || (project.status !== 'processing' && project.status !== 'pending')) {
      return;
    }

    logger.debug('ProjectDetailPage', 'Setting up auto-refresh for in-progress project');

    const intervalId = setInterval(async () => {
      try {
        const updatedProject = await apiClient.getProject(projectId);
        setProject(updatedProject);
      } catch (err) {
        logger.error('ProjectDetailPage', 'Failed to refresh project', err);
      }
    }, 3000); // Poll every 3 seconds

    return () => {
      logger.debug('ProjectDetailPage', 'Clearing auto-refresh interval');
      clearInterval(intervalId);
    };
  }, [project, projectId]);

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="spinner-apple w-12 h-12 mx-auto mb-4" />
            <p className="text-text-secondary">Loading project...</p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !project) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 px-8 py-8 overflow-y-auto">
          <div className="max-w-4xl mx-auto">
            <Link
              href="/"
              className="text-text-secondary hover:text-text-primary transition-colors mb-6 inline-block"
            >
              ← Back to Projects
            </Link>
            <div className="card-apple p-8 text-center">
              <div className="text-6xl mb-4">⚠️</div>
              <h2 className="text-2xl font-semibold text-text-primary mb-2">
                Project Not Found
              </h2>
              <p className="text-text-secondary mb-6">
                {error || 'The project you are looking for does not exist.'}
              </p>
              <Link
                href="/"
                className="btn-apple btn-apple-primary px-6 py-3 inline-block"
              >
                Back to Projects
              </Link>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // Completed project - Show video player
  if (project.status === 'completed' && project.video_path) {
    const videoUrl = `${getApiBase()}${project.video_path}`;
    const thumbnailUrl = project.thumbnail_path
      ? apiClient.getProjectThumbnailUrl(project.id)
      : undefined;

    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 px-8 py-8 overflow-y-auto">
          <div className="max-w-5xl mx-auto">
            {/* Back Button and Status */}
            <div className="flex items-center justify-between mb-6">
              <Link
                href="/"
                className="text-text-secondary hover:text-text-primary transition-colors"
              >
                ← Back to Projects
              </Link>
              <span className="px-3 py-1.5 rounded-full bg-success text-[#0A0A0B] text-sm font-medium shadow-apple-sm">
                ✓ Completed
              </span>
            </div>

            {/* Project Info */}
            <div className="mb-8">
              <h1 className="text-4xl font-bold tracking-[-0.02em] text-text-primary mb-2">
                {project.name}
              </h1>
              {project.description && (
                <p className="text-lg text-text-secondary">
                  {project.description}
                </p>
              )}
              <div className="flex items-center gap-4 mt-4 text-sm text-text-tertiary">
                <span className="px-3 py-1 rounded border border-hairline bg-surface-hover">
                  {project.video_type.replaceAll('_', ' ')}
                </span>
                <span className="px-3 py-1 rounded border border-hairline bg-surface-hover">
                  {project.mode} mode
                </span>
                {project.duration && (
                  <span>⏱️ {Math.floor(project.duration / 60)}:{Math.floor(project.duration % 60).toString().padStart(2, '0')}</span>
                )}
                {project.scene_count && (
                  <span>🎬 {project.scene_count} scenes</span>
                )}
              </div>
            </div>

            {/* Video Player */}
            <div className="bg-black border border-hairline rounded-apple-lg overflow-hidden shadow-apple-md mb-8">
              <video
                controls
                className="w-full"
                poster={thumbnailUrl}
                src={videoUrl}
              >
                Your browser does not support the video tag.
              </video>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-center gap-4">
              <a
                href={videoUrl}
                download={`${project.name}.mp4`}
                className="btn-apple btn-apple-primary px-6 py-3"
              >
                Download Video
              </a>
              <Link
                href="/"
                className="btn-apple btn-apple-secondary px-6 py-3"
              >
                Back to Projects
              </Link>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // Failed project - Show error
  if (project.status === 'failed') {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 px-8 py-8 overflow-y-auto">
          <div className="max-w-4xl mx-auto">
            <Link
              href="/"
              className="text-text-secondary hover:text-text-primary transition-colors mb-6 inline-block"
            >
              ← Back to Projects
            </Link>

            <div className="card-apple p-8">
              <div className="text-center mb-6">
                <div className="text-6xl mb-4">❌</div>
                <h2 className="text-2xl font-semibold text-text-primary mb-2">
                  Generation Failed
                </h2>
                <p className="text-text-secondary">
                  {project.name}
                </p>
              </div>

              {project.error_message && (
                <div className="bg-error-soft border border-error-border rounded-apple-md p-4 mb-6">
                  <h3 className="text-sm font-semibold text-error-text mb-2">Error Details:</h3>
                  <p className="text-sm text-text-secondary font-mono">
                    {project.error_message}
                  </p>
                </div>
              )}

              <div className="flex items-center justify-center gap-4">
                <button
                  onClick={() => {
                    // TODO: Implement retry logic
                    alert('Retry functionality coming soon!');
                  }}
                  className="btn-apple btn-apple-primary px-6 py-3"
                >
                  Retry Generation
                </button>
                <Link
                  href="/"
                  className="btn-apple btn-apple-secondary px-6 py-3"
                >
                  Back to Projects
                </Link>
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // In-progress project - Show progress
  if (project.status === 'processing' || project.status === 'pending') {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 px-8 py-8 overflow-y-auto">
          <div className="max-w-4xl mx-auto">
            {/* Back Button and Status */}
            <div className="flex items-center justify-between mb-6">
              <Link
                href="/"
                className="text-text-secondary hover:text-text-primary transition-colors"
              >
                ← Back to Projects
              </Link>
              <span className="px-3 py-1.5 rounded-full bg-accent text-[#0A0A0B] text-sm font-medium shadow-apple-sm animate-pulse">
                ⚡ Generating...
              </span>
            </div>

            {/* Project Info */}
            <div className="mb-8">
              <h1 className="text-3xl font-bold text-text-primary mb-2">
                {project.name}
              </h1>
              {project.description && (
                <p className="text-base text-text-secondary">
                  {project.description}
                </p>
              )}
            </div>

            {/* Progress Card */}
            <div className="card-apple p-8">
              <div className="text-center mb-8">
                <div className="text-6xl mb-4">🎬</div>
                <h2 className="text-2xl font-semibold text-text-primary mb-2">
                  Generating Your Video
                </h2>
                <p className="text-text-secondary">
                  This may take several minutes. You can close this page and come back later.
                </p>
              </div>

              {/* Progress Bar */}
              <div className="mb-6">
                <div className="flex items-center justify-between text-sm text-text-secondary mb-2">
                  <span>Progress</span>
                  <span className="font-semibold">{project.progress}%</span>
                </div>
                <div className="progress-apple">
                  <div
                    className="progress-apple-fill"
                    style={{ width: `${project.progress}%` }}
                  />
                </div>
              </div>

              {/* Status Message */}
              <div className="text-center">
                <p className="text-sm text-text-tertiary">
                  {project.status === 'pending' ? 'Waiting to start...' : 'Processing your video...'}
                </p>
              </div>
            </div>

            {/* Info */}
            <div className="mt-8 text-center text-sm text-text-tertiary">
              <p>💡 Tip: You can safely close this page. The generation will continue in the background.</p>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // Cancelled project
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 px-8 py-8 overflow-y-auto">
        <div className="max-w-4xl mx-auto">
          <Link
            href="/"
            className="text-text-secondary hover:text-text-primary transition-colors mb-6 inline-block"
          >
            ← Back to Projects
          </Link>
          <div className="card-apple p-8 text-center">
            <div className="text-6xl mb-4">⊘</div>
            <h2 className="text-2xl font-semibold text-text-primary mb-2">
              Project Cancelled
            </h2>
            <p className="text-text-secondary mb-6">
              {project.name}
            </p>
            <Link
              href="/"
              className="btn-apple btn-apple-primary px-6 py-3 inline-block"
            >
              Back to Projects
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
