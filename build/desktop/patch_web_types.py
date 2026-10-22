"""Extend the frontend settings types with the Doubao video + Volcano TTS fields."""

from pathlib import Path

path = Path("frontend/src/lib/api.ts")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"


def must_replace(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"MISSING {label}:\n{old[:300]}")
    text = text.replace(old, new, 1)
    print(f"ok {label}")


must_replace(
    "      service_type: 'veo3' | 'sora2' | 'ali_token_plan';",
    "      service_type: 'veo3' | 'sora2' | 'ali_token_plan' | 'doubao';",
    "video service_type",
)
must_replace(
    "      ali_token_plan: ProviderConfig & {" + NL
    + "        t2v_model: string;" + NL
    + "        r2v_model: string;" + NL
    + "        default_size: string;" + NL
    + "        default_duration: number;" + NL
    + "        /** Request the watermarked variant (default false). */" + NL
    + "        watermark: boolean;" + NL
    + "      };",
    "      ali_token_plan: ProviderConfig & {" + NL
    + "        t2v_model: string;" + NL
    + "        r2v_model: string;" + NL
    + "        default_size: string;" + NL
    + "        default_duration: number;" + NL
    + "        /** Request the watermarked variant (default false). */" + NL
    + "        watermark: boolean;" + NL
    + "      };" + NL
    + "      /** 豆包 Seedance（火山方舟 Ark 异步视频任务） */" + NL
    + "      doubao: ProviderConfig & {" + NL
    + "        t2v_model: string;" + NL
    + "        default_resolution: '480p' | '720p' | '1080p';" + NL
    + "        default_ratio: string;" + NL
    + "        default_duration: number;" + NL
    + "        watermark: boolean;" + NL
    + "      };",
    "doubao video config",
)
must_replace(
    "export type TTSProvider = 'auto' | 'openai_compatible' | 'dashscope_native';",
    "export type TTSProvider =" + NL
    + "  | 'auto'" + NL
    + "  | 'openai_compatible'" + NL
    + "  | 'dashscope_native'" + NL
    + "  /** 火山引擎语音合成 2.0（v3 双向 WebSocket） */" + NL
    + "  | 'volc_tts2';",
    "TTSProvider literal",
)
must_replace(
    "  native_model: string;" + NL + "  native_voice: string;" + NL + "}",
    "  native_model: string;" + NL
    + "  native_voice: string;" + NL
    + "  /** 火山引擎语音合成 2.0 */" + NL
    + "  volc_api_key: string | null;" + NL
    + "  volc_resource_id: string;" + NL
    + "  volc_voice: string;" + NL
    + "}",
    "voice volc fields",
)

path.write_text(text, encoding="utf-8")
print("patched frontend/src/lib/api.ts")
