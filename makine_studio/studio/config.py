"""Central configuration for Makine Studio 3D blueprint video pipeline."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = ROOT_DIR.parent
OUTPUT_DIR = Path(os.environ.get("MAKINE_OUTPUT_DIR", str(ROOT_DIR / "output")))


def _find_assets_dir() -> Path:
    """Locate assets directory bundled inside engine or parent workspace."""
    local_assets = ROOT_DIR / "assets"
    if local_assets.is_dir():
        return local_assets
    return WORKSPACE_DIR / "assets"


def _find_blender_exe() -> Path:
    """Locate Blender executable via env var, PATH, or standard OS install roots."""
    env_val = os.environ.get("MAKINE_BLENDER_EXE") or os.environ.get("BLENDER_EXE")
    if env_val:
        p = Path(env_val)
        if p.exists():
            return p

    which_blender = shutil.which("blender")
    if which_blender:
        return Path(which_blender)

    win_base = Path(r"C:\Program Files\Blender Foundation")
    if win_base.is_dir():
        candidates = sorted(
            win_base.glob("Blender */blender.exe"),
            key=lambda p: p.parent.name,
            reverse=True,
        )
        if candidates:
            return candidates[0]

    for posix_cand in (
        Path("/Applications/Blender.app/Contents/MacOS/Blender"),
        Path("/usr/bin/blender"),
    ):
        if posix_cand.exists():
            return posix_cand

    return Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def _find_chatterbox_python() -> Path:
    """Locate optional isolated .venv_tts Python interpreter for GPU Chatterbox TTS."""
    env_py = os.environ.get("MAKINE_CHATTERBOX_PYTHON")
    if env_py:
        return Path(env_py)
    win_py = ROOT_DIR / ".venv_tts" / "Scripts" / "python.exe"
    if win_py.exists():
        return win_py
    posix_py = ROOT_DIR / ".venv_tts" / "bin" / "python"
    if posix_py.exists():
        return posix_py
    return win_py


SHARED_ASSETS_DIR = _find_assets_dir()
BLENDER_EXE = _find_blender_exe()
FFMPEG_EXE = os.environ.get("MAKINE_FFMPEG_EXE", "ffmpeg")
FFPROBE_EXE = os.environ.get("MAKINE_FFPROBE_EXE", "ffprobe")

# Fonts
FONT_BOLD = SHARED_ASSETS_DIR / "fonts" / "Montserrat-Black.ttf"
FONT_SUBTITLE = Path(r"C:\Windows\Fonts\segoeuib.ttf")
FONT_TECH = Path(r"C:\Windows\Fonts\bahnschrift.ttf")

# SFX
SFX_DIR = SHARED_ASSETS_DIR / "sfx"

# Render profiles
PROFILES = {
    "shorts": {
        "canvas_w": 1080,
        "canvas_h": 1920,
        "stage_w": 1080,
        "stage_h": 1040,
        "stage_y": 330,
        "feather_top": 150,
        "feather_bottom": 170,
        "fps": 30,
        "eevee_samples": 16,
    },
    "tiktok": {
        "canvas_w": 1080,
        "canvas_h": 1920,
        "stage_w": 1080,
        "stage_h": 1040,
        "stage_y": 330,
        "feather_top": 150,
        "feather_bottom": 170,
        "fps": 30,
        "eevee_samples": 16,
        "target_min_sec": 61.5,
    },
    "landscape": {
        "canvas_w": 1920,
        "canvas_h": 1080,
        "stage_w": 1920,
        "stage_h": 1080,
        "stage_y": 0,
        "feather_top": 90,
        "feather_bottom": 90,
        "fps": 30,
        "eevee_samples": 16,
    },
}

# Brand Palette (Blueprint aesthetic)
PALETTE = {
    "bg_dark": (8, 24, 44),
    "bg_mid": (13, 36, 66),
    "grid_minor": (21, 55, 94),
    "grid_major": (32, 80, 134),
    "border_line": (60, 118, 178),
    "corner_accent": (96, 178, 232),
    "white": (245, 248, 252),
    "cyan": (66, 206, 245),
    "red": (239, 72, 72),
    "amber": (248, 186, 54),
    "green": (72, 212, 128),
    "label_bg": (10, 26, 46, 215),
    "subtitle_bg": (8, 12, 18, 205),
}

DEFAULT_TTS_PROVIDER = "auto"
DEFAULT_TTS_VOICE = "tr-TR-AhmetNeural"
DEFAULT_TTS_RATE = "+10%"
CHATTERBOX_PYTHON = _find_chatterbox_python()
