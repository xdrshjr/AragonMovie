/**
 * Homepage - Project List
 *
 * Displays all video generation projects with auto-refresh for in-progress tasks
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import { apiClient } from '@/lib/api';
import { Project } from '@/lib/types';
import { ProjectGrid } from '@/components/ProjectGrid';
import { logger } from '@/lib/logger';

export default function HomePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch projects from API
  const fetchProjects = useCallback(async () => {
    try {
      logger.info('HomePage', 'Fetching projects');
      const fetchedProjects = await apiClient.listProjects();
      setProjects(fetchedProjects);
      setError(null);
    } catch (err) {
      logger.error('HomePage', 'Failed to fetch projects', err);
      setError(err instanceof Error ? err.message : 'Failed to load projects');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // Auto-refresh for in-progress projects
  useEffect(() => {
    const hasInProgressProjects = projects.some(
      (p) => p.status === 'processing' || p.status === 'pending'
    );

    if (!hasInProgressProjects) {
      return;
    }

    logger.debug('HomePage', 'Setting up auto-refresh for in-progress projects');

    const intervalId = setInterval(() => {
      logger.debug('HomePage', 'Auto-refreshing project list');
      fetchProjects();
    }, 3000); // Poll every 3 seconds

    return () => {
      logger.debug('HomePage', 'Clearing auto-refresh interval');
      clearInterval(intervalId);
    };
  }, [projects, fetchProjects]);

  // Handle project deletion
  const handleProjectDelete = useCallback((projectId: string) => {
    logger.info('HomePage', `Project deleted: ${projectId}`);
    setProjects((prev) => prev.filter((p) => p.id !== projectId));
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <Header />

      {/* Main Content */}
      <main className="flex-1 px-8 py-8 overflow-y-auto">
        <div className="max-w-[1400px] mx-auto">
          {/* Page Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h2 className="text-3xl font-semibold tracking-[-0.02em] text-text-primary mb-2">
                My Projects
              </h2>
              <p className="text-base text-text-secondary">
                {isLoading
                  ? 'Loading projects...'
                  : `${projects.length} project${projects.length !== 1 ? 's' : ''}`}
              </p>
            </div>

            {/* New Project Button */}
            <Link
              href="/projects/new"
              className="btn-apple btn-apple-primary px-6 py-3 flex items-center gap-2"
            >
              <span className="text-lg">+</span>
              <span>New Project</span>
            </Link>
          </div>

          {/* Error Message */}
          {error && (
            <div className="card-apple p-6 mb-8 bg-error-soft border-error-border">
              <div className="flex items-start gap-3">
                <span className="text-2xl">⚠️</span>
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-error-text mb-1">
                    Failed to Load Projects
                  </h3>
                  <p className="text-sm text-text-secondary mb-3">
                    {error}
                  </p>
                  <button
                    onClick={fetchProjects}
                    className="btn-apple btn-apple-secondary text-sm px-4 py-2"
                  >
                    Try Again
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Project Grid */}
          <ProjectGrid
            projects={projects}
            isLoading={isLoading}
            onProjectDelete={handleProjectDelete}
          />
        </div>
      </main>
    </div>
  );
}
