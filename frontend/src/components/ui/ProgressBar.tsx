import React from 'react';

interface ProgressBarProps {
  progress: number; // 0-100
  label?: string;
  showPercentage?: boolean;
  color?: 'blue' | 'green' | 'orange' | 'red' | 'gray';
  size?: 'sm' | 'md' | 'lg';
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  progress,
  label,
  showPercentage = true,
  color = 'gray',
  size = 'md',
}) => {
  const clampedProgress = Math.min(Math.max(progress, 0), 100);

  const colorClasses = {
    blue: 'bg-accent',
    green: 'bg-success',
    orange: 'bg-warning',
    red: 'bg-error',
    gray: 'bg-[#EDEDF0]',
  };
  
  const sizeClasses = {
    sm: 'h-1',
    md: 'h-1.5',
    lg: 'h-2',
  };

  return (
    <div className="w-full">
      {(label || showPercentage) && (
        <div className="flex justify-between items-center mb-2">
          {label && (
            <span className="text-apple-subheadline text-text-primary">
              {label}
            </span>
          )}
          {showPercentage && (
            <span className="text-apple-subheadline text-text-secondary font-medium">
              {Math.round(clampedProgress)}%
            </span>
          )}
        </div>
      )}
      <div className={`progress-apple ${sizeClasses[size]}`}>
        <div
          className={`progress-apple-fill ${colorClasses[color]}`}
          style={{ width: `${clampedProgress}%` }}
        />
      </div>
    </div>
  );
};

export default ProgressBar;

