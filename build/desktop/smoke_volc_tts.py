"""Real smoke test for VolcTTS2Service (writes an mp3 and probes it with ffprobe)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.volc_tts_service import VolcTTS2Service  # noqa: E402

OUT = Path(__file__).resolve().parent / "smoke"


async def main() -> int:
    OUT.mkdir(exist_ok=True)
    service = VolcTTS2Service()
    info = await service.probe()
    print("probe:", info)

    text = "雨夜的巷口，她停下了脚步，抬头看向那盏忽明忽暗的路灯。"
    audio = await service.synthesize(text)
    target = OUT / "smoke-tts2.mp3"
    target.write_bytes(audio)
    print(f"saved {target} ({len(audio)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
