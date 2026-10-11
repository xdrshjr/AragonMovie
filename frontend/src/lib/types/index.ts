/**
 * Shared frontend types (reverse-engineered from component usage and aligned
 * with the backend's JSON payloads, which use snake_case).
 */

export type ProjectStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type GenerationMode = 'full' | 'quick';

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  video_type: string;
  mode: GenerationMode;
  task_id?: string | null;
  status: ProjectStatus;
  progress: number;
  thumbnail_path?: string | null;
  video_path?: string | null;
  created_at: string;
  updated_at?: string;
  duration?: number | null;
  scene_count?: number | null;
  character_count?: number | null;
  error_message?: string | null;
  metadata?: Record<string, unknown>;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
  video_type: string;
  mode: GenerationMode;
}

/** Character state used by Step2CharacterImages and the workflow page. */
export interface Character {
  name: string;
  description: string;
  mode: 'generate' | 'upload';
  imageCount: number;
  generatedImages: string[];
  selectedImage: string | null;
}

/** Scene state used by Step3SceneImages and the workflow page. */
export interface Scene {
  id: string;
  description: string;
  location: string;
  time: string;
  mode: 'generate' | 'upload';
  imageCount: number;
  generatedImages: string[];
  selectedImage: string | null;
}

/** Quick-mode scene built from uploaded images (QuickStep1/2). */
export interface QuickModeScene {
  id: string;
  imageFile?: File;
  imagePreview: string;
  imageBase64: string;
  duration: number;
  prompt: string;
  cameraMotion?: string;
  motionStrength: number;
}

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEntry {
  level: LogLevel;
  component: string;
  message: string;
  timestamp: string | number;
  data?: unknown;
}

/** Mirrors backend `TaskResult` (GET /api/v1/tasks/{task_id}). */
export interface TaskStatusResponse {
  task_id: string;
  status: ProjectStatus;
  progress: number;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  result?: WorkflowResult | null;
  error?: TaskError | null;
}

export interface TaskError {
  error_type?: string;
  message?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface WorkflowResult {
  video_url: string;
  duration?: number;
  scene_count?: number;
  character_count?: number;
  assets?: Array<{
    type: string;
    url: string;
    filename?: string;
  }>;
  [key: string]: unknown;
}

/** Error thrown by apiClient for non-2xx backend responses. */
export class APIException extends Error {
  code: string;
  details: unknown;
  retryable: boolean;

  constructor(message: string, code = 'API_ERROR', details: unknown = null, retryable = false) {
    super(message);
    this.name = 'APIException';
    this.code = code;
    this.details = details;
    this.retryable = retryable;
  }
}

// Re-export the video-type taxonomy for convenience
export type { VideoType, VideoSubtype } from './videoTypes';
