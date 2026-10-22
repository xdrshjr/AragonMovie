import React from 'react';

interface CardProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  className?: string;
  hoverable?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  title,
  subtitle,
  className = '',
  hoverable = false,
}) => {
  return (
    <div
      className={`card-apple border border-hairline ${
        hoverable ? '' : 'hover:shadow-apple-md hover:transform-none'
      } ${className}`}
    >
      {(title || subtitle) && (
        <div className="mb-4">
          {title && (
            <h3 className="text-lg font-semibold text-text-primary tracking-[-0.01em]">
              {title}
            </h3>
          )}
          {subtitle && (
            <p className="text-sm text-text-secondary mt-1">
              {subtitle}
            </p>
          )}
        </div>
      )}
      {children}
    </div>
  );
};

export default Card;
