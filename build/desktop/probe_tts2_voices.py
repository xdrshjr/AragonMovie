"""List which female speakers work for resource seed-tts-2.0."""

import asyncio
import os
import sys

sys.path.insert(0, r"C:\Users\Administrator\.claude\skills\daily-radar-video\scripts")

import tts_volc2_ws as tts  # noqa: E402

KEY = os.environ["PROBE_TTS_KEY"]
VOICES = [
    "zh_female_xiaohe_uranus_bigtts",
    "zh_female_gaolengyujie_uranus_bigtts",
    "zh_female_wenrouxiaoya_uranus_bigtts",
    "zh_female_roumeinvyou_uranus_bigtts",
    "zh_female_qingxin_uranus_bigtts",
    "zh_male_shaonianzixin_uranus_bigtts",
]


async def main() -> None:
    for voice in VOICES:
        try:
            audio = await tts.synthesize(KEY, voice, "雨夜的巷口，她停下了脚步。", timeout=60, resource_id="seed-tts-2.0")
            print(f"{voice}: OK {len(audio)} bytes")
        except Exception as exc:  # noqa: BLE001
            print(f"{voice}: FAIL {str(exc)[:160]}")


asyncio.run(main())
