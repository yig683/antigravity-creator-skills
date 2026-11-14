"""assets/logo.svg geometrisinden assets/icon.png üretir (pencere ikonu,
favicon, yedek kapak). Pillow ile çalışır; SVG işleyiciye gerek yok.

    python tools/make_icon.py

Geometriyi değiştirirsen logo.svg ile birlikte değiştir.
"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
SIZE = 256
SS = 4  # süper örnekleme
S = SIZE * SS / 100.0  # viewBox 100 → piksel

# Dalga: üç kübik Bezier (logo.svg ile aynı).
SEGMENTS = [
    ((20, 50), (25, 20.7), (35, 20.7), (40, 50)),
    ((40, 50), (45.5, 70), (56.5, 70), (62, 50)),
    ((62, 50), (66.5, 39.3), (75.5, 39.3), (80, 50)),
]
STROKE = 9
WAVE_FROM = (0xFF, 0x8A, 0x2A)
WAVE_TO = (0xFF, 0x4D, 0x00)
TILE_TOP = (0x1E, 0x1E, 0x22)
TILE_BOTTOM = (0x12, 0x12, 0x14)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def main():
    w = SIZE * SS
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))

    # Karo: dikey gradyan + yuvarlak köşe maskesi.
    grad = Image.new("RGBA", (w, w))
    gd = ImageDraw.Draw(grad)
    for y in range(w):
        gd.line([(0, y), (w, y)], fill=lerp(TILE_TOP, TILE_BOTTOM, y / (w - 1)) + (255,))
    mask = Image.new("L", (w, w), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, w - 1], radius=round(24 * S), fill=255)
    img.paste(grad, (0, 0), mask)

    # İnce iç kenar.
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([round(.5 * S), round(.5 * S), w - 1 - round(.5 * S), w - 1 - round(.5 * S)],
                        radius=round(23.5 * S), outline=(255, 255, 255, 20), width=max(1, round(S * .9)))

    # Dalga: eğri boyunca yuvarlak fırça (yuvarlak uçlar kendiliğinden oluşur).
    r = STROKE / 2 * S
    for p0, p1, p2, p3 in SEGMENTS:
        for i in range(0, 401):
            x, y = bezier(p0, p1, p2, p3, i / 400)
            color = lerp(WAVE_FROM, WAVE_TO, (x - 20) / (80 - 20)) + (255,)
            cx, cy = x * S, y * S
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    img.resize((SIZE, SIZE), Image.LANCZOS).save(OUT)
    print("yazıldı:", OUT)


if __name__ == "__main__":
    main()
