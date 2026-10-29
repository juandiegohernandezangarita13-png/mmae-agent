"""
Genera el icono oficial de JEV (reactor holográfico) en assets/jev.ico.

Uso:
    .\.venv\Scripts\python.exe scripts\generate_jev_icon.py

Produce un ICO multirresolución (16 a 256 px) con fondo transparente, anillo
cian y núcleo luminoso: se ve nítido tanto en el escritorio como en la barra de
tareas o en el menú Inicio.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "jev.ico"
PREVIEW = ROOT / "assets" / "jev_icon_256.png"

SIZE = 1024
CYAN = (0, 240, 255)
CYAN_SOFT = (0, 190, 255)
WHITE = (235, 255, 255)
BG_TOP = (7, 16, 30)
BG_BOTTOM = (3, 7, 14)


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return grad.resize((size, size), Image.BICUBIC)


def draw_reactor() -> Image.Image:
    base = vertical_gradient(SIZE, BG_TOP, BG_BOTTOM).convert("RGBA")
    base.putalpha(rounded_mask(SIZE, int(SIZE * 0.22)))

    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    c = SIZE / 2

    # Halo exterior
    for step in range(9, 0, -1):
        r = int(SIZE * 0.40 * step / 9)
        alpha = int(7 + (9 - step) * 3)
        gd.ellipse((c - r, c - r, c + r, c + r), outline=(0, 240, 255, alpha), width=int(SIZE * 0.02))
    glow = glow.filter(ImageFilter.GaussianBlur(SIZE * 0.02))

    ring = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((c - SIZE * 0.385, c - SIZE * 0.385, c + SIZE * 0.385, c + SIZE * 0.385),
               outline=(*CYAN, 245), width=int(SIZE * 0.055))
    rd.ellipse((c - SIZE * 0.285, c - SIZE * 0.285, c + SIZE * 0.285, c + SIZE * 0.285),
               outline=(*CYAN_SOFT, 200), width=int(SIZE * 0.022))

    # Bobinas radiales (8 segmentos tipo arc reactor)
    for i in range(8):
        angle = i * math.pi / 4 + math.pi / 8
        r0, r1 = SIZE * 0.15, SIZE * 0.265
        x0, y0 = c + r0 * math.cos(angle), c + r0 * math.sin(angle)
        x1, y1 = c + r1 * math.cos(angle), c + r1 * math.sin(angle)
        rd.line((x0, y0, x1, y1), fill=(*CYAN, 220), width=int(SIZE * 0.045))

    # Núcleo luminoso
    for r, alpha in ((SIZE * 0.13, 90), (SIZE * 0.095, 160), (SIZE * 0.062, 240)):
        rd.ellipse((c - r, c - r, c + r, c + r), fill=(*WHITE, alpha))
    rd.ellipse((c - SIZE * 0.036, c - SIZE * 0.036, c + SIZE * 0.036, c + SIZE * 0.036),
               fill=(255, 255, 255, 255))

    icon = Image.alpha_composite(base, glow)
    icon = Image.alpha_composite(icon, ring)

    # Brillo del núcleo difuminado por encima
    core = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    cd = ImageDraw.Draw(core)
    cd.ellipse((c - SIZE * 0.09, c - SIZE * 0.09, c + SIZE * 0.09, c + SIZE * 0.09),
               fill=(180, 250, 255, 140))
    core = core.filter(ImageFilter.GaussianBlur(SIZE * 0.04))
    return Image.alpha_composite(icon, core)


def main() -> int:
    icon = draw_reactor()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(PREVIEW, "PNG")
    icon.save(
        OUT,
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
               (64, 64), (128, 128), (256, 256)],
    )
    print(f"Icono generado: {OUT} ({OUT.stat().st_size} bytes)")
    print(f"Vista previa 256 px: {PREVIEW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
