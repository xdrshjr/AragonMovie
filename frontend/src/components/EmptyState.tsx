/**
 * EmptyState Component
 *
 * Displays an empty state with icon, message, and call-to-action
 */

import React from 'react';
import Link from 'next/link';

interface EmptyStateProps {
  icon?: string;
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon = '🎬',
  title,
  description,
  actionLabel,
  actionHref,
  onAction,
}) => {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-4">
      {/* Icon */}
      <div className="text-8xl mb-6 opacity-50">
        {icon}
      </div>

      {/* Title */}
      <h2 className="text-2xl font-semibold text-text-primary mb-3">
        {title}
      </h2>

      {/* Description */}
      <p className="text-base text-text-secondary text-center max-w-md mb-8">
        {description}
      </p>

      {/* Action Button */}
      {(actionLabel && (actionHref || onAction)) && (
        actionHref ? (
          <Link
            href={actionHref}
            className="btn-apple btn-apple-primary px-6 py-3 text-base"
          >
            {actionLabel}
          </Link>
        ) : (
          <button
            onClick={onAction}
            className="btn-apple btn-apple-primary px-6 py-3 text-base"
          >
            {actionLabel}
          </button>
        )
      )}
    </div>
  );
};

export default EmptyState;
