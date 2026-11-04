"""
Prueba y validación de generación de sprites del Pato Pixel-Art.
"""
from PIL import Image, ImageOps

PALETTE = {
    ' ': (0, 0, 0, 0),
    'B': (15, 15, 20, 255),
    'W': (255, 255, 255, 255),
    'S': (225, 230, 240, 255),
    'O': (255, 85, 0, 255),
    'D': (215, 55, 0, 255)
}

FRAMES = {
    "STAND": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   BOOBB    ",
        "   BOOB OB  ",
        "   BBBB BB  "
    ],
    "WALK_1": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "  BOOBB     ",
        " OOOOB  OB  ",
        " BBBBB  BB  "
    ],
    "WALK_2": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   BOOBB    ",
        "   BOOB OOB ",
        "   BBBB     "
    ],
    "WALK_3": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "    BOOBB   ",
        " BO  OOOOOB ",
        " BB  BBBBBB "
    ],
    "WALK_4": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   OOB BOOB ",
        "       BOOB ",
        "       BBBB "
    ],
}

def render_sprite(pattern, scale=8):
    h = len(pattern)
    w = len(pattern[0])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for r, row in enumerate(pattern):
        for c, char in enumerate(row):
            color = PALETTE.get(char, (0, 0, 0, 0))
            img.putpixel((c, r), color)
    return img.resize((w * scale, h * scale), Image.Resampling.NEAREST)

for name, pat in FRAMES.items():
    sp = render_sprite(pat, scale=8)
    sp_mirrored = ImageOps.mirror(sp)
    print(f"Rendered {name}: {sp.size[0]}x{sp.size[1]}px, mirror ok")

print("All frames rendered successfully.")
