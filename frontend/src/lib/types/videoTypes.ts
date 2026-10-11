/**
 * Video type taxonomy — frontend mirror of backend `models/video_types.py`.
 *
 * Keep the string unions in sync with the backend enums: these values are
 * sent to `/api/v1/workflow/generate` as `video_type` / `video_subtype`.
 */

export type VideoType = 'news_broadcast' | 'anime' | 'movie' | 'short_drama';

export type VideoSubtype =
  // news_broadcast
  | 'solo_anchor'
  | 'interview'
  | 'panel_discussion'
  | 'field_reporting'
  // anime
  | 'ghibli_style'
  | 'american_style'
  | 'chibi_sd'
  | 'realistic_anime'
  // movie
  | 'action'
  | 'drama'
  | 'sci_fi'
  | 'horror'
  | 'romance'
  // short_drama
  | 'modern_drama'
  | 'period_drama'
  | 'comedy_sketch'
  | 'romantic_short';

export interface VideoSubtypeDefinition {
  name_zh: string;
  name_en: string;
  description_zh: string;
  description_en: string;
  styleKeywords: string[];
}

export interface VideoTypeDefinition {
  icon: string;
  name_zh: string;
  name_en: string;
  description_zh: string;
  description_en: string;
  /** keyed by subtype id; plain Record so dynamic lookups typecheck */
  subtypes: Record<string, VideoSubtypeDefinition>;
}

export const VIDEO_TYPE_DEFINITIONS: Record<VideoType, VideoTypeDefinition> = {
  news_broadcast: {
    icon: '📰',
    name_zh: '新闻播报',
    name_en: 'News Broadcast',
    description_zh: '专业新闻播报视频',
    description_en: 'Professional news broadcast video',
    subtypes: {
      solo_anchor: {
        name_zh: '单人播报',
        name_en: 'Solo Anchor',
        description_zh: '单人新闻主播专业播报',
        description_en: 'Professional news anchor presenting alone',
        styleKeywords: ['professional', 'formal', 'clean lighting', 'studio setup'],
      },
      interview: {
        name_zh: '采访',
        name_en: 'Interview',
        description_zh: '主播采访嘉宾对话形式',
        description_en: 'Anchor interviewing guest(s)',
        styleKeywords: ['professional', 'conversational', 'interview setup', 'multiple angles'],
      },
      panel_discussion: {
        name_zh: '多人讨论',
        name_en: 'Panel Discussion',
        description_zh: '多位主播或专家讨论话题',
        description_en: 'Multiple anchors/experts discussing topics',
        styleKeywords: ['professional', 'round table', 'debate format', 'multiple participants'],
      },
      field_reporting: {
        name_zh: '现场报道',
        name_en: 'Field Reporting',
        description_zh: '记者现场实地报道',
        description_en: 'Reporter on location with live coverage',
        styleKeywords: ['on-location', 'outdoor', 'handheld camera', 'dynamic', 'live coverage'],
      },
    },
  },
  anime: {
    icon: '🌸',
    name_zh: '动漫',
    name_en: 'Anime',
    description_zh: '动画风格视频',
    description_en: 'Animated style video',
    subtypes: {
      ghibli_style: {
        name_zh: '吉卜力风格',
        name_en: 'Ghibli Style',
        description_zh: '手绘美学、柔和色彩、自然主题、奇幻风格',
        description_en: 'Hand-drawn aesthetic, soft colors, nature themes, whimsical',
        styleKeywords: ['hand-drawn', 'soft colors', 'nature', 'whimsical', 'Studio Ghibli style'],
      },
      american_style: {
        name_zh: '欧美风格',
        name_en: 'American Style',
        description_zh: '粗线条、鲜艳色彩、动作导向、漫画风格',
        description_en: 'Bold lines, vibrant colors, action-oriented, comic book feel',
        styleKeywords: ['bold lines', 'vibrant colors', 'action-packed', 'comic book style'],
      },
      chibi_sd: {
        name_zh: 'Q版/SD',
        name_en: 'Chibi/SD',
        description_zh: '超级变形角色、可爱、夸张表情',
        description_en: 'Super-deformed characters, cute, exaggerated expressions',
        styleKeywords: ['chibi', 'cute', 'super-deformed', 'exaggerated', 'kawaii'],
      },
      realistic_anime: {
        name_zh: '写实动漫',
        name_en: 'Realistic Anime',
        description_zh: '细节丰富、真实比例、电影级光影',
        description_en: 'Detailed characters, realistic proportions, cinematic lighting',
        styleKeywords: ['detailed', 'realistic proportions', 'cinematic lighting', 'high quality anime'],
      },
    },
  },
  movie: {
    icon: '🎬',
    name_zh: '电影',
    name_en: 'Movie',
    description_zh: '电影质感的长镜头叙事视频',
    description_en: 'Cinematic long-form narrative video',
    subtypes: {
      action: {
        name_zh: '动作',
        name_en: 'Action',
        description_zh: '高速节奏、打斗场面、特技效果',
        description_en: 'Fast-paced, fight scenes, stunts',
        styleKeywords: ['dynamic', 'fast-paced', 'stunts', 'impactful'],
      },
      drama: {
        name_zh: '剧情',
        name_en: 'Drama',
        description_zh: '情感驱动的角色故事',
        description_en: 'Emotion-driven character stories',
        styleKeywords: ['emotional', 'character-driven', 'realistic', 'dramatic'],
      },
      sci_fi: {
        name_zh: '科幻',
        name_en: 'Sci-Fi',
        description_zh: '未来世界、科技元素、特效场面',
        description_en: 'Futuristic worlds, technology, VFX',
        styleKeywords: ['futuristic', 'technology', 'VFX', 'sci-fi atmosphere'],
      },
      horror: {
        name_zh: '恐怖',
        name_en: 'Horror',
        description_zh: '悬疑紧张、惊悚氛围',
        description_en: 'Suspense, tension, thrills',
        styleKeywords: ['suspense', 'tension', 'dark atmosphere', 'thriller'],
      },
      romance: {
        name_zh: '爱情',
        name_en: 'Romance',
        description_zh: '浪漫情感、温馨故事',
        description_en: 'Romantic, heartwarming stories',
        styleKeywords: ['romantic', 'warm', 'soft lighting', 'emotional'],
      },
    },
  },
  short_drama: {
    icon: '🎭',
    name_zh: '短剧',
    name_en: 'Short Drama',
    description_zh: '节奏紧凑的剧情短视频',
    description_en: 'Short-form drama with tight pacing',
    subtypes: {
      modern_drama: {
        name_zh: '现代都市',
        name_en: 'Modern Drama',
        description_zh: '现代都市背景的短剧',
        description_en: 'Contemporary urban settings',
        styleKeywords: ['realistic', 'contemporary', 'dramatic', 'character-focused'],
      },
      period_drama: {
        name_zh: '古装',
        name_en: 'Period Drama',
        description_zh: '历史或古装背景的短剧',
        description_en: 'Historical or period settings',
        styleKeywords: ['period costume', 'historical', 'classical', 'elegant'],
      },
      comedy_sketch: {
        name_zh: '喜剧小品',
        name_en: 'Comedy Sketch',
        description_zh: '幽默搞笑的短剧',
        description_en: 'Humorous short sketches',
        styleKeywords: ['humorous', 'lighthearted', 'expressive', 'playful'],
      },
      romantic_short: {
        name_zh: '言情短剧',
        name_en: 'Romantic Short',
        description_zh: '爱情主题的短剧',
        description_en: 'Romance-themed short drama',
        styleKeywords: ['romantic', 'warm tones', 'emotional', 'tender'],
      },
    },
  },
};

export function getVideoTypeDisplayName(
  type: VideoType,
  lang: 'zh' | 'en' = 'zh'
): string {
  const def = VIDEO_TYPE_DEFINITIONS[type];
  if (!def) return type;
  return lang === 'zh' ? def.name_zh : def.name_en;
}

export function getSubtypeDisplayName(
  type: VideoType,
  subtype: VideoSubtype | string,
  lang: 'zh' | 'en' = 'zh'
): string {
  const def = VIDEO_TYPE_DEFINITIONS[type];
  const sub = def?.subtypes?.[subtype];
  if (!sub) return subtype;
  return lang === 'zh' ? sub.name_zh : sub.name_en;
}

export function getSubtypeDescription(
  type: VideoType,
  subtype: VideoSubtype | string,
  lang: 'zh' | 'en' = 'zh'
): string {
  const def = VIDEO_TYPE_DEFINITIONS[type];
  const sub = def?.subtypes?.[subtype];
  if (!sub) return subtype;
  return lang === 'zh' ? sub.description_zh : sub.description_en;
}
