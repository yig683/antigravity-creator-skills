"""Compose YouTube-ready channel profile avatar (800x800) and banner (2560x1440).

Places crisp Montserrat Turkish typography and CAD blueprint HUD framing inside
YouTube's exact cross-device safe zone (center 1546x423 inside 2560x1440) and
builds a circular-crop-safe 800x800 channel icon.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT_DIR = Path(__file__).resolve().parent.parent
FONT_BLACK = ROOT_DIR / "assets" / "fonts" / "Montserrat-Black.ttf"

NAVY_BG = (8, 22, 42)
GRID_LINE = (24, 56, 94, 70)
CYAN = (66, 206, 245)
AMBER = (248, 186, 54)
WHITE = (244, 248, 255)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        FONT_BLACK,
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _cover_fit(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = int(round(src_w * scale)), int(round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _draw_blueprint_grid(canvas: Image.Image, step: int = 80, alpha: int = 42) -> None:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = canvas.size
    col = (40, 118, 178, alpha)
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=col, width=1)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=col, width=1)
    canvas.alpha_composite(overlay)


def compose_profile_icon(raw_profile_path: Path, out_path: Path) -> Path:
    size = 800
    art = Image.open(raw_profile_path).convert("RGBA")
    # Sample dark corner pixel from the raw artwork so subtle safety padding is seamless
    tl = art.getpixel((8, 8))
    canvas = Image.new("RGBA", (size, size), (tl[0], tl[1], tl[2], 255))

    # Give ~4% circular-crop safety breathing room around outer cyan rim
    inset = int(round(size * 0.94))
    art_fit = _cover_fit(art, inset, inset)
    offset = (size - inset) // 2

    # Smooth edge feather mask so inset blends invisibly into corner tone
    mask = Image.new("L", (inset, inset), 255)
    mdraw = ImageDraw.Draw(mask)
    fade = 28
    for i in range(fade):
        val = int(255 * (i + 1) / fade)
        mdraw.rectangle([i, i, inset - 1 - i, inset - 1 - i], outline=val)
    art_fit.putalpha(mask)

    canvas.alpha_composite(art_fit, (offset, offset))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


def _draw_centered_text_with_shadow(
    canvas: Image.Image,
    center_x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
    glow_color: tuple[int, int, int] | None = None,
) -> int:
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = center_x - tw // 2 - bbox[0]
    yy = y - bbox[1]

    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_layer)
    if glow_color:
        sdraw.text((x, yy), text, font=font, fill=(*glow_color, 130))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=12))
    sdraw2 = ImageDraw.Draw(shadow_layer)
    sdraw2.text((x + 3, yy + 5), text, font=font, fill=(2, 8, 18, 220))
    canvas.alpha_composite(shadow_layer)

    draw = ImageDraw.Draw(canvas)
    draw.text((x, yy), text, font=font, fill=(*fill, 255), stroke_width=3, stroke_fill=(6, 16, 32, 235))
    return y + th


def compose_banner(
    raw_banner_path: Path,
    out_path: Path,
    title_top: str = "NASIL İCAT",
    title_bottom: str = "EDERSİN?",
    subtitle: str = "3D MÜHENDİSLİK ŞEMASI  •  SIFIRDAN ADIM ADIM İCAT",
    header_left: str = "SERİ // 3D BLUEPRINT ATÖLYE",
    header_right: str = "ÖLÇEK 1:1  |  SHORTS + UZUN VİDEO",
) -> Path:
    W, H = 2560, 1440
    SAFE_W, SAFE_H = 1546, 423
    SX0 = (W - SAFE_W) // 2   # 507
    SX1 = SX0 + SAFE_W        # 2053
    SY0 = (H - SAFE_H) // 2   # 508
    SY1 = SY0 + SAFE_H        # 931
    CX = W // 2               # 1280

    art = Image.open(raw_banner_path).convert("RGBA")
    canvas = _cover_fit(art, W, H)

    # Smooth center horizontal darkening band so center text reads crisply on mobile/desktop/TV
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(band)
    for y in range(SY0 - 70, SY1 + 70):
        # Smooth bell envelope over desktop/mobile band
        dist = abs(y - (SY0 + SAFE_H / 2)) / ((SAFE_H / 2) + 70)
        alpha = int(max(0.0, (1.0 - dist * dist)) * 145)
        bdraw.line([(0, y), (W, y)], fill=(6, 15, 30, alpha))
    # Horizontal focal dark vignette in center safe box so flanking 3D gears pop cleanly on left & right
    center_panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(center_panel)
    pdraw.rounded_rectangle(
        [SX0 + 18, SY0 + 14, SX1 - 18, SY1 - 14],
        radius=16,
        fill=(7, 19, 36, 165),
        outline=(*CYAN, 115),
        width=2,
    )
    canvas.alpha_composite(band)
    _draw_blueprint_grid(canvas, step=72, alpha=36)
    canvas.alpha_composite(center_panel)

    hud = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(hud)
    fx0, fy0, fx1, fy1 = SX0 + 36, SY0 + 26, SX1 - 36, SY1 - 26
    # Corner CAD brackets inside mobile-safe boundary
    arm = 24
    bcol = (*CYAN, 220)
    for bx, by, dx, dy in (
        (fx0, fy0, 1, 1),
        (fx1, fy0, -1, 1),
        (fx0, fy1, 1, -1),
        (fx1, fy1, -1, -1),
    ):
        hdraw.line([(bx, by), (bx + dx * arm, by)], fill=bcol, width=3)
        hdraw.line([(bx, by), (bx, by + dy * arm)], fill=bcol, width=3)

    # Top header metadata strip inside safe box
    f_meta = _load_font(22)
    hdraw.text((fx0 + 18, fy0 + 10), header_left, font=f_meta, fill=(135, 200, 232, 220))
    rb = hdraw.textbbox((0, 0), header_right, font=f_meta)
    hdraw.text((fx1 - 18 - (rb[2] - rb[0]), fy0 + 10), header_right, font=f_meta, fill=(135, 200, 232, 220))
    hdraw.line([(fx0 + 18, fy0 + 46), (fx1 - 18, fy0 + 46)], fill=(*CYAN, 85), width=1)
    canvas.alpha_composite(hud)

    # Main hero title lines (balanced vertically between header line y=580 and pill y=840)
    f_title = _load_font(94)
    y_cursor = SY0 + 98
    if title_top.strip():
        y_cursor = _draw_centered_text_with_shadow(canvas, CX, y_cursor, title_top.strip(), f_title, WHITE)
        y_cursor += 18
    if title_bottom.strip():
        y_cursor = _draw_centered_text_with_shadow(canvas, CX, y_cursor, title_bottom.strip(), f_title, CYAN, glow_color=CYAN)

    # Subtitle capsule badge inside bottom of safe box
    f_sub = _load_font(26)
    pill_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(pill_overlay)
    sb = sdraw.textbbox((0, 0), subtitle, font=f_sub)
    sw = sb[2] - sb[0]
    sh = sb[3] - sb[1]
    pad_x, pad_y = 36, 15
    pw, ph = sw + 2 * pad_x, sh + 2 * pad_y
    px0 = CX - pw // 2
    py0 = SY1 - 38 - ph
    sdraw.rounded_rectangle(
        [px0, py0, px0 + pw, py0 + ph],
        radius=12,
        fill=(10, 32, 58, 220),
        outline=(*CYAN, 185),
        width=2,
    )
    sdraw.text((px0 + pad_x - sb[0], py0 + pad_y - sb[1]), subtitle, font=f_sub, fill=(*WHITE, 245))
    canvas.alpha_composite(pill_overlay)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose YouTube 800x800 avatar and 2560x1440 safe-zone banner")
    parser.add_argument("--raw-profile", required=True)
    parser.add_argument("--raw-banner", required=True)
    parser.add_argument("--out-dir", default=str(ROOT_DIR / "branding"))
    parser.add_argument("--title-top", default="NASIL İCAT")
    parser.add_argument("--title-bottom", default="EDERSİN?")
    parser.add_argument("--subtitle", default="3D MÜHENDİSLİK ŞEMASI  •  SIFIRDAN ADIM ADIM İCAT")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    prof_out = compose_profile_icon(Path(args.raw_profile), out_dir / "channel_profile_800x800.png")
    ban_out = compose_banner(
        Path(args.raw_banner),
        out_dir / "channel_banner_2560x1440.png",
        title_top=args.title_top,
        title_bottom=args.title_bottom,
        subtitle=args.subtitle,
    )
    print(f"Profile saved: {prof_out}")
    print(f"Banner saved: {ban_out}")


if __name__ == "__main__":
    main()
