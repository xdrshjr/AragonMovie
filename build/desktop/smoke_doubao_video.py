"""Real smoke test for DoubaoVideoService (one i2v clip, real Ark call)."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image, ImageDraw  # noqa: E402

from services.doubao_video_service import DoubaoVideoService  # noqa: E402

OUT = Path(__file__).resolve().parent / "smoke"
OUT.mkdir(exist_ok=True)


def make_still() -> Path:
    width, height = 1280, 720
    img = Image.new("RGB", (width, height), (18, 20, 28))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / height
        draw.line(
            [(0, y), (width, y)],
            fill=(int(24 + 40 * t), int(28 + 44 * t), int(46 + 78 * t)),
        )
    # simple "city skyline + street" so Seedance has structure to animate
    draw.rectangle([0, int(height * 0.62), width, height], fill=(14, 15, 20))
    for x in range(40, width - 40, 120):
        h = 120 + (x * 7) % 180
        draw.rectangle([x, int(height * 0.62) - h, x + 78, int(height * 0.62)], fill=(26, 30, 42))
        for wy in range(int(height * 0.62) - h + 14, int(height * 0.62) - 10, 26):
            draw.rectangle([x + 12, wy, x + 26, wy + 12], fill=(250, 226, 168))
    draw.ellipse([width * 0.62, 120, width * 0.62 + 90, 210], fill=(255, 236, 200))
    path = OUT / "first-frame.png"
    img.save(path)
    return path


async def main() -> int:
    service = DoubaoVideoService()
    image = make_still()
    started = time.time()
    result = await service.image_to_video(
        image_path=str(image),
        duration=5,
        prompt=(
            "Cinematic night city street, the camera slowly pushes forward, "
            "warm street lights flicker, light rain, subtle handheld motion"
        ),
        resolution="720p",
        ratio="16:9",
    )
    elapsed = time.time() - started
    print(f"task id: {result['id']}  status: {result['status']}  elapsed: {elapsed:.0f}s")
    target = OUT / "smoke-i2v.mp4"
    await service.download_video(result["video_url"], target)
    print(f"saved: {target} ({target.stat().st_size / 1024:.0f} KB)")
    await service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
