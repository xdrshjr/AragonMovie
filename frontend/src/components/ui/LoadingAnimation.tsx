import React from 'react';

interface LoadingAnimationProps {
  size?: 'sm' | 'md' | 'lg';
  message?: string;
}

export const LoadingAnimation: React.FC<LoadingAnimationProps> = ({
  size = 'md',
  message,
}) => {
  const sizeClasses = {
    sm: 'w-6 h-6 border-2',
    md: 'w-12 h-12 border-[3px]',
    lg: 'w-16 h-16 border-4',
  };

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-8">
      <div className={`spinner-apple ${sizeClasses[size]}`} />
      {message && (
        <p className="text-apple-body text-text-secondary animate-pulse">
          {message}
        </p>
      )}
    </div>
  );
};

export default LoadingAnimation;

