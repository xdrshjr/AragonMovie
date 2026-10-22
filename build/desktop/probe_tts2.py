"""Probe Volcano TTS 2.0 with the given key: which speakers/resources work."""

import asyncio
import os
import sys

sys.path.insert(0, r"C:\Users\Administrator\.claude\skills\daily-radar-video\scripts")

import tts_volc2_ws as tts  # noqa: E402

KEY = os.environ["PROBE_TTS_KEY"]

CANDIDATES = [
    ("seed-tts-2.0", "zh_female_cancan_mars_bigtts"),
    ("seed-tts-2.0", "zh_male_shaonianzixin_uranus_bigtts"),
    ("seed-tts-2.0", "zh_female_xiaohe_uranus_bigtts"),
    ("volc.service_type.10029", "zh_female_cancan_mars_bigtts"),
]


async def try_one(resource_id: str, voice: str) -> None:
    try:
        audio = await tts.synthesize(KEY, voice, "你好，这是一次语音合成测试。", timeout=60, resource_id=resource_id)
        print(f"{resource_id} / {voice}: OK, {len(audio)} bytes, head={audio[:4]!r}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"{resource_id} / {voice}: FAIL {type(exc).__name__}: {str(exc)[:220]}")
        return False


async def main() -> None:
    for resource_id, voice in CANDIDATES:
        if await try_one(resource_id, voice):
            return


asyncio.run(main())
