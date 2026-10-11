/**
 * Image URL/base64 helpers.
 *
 * The image-generation endpoint returns either an `image_url` or `image_b64`;
 * components need both normalized to strings that an <img src> accepts.
 */

/** A value usable directly as <img src>: http(s) URL or data URL. */
export function isValidImageUrl(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0) return false;
  return (
    value.startsWith('http://') ||
    value.startsWith('https://') ||
    value.startsWith('data:image/')
  );
}

interface RawImageResult {
  image_url?: string | null;
  image_b64?: string | null;
  image_base64?: string | null;
  service?: string;
  [key: string]: unknown;
}

/**
 * Normalize an array of image-generation responses into displayable srcs.
 * Base64 payloads (with or without the data-URL prefix) become data URLs.
 */
export function processImageResults(results: RawImageResult[]): string[] {
  const urls: string[] = [];
  for (const result of results) {
    if (!result) continue;
    if (isValidImageUrl(result.image_url)) {
      urls.push(result.image_url as string);
      continue;
    }
    const b64 = result.image_b64 ?? result.image_base64;
    if (typeof b64 === 'string' && b64.length > 0) {
      urls.push(b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}`);
    }
  }
  return urls;
}
