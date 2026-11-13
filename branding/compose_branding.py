"""Compose YouTube, TikTok, and Instagram Reels branding assets for VICE VAULT (GTA 6 & Streamer Clips)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_BLACK = ROOT / "assets" / "fonts" / "Montserrat-Black.ttf"
FONT_TECH = Path(r"C:\Windows\Fonts\bahnschrift.ttf")
FONT_FALLBACK = Path(r"C:\Windows\Fonts\segoeuib.ttf")


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    for cand in (path, FONT_BLACK, FONT_FALLBACK):
        if cand.exists():
            try:
                return ImageFont.truetype(str(cand), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def build_profile_avatar(raw_profile_path: Path, out_path: Path, size: int = 800) -> Path:
    """Create a razor-sharp 800x800 circular-safe avatar on deep midnight obsidian."""
    with Image.open(raw_profile_path) as src:
        rgb = src.convert("RGB")
        w, h = rgb.size
        # Slight zoom crop (6% margin trimmed) so the neon hex-play emblem pops even at 36px circle size
        inset = int(min(w, h) * 0.055)
        crop_box = (inset, inset, w - inset, h - inset)
        emblem = rgb.crop(crop_box).resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")

    # Smooth radial edge blend into uniform deep midnight obsidian (#080B14) to eliminate corner seams
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    dist = np.sqrt(((xx - size * 0.5) / (size * 0.5)) ** 2 + ((yy - size * 0.5) / (size * 0.5)) ** 2)
    alpha_mask = np.clip((0.92 - dist) / 0.14, 0.0, 1.0)
    mask_img = Image.fromarray((alpha_mask * 255).astype(np.uint8), mode="L")

    base = Image.new("RGBA", (size, size), (8, 11, 20, 255))
    # Subtle soft neon halo behind center
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((int(size * 0.16), int(size * 0.16), int(size * 0.84), int(size * 0.84)), fill=(255, 42, 133, 38))
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.07))
    base = Image.alpha_composite(base, glow)
    base.paste(emblem, (0, 0), mask_img)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(out_path, format="PNG", optimize=True)
    return out_path


def _extract_circular_emblem(profile_png: Path, diameter: int) -> Image.Image:
    with Image.open(profile_png) as im:
        sq = im.convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
    # Trim into a crisp neon-ringed badge for the banner lockup
    mask = Image.new("L", (diameter, diameter), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((4, 4, diameter - 5, diameter - 5), fill=255)
    out = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    out.paste(sq, (0, 0), mask)

    ring = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((4, 4, diameter - 5, diameter - 5), outline=(0, 229, 255, 220), width=4)
    rd.ellipse((9, 9, diameter - 10, diameter - 10), outline=(255, 42, 133, 180), width=2)
    return Image.alpha_composite(out, ring)


def _draw_stroked_text(
    canvas: Image.Image,
    pos: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    *,
    stroke_fill: tuple[int, int, int, int] = (5, 7, 14, 255),
    stroke_width: int = 8,
    glow_color: tuple[int, int, int, int] | None = None,
) -> None:
    if glow_color:
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.text(pos, text, font=font, fill=glow_color)
        glow = glow.filter(ImageFilter.GaussianBlur(12))
        canvas.alpha_composite(glow)
    draw = ImageDraw.Draw(canvas)
    draw.text(pos, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


def build_channel_banner(
    raw_banner_path: Path,
    profile_png: Path,
    out_path: Path,
    qa_path: Path | None = None,
) -> Path:
    """Compose a 2560x1440 YouTube banner with all text/emblem centered inside the 1546x423 safe area."""
    W, H = 2560, 1440
    SAFE_W, SAFE_H = 1546, 423
    SAFE_X0 = (W - SAFE_W) // 2  # 507
    SAFE_Y0 = (H - SAFE_H) // 2  # 508
    SAFE_X1 = SAFE_X0 + SAFE_W   # 2053
    SAFE_Y1 = SAFE_Y0 + SAFE_H   # 931

    with Image.open(raw_banner_path) as src:
        bg = src.convert("RGB").resize((W, H), Image.Resampling.LANCZOS).convert("RGBA")

    # Gentle radial dark vignette over center safe zone so white/gold title maintains maximum contrast
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx = (xx - W * 0.5) / 620.0
    dy = (yy - H * 0.5) / 240.0
    pocket = np.exp(-(dx * dx + dy * dy) * 0.55)
    scrim = np.zeros((H, W, 4), dtype=np.uint8)
    scrim[:, :, :3] = np.array([7, 9, 18], dtype=np.uint8)
    scrim[:, :, 3] = np.clip(pocket * 140.0, 0.0, 140.0).astype(np.uint8)
    bg = Image.alpha_composite(bg, Image.fromarray(scrim, mode="RGBA"))

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # Top-and-bottom thin neon horizon hairlines framing desktop strip subtly
    for y_line, col in [(SAFE_Y0 + 18, (255, 42, 133, 120)), (SAFE_Y1 - 18, (0, 229, 255, 120))]:
        od.line([(SAFE_X0 + 140, y_line), (SAFE_X1 - 140, y_line)], fill=col, width=2)

    # Left circular brand emblem + right typography lockup cleanly inside [SAFE_X0+90 .. SAFE_X1-90]
    emblem_d = 248
    emblem = _extract_circular_emblem(profile_png, emblem_d)

    f_eyebrow = _font(FONT_TECH, 26)
    f_title = _font(FONT_BLACK, 114)
    f_sub = _font(FONT_TECH, 34)
    f_pill = _font(FONT_TECH, 24)

    title_left = "VICE "
    title_right = "VAULT"
    tw1 = int(od.textbbox((0, 0), title_left, font=f_title)[2])
    tw2 = int(od.textbbox((0, 0), title_right, font=f_title)[2])
    th_title = int(od.textbbox((0, 0), "VICE VAULT", font=f_title)[3])
    title_w = tw1 + tw2

    sub_text = "DAILY GTA 6 & VIRAL STREAMER CLIPS"
    sub_w = int(od.textbbox((0, 0), sub_text, font=f_sub)[2])

    block_w = max(title_w, sub_w)
    gap = 46
    total_w = emblem_d + gap + block_w
    start_x = (W - total_w) // 2

    emblem_y = (H - emblem_d) // 2
    # Add outer ambient glow behind emblem
    emb_glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    egd = ImageDraw.Draw(emb_glow)
    egd.ellipse(
        (start_x - 24, emblem_y - 24, start_x + emblem_d + 24, emblem_y + emblem_d + 24),
        fill=(255, 42, 133, 95),
    )
    emb_glow = emb_glow.filter(ImageFilter.GaussianBlur(26))
    overlay = Image.alpha_composite(overlay, emb_glow)
    overlay.alpha_composite(emblem, (start_x, emblem_y))

    tx = start_x + emblem_d + gap

    # Row 1: Eyebrow pill inside safe top
    eyebrow_txt = "GTA VI  //  TOP COUNTDOWNS"
    ew = int(od.textbbox((0, 0), eyebrow_txt, font=f_eyebrow)[2]) + 34
    eh = 40
    eyebrow_y = SAFE_Y0 + 54
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(
        (tx, eyebrow_y, tx + ew, eyebrow_y + eh),
        radius=20,
        fill=(228, 30, 90, 235),
        outline=(255, 165, 200, 200),
        width=2,
    )
    od.text((tx + 17, eyebrow_y + 7), eyebrow_txt, font=f_eyebrow, fill=(255, 255, 255, 255))

    # Row 2: Giant VICE VAULT title
    title_y = eyebrow_y + eh + 14
    _draw_stroked_text(
        overlay,
        (tx, title_y),
        title_left,
        f_title,
        fill=(255, 255, 255, 255),
        stroke_width=10,
        glow_color=(0, 229, 255, 110),
    )
    _draw_stroked_text(
        overlay,
        (tx + tw1, title_y),
        title_right,
        f_title,
        fill=(255, 212, 38, 255),
        stroke_width=10,
        glow_color=(255, 140, 25, 120),
    )

    # Row 3: Tagline & platform pills
    sub_y = title_y + th_title + 26
    _draw_stroked_text(
        overlay,
        (tx, sub_y),
        sub_text,
        f_sub,
        fill=(220, 245, 255, 255),
        stroke_width=5,
    )

    pill_y = sub_y + 52
    px_cursor = tx
    od = ImageDraw.Draw(overlay)
    for label, border_col, txt_col in [
        ("YOUTUBE SHORTS", (255, 70, 95, 230), (255, 255, 255, 255)),
        ("TIKTOK", (0, 229, 255, 230), (225, 250, 255, 255)),
        ("REELS", (255, 175, 45, 230), (255, 242, 210, 255)),
    ]:
        pw = int(od.textbbox((0, 0), label, font=f_pill)[2]) + 28
        ph = 34
        od.rounded_rectangle(
            (px_cursor, pill_y, px_cursor + pw, pill_y + ph),
            radius=17,
            fill=(14, 18, 36, 220),
            outline=border_col,
            width=2,
        )
        od.text((px_cursor + 14, pill_y + 5), label, font=f_pill, fill=txt_col)
        px_cursor += pw + 14

    final = Image.alpha_composite(bg, overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(out_path, format="PNG", optimize=True)
    # YouTube enforces 6 MB max on channel banners; fallback to ultra-high JPEG only if PNG exceeds 5.8 MB
    if out_path.stat().st_size > 5_800_000:
        final.save(out_path.with_suffix(".jpg"), format="JPEG", quality=95, subsampling=0)

    if qa_path is not None:
        qa_img = final.copy().convert("RGBA")
        qd = ImageDraw.Draw(qa_img)
        # Desktop strip rectangle (yellow dashed feel) + mobile 1546x423 safe rectangle (bright green)
        qd.rectangle((0, SAFE_Y0, W - 1, SAFE_Y1), outline=(255, 210, 40, 220), width=4)
        qd.rectangle((SAFE_X0, SAFE_Y0, SAFE_X1, SAFE_Y1), outline=(0, 255, 140, 255), width=6)
        qd.text((SAFE_X0 + 14, SAFE_Y0 - 34), "MOBILE + DESKTOP SAFE ZONE (1546x423)", font=f_pill, fill=(0, 255, 140, 255))
        qa_img.convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS).save(qa_path, format="PNG")

    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose VICE VAULT channel avatar & YouTube 2560x1440 banner.")
    parser.add_argument("--raw-profile", type=Path, required=True)
    parser.add_argument("--raw-banner", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--qa-path", type=Path, default=None)
    args = parser.parse_args()

    prof_out = build_profile_avatar(args.raw_profile, args.out_dir / "channel_profile_800x800.png")
    banner_out = build_channel_banner(
        args.raw_banner,
        prof_out,
        args.out_dir / "channel_banner_2560x1440.png",
        qa_path=args.qa_path,
    )

    kit = {
        "brand_name": "VICE VAULT",
        "primary_handle": "@ViceVaultClips",
        "backup_names": [
            {"name": "VICE PULSE", "handle": "@VicePulseClips"},
            {"name": "LEONIDA CLIPS", "handle": "@LeonidaClips"},
            {"name": "GTA 6 VAULT", "handle": "@GTA6VaultDaily"},
            {"name": "VICE FEED", "handle": "@ViceFeedTV"},
        ],
        "channel_bio": (
            "Daily #1 GTA 6 & viral streamer reactions — fast-paced countdowns, "
            "live fails, and wildest moments. New Shorts, TikToks & Reels every day!"
        ),
        "profile_png": str(prof_out.resolve()),
        "profile_bytes": prof_out.stat().st_size,
        "banner_png": str(banner_out.resolve()),
        "banner_bytes": banner_out.stat().st_size,
    }
    kit_path = args.out_dir / "channel_kit.json"
    kit_path.write_text(json.dumps(kit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(kit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
