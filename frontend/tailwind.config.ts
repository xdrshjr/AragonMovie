import type { Config } from 'tailwindcss';

/**
 * Every brand-ish colour resolves to a CSS custom property declared in
 * `src/app/globals.css`, so markup never hardcodes a light surface. The app is
 * dark-only (`<html class="dark">`), which keeps `dark:` variants meaningful
 * while the tokens themselves already point at the gray-black palette.
 */
const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Gray-black surfaces
        background: 'var(--color-background)',
        'background-deep': 'var(--color-background-deep)',
        surface: 'var(--color-surface)',
        'surface-elevated': 'var(--color-surface-elevated)',
        'surface-hover': 'var(--color-surface-hover)',
        // Hairline separators
        hairline: 'var(--color-border)',
        'hairline-strong': 'var(--color-border-strong)',
        // Typography
        'text-primary': 'var(--color-text-primary)',
        'text-secondary': 'var(--color-text-secondary)',
        'text-tertiary': 'var(--color-text-tertiary)',
        // Restrained cool-indigo accent
        accent: 'var(--color-accent)',
        'accent-strong': 'var(--color-accent-strong)',
        'accent-soft': 'var(--color-accent-soft)',
        'accent-border': 'var(--color-accent-border)',
        'accent-ring': 'var(--color-accent-ring)',
        'accent-text': 'var(--color-accent-text)',
        primary: 'var(--color-accent)',
        'primary-strong': 'var(--color-accent-strong)',
        // Semantic tones — readable on #0A0A0B
        success: 'var(--color-success)',
        'success-soft': 'var(--color-success-soft)',
        'success-border': 'var(--color-success-border)',
        'success-text': 'var(--color-success-text)',
        warning: 'var(--color-warning)',
        'warning-soft': 'var(--color-warning-soft)',
        'warning-border': 'var(--color-warning-border)',
        'warning-text': 'var(--color-warning-text)',
        error: 'var(--color-error)',
        'error-soft': 'var(--color-error-soft)',
        'error-border': 'var(--color-error-border)',
        'error-text': 'var(--color-error-text)',
        // Apple-inspired accents, tuned for dark backgrounds
        apple: {
          blue: '#7C86FF',
          'blue-dark': '#6A74F0',
          purple: '#9C8CFF',
          green: '#3FD07A',
          orange: '#FFB020',
          red: '#FF5A57',
          pink: '#FF7BA9',
          yellow: '#FFD166',
          teal: '#5AC8FA',
          indigo: '#7C86FF',
          gray: 'var(--color-surface-elevated)',
          'gray-hover': 'var(--color-surface-hover)',
          'gray-active': 'var(--color-border-strong)',
          'gray-light': 'var(--color-border)',
        },
        // Legacy aliases kept so pre-existing `dark-*` references keep resolving
        'dark-background': 'var(--color-background)',
        'dark-surface': 'var(--color-surface)',
        'dark-surface-elevated': 'var(--color-surface-elevated)',
        'dark-text-primary': 'var(--color-text-primary)',
        'dark-text-secondary': 'var(--color-text-secondary)',
        'dark-text-tertiary': 'var(--color-text-tertiary)',
      },
      fontFamily: {
        sans: [
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"SF Pro Display"',
          '"Segoe UI"',
          'Roboto',
          'Oxygen',
          'Ubuntu',
          'Cantarell',
          'sans-serif',
        ],
      },
      borderRadius: {
        'apple-sm': '8px',
        'apple-md': '12px',
        'apple-lg': '16px',
        'apple-xl': '20px',
      },
      boxShadow: {
        'apple-sm': 'var(--shadow-sm)',
        'apple-md': 'var(--shadow-md)',
        'apple-lg': 'var(--shadow-lg)',
        'apple-xl': 'var(--shadow-xl)',
        'apple-glow': '0 0 0 1px var(--color-accent-border), 0 12px 32px -16px rgba(124, 134, 255, 0.55)',
      },
      // A dark page needs a dark ring offset, otherwise focus rings show a white slab.
      ringOffsetColor: {
        DEFAULT: 'var(--color-background)',
      },
      transitionDuration: {
        apple: '240ms',
      },
      transitionTimingFunction: {
        apple: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [],
  darkMode: 'class',
};

export default config;
