import React, { useEffect, useRef } from 'react';
import { LogEntry } from '@/lib/types';

interface LogViewerProps {
  logs: LogEntry[];
  maxHeight?: string;
  autoScroll?: boolean;
}

export const LogViewer: React.FC<LogViewerProps> = ({
  logs,
  maxHeight = '400px',
  autoScroll = true,
}) => {
  const logEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      // Scroll the container to bottom
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const getLevelColor = (level: LogEntry['level']) => {
    const colors = {
      debug: 'text-text-secondary',
      info: 'text-accent-text',
      warn: 'text-warning-text',
      error: 'text-error-text',
    };
    return colors[level];
  };

  const getLevelBg = (level: LogEntry['level']) => {
    const colors = {
      debug: 'bg-transparent',
      info: 'bg-accent-soft',
      warn: 'bg-warning-soft',
      error: 'bg-error-soft',
    };
    return colors[level];
  };

  return (
    <div
      ref={containerRef}
      className="bg-background-deep border border-hairline rounded-apple-md p-4 font-mono text-[13px] leading-5 overflow-y-auto scroll-smooth"
      style={{ maxHeight }}
    >
      {logs.length === 0 ? (
        <p className="text-text-secondary text-center py-8">
          No logs available yet...
        </p>
      ) : (
        <div className="space-y-1">
          {logs.map((log, index) => (
            <div
              key={index}
              className={`p-2 rounded border border-transparent transition-apple ${getLevelBg(log.level)}`}
            >
              <div className="flex items-start gap-3">
                <span className="text-text-tertiary text-xs whitespace-nowrap">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span
                  className={`font-semibold text-xs uppercase ${getLevelColor(log.level)}`}
                >
                  {log.level}
                </span>
                <span className="text-text-secondary text-xs">
                  [{log.component}]
                </span>
                <span className="text-text-primary flex-1 whitespace-pre-wrap break-words">{log.message}</span>
              </div>
              {log.data != null && (
                <pre className="mt-1 ml-24 text-xs text-text-secondary overflow-x-auto">
                  {JSON.stringify(log.data, null, 2)}
                </pre>
              )}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}
    </div>
  );
};

export default LogViewer;

