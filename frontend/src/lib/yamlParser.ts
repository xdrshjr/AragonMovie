/**
 * YAML script parsing on the client.
 *
 * The script format matches the backend's `Script` model
 * (models/script_models.py): `{ title, characters: [...], scenes: [...] }`
 * where scenes use `scene_id` (or `id`) for identification.
 */

import yaml from 'js-yaml';

export interface ParsedCharacter {
  name: string;
  description: string;
  age?: number;
  gender?: string;
  appearance?: string;
}

export interface ParsedScene {
  id: string;
  description: string;
  location: string;
  time: string;
  weather?: string;
  atmosphere?: string;
  characters?: string[];
  action?: string;
}

export interface ParsedScript {
  title?: string;
  description?: string;
  characters: ParsedCharacter[];
  scenes: ParsedScene[];
}

export interface YamlParseResult {
  success: boolean;
  data?: ParsedScript;
  error?: string;
}

/** Parse a YAML script string into a normalized structure. */
export function parseYamlScript(scriptText: string): YamlParseResult {
  if (!scriptText || !scriptText.trim()) {
    return { success: false, error: 'Script is empty' };
  }

  // Strip a surrounding markdown code fence if present
  let cleaned = scriptText.trim();
  const fence = cleaned.match(/^```(?:yaml|yml)?\s*\n([\s\S]*?)\n```$/);
  if (fence) {
    cleaned = fence[1].trim();
  }

  let raw: unknown;
  try {
    raw = yaml.load(cleaned);
  } catch (e) {
    return {
      success: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }

  if (raw == null || typeof raw !== 'object') {
    return { success: false, error: 'Script is not a valid YAML mapping' };
  }

  const doc = raw as Record<string, unknown>;
  const data: ParsedScript = {
    title: typeof doc.title === 'string' ? doc.title : undefined,
    description: typeof doc.description === 'string' ? doc.description : undefined,
    characters: [],
    scenes: [],
  };

  // Characters may live top-level and/or referenced inside scenes
  if (Array.isArray(doc.characters)) {
    data.characters = doc.characters
      .map((c) => normalizeCharacter(c))
      .filter((c): c is ParsedCharacter => c !== null);
  }

  if (Array.isArray(doc.scenes)) {
    data.scenes = doc.scenes
      .map((s, index) => normalizeScene(s, index))
      .filter((s): s is ParsedScene => s !== null);
  }

  return { success: true, data };
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function normalizeCharacter(raw: unknown): ParsedCharacter | null {
  if (raw == null) return null;
  if (typeof raw === 'string') {
    return { name: raw, description: '' };
  }
  const obj = raw as Record<string, unknown>;
  const name = asString(obj.name).trim();
  if (!name) return null;
  return {
    name,
    description: asString(obj.description || obj.appearance),
    age: typeof obj.age === 'number' ? obj.age : undefined,
    gender: typeof obj.gender === 'string' ? obj.gender : undefined,
    appearance: typeof obj.appearance === 'string' ? obj.appearance : undefined,
  };
}

function normalizeScene(raw: unknown, index: number): ParsedScene | null {
  if (raw == null) return null;
  if (typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const id = asString(obj.scene_id || obj.id).trim() || `scene_${String(index + 1).padStart(3, '0')}`;
  return {
    id,
    description: asString(obj.description || obj.action),
    location: asString(obj.location),
    time: asString(obj.time),
    weather: typeof obj.weather === 'string' ? obj.weather : undefined,
    atmosphere: typeof obj.atmosphere === 'string' ? obj.atmosphere : undefined,
    characters: Array.isArray(obj.characters)
      ? obj.characters.map((c) => (typeof c === 'string' ? c : asString((c as Record<string, unknown>)?.name)))
      : undefined,
    action: typeof obj.action === 'string' ? obj.action : undefined,
  };
}

/** Extract the characters list from a parsed script (falls back to scene refs). */
export function extractCharactersFromParsedScript(data: ParsedScript): ParsedCharacter[] {
  if (!data) return [];
  if (data.characters.length > 0) return data.characters;

  // Fall back to names referenced from scenes
  const seen = new Map<string, ParsedCharacter>();
  for (const scene of data.scenes) {
    for (const name of scene.characters ?? []) {
      const trimmed = name.trim();
      if (trimmed && !seen.has(trimmed)) {
        seen.set(trimmed, { name: trimmed, description: '' });
      }
    }
  }
  return Array.from(seen.values());
}

/** Extract the scenes list from a parsed script. */
export function extractScenesFromParsedScript(data: ParsedScript): ParsedScene[] {
  if (!data) return [];
  return data.scenes;
}
