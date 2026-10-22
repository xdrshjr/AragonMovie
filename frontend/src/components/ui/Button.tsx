import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  /**
   * 文案在 loading 时显示的内容（默认 "Loading..."）。
   * 传了它，加载中就不会丢掉调用方想表达的语义（例如 "Generating..."）。
   */
  loadingText?: React.ReactNode;
  /**
   * loading 时保留 children 的宽度（默认 true）：children 以不可见方式留在
   * 布局里，spinner + 文案覆盖在上面，避免按钮宽度跳变。
   */
  keepWidthOnLoading?: boolean;
  as?: 'button' | 'span';
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  loadingText,
  keepWidthOnLoading = true,
  disabled,
  as = 'button',
  children,
  className = '',
  ...props
}) => {
  const baseClasses = 'btn-apple transition-apple inline-flex items-center justify-center focus-visible:outline-none';

  const variantClasses = {
    primary: 'btn-apple-primary',
    secondary: 'btn-apple-secondary',
    danger: 'bg-apple-red text-white border-transparent hover:bg-apple-red/90 active:bg-apple-red/80',
  };
  
  const sizeClasses = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-5 py-2.5 text-base',
  };
  
  const combinedClasses = [
    baseClasses,
    variantClasses[variant],
    sizeClasses[size],
    (disabled || loading) && 'opacity-50 cursor-not-allowed',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const loadingContent = (
    <span className="flex items-center justify-center gap-2">
      <span className="spinner-apple" aria-hidden="true" />
      <span>{loadingText ?? 'Loading...'}</span>
    </span>
  );

  let content: React.ReactNode = children;

  if (loading) {
    content = keepWidthOnLoading ? (
      // children 保留在布局中（不可见）以固定宽度，加载态覆盖显示
      <span className="relative inline-flex items-center justify-center">
        <span className="invisible inline-flex items-center" aria-hidden="true">
          {children}
        </span>
        <span className="absolute inset-0 flex items-center justify-center">
          {loadingContent}
        </span>
      </span>
    ) : (
      loadingContent
    );
  }

  if (as === 'span') {
    return (
      <span className={combinedClasses} aria-busy={loading || undefined} {...(props as any)}>
        {content}
      </span>
    );
  }

  return (
    <button
      className={combinedClasses}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {content}
    </button>
  );
};

export default Button;
