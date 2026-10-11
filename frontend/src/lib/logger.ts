/**
 * Lightweight frontend logger.
 *
 * Usage: logger.info('ComponentName', 'what happened', optionalData)
 * Errors can be passed as the third argument and are stringified safely.
 */

type LogData = unknown;

function serialize(data: LogData): string {
  if (data instanceof Error) {
    return data.stack || `${data.name}: ${data.message}`;
  }
  if (typeof data === 'string') return data;
  try {
    return JSON.stringify(data);
  } catch {
    return String(data);
  }
}

function emit(level: 'debug' | 'info' | 'warn' | 'error', component: string, message: string, data?: LogData) {
  const prefix = `[${component}]`;
  const line = data === undefined ? `${prefix} ${message}` : `${prefix} ${message} ${serialize(data)}`;
  switch (level) {
    case 'debug':
      console.debug(line);
      break;
    case 'info':
      console.info(line);
      break;
    case 'warn':
      console.warn(line);
      break;
    case 'error':
      console.error(line);
      break;
  }
}

export const logger = {
  debug: (component: string, message: string, data?: LogData) => emit('debug', component, message, data),
  info: (component: string, message: string, data?: LogData) => emit('info', component, message, data),
  warn: (component: string, message: string, data?: LogData) => emit('warn', component, message, data),
  error: (component: string, message: string, data?: LogData) => emit('error', component, message, data),
};

export default logger;
