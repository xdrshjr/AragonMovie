import React, { useId } from 'react';

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea: React.FC<TextareaProps> = ({
  label,
  error,
  helperText,
  className = '',
  id,
  ...props
}) => {
  // label 必须与控件真正关联：htmlFor/id + aria-describedby，
  // 这样点击 label 会聚焦文本框，屏幕阅读器能读出名称，getByLabel 也能定位。
  // useId() yields ':r0:' style ids; colons are legal in HTML but break CSS
  // selectors such as '#\:r0\:', so normalise them away.
  const generatedId = useId().replace(/:/g, '');
  const textareaId = id ?? `textarea-${generatedId}`;
  const errorId = `${textareaId}-error`;
  const helperId = `${textareaId}-helper`;
  const describedBy = error ? errorId : helperText ? helperId : undefined;

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={textareaId}
          className="block text-apple-body font-medium mb-2 text-text-primary"
        >
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        className={`input-apple min-h-[120px] resize-vertical ${
          error ? 'border-apple-red' : ''
        } ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...props}
      />
      {error && (
        <p id={errorId} role="alert" className="mt-1 text-sm text-apple-red">
          {error}
        </p>
      )}
      {helperText && !error && (
        <p id={helperId} className="mt-1 text-sm text-text-secondary">
          {helperText}
        </p>
      )}
    </div>
  );
};

export default Textarea;
