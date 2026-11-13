from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from clip_finder.captions import ensure_montserrat_font


def _format_views(views: int) -> str:
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K"
    return str(max(views, 0))


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_dir, _ = ensure_montserrat_font()
    if font_dir:
        ttf = font_dir / "Montserrat-Black.ttf"
        if ttf.exists():
            try:
                return ImageFont.truetype(str(ttf), size)
            except Exception:
                pass
    for fallback in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(fallback, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _is_latin_text(text: str) -> bool:
    return all(ord(ch) <= 0x024F or ch in "•—–… " for ch in text)


def _load_cjk_fallback_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont | None:
    for path_or_name in (
        "C:/Windows/Fonts/YuGothB.ttc",
        "C:/Windows/Fonts/meiryob.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
    ):
        try:
            return ImageFont.truetype(path_or_name, size)
        except Exception:
            continue
    return None


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int, int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


def render_rank_pill_png(
    rank_num: int,
    channel_name: str,
    views: int,
    out_path: str | Path,
    *,
    fallback_handle: str = "",
    show_views: bool = False,
) -> Path:
    """Render an anti-aliased glassmorphic rank & creator HUD pill PNG (2x supersampled)."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    S = 2  # 2x supersampling for crisp edges & typography
    rank_txt = f"#{rank_num}"
    clean_name = channel_name.lstrip("@").strip()
    if not _is_latin_text(clean_name) and fallback_handle.strip() and _is_latin_text(fallback_handle):
        display_name = fallback_handle.lstrip("@").strip()
    else:
        display_name = clean_name
    name_txt = f"@{display_name}"
    views_txt = f"{_format_views(views)}" if (show_views and views > 0) else ""

    f_rank = _load_font(56 * S)
    f_name = _load_font(48 * S)
    if not _is_latin_text(display_name):
        f_name = _load_cjk_fallback_font(48 * S) or f_name
    f_view = _load_font(34 * S)

    probe_img = Image.new("RGBA", (10, 10))
    pdraw = ImageDraw.Draw(probe_img)
    rw, rh, rx0, ry0 = _text_size(pdraw, rank_txt, f_rank)
    nw, nh, nx0, ny0 = _text_size(pdraw, name_txt, f_name)
    vw, vh, vx0, vy0 = _text_size(pdraw, views_txt, f_view) if views_txt else (0, 0, 0, 0)

    pad = 24 * S
    chip_pad_x = 26 * S
    chip_w = rw + chip_pad_x * 2
    chip_h = 84 * S
    inner_gap = 20 * S

    total_inner_w = chip_w + inner_gap + nw + (inner_gap + vw + 30 * S if views_txt else 10 * S)
    max_pill_w = 980 * S
    if total_inner_w + pad * 2 > max_pill_w:
        shrink = (max_pill_w - pad * 2 - chip_w - inner_gap * 2 - 40 * S) / max(nw + vw, 1)
        shrink = max(min(shrink, 1.0), 0.55)
        name_sz = max(int(48 * S * shrink), 28 * S)
        view_sz = max(int(34 * S * shrink), 22 * S)
        f_name = (_load_cjk_fallback_font(name_sz) or _load_font(name_sz)) if not _is_latin_text(display_name) else _load_font(name_sz)
        f_view = _load_font(view_sz)
        nw, nh, nx0, ny0 = _text_size(pdraw, name_txt, f_name)
        vw, vh, vx0, vy0 = _text_size(pdraw, views_txt, f_view) if views_txt else (0, 0, 0, 0)
        total_inner_w = chip_w + inner_gap + nw + (inner_gap + vw + 30 * S if views_txt else 10 * S)

    pill_w = min(total_inner_w + pad * 2, max_pill_w)
    pill_h = 118 * S

    margin = 18 * S
    cw = pill_w + margin * 2
    ch = pill_h + margin * 2

    # Soft diffused shadow layer
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        [margin, margin + 6 * S, margin + pill_w, margin + pill_h + 6 * S],
        radius=pill_h // 2,
        fill=(0, 0, 0, 210),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=11 * S))

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas)

    # Glass pill background + bold Vice City accent border
    border_col = (250, 204, 21, 250) if rank_num == 1 else ((236, 72, 153, 240) if rank_num <= 3 else (34, 211, 238, 220))
    draw.rounded_rectangle(
        [margin, margin, margin + pill_w, margin + pill_h],
        radius=pill_h // 2,
        fill=(10, 14, 24, 242),
        outline=border_col,
        width=max(3 * S, 3),
    )

    # Left rank chip
    if rank_num == 1:
        chip_bg = (250, 204, 21, 255)   # Gold
        chip_fg = (11, 15, 25, 255)
    elif rank_num <= 3:
        chip_bg = (236, 72, 153, 255)   # Vice City Neon Magenta
        chip_fg = (255, 255, 255, 255)
    else:
        chip_bg = (249, 115, 22, 255)   # Vivid Amber-Orange
        chip_fg = (255, 255, 255, 255)

    cx0 = margin + 16 * S
    cy0 = margin + (pill_h - chip_h) // 2
    draw.rounded_rectangle(
        [cx0, cy0, cx0 + chip_w, cy0 + chip_h],
        radius=chip_h // 2,
        fill=chip_bg,
    )
    draw.text(
        (cx0 + (chip_w - rw) // 2 - rx0, cy0 + (chip_h - rh) // 2 - ry0),
        rank_txt,
        font=f_rank,
        fill=chip_fg,
    )

    # Streamer handle
    nx = cx0 + chip_w + inner_gap
    ny = margin + (pill_h - nh) // 2 - ny0
    draw.text((nx, ny), name_txt, font=f_name, fill=(255, 255, 255, 255))

    # Optional views sub-pill
    if views_txt:
        vx = nx + nw + inner_gap - 2 * S
        vp_h = 58 * S
        vp_w = vw + 32 * S
        vp_y = margin + (pill_h - vp_h) // 2
        draw.rounded_rectangle(
            [vx, vp_y, vx + vp_w, vp_y + vp_h],
            radius=vp_h // 2,
            fill=(30, 41, 59, 250),
            outline=(148, 163, 184, 140),
            width=max(2 * S, 2),
        )
        draw.text(
            (vx + (vp_w - vw) // 2 - vx0, vp_y + (vp_h - vh) // 2 - vy0),
            views_txt,
            font=f_view,
            fill=(34, 211, 238, 255),
        )

    final = canvas.resize((cw // S, ch // S), Image.Resampling.LANCZOS)
    final.save(out, format="PNG")
    return out


def _render_vice_logo_rgba(target_w: int, target_h: int) -> Image.Image:
    """Render official transparent GTA VI logo (with soft Vice-City glow) or crisp vector fallback."""
    official_path = Path("assets/ui/gtavi_official.png")
    if official_path.exists():
        with Image.open(official_path) as raw:
            src = raw.convert("RGBA")
        # Fit preserving exact 960:729 aspect ratio with generous margin so Gaussian aura never clips edges
        scale = min((target_w * 0.84) / src.width, (target_h * 0.84) / src.height)
        nw = max(int(round(src.width * scale)), 16)
        nh = max(int(round(src.height * scale)), 16)
        resized = src.resize((nw, nh), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        glow = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        ox = (target_w - nw) // 2
        oy = (target_h - nh) // 2
        blur_r = max(min(ox // 3, oy // 3, int(target_h * 0.045)), 2)
        alpha_mask = resized.getchannel("A")
        halo = Image.new("RGBA", (nw, nh), (236, 72, 153, 145))
        halo.putalpha(alpha_mask)
        glow.paste(halo, (ox, oy))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=blur_r))
        canvas.alpha_composite(glow)
        canvas.alpha_composite(resized, (ox, oy))
        return canvas

    # Crisp clean fallback (only if official PNG missing)
    S = 2
    w, h = target_w * S, target_h * S
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    vi_font = _load_font(int(h * 0.78))
    vw, vh, vx0, vy0 = _text_size(draw, "VI", vi_font)
    vx = (w - vw) // 2 - vx0
    vy = int(h * 0.56) - vh // 2 - vy0
    draw.text((vx, vy), "VI", font=vi_font, fill=(236, 72, 153, 255), stroke_width=max(int(h * 0.05), 3), stroke_fill=(9, 13, 22, 255))
    gta_font = _load_font(int(h * 0.25))
    gw, gh, gx0, gy0 = _text_size(draw, "GTA", gta_font)
    bx, by = (w - gw - 28) // 2, int(h * 0.14)
    draw.rounded_rectangle([bx, by, bx + gw + 28, by + gh + 16], radius=8, fill=(9, 13, 22, 238), outline=(34, 211, 238, 255), width=3)
    draw.text((bx + 14 - gx0, by + 8 - gy0), "GTA", font=gta_font, fill=(255, 255, 255, 255))
    return canvas.resize((target_w, target_h), Image.Resampling.LANCZOS)


def render_gta_logo_png(out_path: str | Path, width: int = 380) -> Path:
    """Save a standalone official GTA VI logo crest PNG."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    height = max(int(round(width * 0.76)), 48)
    img = _render_vice_logo_rgba(width, height)
    img.save(out, format="PNG")
    return out


def render_neon_divider_png(
    width: int = 1080,
    height: int = 6,
    out_path: str | Path = "assets/ui/neon_divider_1080x6.png",
) -> Path:
    """Generate a vibrant Vice-City neon gradient seam divider (pink -> orange -> gold -> cyan)."""
    out = Path(out_path)
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    r = np.interp(x, [0.0, 0.35, 0.65, 1.0], [236.0, 249.0, 250.0, 34.0])
    g = np.interp(x, [0.0, 0.35, 0.65, 1.0], [72.0, 115.0, 204.0, 211.0])
    b = np.interp(x, [0.0, 0.35, 0.65, 1.0], [153.0, 22.0, 21.0, 238.0])
    row = np.stack([r, g, b, np.full_like(x, 255.0)], axis=-1).astype(np.uint8)
    arr = np.broadcast_to(row[None, :, :], (height, width, 4)).copy()
    Image.fromarray(arr, mode="RGBA").save(out, format="PNG")
    return out


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    start_px: int,
    min_px: int,
    max_w: int,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, int, int, int, int]:
    """Scale down a font smoothly only if text would exceed max_w."""
    for sz in range(start_px, min_px - 1, -4):
        f = _load_font(sz)
        w, h, x0, y0 = _text_size(draw, text, f)
        if w <= max_w:
            return f, w, h, x0, y0
    f = _load_font(min_px)
    w, h, x0, y0 = _text_size(draw, text, f)
    return f, w, h, x0, y0


def render_hook_card_png(
    badge_text: str,
    main_title: str,
    sub_accent: str,
    out_path: str | Path,
) -> Path:
    """Render floating borderless poster typography with glowing GTA VI crest (never hides gameplay behind a dark box)."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    S = 2
    show_gta_emblem = "gta 6" in badge_text.lower() or "gtavi" in badge_text.lower() or "gta vi" in badge_text.lower()
    clean_title = main_title.strip()
    if "\n" in clean_title:
        line1, line2 = [p.strip() for p in clean_title.split("\n", 1)]
    else:
        tokens = clean_title.split()
        if len(tokens) >= 4:
            mid = len(tokens) // 2
            line1 = " ".join(tokens[:mid])
            line2 = " ".join(tokens[mid:])
        else:
            line1 = clean_title
            line2 = ""

    card_w = 980 * S
    inner_max_w = card_w - 48 * S
    probe_img = Image.new("RGBA", (10, 10))
    pdraw = ImageDraw.Draw(probe_img)

    f_badge, bw, bh, bx0, by0 = _fit_font(pdraw, badge_text, 40 * S, 24 * S, card_w - 80 * S)
    f_l1, l1w, l1h, l1x0, l1y0 = _fit_font(pdraw, line1, 90 * S, 48 * S, inner_max_w)
    if line2:
        f_l2, l2w, l2h, l2x0, l2y0 = _fit_font(pdraw, line2, 100 * S, 50 * S, inner_max_w - 56 * S)
    else:
        f_l2 = _load_font(100 * S)
        l2w = l2h = l2x0 = l2y0 = 0
    if sub_accent:
        f_sub, sw, sh, sx0, sy0 = _fit_font(pdraw, sub_accent, 44 * S, 26 * S, inner_max_w - 24 * S)
    else:
        f_sub = _load_font(44 * S)
        sw = sh = sx0 = sy0 = 0

    logo_w, logo_h = (340 * S, 258 * S) if show_gta_emblem else (0, 0)
    l2_box_w = min(max(l2w + 72 * S, 680 * S), inner_max_w) if line2 else 0
    l2_box_h = (l2h + 34 * S) if line2 else 0

    badge_pill_w = bw + 64 * S
    badge_pill_h = 66 * S

    y_cur = 18 * S
    top_pad = y_cur
    if show_gta_emblem:
        y_cur += badge_pill_h + 10 * S
        y_logo_start = y_cur
        y_cur += logo_h + 6 * S
    else:
        y_logo_start = y_cur
        y_cur += badge_pill_h + 16 * S
    y_l1_start = y_cur
    y_cur += l1h + 18 * S
    y_l2_start = y_cur
    if line2:
        y_cur += l2_box_h + 18 * S
    y_sub_start = y_cur
    if sub_accent:
        y_cur += sh + 12 * S
    card_h = y_cur + 16 * S

    margin = 20 * S
    cw = card_w + margin * 2
    ch = card_h + margin * 2

    # Soft diffused glow/shadow ONLY directly behind floating elements (no opaque wall box!)
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    bpx = margin + (card_w - badge_pill_w) // 2
    bpy = margin + top_pad
    sdraw.rounded_rectangle([bpx - 6 * S, bpy, bpx + badge_pill_w + 6 * S, bpy + badge_pill_h + 10 * S], radius=badge_pill_h // 2, fill=(0, 0, 0, 220))
    l1_x = margin + (card_w - l1w) // 2 - l1x0
    l1_y = margin + y_l1_start - l1y0
    sdraw.text((l1_x, l1_y + 6 * S), line1, font=f_l1, fill=(0, 0, 0, 245), stroke_width=14 * S, stroke_fill=(0, 0, 0, 245))
    if line2:
        bx2 = margin + (card_w - l2_box_w) // 2
        by2 = margin + y_l2_start
        sdraw.rounded_rectangle([bx2 - 4 * S, by2 + 6 * S, bx2 + l2_box_w + 4 * S, by2 + l2_box_h + 12 * S], radius=24 * S, fill=(0, 0, 0, 235))
    if sub_accent:
        s_x = margin + (card_w - sw) // 2 - sx0
        s_y = margin + y_sub_start - sy0
        sdraw.text((s_x, s_y + 5 * S), sub_accent, font=f_sub, fill=(0, 0, 0, 240), stroke_width=10 * S, stroke_fill=(0, 0, 0, 240))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=12 * S))

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas)

    # Top glowing crimson-magenta hook badge pill
    draw.rounded_rectangle(
        [bpx, bpy, bpx + badge_pill_w, bpy + badge_pill_h],
        radius=badge_pill_h // 2,
        fill=(225, 29, 72, 255),
        outline=(255, 255, 255, 220),
        width=max(2 * S, 2),
    )
    draw.text(
        (bpx + (badge_pill_w - bw) // 2 - bx0, bpy + (badge_pill_h - bh) // 2 - by0),
        badge_text,
        font=f_badge,
        fill=(255, 255, 255, 255),
    )

    if show_gta_emblem:
        logo_rgba = _render_vice_logo_rgba(logo_w, logo_h)
        lx = margin + (card_w - logo_w) // 2
        ly = margin + y_logo_start
        canvas.alpha_composite(logo_rgba, (lx, ly))

    draw.text(
        (l1_x, l1_y),
        line1,
        font=f_l1,
        fill=(255, 255, 255, 255),
        stroke_width=10 * S,
        stroke_fill=(8, 11, 20, 255),
    )

    if line2:
        bx2 = margin + (card_w - l2_box_w) // 2
        by2 = margin + y_l2_start
        draw.rounded_rectangle(
            [bx2, by2, bx2 + l2_box_w, by2 + l2_box_h],
            radius=22 * S,
            fill=(250, 204, 21, 255),
            outline=(10, 13, 22, 255),
            width=max(3 * S, 3),
        )
        draw.text(
            (bx2 + (l2_box_w - l2w) // 2 - l2x0, by2 + (l2_box_h - l2h) // 2 - l2y0),
            line2,
            font=f_l2,
            fill=(9, 13, 22, 255),
        )

    if sub_accent:
        s_x = margin + (card_w - sw) // 2 - sx0
        s_y = margin + y_sub_start - sy0
        draw.text(
            (s_x, s_y),
            sub_accent,
            font=f_sub,
            fill=(34, 211, 238, 255),
            stroke_width=7 * S,
            stroke_fill=(8, 11, 20, 255),
        )

    final = canvas.resize((cw // S, ch // S), Image.Resampling.LANCZOS)
    final.save(out, format="PNG")
    return out


def render_mystery_lock_png(
    headline: str,
    subtext: str,
    out_path: str | Path,
) -> Path:
    """Render a floating neon-stroked open-loop vector padlock overlay for Beat 3."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    S = 2
    card_w = 960 * S
    inner_max_w = card_w - 64 * S
    probe = Image.new("RGBA", (10, 10))
    pdraw = ImageDraw.Draw(probe)
    f_main, mw, mh, mx0, my0 = _fit_font(pdraw, headline, 88 * S, 48 * S, inner_max_w)
    if subtext:
        f_sub, sw, sh, sx0, sy0 = _fit_font(pdraw, subtext, 40 * S, 24 * S, inner_max_w - 48 * S)
    else:
        f_sub = _load_font(40 * S)
        sw = sh = sx0 = sy0 = 0

    lock_w, lock_h = 172 * S, 176 * S
    sub_pill_w = min(max(sw + 68 * S, 620 * S), inner_max_w) if subtext else 0
    sub_pill_h = (sh + 32 * S) if subtext else 0
    card_h = 24 * S + lock_h + 24 * S + mh + (24 * S + sub_pill_h if subtext else 0) + 24 * S

    margin = 20 * S
    cw = card_w + margin * 2
    ch = card_h + margin * 2

    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    ix = margin + (card_w - lock_w) // 2
    iy = margin + 24 * S
    sdraw.rounded_rectangle([ix, iy + 64 * S, ix + lock_w, iy + lock_h + 8 * S], radius=24 * S, fill=(0, 0, 0, 230))
    m_x = margin + (card_w - mw) // 2 - mx0
    m_y = iy + lock_h + 24 * S - my0
    sdraw.text((m_x, m_y + 6 * S), headline, font=f_main, fill=(0, 0, 0, 245), stroke_width=14 * S, stroke_fill=(0, 0, 0, 245))
    if subtext:
        spx = margin + (card_w - sub_pill_w) // 2
        spy = iy + lock_h + 24 * S + mh + 24 * S
        sdraw.rounded_rectangle([spx, spy + 6 * S, spx + sub_pill_w, spy + sub_pill_h + 10 * S], radius=sub_pill_h // 2, fill=(0, 0, 0, 230))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14 * S))

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas)

    draw.arc([ix + 30 * S, iy, ix + lock_w - 30 * S, iy + 104 * S], start=180, end=0, fill=(250, 204, 21, 255), width=18 * S)
    draw.line([ix + 39 * S, iy + 50 * S, ix + 39 * S, iy + 80 * S], fill=(250, 204, 21, 255), width=18 * S)
    draw.line([ix + lock_w - 39 * S, iy + 50 * S, ix + lock_w - 39 * S, iy + 80 * S], fill=(250, 204, 21, 255), width=18 * S)
    draw.rounded_rectangle(
        [ix + 10 * S, iy + 74 * S, ix + lock_w - 10 * S, iy + lock_h],
        radius=24 * S,
        fill=(250, 204, 21, 255),
        outline=(9, 13, 22, 255),
        width=max(4 * S, 4),
    )
    kx = ix + lock_w // 2
    ky = iy + 112 * S
    draw.ellipse([kx - 14 * S, ky - 14 * S, kx + 14 * S, ky + 14 * S], fill=(14, 10, 26, 255))
    draw.rectangle([kx - 6 * S, ky + 4 * S, kx + 6 * S, ky + 36 * S], fill=(14, 10, 26, 255))

    draw.text(
        (m_x, m_y),
        headline,
        font=f_main,
        fill=(255, 255, 255, 255),
        stroke_width=10 * S,
        stroke_fill=(8, 11, 20, 255),
    )

    if subtext:
        draw.rounded_rectangle(
            [spx, spy, spx + sub_pill_w, spy + sub_pill_h],
            radius=sub_pill_h // 2,
            fill=(225, 29, 72, 255),
            outline=(255, 255, 255, 220),
            width=max(2 * S, 2),
        )
        draw.text(
            (spx + (sub_pill_w - sw) // 2 - sx0, spy + (sub_pill_h - sh) // 2 - sy0),
            subtext,
            font=f_sub,
            fill=(255, 255, 255, 255),
        )

    final = canvas.resize((cw // S, ch // S), Image.Resampling.LANCZOS)
    final.save(out, format="PNG")
    return out


def render_progress_bar_layers(
    width: int = 1080,
    height: int = 9,
    out_dir: str | Path = "assets/ui",
) -> tuple[Path, Path]:
    """Generate a dark translucent track and amber-to-gold gradient fill bar PNG."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    track_p = root / f"prog_track_{width}x{height}.png"
    fill_p = root / f"prog_fill_{width}x{height}.png"

    if not track_p.exists():
        track = Image.new("RGBA", (width, height), (9, 13, 22, 185))
        track.save(track_p, format="PNG")

    if not fill_p.exists():
        fill = Image.new("RGBA", (width, height))
        px = fill.load()
        for x in range(width):
            t = x / max(width - 1, 1)
            # Smooth vivid orange (#F97316) -> vibrant gold (#FACC15) -> bright warm glow (#FEF08A)
            if t < 0.7:
                u = t / 0.7
                r = int(249 + (250 - 249) * u)
                g = int(115 + (204 - 115) * u)
                b = int(22 + (21 - 22) * u)
            else:
                u = (t - 0.7) / 0.3
                r = int(250 + (254 - 250) * u)
                g = int(204 + (240 - 204) * u)
                b = int(21 + (138 - 21) * u)
            for y in range(height):
                px[x, y] = (r, g, b, 255)
        fill.save(fill_p, format="PNG")

    return track_p, fill_p
