/**
 * Resolve which image-generation service the backend is actually using.
 *
 * The workflow steps used to hardcode `service: 'doubao'`, which ignores both
 * `.env` (`IMAGE_SERVICE_TYPE`) and the runtime settings center
 * (`image_service_type`) — on a Token-Plan-only setup "Auto Generate" always
 * failed with missing-credentials errors.
 *
 * Resolution order:
 *   1. `NEXT_PUBLIC_IMAGE_SERVICE_TYPE` (explicit frontend override, optional)
 *   2. `GET /api/v1/settings` → `image.service_type` (hot-reloadable settings)
 *   3. `undefined` → the request omits `service`, and the backend falls back to
 *      its own effective `settings.image_service_type`
 *
 * The value is cached briefly (see `CACHE_TTL_MS`) and dropped immediately by
 * `invalidateActiveImageService()`, which the settings page calls after saving.
 */

import { apiClient } from '@/lib/api';
import { logger } from '@/lib/logger';

export type ImageServiceType = 'doubao' | 'nano_banana' | 'midjourney' | 'ali_token_plan';

const CACHE_TTL_MS = 30_000;

let cached: { value: Promise<string | undefined>; at: number } | null = null;

function envOverride(): string | undefined {
  const value = process.env.NEXT_PUBLIC_IMAGE_SERVICE_TYPE;
  return value && value.trim() ? value.trim() : undefined;
}

function isFresh(): boolean {
  return cached !== null && Date.now() - cached.at < CACHE_TTL_MS;
}

/**
 * Resolve the effective image service name.
 *
 * Returns `undefined` when it cannot be determined — callers should then omit
 * the `service` field so the backend applies its configured default.
 */
export async function resolveActiveImageService(): Promise<string | undefined> {
  const override = envOverride();
  if (override) {
    return override;
  }

  if (!isFresh()) {
    const value = apiClient.settings
      .get()
      .then((response) => response?.settings?.image?.service_type)
      .catch((err) => {
        logger.warn(
          'imageService',
          'Could not read image service from backend settings, falling back to backend default',
          err
        );
        cached = null;
        return undefined;
      });
    cached = { value, at: Date.now() };
  }

  return cached!.value;
}

/** Drop the cached value (call after the settings center is updated). */
export function invalidateActiveImageService(): void {
  cached = null;
}
