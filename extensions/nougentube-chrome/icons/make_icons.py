"""Draws the NouGenTube extension icons (16, 32, 48 and 128 px) in Mono Violet.

Run from this folder:  python make_icons.py
Needs Pillow. The shape is a superellipse (a smooth, continuous corner) and the glyph is the same "N" on the same
violet gradient as the badge in the panel header. Each size is drawn at 8x and scaled down, so the 16 px icon stays crisp.
Chrome picks the size it needs from the manifest's "icons" (toolbar and extensions page use 16 and 32, the extensions
page and the Web Store use 48 and 128). Same idea as supplying several scale factors in Electron's nativeImage.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

SIZES = (16, 32, 48, 128)
TOP, BOTTOM, INK = (210, 187, 255), (164, 123, 255), (11, 9, 17)       # --ac2, --ac, --bg of Mono Violet dark
FONTS = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")
HERE = os.path.dirname(os.path.abspath(__file__))


def superellipse(size: int, n: float = 5.0, inset: float = 0.0) -> Image.Image:
    """An L-mode mask of a superellipse filling the square (n=2 is a circle, large n approaches a square)."""
    mask = Image.new("L", (size, size), 0)
    r = size / 2 - inset
    pts = []
    for i in range(720):
        t = 2 * math.pi * i / 720
        c, s = math.cos(t), math.sin(t)
        pts.append((size / 2 + r * math.copysign(abs(c) ** (2 / n), c), size / 2 + r * math.copysign(abs(s) ** (2 / n), s)))
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    return mask


def font(px: int) -> ImageFont.FreeTypeFont:
    for name in FONTS:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    raise SystemExit("no bold font found; install one of: " + ", ".join(FONTS))


def draw(size: int) -> Image.Image:
    big = size * 8
    grad = Image.new("RGB", (big, big))
    px = grad.load()
    for y in range(big):
        for x in range(big):
            k = (x + y) / (2 * (big - 1))                           # diagonal, light top-left to violet bottom-right
            px[x, y] = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * k) for i in range(3))
    icon = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), superellipse(big, inset=big * 0.02))
    d = ImageDraw.Draw(icon)
    f = font(int(big * 0.66))
    box = d.textbbox((0, 0), "N", font=f)
    d.text(((big - (box[2] - box[0])) / 2 - box[0], (big - (box[3] - box[1])) / 2 - box[1]), "N", font=f, fill=INK)
    return icon.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    for s in SIZES:
        draw(s).save(os.path.join(HERE, f"icon{s}.png"), optimize=True)
        print("wrote", f"icon{s}.png")
