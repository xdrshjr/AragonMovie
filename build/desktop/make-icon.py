#!/usr/bin/env python
"""Generate the desktop app icon (PNG + multi-size ICO).

Design: a near-black rounded square with a soft indigo glow, a hairline
frame and a play/film glyph — matching the product's gray-black language.
Run with the repo virtualenv python:  venv\\Scripts\\python.exe make-icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
OUT_DIR = Path(__file__).resolve().parents[2] / "desktop" / "assets"


def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def build():
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Outer rounded square (near-black vertical gradient).
    card = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    for y in range(SIZE):
        t = y / SIZE
        r = int(28 - 18 * t)
        g = int(28 - 18 * t)
        b = int(34 - 22 * t)
        draw.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))
    card.putalpha(rounded_mask(SIZE, 210))

    # Indigo glow in the upper-right corner.
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([SIZE * 0.42, -SIZE * 0.28, SIZE * 1.28, SIZE * 0.62], fill=(124, 134, 255, 190))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    glow.putalpha(Image.composite(glow.getchannel("A"), Image.new("L", (SIZE, SIZE), 0), rounded_mask(SIZE, 210)))
    base.alpha_composite(glow)
    base.alpha_composite(card)

    # Hairline frame.
    frame = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rounded_rectangle(
        [6, 6, SIZE - 7, SIZE - 7], radius=204, outline=(255, 255, 255, 38), width=6
    )
    base.alpha_composite(frame)

    # Glyph: rounded "play" triangle inside a soft ring.
    glyph = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)
    gd.ellipse([SIZE * 0.2, SIZE * 0.2, SIZE * 0.8, SIZE * 0.8], outline=(255, 255, 255, 56), width=9)
    gd.polygon(
        [
            (SIZE * 0.42, SIZE * 0.34),
            (SIZE * 0.70, SIZE * 0.50),
            (SIZE * 0.42, SIZE * 0.66),
        ],
        fill=(243, 243, 245, 255),
    )
    glyph = glyph.filter(ImageFilter.GaussianBlur(1.1))
    base.alpha_composite(glyph)

    # Subtle inner top highlight.
    hi = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(hi).rounded_rectangle([12, 12, SIZE - 13, SIZE * 0.46], radius=196, fill=(255, 255, 255, 16))
    hi = hi.filter(ImageFilter.GaussianBlur(18))
    base.alpha_composite(hi)

    return base


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icon = build()
    png_path = OUT_DIR / "icon.png"
    icon.resize((512, 512), Image.LANCZOS).save(png_path)

    ico_path = OUT_DIR / "icon.ico"
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icon.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"wrote {png_path} ({png_path.stat().st_size} bytes)")
    print(f"wrote {ico_path} ({ico_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
