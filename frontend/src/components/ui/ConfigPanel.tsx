'use client';

import React from 'react';

interface ConfigPanelProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}

export const ConfigPanel: React.FC<ConfigPanelProps> = ({
  title,
  description,
  children,
  className = '',
}) => {
  return (
    <div className={`bg-surface rounded-apple-lg border border-hairline p-6 shadow-apple-md ${className}`}>
      <div className="mb-4">
        <h3 className="text-apple-title-3 font-semibold text-text-primary mb-1">
          {title}
        </h3>
        {description && (
          <p className="text-apple-caption text-text-secondary">
            {description}
          </p>
        )}
      </div>
      <div className="space-y-4">
        {children}
      </div>
    </div>
  );
};

interface ConfigRowProps {
  label: string;
  description?: string;
  children: React.ReactNode;
  required?: boolean;
}

export const ConfigRow: React.FC<ConfigRowProps> = ({
  label,
  description,
  children,
  required = false,
}) => {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex-1 min-w-0">
        <label className="block text-apple-body font-medium text-text-primary mb-1">
          {label}
          {required && <span className="text-apple-red ml-1">*</span>}
        </label>
        {description && (
          <p className="text-apple-caption text-text-secondary">
            {description}
          </p>
        )}
      </div>
      <div className="flex-shrink-0">
        {children}
      </div>
    </div>
  );
};

interface CheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
  disabled?: boolean;
}

export const Checkbox: React.FC<CheckboxProps> = ({
  label,
  checked,
  onChange,
  description,
  disabled = false,
}) => {
  return (
    <label className={`flex items-start gap-3 cursor-pointer ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="mt-1 w-5 h-5 rounded border-hairline bg-background-deep text-accent focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background cursor-pointer disabled:cursor-not-allowed"
      />
      <div className="flex-1">
        <span className="text-apple-body text-text-primary block">
          {label}
        </span>
        {description && (
          <span className="text-apple-caption text-text-secondary block mt-1">
            {description}
          </span>
        )}
      </div>
    </label>
  );
};

interface NumberInputProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}

export const NumberInput: React.FC<NumberInputProps> = ({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  disabled = false,
}) => {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      className="w-24 px-3 py-2 border border-hairline rounded-apple-md text-apple-body text-text-primary bg-background-deep transition-colors hover:border-hairline-strong focus:outline-none focus:ring-2 focus:ring-accent-ring focus:border-accent-border disabled:opacity-50 disabled:cursor-not-allowed"
    />
  );
};

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string; description?: string }>;
  disabled?: boolean;
  className?: string;
  /** Lets a sibling <label htmlFor> point at this control */
  id?: string;
  name?: string;
  'aria-label'?: string;
}

export const Select: React.FC<SelectProps> = ({
  value,
  onChange,
  options,
  disabled = false,
  className = '',
  id,
  name,
  'aria-label': ariaLabel,
}) => {
  return (
    <select
      id={id}
      name={name}
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={`px-4 py-2 border border-hairline rounded-apple-md text-apple-body text-text-primary bg-background-deep transition-colors hover:border-hairline-strong focus:outline-none focus:ring-2 focus:ring-accent-ring focus:border-accent-border disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
};

interface GenreCardProps {
  genre: string;
  label: string;
  description: string;
  selected: boolean;
  onClick: () => void;
}

export const GenreCard: React.FC<GenreCardProps> = ({
  label,
  description,
  selected,
  onClick,
}) => {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        relative p-4 rounded-apple-lg border-2 text-left transition-all duration-200
        ${selected
          ? 'border-accent bg-accent-soft shadow-apple-md'
          : 'border-hairline bg-surface hover:border-accent-border hover:shadow-apple-sm'
        }
      `}
    >
      {selected && (
        <div className="absolute top-2 right-2 w-6 h-6 bg-accent rounded-full flex items-center justify-center">
          <svg className="w-4 h-4 text-[#0A0A0B]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
      )}
      <div className="pr-8">
        <h4 className="text-apple-headline font-semibold text-text-primary mb-1">
          {label}
        </h4>
        <p className="text-apple-caption text-text-secondary">
          {description}
        </p>
      </div>
    </button>
  );
};
