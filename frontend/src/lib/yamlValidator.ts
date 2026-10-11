/**
 * YAML script validation used by Step1 before generation starts.
 *
 * Rules mirror the backend parser's expectations (models/script_models.py):
 * - top-level mapping with a `scenes` list
 * - each scene has an id (scene_id|id), location, description
 * - `characters` (optional) entries need a name
 */

import { parseYamlScript } from './yamlParser';
import type { ParsedScript } from './yamlParser';

export interface YamlValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
  data?: ParsedScript;
}

const VALID_SHOT_TYPES = [
  'close_up',
  'medium_shot',
  'long_shot',
  'full_shot',
  'extreme_close_up',
  'over_shoulder',
];

const VALID_CAMERA_MOVEMENTS = ['static', 'pan', 'tilt', 'zoom', 'dolly', 'tracking'];

export function validateYAMLScript(scriptText: string): YamlValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  const parsed = parseYamlScript(scriptText);
  if (!parsed.success || !parsed.data) {
    return { isValid: false, errors: [parsed.error ?? 'Failed to parse YAML'], warnings };
  }

  const data = parsed.data;

  if (!data.title) {
    warnings.push('Missing "title" — a default title will be used');
  }

  if (!Array.isArray(data.characters) || data.characters.length === 0) {
    warnings.push('No characters defined; character reference images will be skipped');
  } else {
    data.characters.forEach((c, i) => {
      if (!c.name) errors.push(`characters[${i}] is missing "name"`);
    });
  }

  if (!Array.isArray(data.scenes) || data.scenes.length === 0) {
    errors.push('Script must contain at least one scene under "scenes"');
    return { isValid: false, errors, warnings, data };
  }

  const seenIds = new Set<string>();
  data.scenes.forEach((scene, i) => {
    const label = scene.id || `scenes[${i}]`;
    if (!scene.id) errors.push(`${label}: missing scene id ("scene_id")`);
    if (seenIds.has(scene.id)) errors.push(`Duplicate scene id: ${scene.id}`);
    seenIds.add(scene.id);
    if (!scene.location) warnings.push(`${label}: missing "location"`);
    if (!scene.description) warnings.push(`${label}: missing "description"`);
    if (!scene.time) warnings.push(`${label}: missing "time"`);
  });

  // Loose checks on raw shot/camera values (unknown values are warnings,
  // the backend maps or defaults them)
  const raw = scriptText;
  const shotMatch = raw.match(/shot_type:\s*"?(\w+)"?/g) ?? [];
  for (const m of shotMatch) {
    const value = m.replace(/shot_type:\s*"?/, '').replace(/"?$/, '');
    if (!VALID_SHOT_TYPES.includes(value)) {
      warnings.push(`Unknown shot_type "${value}" (allowed: ${VALID_SHOT_TYPES.join(', ')})`);
    }
  }
  const camMatch = raw.match(/camera_movement:\s*"?(\w+)"?/g) ?? [];
  for (const m of camMatch) {
    const value = m.replace(/camera_movement:\s*"?/, '').replace(/"?$/, '');
    if (!VALID_CAMERA_MOVEMENTS.includes(value)) {
      warnings.push(
        `Unknown camera_movement "${value}" (allowed: ${VALID_CAMERA_MOVEMENTS.join(', ')})`
      );
    }
  }

  return { isValid: errors.length === 0, errors, warnings, data };
}

/** A ready-to-edit sample matching templates/default/script.yaml. */
export function getSampleYAMLScript(): string {
  return `title: "城市傍晚"
description: "一个关于加班程序员在傍晚天台遇见同事的温情短剧"

characters:
  - name: "李明"
    description: "28岁程序员，穿着格子衫，背着双肩包，疲惫但眼神明亮"
    age: 28
    gender: "male"
    appearance: "黑色短发，戴黑框眼镜，格子衬衫，牛仔裤"
  - name: "小雨"
    description: "26岁设计师，穿着米色风衣，温柔安静"
    age: 26
    gender: "female"
    appearance: "长发披肩，米色风衣，白色运动鞋"

scenes:
  - scene_id: "scene_001"
    location: "写字楼顶楼天台"
    time: "傍晚"
    weather: "晴"
    atmosphere: "夕阳温暖，城市天际线剪影"
    description: "天台水泥地面，远处是夕阳下的城市轮廓，风力发电机组缓缓转动"
    shot_type: "long_shot"
    camera_movement: "static"
    duration: 8.0
    visual_style: "cinematic"
    color_tone: "warm"
    action: "李明靠着围栏看夕阳，手里拿着一罐咖啡"
    characters:
      - "李明"
    dialogues:
      - character: "李明"
        content: "又是最后一个走。"
        emotion: "疲惫"
        voice_style: "轻声自语"

  - scene_id: "scene_002"
    location: "写字楼顶楼天台"
    time: "傍晚"
    weather: "晴"
    atmosphere: "夕阳渐暗，暖光斜射"
    description: "小雨推开天台门走来，逆光剪影"
    shot_type: "medium_shot"
    camera_movement: "pan"
    duration: 6.0
    visual_style: "cinematic"
    color_tone: "warm"
    action: "小雨走向李明，微微一笑"
    characters:
      - "李明"
      - "小雨"
    dialogues:
      - character: "小雨"
        content: "还没走？一起下去吧。"
        emotion: "温和"
        voice_style: "轻快"
`;
}
