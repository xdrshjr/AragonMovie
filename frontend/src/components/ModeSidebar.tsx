'use client';

import { GenerationMode } from '@/lib/types';

interface ModeSidebarProps {
  currentMode: GenerationMode;
  onModeChange: (mode: GenerationMode) => void;
}

export default function ModeSidebar({ currentMode, onModeChange }: ModeSidebarProps) {
  const modes = [
    {
      id: 'full' as GenerationMode,
      name: '完整模式',
      icon: '📝',
    },
    {
      id: 'quick' as GenerationMode,
      name: '快速模式',
      icon: '⚡',
    },
  ];

  return (
    <div className="w-16 h-full bg-surface border-r border-hairline flex flex-col items-center py-4 gap-4">
      {modes.map((mode) => (
        <button
          key={mode.id}
          onClick={() => onModeChange(mode.id)}
          title={mode.name}
          className={`
            w-9 h-9 rounded-lg border border-transparent transition-all duration-200
            flex items-center justify-center
            ${
              currentMode === mode.id
                ? 'bg-accent-soft text-accent-text border border-accent-border shadow-apple-sm'
                : 'bg-surface-elevated text-text-secondary hover:bg-surface-hover hover:text-text-primary border border-hairline'
            }
          `}
        >
          <span className="text-xl">{mode.icon}</span>
        </button>
      ))}
    </div>
  );
}
