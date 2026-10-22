/**
 * ProjectGrid Component
 *
 * Displays a responsive grid of project cards with loading and empty states
 */

import React from 'react';
import { Project } from '@/lib/types';
import { ProjectCard } from './ProjectCard';
import { EmptyState } from './EmptyState';

interface ProjectGridProps {
  projects: Project[];
  isLoading?: boolean;
  onProjectDelete?: (projectId: string) => void;
}

const SkeletonCard: React.FC = () => (
  <div className="card-apple overflow-hidden animate-pulse">
    {/* Thumbnail Skeleton */}
    <div className="w-full aspect-video bg-background-deep" />

    {/* Content Skeleton */}
    <div className="p-4">
      {/* Title */}
      <div className="h-6 bg-surface-hover rounded mb-2 w-3/4" />

      {/* Description */}
      <div className="h-4 bg-surface-hover rounded mb-1 w-full" />
      <div className="h-4 bg-surface-hover rounded mb-3 w-2/3" />

      {/* Metadata */}
      <div className="flex gap-4 mb-3">
        <div className="h-3 bg-surface-hover rounded w-24" />
        <div className="h-3 bg-surface-hover rounded w-16" />
      </div>

      {/* Actions */}
      <div className="flex justify-between pt-3 border-t border-hairline">
        <div className="flex gap-2">
          <div className="h-6 bg-surface-hover rounded w-16" />
          <div className="h-6 bg-surface-hover rounded w-12" />
        </div>
        <div className="h-6 bg-surface-hover rounded w-16" />
      </div>
    </div>
  </div>
);

export const ProjectGrid: React.FC<ProjectGridProps> = ({
  projects,
  isLoading = false,
  onProjectDelete,
}) => {
  // Loading State
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {[...Array(8)].map((_, index) => (
          <SkeletonCard key={index} />
        ))}
      </div>
    );
  }

  // Empty State
  if (projects.length === 0) {
    return (
      <EmptyState
        icon="🎬"
        title="No Projects Yet"
        description="Create your first AI-generated video project to get started"
        actionLabel="+ New Project"
        actionHref="/projects/new"
      />
    );
  }

  // Project Grid
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      {projects.map((project, index) => (
        <div
          key={project.id}
          style={{
            animationDelay: `${index * 50}ms`,
          }}
        >
          <ProjectCard
            project={project}
            onDelete={onProjectDelete}
          />
        </div>
      ))}
    </div>
  );
};

export default ProjectGrid;
