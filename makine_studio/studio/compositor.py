"""2D blueprint compositor, HUD overlay renderer, and FFmpeg video muxer."""

from __future__ import annotations

import functools
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import (
    FFMPEG_EXE,
    FONT_BOLD,
    FONT_SUBTITLE,
    FONT_TECH,
    PALETTE,
    PROFILES,
)


def _color(color_ref: str | tuple[int, ...] | list[int], alpha: int | None = None) -> tuple[int, ...]:
    """Resolve a palette color name or tuple, optionally attaching alpha."""
    if isinstance(color_ref, str):
        base = PALETTE.get(color_ref, PALETTE["white"])
    else:
        base = tuple(int(c) for c in color_ref)
    if alpha is not None:
        return (base[0], base[1], base[2], int(alpha))
    return base


@functools.lru_cache(maxsize=32)
def _load_font(kind: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load and cache TrueType fonts with cross-platform fallbacks."""
    candidates_map = {
        "bold": [
            FONT_BOLD,
            FONT_SUBTITLE,
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ],
        "subtitle": [
            FONT_SUBTITLE,
            FONT_BOLD,
            Path(r"C:\Windows\Fonts\segoeui.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ],
        "tech": [
            FONT_TECH,
            FONT_SUBTITLE,
            Path(r"C:\Windows\Fonts\consola.ttf"),
            Path("/System/Library/Fonts/Menlo.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        ],
    }
    for path in candidates_map.get(kind, [FONT_BOLD]):
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    """Return rendered pixel (width, height) of a text string."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])


def _normalize_word(word: str) -> str:
    """Normalize Turkish token for matching spoken timeline words."""
    lowered = word.replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"[^\wçğıöşü]", "", lowered)


def build_blueprint_background(profile_cfg: dict[str, Any], header_tag: str = "") -> Image.Image:
    """Render the base dark-navy architectural blueprint grid canvas as RGB Image."""
    w = int(profile_cfg["canvas_w"])
    h = int(profile_cfg["canvas_h"])

    # Smooth vertical + subtle radial vignette gradient between bg_dark and bg_mid.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx / max(w - 1, 1)) * 2.0 - 1.0
    ny = (yy / max(h - 1, 1)) * 2.0 - 1.0
    center_y = -0.10 if h > w else 0.0
    dist = np.sqrt((nx * 0.85) ** 2 + ((ny - center_y) * 0.95) ** 2)
    glow = np.clip(1.0 - dist * 0.82, 0.0, 1.0) ** 1.4

    c_dark = np.array(PALETTE["bg_dark"][:3], dtype=np.float32)
    c_mid = np.array(PALETTE["bg_mid"][:3], dtype=np.float32)
    bg_arr = c_dark + (c_mid - c_dark) * glow[..., None]

    # Fast vectorized grid overlay (40px minor, 200px major).
    minor_col = np.array(PALETTE["grid_minor"][:3], dtype=np.float32)
    major_col = np.array(PALETTE["grid_major"][:3], dtype=np.float32)

    minor_step = 40
    major_step = 200
    x_idx = np.arange(w)
    y_idx = np.arange(h)
    minor_mask_x = (x_idx % minor_step) == 0
    minor_mask_y = (y_idx % minor_step) == 0
    major_mask_x = (x_idx % major_step) == 0
    major_mask_y = (y_idx % major_step) == 0

    bg_arr[:, minor_mask_x, :] = bg_arr[:, minor_mask_x, :] * 0.55 + minor_col * 0.45
    bg_arr[minor_mask_y, :, :] = bg_arr[minor_mask_y, :, :] * 0.55 + minor_col * 0.45
    bg_arr[:, major_mask_x, :] = bg_arr[:, major_mask_x, :] * 0.40 + major_col * 0.60
    bg_arr[major_mask_y, :, :] = bg_arr[major_mask_y, :, :] * 0.40 + major_col * 0.60

    img = Image.fromarray(np.clip(bg_arr, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Outer engineering sheet border, corner brackets, and ruler ticks.
    margin = 26
    border_col = _color("border_line", 150)
    corner_col = _color("corner_accent", 215)
    draw.rectangle([margin, margin, w - margin, h - margin], outline=border_col, width=2)

    # Ruler tick marks along the outer border.
    for x in range(margin + minor_step, w - margin, minor_step):
        tick = 10 if (x % major_step) == 0 else 5
        draw.line([(x, margin), (x, margin + tick)], fill=border_col, width=1)
        draw.line([(x, h - margin), (x, h - margin - tick)], fill=border_col, width=1)
    for y in range(margin + minor_step, h - margin, minor_step):
        tick = 10 if (y % major_step) == 0 else 5
        draw.line([(margin, y), (margin + tick, y)], fill=border_col, width=1)
        draw.line([(w - margin, y), (w - margin - tick, y)], fill=border_col, width=1)

    # Corner CAD brackets + tiny anchor squares.
    arm = 32
    for cx, cy, sx, sy in [
        (margin, margin, 1, 1),
        (w - margin, margin, -1, 1),
        (margin, h - margin, 1, -1),
        (w - margin, h - margin, -1, -1),
    ]:
        draw.line([(cx, cy), (cx + sx * arm, cy)], fill=corner_col, width=3)
        draw.line([(cx, cy), (cx, cy + sy * arm)], fill=corner_col, width=3)
        draw.rectangle([cx - 3, cy - 3, cx + 3, cy + 3], fill=corner_col)

    # Subtle engineering sheet header safely below Shorts top overlay (y=260 for Shorts).
    header_y = 262 if h > w else 44
    stage_divider_top = int(profile_cfg["stage_y"]) - 18
    stage_divider_bot = int(profile_cfg["stage_y"]) + int(profile_cfg["stage_h"]) + 12

    if h > w:
        tech_font = _load_font("tech", 20)
        left_tag = header_tag.upper() if header_tag else "MÜHENDİSLİK ŞEMASI  //  KESİT GÖRÜNÜMÜ"
        right_tag = "ÖLÇEK 1:25  |  REV-01"
        draw.text((margin + 18, header_y), left_tag, font=tech_font, fill=_color("corner_accent", 165))
        rw, _ = _text_size(draw, right_tag, tech_font)
        draw.text((w - margin - 18 - rw, header_y), right_tag, font=tech_font, fill=_color("border_line", 180))
        if stage_divider_top > header_y + 24:
            draw.line(
                [(margin + 16, stage_divider_top), (w - margin - 16, stage_divider_top)],
                fill=_color("border_line", 105),
                width=1,
            )
        if stage_divider_bot < h - 280:
            draw.line(
                [(margin + 16, stage_divider_bot), (w - margin - 16, stage_divider_bot)],
                fill=_color("border_line", 105),
                width=1,
            )

    return img.convert("RGB")


def build_stage_mask(profile_cfg: dict[str, Any]) -> np.ndarray:
    """Precompute smooth float32 feather mask (stage_h, stage_w, 1) in [0, 1]."""
    sw = int(profile_cfg["stage_w"])
    sh = int(profile_cfg["stage_h"])
    ft = max(1, int(profile_cfg["feather_top"]))
    fb = max(1, int(profile_cfg["feather_bottom"]))

    wy = np.ones(sh, dtype=np.float32)
    top_ramp = np.linspace(0.0, 1.0, ft, dtype=np.float32)
    wy[:ft] = 0.5 - 0.5 * np.cos(np.pi * top_ramp)
    bot_ramp = np.linspace(1.0, 0.0, fb, dtype=np.float32)
    wy[sh - fb :] = 0.5 - 0.5 * np.cos(np.pi * bot_ramp)

    wx = np.ones(sw, dtype=np.float32)
    fs = 28
    if sw > fs * 2:
        side_ramp = np.linspace(0.0, 1.0, fs, dtype=np.float32)
        smooth_side = 0.5 - 0.5 * np.cos(np.pi * side_ramp)
        wx[:fs] = smooth_side
        wx[sw - fs :] = smooth_side[::-1]

    mask = np.outer(wy, wx)[..., None]
    return mask.astype(np.float32)


def _find_blender_frame(frames_dir: Path, frame_idx: int) -> Path:
    """Locate Blender output PNG for a 1-based frame index."""
    candidates = [
        frames_dir / f"frame_{frame_idx:04d}.png",
        frames_dir / f"{frame_idx:04d}.png",
        frames_dir / f"frame_{frame_idx:05d}.png",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Missing rendered Blender frame {frame_idx} in {frames_dir}")


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    p0: tuple[float, float],
    p1: tuple[float, float],
    color: tuple[int, ...],
    size: float = 15.0,
) -> None:
    """Draw a crisp filled triangular arrowhead at p1 pointing from p0."""
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1e-3:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    base_x = p1[0] - ux * size
    base_y = p1[1] - uy * size
    wing = size * 0.52
    pts = [
        (p1[0], p1[1]),
        (base_x + px * wing, base_y + py * wing),
        (base_x - px * wing, base_y - py * wing),
    ]
    draw.polygon(pts, fill=color)


def _draw_music_note(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    color: tuple[int, ...],
    scale: float = 1.0,
) -> None:
    """Draw a crisp vector musical eighth note without relying on font glyphs."""
    r = 9.0 * scale
    head_box = [cx - r * 1.15, cy - r * 0.75, cx + r * 0.85, cy + r * 0.85]
    draw.ellipse(head_box, fill=color)
    stem_x = cx + r * 0.68
    stem_top = cy - r * 3.1
    draw.line([(stem_x, cy), (stem_x, stem_top)], fill=color, width=max(2, int(3.5 * scale)))
    flag = [
        (stem_x, stem_top),
        (stem_x + r * 1.5, stem_top + r * 0.9),
        (stem_x + r * 1.35, stem_top + r * 1.65),
        (stem_x, stem_top + r * 0.85),
    ]
    draw.polygon(flag, fill=color)


def _draw_hud_overlays(
    canvas_rgba: Image.Image,
    hud_items: list[dict[str, Any]],
    profile_cfg: dict[str, Any],
    frame_idx: int,
    fps: int,
) -> None:
    """Render tracked 3D callouts, alerts, badges, arrows, and musical cues onto canvas."""
    if not hud_items:
        return

    overlay = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    cw = int(profile_cfg["canvas_w"])
    stage_y = int(profile_cfg["stage_y"])
    stage_h = int(profile_cfg["stage_h"])
    tech_font = _load_font("tech", 24 if cw >= 1080 else 20)
    badge_font = _load_font("bold", 24 if cw >= 1080 else 20)
    alert_font = _load_font("bold", 34)

    for item in hud_items:
        kind = item.get("kind", "callout")
        label = str(item.get("label", "")).strip()
        color_name = item.get("color", "cyan")
        col = _color(color_name, 255)
        extra = item.get("extra") or {}

        ax = float(item.get("x", 0.0))
        ay = float(stage_y) + float(item.get("y", 0.0))
        dx, dy = item.get("offset_px", [130, -80])
        dx, dy = float(dx), float(dy)

        if kind == "callout":
            tw, th = _text_size(draw, label, tech_font)
            pad_x, pad_y = 14, 8
            box_w = max(84, tw + pad_x * 2)
            box_h = th + pad_y * 2

            # Target box center clamped neatly inside safe margins.
            bx = max(44 + box_w * 0.5, min(cw - 44 - box_w * 0.5, ax + dx))
            by = max(stage_y + 24 + box_h * 0.5, min(stage_y + stage_h - 18 - box_h * 0.5, ay + dy))

            # Anchor point glow + solid ring.
            draw.ellipse([ax - 11, ay - 11, ax + 11, ay + 11], fill=_color(color_name, 70))
            draw.ellipse([ax - 5, ay - 5, ax + 5, ay + 5], fill=col, outline=_color("white", 230), width=2)

            # Two-segment crisp engineering leader line.
            edge_x = bx - box_w * 0.5 if bx >= ax else bx + box_w * 0.5
            elbow_x = ax + (edge_x - ax) * 0.58
            draw.line([(ax, ay), (elbow_x, by), (edge_x, by)], fill=col, width=3)

            rect = [bx - box_w * 0.5, by - box_h * 0.5, bx + box_w * 0.5, by + box_h * 0.5]
            draw.rounded_rectangle(rect, radius=8, fill=PALETTE["label_bg"], outline=col, width=2)
            draw.text((bx - tw * 0.5, by - th * 0.5 - 2), label, font=tech_font, fill=_color("white", 250))

        elif kind == "alert":
            pulse = 0.5 + 0.5 * math.sin(frame_idx * (2.0 * math.pi / max(1, fps * 0.45)))
            px = max(56.0, min(cw - 56.0, ax + dx))
            py = max(float(stage_y + 36), min(float(stage_y + stage_h - 24), ay + dy))
            outer_r = 30.0 + pulse * 10.0
            inner_r = 22.0 + pulse * 2.0

            draw.ellipse([px - outer_r, py - outer_r, px + outer_r, py + outer_r], fill=_color(color_name, int(85 + 75 * pulse)))
            draw.ellipse([px - inner_r, py - inner_r, px + inner_r, py + inner_r], fill=col, outline=_color("white", 240), width=3)
            mark = str(extra.get("symbol", "!"))
            mw, mh = _text_size(draw, mark, alert_font)
            draw.text((px - mw * 0.5, py - mh * 0.58), mark, font=alert_font, fill=_color("white", 255))

            if label:
                lw, lh = _text_size(draw, label, tech_font)
                tag_x = min(cw - 48 - lw - 24, px + inner_r + 12)
                if tag_x < px + inner_r:
                    tag_x = max(48.0, px - inner_r - lw - 34)
                rect = [tag_x, py - lh * 0.5 - 7, tag_x + lw + 22, py + lh * 0.5 + 7]
                draw.rounded_rectangle(rect, radius=7, fill=PALETTE["label_bg"], outline=col, width=2)
                draw.text((tag_x + 11, py - lh * 0.5 - 2), label, font=tech_font, fill=_color("white", 255))

        elif kind == "badge":
            tw, th = _text_size(draw, label, badge_font)
            pad_x, pad_y = 18, 10
            box_w = tw + pad_x * 2 + 8
            box_h = th + pad_y * 2
            bx = max(44 + box_w * 0.5, min(cw - 44 - box_w * 0.5, ax + dx))
            by = max(stage_y + 24 + box_h * 0.5, min(stage_y + stage_h - 18 - box_h * 0.5, ay + dy))

            if extra.get("leader"):
                draw.line([(ax, ay), (bx, by)], fill=_color(color_name, 190), width=2)
                draw.ellipse([ax - 4, ay - 4, ax + 4, ay + 4], fill=col)

            rect = [bx - box_w * 0.5, by - box_h * 0.5, bx + box_w * 0.5, by + box_h * 0.5]
            draw.rounded_rectangle(rect, radius=10, fill=PALETTE["label_bg"], outline=col, width=2)
            # Crisp left accent stripe.
            draw.rounded_rectangle(
                [rect[0] + 4, rect[1] + 5, rect[0] + 10, rect[3] - 5],
                radius=3,
                fill=col,
            )
            draw.text((rect[0] + 18, by - th * 0.5 - 2), label, font=badge_font, fill=_color("white", 255))

        elif kind == "arrow":
            osc = 0.0
            if extra.get("oscillate"):
                osc = math.sin(frame_idx * (8.4 / max(1, fps))) * 14.0
            p0 = (ax, ay + osc * 0.4)
            p1 = (ax + dx, ay + dy + osc)
            draw.line([p0, p1], fill=col, width=4)
            _draw_arrowhead(draw, p0, p1, col, size=16.0)
            if label:
                mx = (p0[0] + p1[0]) * 0.5
                my = (p0[1] + p1[1]) * 0.5 - 18
                lw, lh = _text_size(draw, label, tech_font)
                draw.rounded_rectangle(
                    [mx - lw * 0.5 - 10, my - lh * 0.5 - 5, mx + lw * 0.5 + 10, my + lh * 0.5 + 5],
                    radius=6,
                    fill=PALETTE["label_bg"],
                    outline=col,
                    width=1,
                )
                draw.text((mx - lw * 0.5, my - lh * 0.5 - 2), label, font=tech_font, fill=_color("white", 255))

        elif kind == "note":
            bob = math.sin(frame_idx * (6.72 / max(1, fps))) * 10.0
            if label:
                lw, lh = _text_size(draw, label, tech_font)
                box_w = 56 + lw + 18
                box_h = max(46, lh + 20)
                nx = max(44.0 + box_w * 0.5, min(cw - 44.0 - box_w * 0.5, ax + dx))
                ny = max(float(stage_y + 40), min(float(stage_y + stage_h - 32), ay + dy + bob))
                x0 = nx - box_w * 0.5
                y0 = ny - box_h * 0.5
                draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=12, fill=PALETTE["label_bg"], outline=col, width=2)
                _draw_music_note(draw, x0 + 24, ny + 4, col, scale=0.88)
                draw.text((x0 + 52, ny - lh * 0.5 - 2), label, font=tech_font, fill=_color("white", 255))
            else:
                nx = max(56.0, min(cw - 56.0, ax + dx))
                ny = max(float(stage_y + 40), min(float(stage_y + stage_h - 30), ay + dy + bob))
                draw.rounded_rectangle([nx - 26, ny - 32, nx + 26, ny + 18], radius=14, fill=PALETTE["label_bg"], outline=col, width=2)
                _draw_music_note(draw, nx - 4, ny - 2, col, scale=0.95)

    canvas_rgba.alpha_composite(overlay)


def _wrap_colored_headline(
    draw: ImageDraw.ImageDraw,
    segments: list[tuple[str, str]] | list[list[str]],
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[list[tuple[str, str]]]:
    """Pack colored text segments into centered lines within max_width."""
    tokens: list[tuple[str, str]] = []
    for seg in segments:
        text, color_key = seg[0], seg[1]
        for piece in re.findall(r"\n|[^\S\n]+|\S+", text):
            tokens.append((piece, color_key))

    lines: list[list[tuple[str, str]]] = [[]]
    line_widths: list[int] = [0]

    for piece, color_key in tokens:
        if piece == "\n":
            if lines[-1]:
                lines.append([])
                line_widths.append(0)
            continue
        is_space = piece.isspace()
        if is_space and not lines[-1]:
            continue
        test_w, _ = _text_size(draw, piece, font)
        if not is_space and lines[-1] and line_widths[-1] + test_w > max_width:
            lines.append([])
            line_widths.append(0)
        lines[-1].append((piece, color_key))
        line_widths[-1] += test_w

    # Trim trailing whitespace tokens on the right of each line for exact visual centering.
    cleaned: list[list[tuple[str, str]]] = []
    for line in lines:
        while line and line[-1][0].isspace():
            line.pop()
        if line:
            cleaned.append(line)
    return cleaned


def _draw_headline(
    canvas_rgba: Image.Image,
    beat: dict[str, Any] | None,
    profile_cfg: dict[str, Any],
    frame_idx: int,
    fps: int = 30,
) -> None:
    """Draw the kinetic multi-color engineering headline in the lower blueprint band."""
    if not beat or not beat.get("headline"):
        return

    cw = int(profile_cfg["canvas_w"])
    ch = int(profile_cfg["canvas_h"])
    is_shorts = ch > cw
    max_width = cw - (110 if is_shorts else 260)

    probe_draw = ImageDraw.Draw(canvas_rgba)
    font_size = 56 if is_shorts else 50
    lines: list[list[tuple[str, str]]] = []
    font = _load_font("bold", font_size)

    # Shrink font slightly if multi-line would exceed 2 lines.
    for sz in range(font_size, 36, -4):
        font = _load_font("bold", sz)
        lines = _wrap_colored_headline(probe_draw, beat["headline"], font, max_width)
        if len(lines) <= 2:
            font_size = sz
            break

    if not lines:
        return

    # Subtle 0.20s pop-in slide at the start of each beat (FPS-independent).
    beat_age_sec = max(0, frame_idx - int(beat.get("frame_start", frame_idx))) / max(1, fps)
    ease = min(1.0, beat_age_sec / 0.20)
    slide_y = int((1.0 - ease) ** 2 * 14)

    line_h = int(font_size * 1.20)
    total_h = len(lines) * line_h
    center_y = 1438 if is_shorts else int(ch * 0.815)
    start_y = center_y - total_h * 0.5 + slide_y

    overlay = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for li, line in enumerate(lines):
        full_str = "".join(t for t, _ in line)
        total_w, _ = _text_size(draw, full_str, font)
        cursor_x = (cw - total_w) * 0.5
        ly = start_y + li * line_h
        for seg_text, seg_color in line:
            col = _color(seg_color, 255)
            # Crisp dark drop-shadow + stroke for contrast on blueprint grid.
            draw.text((cursor_x + 2, ly + 3), seg_text, font=font, fill=(3, 10, 20, 220))
            draw.text((cursor_x, ly), seg_text, font=font, fill=col, stroke_width=2, stroke_fill=(5, 14, 28, 220))
            sw, _ = _text_size(draw, seg_text, font)
            cursor_x += sw

    canvas_rgba.alpha_composite(overlay)


def _draw_subtitle(
    canvas_rgba: Image.Image,
    timeline: dict[str, Any],
    profile_cfg: dict[str, Any],
    time_sec: float,
) -> None:
    """Draw active caption cue with subtle live active-word highlight in safe zone."""
    subtitles = timeline.get("subtitles", [])
    active_cue = None
    for cue in subtitles:
        if float(cue["start"]) - 0.03 <= time_sec <= float(cue["end"]) + 0.06:
            active_cue = cue
            break
    if not active_cue:
        return

    text = str(active_cue.get("text", "")).strip()
    if not text:
        return

    # Find spoken word overlapping current time to highlight in cyan.
    active_words_norm: set[str] = set()
    for w in timeline.get("words", []):
        if float(w["start"]) - 0.04 <= time_sec <= float(w["end"]) + 0.05:
            norm = _normalize_word(str(w["text"]))
            if norm:
                active_words_norm.add(norm)

    cw = int(profile_cfg["canvas_w"])
    ch = int(profile_cfg["canvas_h"])
    is_shorts = ch > cw
    max_text_w = cw - (150 if is_shorts else 360)

    font_size = 38 if is_shorts else 34
    font = _load_font("subtitle", font_size)

    overlay = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Greedy 2-line wrap so captions stay inside safe box margins.
    words = text.split()
    lines: list[list[str]] = [[]]
    for tok in words:
        trial = " ".join(lines[-1] + [tok])
        tw, _ = _text_size(draw, trial, font)
        if lines[-1] and tw > max_text_w:
            lines.append([tok])
        else:
            lines[-1].append(tok)

    line_widths = [_text_size(draw, " ".join(ln), font)[0] for ln in lines]
    max_lw = max(line_widths) if line_widths else 100
    line_h = int(font_size * 1.24)
    text_block_h = len(lines) * line_h

    pad_x, pad_y = 26, 12
    box_w = max_lw + pad_x * 2
    box_h = text_block_h + pad_y * 2
    # Keep bottom strictly above YouTube Shorts UI chrome (y <= 1675 on 1920h).
    center_y = 1585 if is_shorts else int(ch * 0.915)
    box_x0 = (cw - box_w) * 0.5
    box_y0 = center_y - box_h * 0.5

    draw.rounded_rectangle(
        [box_x0, box_y0, box_x0 + box_w, box_y0 + box_h],
        radius=14,
        fill=PALETTE["subtitle_bg"],
        outline=_color("border_line", 145),
        width=2,
    )

    for li, line_words in enumerate(lines):
        joined = " ".join(line_words)
        lw, _ = _text_size(draw, joined, font)
        cx = (cw - lw) * 0.5
        cy = box_y0 + pad_y + li * line_h - 3
        for wi, tok in enumerate(line_words):
            suffix = " " if wi < len(line_words) - 1 else ""
            piece = tok + suffix
            is_active = _normalize_word(tok) in active_words_norm
            fill_col = _color("cyan", 255) if is_active else _color("white", 255)
            draw.text((cx + 1, cy + 2), piece, font=font, fill=(0, 0, 0, 200))
            draw.text((cx, cy), piece, font=font, fill=fill_col)
            pw, _ = _text_size(draw, piece, font)
            cx += pw

    canvas_rgba.alpha_composite(overlay)


def _active_beat_for_frame(beats: list[dict[str, Any]], frame_idx: int) -> dict[str, Any] | None:
    """Locate beat covering 1-based frame_idx."""
    if not beats:
        return None
    if frame_idx < int(beats[0]["frame_start"]):
        return beats[0]
    for beat in beats:
        if int(beat["frame_start"]) <= frame_idx <= int(beat["frame_end"]):
            return beat
    return beats[-1]


def _blend_stage_onto_bg(
    bg_np: np.ndarray,
    blender_frame_path: Path,
    sw: int,
    sh: int,
    sy: int,
    stage_mask: np.ndarray,
) -> Image.Image:
    """Alpha-blend an RGBA 3D stage frame onto blueprint canvas using feather stage_mask."""
    stage_img = Image.open(blender_frame_path).convert("RGBA")
    if stage_img.size != (sw, sh):
        stage_img = stage_img.resize((sw, sh), Image.Resampling.LANCZOS)
    stage_rgba = np.asarray(stage_img, dtype=np.float32)
    stage_rgb = stage_rgba[..., :3]
    stage_alpha = (stage_rgba[..., 3:4] / 255.0) * stage_mask

    canvas_np = bg_np.copy()
    roi = canvas_np[sy : sy + sh, :sw, :]
    canvas_np[sy : sy + sh, :sw, :] = roi * (1.0 - stage_alpha) + stage_rgb * stage_alpha
    return Image.fromarray(np.clip(canvas_np, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")


def render_composited_frame(
    frame_idx: int,
    blender_frame_path: Path,
    timeline: dict[str, Any],
    hud_frames: dict[str, Any],
    bg_np: np.ndarray,
    stage_mask: np.ndarray,
    profile_cfg: dict[str, Any],
) -> Image.Image:
    """Composite one Blender 3D stage frame onto blueprint grid with HUD, headline, and captions."""
    sw = int(profile_cfg["stage_w"])
    sh = int(profile_cfg["stage_h"])
    sy = int(profile_cfg["stage_y"])
    fps = int(timeline.get("fps", profile_cfg["fps"]))

    canvas_rgba = _blend_stage_onto_bg(bg_np, blender_frame_path, sw, sh, sy, stage_mask)

    hud_items = hud_frames.get(str(frame_idx), [])
    _draw_hud_overlays(canvas_rgba, hud_items, profile_cfg, frame_idx, fps)

    beat = _active_beat_for_frame(timeline.get("beats", []), frame_idx)
    _draw_headline(canvas_rgba, beat, profile_cfg, frame_idx, fps)

    time_sec = max(0.0, (frame_idx - 1) / max(1, fps))
    _draw_subtitle(canvas_rgba, timeline, profile_cfg, time_sec)

    return canvas_rgba.convert("RGB")


def _load_hud_frames(hud_tracks_path: Path) -> dict[str, Any]:
    """Load Blender-exported HUD frame dictionary."""
    if not hud_tracks_path.exists():
        return {}
    data = json.loads(hud_tracks_path.read_text(encoding="utf-8"))
    return data.get("frames", {})


def compose_preview_frames(
    frames_dir: Path,
    timeline: dict[str, Any],
    hud_tracks_path: Path,
    out_dir: Path,
    frame_indices: list[int],
    profile: str = "shorts",
    header_tag: str = "",
) -> list[Path]:
    """Render standalone composited PNGs for visual inspection before full encode."""
    profile_cfg = PROFILES[profile]
    bg_np = np.asarray(build_blueprint_background(profile_cfg, header_tag=header_tag), dtype=np.float32)
    stage_mask = build_stage_mask(profile_cfg)
    hud_frames = _load_hud_frames(hud_tracks_path)

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for fidx in frame_indices:
        src_path = _find_blender_frame(frames_dir, fidx)
        comp = render_composited_frame(fidx, src_path, timeline, hud_frames, bg_np, stage_mask, profile_cfg)
        beat = _active_beat_for_frame(timeline.get("beats", []), fidx)
        beat_id = beat["id"] if beat else "frame"
        dst = out_dir / f"preview_{beat_id}_f{fidx:04d}.png"
        comp.save(dst, format="PNG")
        saved.append(dst)
    return saved


def compose_video(
    frames_dir: Path,
    timeline: dict[str, Any],
    hud_tracks_path: Path,
    master_audio_wav: Path,
    out_mp4: Path,
    profile: str = "shorts",
    header_tag: str = "",
) -> Path:
    """Composite all frames in memory and pipe RGB24 stream directly into FFmpeg MP4 mux."""
    profile_cfg = PROFILES[profile]
    cw = int(profile_cfg["canvas_w"])
    ch = int(profile_cfg["canvas_h"])
    fps = int(timeline.get("fps", profile_cfg["fps"]))
    total_frames = int(timeline["total_frames"])

    bg_np = np.asarray(build_blueprint_background(profile_cfg, header_tag=header_tag), dtype=np.float32)
    stage_mask = build_stage_mask(profile_cfg)
    hud_frames = _load_hud_frames(hud_tracks_path)

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_mp4.with_suffix(".ffmpeg.log")
    cmd = [
        FFMPEG_EXE,
        "-y",
        "-loglevel", "warning",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{cw}x{ch}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-i", str(master_audio_wav),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        str(out_mp4),
    ]

    with log_path.open("w", encoding="utf-8") as log_fh:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log_fh)
        assert proc.stdin is not None
        try:
            for fidx in range(1, total_frames + 1):
                src_path = _find_blender_frame(frames_dir, fidx)
                frame_img = render_composited_frame(fidx, src_path, timeline, hud_frames, bg_np, stage_mask, profile_cfg)
                proc.stdin.write(frame_img.tobytes())
                if fidx % 200 == 0 or fidx == total_frames:
                    print(f"[Compositor] {fidx}/{total_frames} frames encoded", flush=True)
        except BrokenPipeError:
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
        ret = proc.wait()

    if ret != 0:
        err_txt = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        raise RuntimeError(f"FFmpeg video mux failed (exit {ret}):\n{err_txt}")
    log_path.unlink(missing_ok=True)
    return out_mp4


def generate_cover_thumbnail(
    blender_hero_path: Path,
    out_path: Path,
    title_lines: list[tuple[str, str]],
    profile: str = "shorts",
    header_tag: str = "",
) -> Path:
    """Create a high-contrast blueprint cover thumbnail from a hero 3D render frame."""
    profile_cfg = PROFILES[profile]
    cw = int(profile_cfg["canvas_w"])
    ch = int(profile_cfg["canvas_h"])
    sw = int(profile_cfg["stage_w"])
    sh = int(profile_cfg["stage_h"])
    sy = int(profile_cfg["stage_y"])

    bg_np = np.asarray(build_blueprint_background(profile_cfg, header_tag=header_tag), dtype=np.float32)
    stage_mask = build_stage_mask(profile_cfg)
    canvas = _blend_stage_onto_bg(bg_np, blender_hero_path, sw, sh, sy, stage_mask)

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Punchy large stacked headline in lower blueprint zone (or top for cover clarity).
    is_shorts = ch > cw
    base_size = 76 if is_shorts else 72
    line_y = 1405 if is_shorts else 120
    for idx, (text, color_key) in enumerate(title_lines):
        font = _load_font("bold", base_size)
        tw, _ = _text_size(draw, text, font)
        while tw > cw - 110 and base_size > 44:
            base_size -= 4
            font = _load_font("bold", base_size)
            tw, _ = _text_size(draw, text, font)
        tx = (cw - tw) * 0.5
        ty = line_y + idx * int(base_size * 1.15)
        draw.text((tx + 3, ty + 4), text, font=font, fill=(3, 10, 20, 235))
        draw.text((tx, ty), text, font=font, fill=_color(color_key, 255), stroke_width=3, stroke_fill=(4, 14, 28, 235))

    # Subtle bottom blueprint badge on cover.
    badge_font = _load_font("tech", 28)
    tag = "MÜHENDİSLİK ŞEMASI  •  ADIM ADIM İCAT"
    tw, th = _text_size(draw, tag, badge_font)
    by = 1715 if is_shorts else ch - 95
    draw.rounded_rectangle(
        [(cw - tw) * 0.5 - 24, by - 12, (cw + tw) * 0.5 + 24, by + th + 12],
        radius=10,
        fill=PALETTE["label_bg"],
        outline=_color("cyan", 200),
        width=2,
    )
    draw.text(((cw - tw) * 0.5, by - 2), tag, font=badge_font, fill=_color("cyan", 255))

    canvas.alpha_composite(overlay)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, format="PNG")
    return out_path
