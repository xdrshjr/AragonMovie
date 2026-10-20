/**
 * ProjectCard Component
 *
 * Displays a project card with thumbnail, status, metadata, and actions
 */

import React, { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Project } from '@/lib/types';
import { StatusBadge } from './StatusBadge';
import { apiClient } from '@/lib/api';

interface ProjectCardProps {
  project: Project;
  onDelete?: (projectId: string) => void;
}

export const ProjectCard: React.FC<ProjectCardProps> = ({ project, onDelete }) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return 'N/A';
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!showDeleteConfirm) {
      setShowDeleteConfirm(true);
      return;
    }

    setIsDeleting(true);
    try {
      await apiClient.deleteProject(project.id);
      if (onDelete) {
        onDelete(project.id);
      }
    } catch (error) {
      console.error('Failed to delete project:', error);
      alert('Failed to delete project. Please try again.');
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const thumbnailUrl = project.thumbnail_path
    ? apiClient.getProjectThumbnailUrl(project.id)
    : null;

  return (
    <Link href={`/projects/${project.id}`}>
      <div
        className="
          card-apple overflow-hidden cursor-pointer
          transition-all duration-300
          hover:scale-[1.02] hover:shadow-apple-lg
          fade-in
        "
      >
        {/* Thumbnail */}
        <div className="relative w-full aspect-video bg-[var(--color-surface-elevated)]">
          {thumbnailUrl ? (
            <Image
              src={thumbnailUrl}
              alt={project.name}
              fill
              className="object-cover"
              unoptimized
            />
          ) : (
            <div className="flex items-center justify-center h-full text-6xl opacity-30">
              🎬
            </div>
          )}

          {/* Status Badge Overlay */}
          <div className="absolute top-3 right-3">
            <StatusBadge status={project.status} />
          </div>
        </div>

        {/* Content */}
        <div className="p-4">
          {/* Project Name */}
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2 line-clamp-1">
            {project.name}
          </h3>

          {/* Description */}
          {project.description && (
            <p className="text-sm text-[var(--color-text-secondary)] mb-3 line-clamp-2">
              {project.description}
            </p>
          )}

          {/* Metadata */}
          <div className="flex items-center gap-4 text-xs text-[var(--color-text-tertiary)] mb-3">
            <span className="flex items-center gap-1">
              📅 {formatDate(project.created_at)}
            </span>
            {project.duration && (
              <span className="flex items-center gap-1">
                ⏱️ {formatDuration(project.duration)}
              </span>
            )}
          </div>

          {/* Progress Bar (for in-progress projects) */}
          {project.status === 'processing' && (
            <div className="mb-3">
              <div className="flex items-center justify-between text-xs text-[var(--color-text-secondary)] mb-1">
                <span>Progress</span>
                <span>{project.progress}%</span>
              </div>
              <div className="progress-apple">
                <div
                  className="progress-apple-bar"
                  style={{ width: `${project.progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between pt-3 border-t border-[var(--color-border)]">
            <div className="flex items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
              <span className="px-2 py-1 rounded bg-[var(--color-surface-elevated)]">
                {project.video_type.replaceAll('_', ' ')}
              </span>
              <span className="px-2 py-1 rounded bg-[var(--color-surface-elevated)]">
                {project.mode}
              </span>
            </div>

            {/* Delete Button */}
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className={`
                text-xs px-3 py-1.5 rounded-md
                transition-colors duration-200
                ${showDeleteConfirm
                  ? 'bg-[#FF3B30] text-white hover:bg-[#FF2D1F]'
                  : 'text-[var(--color-text-tertiary)] hover:text-[#FF3B30] hover:bg-[var(--color-surface-elevated)]'
                }
                ${isDeleting ? 'opacity-50 cursor-not-allowed' : ''}
              `}
            >
              {isDeleting ? 'Deleting...' : showDeleteConfirm ? 'Confirm?' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    </Link>
  );
};

export default ProjectCard;
