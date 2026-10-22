"""Extend the frontend settings types with the Doubao video + Volcano TTS fields."""

from pathlib import Path

path = Path("frontend/src/lib/api.ts")
raw = path.read_text(encoding="utf-8")


def replace_any(text: str, old: str, new: str, label: str) -> str:
    """Try the literal string with LF and CRLF line endings."""
    for sep in ("\n", "\r\n"):
        candidate = old.replace("\n", sep)
        if candidate in text:
            print(f"ok {label}")
            return text.replace(candidate, new.replace("\n", sep), 1)
    raise SystemExit(f"MISSING {label}:\n{old[:300]}")


raw = replace_any(
    raw,
    "    service_type: 'veo3' | 'sora2' | 'ali_token_plan';",
    "    service_type: 'veo3' | 'sora2' | 'ali_token_plan' | 'doubao';",
    "video service_type",
)

raw = replace_any(
    raw,
    """      ali_token_plan: ProviderConfig & {
        t2v_model: string;
        r2v_model: string;
        default_size: string;
        default_duration: number;
        /** Request the watermarked variant (default false). */
        watermark: boolean;
      };""",
    """      ali_token_plan: ProviderConfig & {
        t2v_model: string;
        r2v_model: string;
        default_size: string;
        default_duration: number;
        /** Request the watermarked variant (default false). */
        watermark: boolean;
      };
      /** 豆包 Seedance（火山方舟 Ark 异步视频任务） */
      doubao: ProviderConfig & {
        t2v_model: string;
        default_resolution: '480p' | '720p' | '1080p';
        default_ratio: string;
        default_duration: number;
        watermark: boolean;
      };""",
    "doubao video config",
)

raw = replace_any(
    raw,
    "export type TTSProvider = 'auto' | 'openai_compatible' | 'dashscope_native';",
    """export type TTSProvider =
  | 'auto'
  | 'openai_compatible'
  | 'dashscope_native'
  /** 火山引擎语音合成 2.0（v3 双向 WebSocket） */
  | 'volc_tts2';""",
    "TTSProvider literal",
)

raw = replace_any(
    raw,
    """  native_model: string;
  native_voice: string;
}""",
    """  native_model: string;
  native_voice: string;
  /** 火山引擎语音合成 2.0 */
  volc_api_key: string | null;
  volc_resource_id: string;
  volc_voice: string;
}""",
    "voice volc fields",
)

path.write_text(raw, encoding="utf-8")
print("patched frontend/src/lib/api.ts")
