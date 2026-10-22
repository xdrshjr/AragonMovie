/**
 * StatusBadge Component
 *
 * Displays a color-coded status badge for projects with animations
 */

import React from 'react';
import { ProjectStatus } from '@/lib/types';

interface StatusBadgeProps {
  status: ProjectStatus;
  className?: string;
}

const statusConfig: Record<ProjectStatus, {
  label: string;
  bgColor: string;
  textColor: string;
  icon: string;
  animate?: boolean;
}> = {
  pending: {
    label: 'Pending',
    bgColor: 'bg-[#FFB020] shadow-apple-sm',
    textColor: 'text-[#0A0A0B]',
    icon: '⏳',
  },
  processing: {
    label: 'Generating...',
    bgColor: 'bg-[#7C86FF] shadow-apple-sm',
    textColor: 'text-[#0A0A0B]',
    icon: '⚡',
    animate: true,
  },
  completed: {
    label: 'Completed',
    bgColor: 'bg-[#3FD07A] shadow-apple-sm',
    textColor: 'text-[#0A0A0B]',
    icon: '✓',
  },
  failed: {
    label: 'Failed',
    bgColor: 'bg-[#FF5A57] shadow-apple-sm',
    textColor: 'text-[#0A0A0B]',
    icon: '✕',
  },
  cancelled: {
    label: 'Cancelled',
    bgColor: 'bg-[#2A2A31] border border-hairline',
    textColor: 'text-text-secondary',
    icon: '⊘',
  },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  const config = statusConfig[status];

  return (
    <div
      className={`
        inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full
        text-xs font-medium
        ${config.bgColor} ${config.textColor}
        ${config.animate ? 'animate-pulse' : ''}
        ${className}
      `}
    >
      <span className="text-sm">{config.icon}</span>
      <span>{config.label}</span>
    </div>
  );
};

export default StatusBadge;
