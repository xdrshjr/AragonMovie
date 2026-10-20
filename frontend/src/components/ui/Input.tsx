import React, { useId } from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  helperText,
  className = '',
  id,
  ...props
}) => {
  // label 必须与控件真正关联：htmlFor/id + aria-describedby，
  // 这样点击 label 会聚焦输入框，屏幕阅读器能读出名称，getByLabel 也能定位。
  // useId() yields ':r0:' style ids; colons are legal in HTML but break CSS
  // selectors such as '#\:r0\:', so normalise them away.
  const generatedId = useId().replace(/:/g, '');
  const inputId = id ?? `input-${generatedId}`;
  const errorId = `${inputId}-error`;
  const helperId = `${inputId}-helper`;
  const describedBy = error ? errorId : helperText ? helperId : undefined;

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-apple-body font-medium mb-2 text-text-primary"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`input-apple ${error ? 'border-apple-red' : ''} ${className}`}
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

export default Input;
