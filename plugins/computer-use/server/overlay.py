"""Antigravity / Google-aesthetic live desktop visual overlay for Computer Use.

1. Full-monitor feathered ambient vignette frame (4 non-overlapping edge strips
   with Google Blue -> Cyan -> Indigo -> Violet glow, shifting to calm warm
   champagne-amber when control is handed back to the user).
2. Slim bottom-center frosted Obsidian dock with curved chromatic orbital ring
   emblem, single-line calm status text, non-activating "Kontrolü al" handover
   button, and Google-Blue "Devam et" + dismiss controls when paused.
3. Fluid spring-interpolated AI cursor aura featuring a smooth Gaussian
   atmospheric glow, slender silk comet trail ribbon, soft press-compression,
   whisper-thin click ripples, and cached 4x supersampled vector pointer sprites.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    winmm = ctypes.WinDLL("winmm", use_last_error=True)
except OSError:
    winmm = None

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_HIDE = 0
HWND_TOPMOST = wt.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

WM_NCHITTEST = 0x0084
WM_SETCURSOR = 0x0020
WM_MOUSEACTIVATE = 0x0021
WM_LBUTTONUP = 0x0202
WM_APP_SYNC = 0x8001
WM_APP_QUIT = 0x8002

HTTRANSPARENT = -1
HTCLIENT = 1
MA_NOACTIVATE = 3
IDC_ARROW = 32512
IDC_HAND = 32649

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0
PM_REMOVE = 0x0001
WDA_EXCLUDEFROMCAPTURE = 0x00000011

# -- Google / Antigravity Obsidian & Gemini Reference Palette -----------------
OBSIDIAN_BG = (14, 18, 26)        # #0E121A
OBSIDIAN_ELEV = (34, 41, 54)      # #222936
OBSIDIAN_HOVER = (48, 57, 74)     # #30394A
GOOGLE_BLUE = (26, 115, 232)      # #1A73E8 primary CTA
GEMINI_BLUE = (66, 133, 244)      # #4285F4
ANTIGRAVITY_CYAN = (56, 189, 248) # #38BDF8
GEMINI_INDIGO = (99, 102, 241)    # #6366F1
GEMINI_VIOLET = (168, 85, 247)    # #A855F7
CHAMPAGNE_AMBER = (242, 197, 139) # #F2C58B calm user-control handover halo
GOOGLE_GREEN = (52, 168, 83)      # #34A853
GOOGLE_AMBER = (251, 188, 5)      # #FBBC05
GOOGLE_RED = (234, 67, 53)        # #EA4335


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wt.LONG), ("cy", wt.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER_OV(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO_OV(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER_OV), ("bmiColors", wt.DWORD * 3)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HANDLE),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HANDLE),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", wt.HANDLE),
    ]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]
user32.CreateWindowExW.restype = wt.HWND
user32.DestroyWindow.argtypes = [wt.HWND]
user32.DestroyWindow.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowPos.restype = wt.BOOL
user32.SetWindowDisplayAffinity.argtypes = [wt.HWND, wt.DWORD]
user32.SetWindowDisplayAffinity.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(SIZE),
    wt.HDC, ctypes.POINTER(wt.POINT), wt.COLORREF, ctypes.POINTER(BLENDFUNCTION), wt.DWORD,
]
user32.UpdateLayeredWindow.restype = wt.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.PeekMessageW.restype = wt.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = wt.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.TranslateMessage.restype = wt.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wt.HWND, ctypes.c_size_t]
user32.KillTimer.restype = wt.BOOL
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetCursorPos.restype = wt.BOOL
user32.LoadCursorW.argtypes = [wt.HINSTANCE, wt.LPCWSTR]
user32.LoadCursorW.restype = wt.HANDLE
user32.SetCursor.argtypes = [wt.HANDLE]
user32.SetCursor.restype = wt.HANDLE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteObject.restype = wt.BOOL
gdi32.CreateDIBSection.argtypes = [
    wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD,
]
gdi32.CreateDIBSection.restype = wt.HBITMAP


def _load_ui_font(size: int = 13, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [Path(r"C:\Windows\Fonts\seguisb.ttf"), Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\arial.ttf")]
        if bold
        else [Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\seguisb.ttf"), Path(r"C:\Windows\Fonts\arial.ttf")]
    )
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except Exception:
                continue
    return ImageFont.load_default()


def _lerp_rgb(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        round(c1[0] + (c2[0] - c1[0]) * t),
        round(c1[1] + (c2[1] - c1[1]) * t),
        round(c1[2] + (c2[2] - c1[2]) * t),
    )


def _sample_palette(stops: list[tuple[int, int, int]], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    if len(stops) == 1:
        return stops[0]
    scaled = t * (len(stops) - 1)
    idx = min(len(stops) - 2, int(scaled))
    return _lerp_rgb(stops[idx], stops[idx + 1], scaled - idx)


def _build_spectrum_lut(stops: list[tuple[int, int, int]], width: int = 256, height: int = 1) -> Image.Image:
    lut = Image.new("RGB", (width, 1))
    px = [_sample_palette(stops, i / max(1, width - 1)) for i in range(width)]
    lut.putdata(px)
    return lut if height == 1 else lut.resize((width, height), Image.Resampling.BILINEAR)


@lru_cache(maxsize=12)
def build_vector_pointer_sprite(height_px: int = 24) -> tuple[Image.Image, tuple[int, int]]:
    """Build a 4x supersampled Obsidian + ice-cyan pointer arrow anchored at its hot tip."""
    h_px = max(14, int(height_px))
    s4 = 4
    pad = 8 * s4
    h4 = h_px * s4
    canvas = (h4 + pad * 2, h4 + pad * 2)
    ox, oy = float(pad), float(pad)

    # Clean modern macOS / Figma precision cursor silhouette (normalized to arrow height)
    norm_pts = [
        (0.00, 0.00),
        (0.00, 0.83),
        (0.22, 0.65),
        (0.38, 0.97),
        (0.51, 0.91),
        (0.35, 0.60),
        (0.65, 0.58),
    ]
    poly = [(ox + x * h4, oy + y * h4) for x, y in norm_pts]

    shadow = Image.new("RGBA", canvas, (0, 0, 0, 0))
    sh_pts = [(x + 1.4 * s4, y + 2.2 * s4) for x, y in poly]
    ImageDraw.Draw(shadow, "RGBA").polygon(sh_pts, fill=(0, 0, 0, 125))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=1.8 * s4))

    body = Image.new("RGBA", canvas, (0, 0, 0, 0))
    bd = ImageDraw.Draw(body, "RGBA")
    closed = [*poly, poly[0]]
    # Draw crisp ice-blue rim underneath, then cleanly fill Obsidian interior on top for even edge thickness
    bd.line(closed, fill=(226, 244, 255, 250), width=round(2.4 * s4), joint="curve")
    bd.polygon(poly, fill=(14, 18, 28, 252))
    # Subtle razor specular highlight along outer right bevel
    bd.line([poly[0], poly[6]], fill=(125, 211, 252, 235), width=max(2, round(0.9 * s4)))

    composed = Image.alpha_composite(shadow, body).resize(
        (canvas[0] // s4, canvas[1] // s4), Image.Resampling.BICUBIC
    )
    return composed, (pad // s4, pad // s4)


def _to_premultiplied_bgra(img: Image.Image) -> bytes:
    pm = img.convert("RGBa")
    r, g, b, a = pm.split()
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


def _blit_layered_bgra(
    hwnd: wt.HWND,
    left: int,
    top: int,
    w: int,
    h: int,
    bgra: bytes,
    source_alpha: int = 255,
) -> bool:
    if not hwnd or w <= 0 or h <= 0 or not bgra:
        return False

    screen_dc = user32.GetDC(None)
    if not screen_dc:
        return False
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    if not mem_dc:
        user32.ReleaseDC(None, screen_dc)
        return False

    bmi = BITMAPINFO_OV()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER_OV)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    bits_ptr = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits_ptr), None, 0)
    if not hbmp or not bits_ptr.value:
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
        return False

    old_obj = gdi32.SelectObject(mem_dc, hbmp)
    try:
        ctypes.memmove(bits_ptr.value, bgra, len(bgra))
        dst_pt = wt.POINT(int(left), int(top))
        src_pt = wt.POINT(0, 0)
        sz = SIZE(w, h)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, max(0, min(255, int(source_alpha))), AC_SRC_ALPHA)
        return bool(
            user32.UpdateLayeredWindow(
                hwnd, screen_dc, ctypes.byref(dst_pt), ctypes.byref(sz),
                mem_dc, ctypes.byref(src_pt), 0, ctypes.byref(blend), ULW_ALPHA,
            )
        )
    finally:
        if old_obj:
            gdi32.SelectObject(mem_dc, old_obj)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)


def _blit_layered_rgba(hwnd: wt.HWND, left: int, top: int, img: Image.Image, source_alpha: int = 255) -> bool:
    return _blit_layered_bgra(hwnd, left, top, img.width, img.height, _to_premultiplied_bgra(img), source_alpha)


def _catmull_rom_subdivide(points: list[tuple[float, float, float]], subdivisions: int = 3) -> list[tuple[float, float, float]]:
    """Interpolate pointer samples into a silky spline with preserved ages."""
    n = len(points)
    if n < 3:
        return points
    out: list[tuple[float, float, float]] = []
    for i in range(n - 1):
        p0 = points[max(0, i - 1)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(n - 1, i + 2)]
        for s in range(subdivisions):
            t = s / subdivisions
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                (2.0 * p1[0])
                + (-p0[0] + p2[0]) * t
                + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                (2.0 * p1[1])
                + (-p0[1] + p2[1]) * t
                + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
            )
            age = p1[2] + (p2[2] - p1[2]) * t
            out.append((x, y, age))
    out.append(points[-1])
    return out


@dataclass
class _RippleEffect:
    x: int
    y: int
    color: tuple[int, int, int]
    kind: str  # "click" | "double" | "right" | "middle" | "scroll"
    direction: str
    started_at: float
    duration_sec: float = 0.38


@dataclass
class _VignetteStripData:
    name: str
    rel_x: int
    rel_y: int
    width: int
    height: int
    bgra: bytes
    image: Image.Image


class DesktopOverlay:
    """Thread-safe Antigravity/Google glass HUD, feathered vignette, and fluid pointer."""

    IDLE_HIDE_SEC = 25.0
    STOP_HIDE_SEC = 18.0
    TRAIL_LIFETIME_SEC = 0.24
    VIGNETTE_THICK = 76

    # Bottom-center slim Obsidian capsule canvas (with subtle outer aura margin)
    PILL_W = 420
    PILL_H = 82
    _CAPSULE_RECT = (24, 18, 396, 64)
    _BTN_TAKEOVER_RECT = (292, 24, 386, 58)
    _BTN_RESUME_RECT = (258, 24, 350, 58)
    _BTN_DISMISS_RECT = (356, 27, 384, 55)

    CURSOR_SZ = 240
    RIPPLE_SZ = 144

    def __init__(
        self,
        enabled: bool = True,
        on_take_control: Callable[[], None] | None = None,
        on_resume_control: Callable[[], None] | None = None,
    ) -> None:
        env_flag = os.environ.get("COMPUTER_USE_OVERLAY", "1").strip().lower()
        self.enabled = enabled and env_flag not in {"0", "false", "no", "off"}
        self.on_take_control = on_take_control
        self.on_resume_control = on_resume_control

        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._stop_requested = False

        self._status_hwnd: wt.HWND | None = None
        self._cursor_hwnd: wt.HWND | None = None
        self._ripple_hwnd: wt.HWND | None = None
        self._vig_hwnds: dict[str, wt.HWND | None] = {k: None for k in ("top", "bottom", "left", "right")}
        self._wndproc_ref: WNDPROC | None = None

        self._state: str = "idle"  # "working" | "thinking" | "stopped" | "idle"
        self._label: str = "Antigravity hazır"
        self._last_activity: float = 0.0
        self._stop_until: float = 0.0
        self._target_cursor: tuple[int, int] = (0, 0)
        self._has_cursor_pos: bool = False
        self._vis_x: float = 0.0
        self._vis_y: float = 0.0
        self._has_vis_pos: bool = False
        self._last_tick_ts: float = time.monotonic()
        self._press_down: bool = False
        self._press_anim: float = 0.0
        self._trail: deque[tuple[float, float, float]] = deque(maxlen=30)

        self._display_work_rect: tuple[int, int, int, int] = (0, 0, 1920, 1040)
        self._display_bounds: tuple[int, int, int, int] = (0, 0, 1920, 1080)
        self._pill_win_pos: tuple[int, int] = (0, 0)
        self._hover_target: str = ""  # "" | "takeover" | "resume" | "dismiss"
        self._ripple: _RippleEffect | None = None

        self._pill_visible = False
        self._cursor_visible = False
        self._ripple_visible = False
        self._vig_visible = False
        self._timer_active = False
        self._hi_res_active = False
        self._last_vig_key: tuple[int, int, str] | None = None
        self._last_vig_alpha: int = -1

        self._font_label = _load_ui_font(13, bold=True)
        self._font_btn = _load_ui_font(12, bold=True)
        self._pill_base_cache: dict[str, Image.Image] = {}
        self._vig_cache: dict[tuple[int, int, str], list[_VignetteStripData]] = {}
        self._aura_cache: dict[str, Image.Image] = {}
        self._ring_sprite_cache: dict[str, Image.Image] = {}

        if self.enabled:
            self._start_thread()

    def _start_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_requested = False
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._ui_loop,
            name="AntigravityOverlayThread",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=1.2)

    def _wake_ui(self) -> None:
        hwnd = self._status_hwnd
        if hwnd:
            user32.PostMessageW(hwnd, WM_APP_SYNC, 0, 0)

    def _set_hi_res_timer(self, active: bool) -> None:
        if winmm is None or active == self._hi_res_active:
            return
        try:
            if active:
                winmm.timeBeginPeriod(1)
            else:
                winmm.timeEndPeriod(1)
            self._hi_res_active = active
        except Exception:
            pass

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = bool(enabled)
            if not self.enabled:
                self._state = "idle"
                self._ripple = None
        if self.enabled and self._thread is None:
            self._start_thread()
        self._wake_ui()

    def set_display_rect(
        self,
        left: int,
        top: int,
        width: int,
        height: int,
        bounds: tuple[int, int, int, int] | None = None,
    ) -> None:
        with self._lock:
            wl, wt_, ww, wh = int(left), int(top), max(320, int(width)), max(200, int(height))
            self._display_work_rect = (wl, wt_, ww, wh)
            if bounds is not None:
                self._display_bounds = (
                    int(bounds[0]),
                    int(bounds[1]),
                    max(320, int(bounds[2])),
                    max(240, int(bounds[3])),
                )
            else:
                self._display_bounds = (wl, wt_, ww, wh)
            self._last_vig_key = None

    def notify_cursor(self, px: int, py: int, label: str | None = None) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        with self._lock:
            tx, ty = int(px), int(py)
            self._target_cursor = (tx, ty)
            self._has_cursor_pos = True
            if not self._has_vis_pos:
                self._vis_x, self._vis_y = float(tx), float(ty)
                self._has_vis_pos = True
                self._trail.append((float(tx), float(ty), now))
            self._last_activity = now
            if self._state == "idle":
                self._state = "working"
            if label is not None and label != self._label:
                self._label = label
        self._wake_ui()

    def notify_press(self, pressed: bool, px: int | None = None, py: int | None = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._press_down = bool(pressed)
            if px is not None and py is not None:
                self._target_cursor = (int(px), int(py))
                self._has_cursor_pos = True
            self._last_activity = time.monotonic()
        self._wake_ui()

    def notify_action(
        self,
        label: str,
        state: str = "working",
        px: int | None = None,
        py: int | None = None,
    ) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        with self._lock:
            self._state = state
            self._label = label
            self._last_activity = now
            if px is not None and py is not None:
                tx, ty = int(px), int(py)
                self._target_cursor = (tx, ty)
                self._has_cursor_pos = True
                if not self._has_vis_pos:
                    self._vis_x, self._vis_y = float(tx), float(ty)
                    self._has_vis_pos = True
                    self._trail.append((float(tx), float(ty), now))
        self._wake_ui()

    def notify_click(self, px: int, py: int, button: str = "left", count: int = 1) -> None:
        if not self.enabled:
            return
        color = ANTIGRAVITY_CYAN
        kind = "click"
        if button == "right":
            color = GEMINI_VIOLET
            kind = "right"
        elif button == "middle":
            color = GOOGLE_GREEN
            kind = "middle"
        elif count >= 2:
            color = GEMINI_BLUE
            kind = "double"

        now = time.monotonic()
        with self._lock:
            tx, ty = int(px), int(py)
            self._target_cursor = (tx, ty)
            self._vis_x, self._vis_y = float(tx), float(ty)
            self._has_cursor_pos = True
            self._has_vis_pos = True
            self._last_activity = now
            self._ripple = _RippleEffect(
                x=tx,
                y=ty,
                color=color,
                kind=kind,
                direction="",
                started_at=now,
                duration_sec=0.38 if count < 2 else 0.48,
            )
        self._wake_ui()

    def notify_scroll(self, px: int, py: int, direction: str) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        with self._lock:
            tx, ty = int(px), int(py)
            self._target_cursor = (tx, ty)
            self._has_cursor_pos = True
            self._last_activity = now
            self._ripple = _RippleEffect(
                x=tx,
                y=ty,
                color=GOOGLE_GREEN,
                kind="scroll",
                direction=direction,
                started_at=now,
                duration_sec=0.34,
            )
        self._wake_ui()

    def notify_thinking(self, label: str = "Ekran inceleniyor...") -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._state == "stopped":
                return
            self._state = "thinking"
            self._label = label
            self._last_activity = time.monotonic()
        self._wake_ui()

    def notify_stopped(self, reason: str = "Kontrol devralındı") -> None:
        if not self.enabled:
            return
        with self._lock:
            now = time.monotonic()
            self._state = "stopped"
            self._label = reason[:48]
            self._last_activity = now
            self._stop_until = now + self.STOP_HIDE_SEC
            self._press_down = False
            self._ripple = None
            self._last_vig_key = None
        self._wake_ui()

    def dismiss(self) -> None:
        with self._lock:
            self._state = "idle"
            self._ripple = None
            self._hover_target = ""
        self._wake_ui()

    def close(self) -> None:
        self._stop_requested = True
        self._set_hi_res_timer(False)
        if self._status_hwnd:
            user32.PostMessageW(self._status_hwnd, WM_APP_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.2)

    # -- Reference-Faithful Visual Rendering ------------------------------

    @staticmethod
    def _state_stops(state: str) -> list[tuple[int, int, int]]:
        if state == "stopped":
            return [CHAMPAGNE_AMBER, (226, 174, 114), CHAMPAGNE_AMBER]
        if state == "thinking":
            return [GEMINI_BLUE, ANTIGRAVITY_CYAN, GOOGLE_AMBER, GEMINI_INDIGO, GEMINI_BLUE]
        return [GEMINI_BLUE, ANTIGRAVITY_CYAN, GEMINI_INDIGO, GEMINI_VIOLET, GEMINI_BLUE]

    def _build_vignette_strips(self, mon_w: int, mon_h: int, state: str) -> list[_VignetteStripData]:
        """Build 4 feathered vignette edge strips with gentle corner glow and zero inner seam."""
        key = (mon_w, mon_h, state)
        cached = self._vig_cache.get(key)
        if cached is not None:
            return cached

        t_edge = min(self.VIGNETTE_THICK, max(28, min(mon_w, mon_h) // 6))
        scale = 4
        sw = max(240, mon_w // scale)
        sh = max(135, mon_h // scale)

        stops = self._state_stops(state)
        spectrum = _build_spectrum_lut(stops, width=sw, height=sh)

        # Feathered perimeter distance mask decaying smoothly to 0 well inside t_edge
        mask_small = Image.new("L", (sw, sh), 0)
        md = ImageDraw.Draw(mask_small)
        max_depth = max(7, round((t_edge * 0.64) / scale))
        for d in range(max_depth):
            t = d / max(1, max_depth - 1)
            val = round(142 * ((1.0 - t) ** 2.15))
            if val <= 1:
                break
            md.rectangle((d, d, sw - 1 - d, sh - 1 - d), outline=val, width=1)
        # Subtle corner radiance boost matching reference perimeter aura
        corner_r = max(8, max_depth)
        for cx_c, cy_c in ((0, 0), (sw - 1, 0), (0, sh - 1), (sw - 1, sh - 1)):
            md.ellipse((cx_c - corner_r, cy_c - corner_r, cx_c + corner_r, cy_c + corner_r), fill=110)
        # Clear central interior explicitly so center stays 100% untouched
        inner_pad = max_depth + 2
        if sw > inner_pad * 2 and sh > inner_pad * 2:
            md.rectangle((inner_pad, inner_pad, sw - inner_pad, sh - inner_pad), fill=0)
        mask_small = mask_small.filter(ImageFilter.GaussianBlur(radius=2.8))

        full_rgb = spectrum.resize((mon_w, mon_h), Image.Resampling.BILINEAR)
        full_alpha = mask_small.resize((mon_w, mon_h), Image.Resampling.BICUBIC)
        full_vignette = full_rgb.convert("RGBA")
        full_vignette.putalpha(full_alpha)

        # Razor-sharp 1.5px luminous glass rim along outer screen boundary
        rim_draw = ImageDraw.Draw(full_vignette, "RGBA")
        rim_draw.line((0, 0, mon_w - 1, 0), fill=(*stops[1 % len(stops)], 195), width=2)
        rim_draw.line((0, mon_h - 1, mon_w - 1, mon_h - 1), fill=(*stops[0], 195), width=2)
        rim_draw.line((0, 0, 0, mon_h - 1), fill=(*stops[0], 195), width=2)
        rim_draw.line((mon_w - 1, 0, mon_w - 1, mon_h - 1), fill=(*stops[-2], 195), width=2)

        boxes = [
            ("top", 0, 0, mon_w, t_edge),
            ("bottom", 0, mon_h - t_edge, mon_w, mon_h),
            ("left", 0, t_edge, t_edge, mon_h - t_edge),
            ("right", mon_w - t_edge, t_edge, mon_w, mon_h - t_edge),
        ]
        strips: list[_VignetteStripData] = []
        for name, x1, y1, x2, y2 in boxes:
            if x2 <= x1 or y2 <= y1:
                continue
            crop = full_vignette.crop((x1, y1, x2, y2))
            strips.append(
                _VignetteStripData(
                    name=name,
                    rel_x=x1,
                    rel_y=y1,
                    width=x2 - x1,
                    height=y2 - y1,
                    bgra=_to_premultiplied_bgra(crop),
                    image=crop,
                )
            )
        self._vig_cache[key] = strips
        return strips

    def _get_pill_base(self, state: str) -> Image.Image:
        """Render cached frosted Obsidian glass dock backdrop matching ref_ui_components."""
        cached = self._pill_base_cache.get(state)
        if cached is not None:
            return cached

        w, h = self.PILL_W, self.PILL_H
        s2 = 2
        bw, bh = w * s2, h * s2
        cx1, cy1, cx2, cy2 = (v * s2 for v in self._CAPSULE_RECT)
        rad = (cy2 - cy1) // 2
        stops = self._state_stops(state)

        # 1. Outer ambient chromatic aura glow around capsule border (ref_ui_components style)
        halo_rgb = _build_spectrum_lut(stops, width=bw, height=bh).convert("RGBA")
        halo_mask = Image.new("L", (bw, bh), 0)
        halo_strength = 128 if state != "stopped" else 108
        ImageDraw.Draw(halo_mask).rounded_rectangle(
            (cx1 - 3, cy1 - 3, cx2 + 3, cy2 + 3),
            radius=rad + 3,
            outline=halo_strength,
            width=14,
        )
        halo_mask = halo_mask.filter(ImageFilter.GaussianBlur(radius=14))
        halo_rgb.putalpha(halo_mask)

        # 2. Grounding soft dark drop shadow below capsule
        shadow = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((cx1, cy1 + 6, cx2, cy2 + 12), radius=rad + 2, fill=(0, 0, 0, 140))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))

        # 3. Capsule alpha clip mask for interior glass layers
        clip_mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(clip_mask).rounded_rectangle((cx1, cy1, cx2, cy2), radius=rad, fill=255)

        body = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        ImageDraw.Draw(body).rounded_rectangle((cx1, cy1, cx2, cy2), radius=rad, fill=(*OBSIDIAN_BG, 236))

        # Subtle interior chromatic glass wash + smooth vertical top sheen (no hard geometric seams)
        wash = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        wd = ImageDraw.Draw(wash)
        if state == "stopped":
            wd.ellipse((cx1 - 30, cy1 - 40, cx1 + 260, cy2 + 40), fill=(*CHAMPAGNE_AMBER, 16))
        else:
            left_c = ANTIGRAVITY_CYAN if state == "working" else GOOGLE_AMBER
            wd.ellipse((cx1 - 40, cy1 - 50, cx1 + 260, cy2 + 50), fill=(*left_c, 32))
            wd.ellipse((cx2 - 280, cy1 - 30, cx2 + 40, cy2 + 50), fill=(*GEMINI_VIOLET, 26))
        wash = wash.filter(ImageFilter.GaussianBlur(radius=28))

        sheen_alpha = Image.new("L", (bw, bh), 0)
        v_grad = Image.linear_gradient("L").resize((bw, max(1, (cy2 - cy1) // 2 + 1)))
        # linear_gradient goes 0 top -> 255 bottom; invert and soften for a delicate top-edge glass sheen
        v_band = v_grad.point(lambda p: int(((255 - p) / 255.0) ** 1.6 * 16))
        sheen_alpha.paste(v_band, (0, cy1))
        spec = Image.new("RGBA", (bw, bh), (255, 255, 255, 255))
        spec.putalpha(sheen_alpha)

        interior = Image.alpha_composite(wash, spec)
        interior.putalpha(ImageChops.multiply(interior.split()[3], clip_mask))
        body = Image.alpha_composite(body, interior)

        # 4. Crisp outer chromatic edge rim + contour-hugging inner top-lip hairline
        rim_grad = _build_spectrum_lut(stops, width=bw, height=bh).convert("RGBA")
        rim_mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(rim_mask).rounded_rectangle((cx1, cy1, cx2, cy2), radius=rad, outline=220, width=3)
        rim_grad.putalpha(rim_mask)

        inner_glint = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        ImageDraw.Draw(inner_glint).rounded_rectangle(
            (cx1 + 2, cy1 + 2, cx2 - 2, cy2 - 2),
            radius=max(1, rad - 2),
            outline=(255, 255, 255, 24),
            width=2,
        )

        composed = Image.alpha_composite(shadow, halo_rgb)
        composed = Image.alpha_composite(composed, body)
        composed = Image.alpha_composite(composed, rim_grad)
        composed = Image.alpha_composite(composed, inner_glint)
        out = composed.resize((w, h), Image.Resampling.BICUBIC)
        self._pill_base_cache[state] = out
        return out

    def _get_orbital_ring_sprite(self, state: str) -> Image.Image:
        """Build 4x supersampled smooth Gemini chromatic orbital arc sprite (28x28)."""
        cached = self._ring_sprite_cache.get(state)
        if cached is not None:
            return cached

        sz = 28
        s4 = sz * 4
        cx = cy = s4 // 2
        if state == "stopped":
            stops = [(253, 230, 178), CHAMPAGNE_AMBER, (226, 174, 114)]
        elif state == "thinking":
            stops = [GOOGLE_AMBER, ANTIGRAVITY_CYAN, GEMINI_INDIGO]
        else:
            stops = [ANTIGRAVITY_CYAN, GEMINI_BLUE, GEMINI_VIOLET]

        grad = _build_spectrum_lut(stops, width=s4, height=s4).convert("RGBA")
        mask = Image.new("L", (s4, s4), 0)
        md = ImageDraw.Draw(mask)
        r = 38
        stroke_w = 11
        # Open sweeping 265-degree arc with smooth rounded endcaps (no flat cuts)
        if state == "stopped":
            md.ellipse((cx - r, cy - r, cx + r, cy + r), outline=210, width=9)
        else:
            start_deg, end_deg = 25, 290
            md.arc((cx - r, cy - r, cx + r, cy + r), start=start_deg, end=end_deg, fill=245, width=stroke_w)
            cap_r = stroke_w * 0.48
            mid_r = r - stroke_w * 0.5
            for deg in (start_deg, end_deg):
                rad_a = math.radians(deg)
                kx = cx + mid_r * math.cos(rad_a)
                ky = cy + mid_r * math.sin(rad_a)
                md.ellipse((kx - cap_r, ky - cap_r, kx + cap_r, ky + cap_r), fill=245)

        glow_mask = mask.filter(ImageFilter.GaussianBlur(radius=6))
        glow_layer = grad.copy()
        glow_layer.putalpha(glow_mask.point(lambda p: int(p * 0.55)))

        crisp = grad.copy()
        crisp.putalpha(mask)
        combined = Image.alpha_composite(glow_layer, crisp).resize((sz, sz), Image.Resampling.BICUBIC)
        self._ring_sprite_cache[state] = combined
        return combined

    def _hit_test_pill_local(self, lx: int, ly: int, state: str) -> str:
        if state == "stopped":
            rx1, ry1, rx2, ry2 = self._BTN_RESUME_RECT
            if rx1 <= lx <= rx2 and ry1 <= ly <= ry2:
                return "resume"
            dx1, dy1, dx2, dy2 = self._BTN_DISMISS_RECT
            if dx1 <= lx <= dx2 and dy1 <= ly <= dy2:
                return "dismiss"
        elif state in {"working", "thinking"}:
            tx1, ty1, tx2, ty2 = self._BTN_TAKEOVER_RECT
            if tx1 <= lx <= tx2 and ty1 <= ly <= ty2:
                return "takeover"
        return ""

    def _render_pill(
        self,
        state: str,
        label: str,
        phase: float,
        hover_target: str = "",
    ) -> Image.Image:
        img = self._get_pill_base(state).copy()
        draw = ImageDraw.Draw(img, "RGBA")
        pulse = 0.5 + 0.5 * math.sin(phase * 3.6)

        # Left minimal Gemini orbital halo + breathing glowing core dot
        ring = self._get_orbital_ring_sprite(state)
        if state != "stopped":
            rot_deg = -((phase * (115.0 if state == "working" else 165.0)) % 360.0)
            ring = ring.rotate(rot_deg, resample=Image.Resampling.BICUBIC)
        orb_cx, orb_cy = 44, 41
        img.alpha_composite(ring, (orb_cx - ring.width // 2, orb_cy - ring.height // 2))
        core_rgb = CHAMPAGNE_AMBER if state == "stopped" else (_lerp_rgb(ANTIGRAVITY_CYAN, GEMINI_BLUE, pulse) if state == "working" else GOOGLE_AMBER)
        core_r = 3.2 + 0.8 * pulse
        draw.ellipse((orb_cx - core_r - 2, orb_cy - core_r - 2, orb_cx + core_r + 2, orb_cy + core_r + 2), fill=(*core_rgb, 80))
        draw.ellipse((orb_cx - core_r, orb_cy - core_r, orb_cx + core_r, orb_cy + core_r), fill=(248, 250, 252, 240))

        # Normalize text: no ALL-CAPS shouty headers, no bullet separators
        clean_label = label.replace("•", " ").strip()
        clean_label = " ".join(clean_label.split()) or "Antigravity hazır"

        if state == "stopped":
            display_text = "Kontrol sizde"
            rx1, ry1, rx2, ry2 = self._BTN_RESUME_RECT
            btn_fill = (66, 133, 244, 255) if hover_target == "resume" else (*GOOGLE_BLUE, 250)
            draw.rounded_rectangle((rx1, ry1, rx2, ry2), radius=17, fill=btn_fill, outline=(147, 197, 253, 110), width=1)
            r_txt = "Devam et"
            rb = draw.textbbox((0, 0), r_txt, font=self._font_btn)
            rx_text = rx1 + (rx2 - rx1 - (rb[2] - rb[0])) // 2 - rb[0]
            ry_text = ry1 + (ry2 - ry1 - (rb[3] - rb[1])) // 2 - rb[1]
            draw.text((rx_text, ry_text), r_txt, font=self._font_btn, fill=(255, 255, 255, 255))

            dx1, dy1, dx2, dy2 = self._BTN_DISMISS_RECT
            if hover_target == "dismiss":
                draw.ellipse((dx1, dy1, dx2, dy2), fill=(*OBSIDIAN_HOVER, 225))
            cx_d, cy_d = (dx1 + dx2) // 2, (dy1 + dy2) // 2
            x_col = (248, 250, 252, 245) if hover_target == "dismiss" else (148, 163, 184, 220)
            draw.line((cx_d - 4, cy_d - 4, cx_d + 4, cy_d + 4), fill=x_col, width=2)
            draw.line((cx_d - 4, cy_d + 4, cx_d + 4, cy_d - 4), fill=x_col, width=2)
            content_right = rx1 - 12
        else:
            display_text = clean_label
            tx1, ty1, tx2, ty2 = self._BTN_TAKEOVER_RECT
            if hover_target == "takeover":
                t_fill = (*GOOGLE_RED, 238)
                t_outline = (252, 165, 165, 210)
                t_fg = (255, 255, 255, 255)
            else:
                t_fill = (*OBSIDIAN_ELEV, 235)
                t_outline = (255, 255, 255, 40)
                t_fg = (241, 245, 249, 248)
            draw.rounded_rectangle((tx1, ty1, tx2, ty2), radius=17, fill=t_fill, outline=t_outline, width=1)
            t_txt = "Kontrolü al"
            tb = draw.textbbox((0, 0), t_txt, font=self._font_btn)
            tx_text = tx1 + (tx2 - tx1 - (tb[2] - tb[0])) // 2 - tb[0]
            ty_text = ty1 + (ty2 - ty1 - (tb[3] - tb[1])) // 2 - tb[1]
            draw.text((tx_text, ty_text), t_txt, font=self._font_btn, fill=t_fg)
            content_right = tx1 - 12

        text_x = 68
        max_label_px = max(60, content_right - text_x)
        short_label = display_text
        while short_label:
            lb = draw.textbbox((0, 0), short_label, font=self._font_label)
            if (lb[2] - lb[0]) <= max_label_px or len(short_label) <= 4:
                break
            short_label = f"{short_label[:-4]}..."
        lb = draw.textbbox((0, 0), short_label, font=self._font_label)
        cy1, cy2 = self._CAPSULE_RECT[1], self._CAPSULE_RECT[3]
        ly_text = cy1 + (cy2 - cy1 - (lb[3] - lb[1])) // 2 - lb[1]
        draw.text((text_x - lb[0], ly_text), short_label, font=self._font_label, fill=(241, 245, 249, 252))
        return img

    def _get_cursor_aura(self, state: str) -> Image.Image:
        """Build a pure smooth Gaussian atmospheric spotlight under the cursor (zero wireframe rings)."""
        cached = self._aura_cache.get(state)
        if cached is not None:
            return cached
        sz = self.CURSOR_SZ
        half = sz // 2
        cx = cy = half // 2
        aura = Image.new("RGBA", (half, half), (0, 0, 0, 0))
        ad = ImageDraw.Draw(aura, "RGBA")
        c_outer = GEMINI_BLUE if state != "thinking" else GEMINI_INDIGO
        c_inner = ANTIGRAVITY_CYAN if state != "thinking" else GOOGLE_AMBER

        # Continuous radial falloff discs blurred together -> buttery smooth mist with zero edges
        for step in range(14, 0, -1):
            t = step / 14.0
            r = round(3.0 + 22.0 * t)
            col = _lerp_rgb(c_inner, c_outer, t ** 0.85)
            alpha = max(1, round(24 * ((1.0 - t) ** 1.45)))
            ad.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*col, alpha))
        ad.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(240, 249, 255, 115))
        aura = aura.filter(ImageFilter.GaussianBlur(radius=6.5))
        out = aura.resize((sz, sz), Image.Resampling.BICUBIC)
        self._aura_cache[state] = out
        return out

    def _render_cursor_halo(
        self,
        state: str,
        phase: float,
        cur_x: float = 0.0,
        cur_y: float = 0.0,
        trail: list[tuple[float, float, float]] | None = None,
        press_amount: float = 0.0,
    ) -> Image.Image:
        sz = self.CURSOR_SZ
        cx = cy = sz // 2

        base_aura = self._get_cursor_aura(state)
        if press_amount > 0.04:
            scale = max(0.75, 1.0 - 0.20 * press_amount)
            nsz = max(32, round(sz * scale))
            shrunk = base_aura.resize((nsz, nsz), Image.Resampling.BILINEAR)
            img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
            off = (sz - nsz) // 2
            img.paste(shrunk, (off, off))
        else:
            img = base_aura.copy()

        # Subtle ethereal silk comet filament trailing smoothly behind cursor motion
        if trail and len(trail) >= 2:
            raw_pts = [(cx + (tx - cur_x), cy + (ty - cur_y), age) for tx, ty, age in trail]
            clamped = [
                (px, py, age)
                for px, py, age in raw_pts
                if 10 <= px <= sz - 10 and 10 <= py <= sz - 10 and age <= self.TRAIL_LIFETIME_SEC
            ]
            if len(clamped) >= 2:
                span = sum(
                    math.hypot(clamped[i + 1][0] - clamped[i][0], clamped[i + 1][1] - clamped[i][1])
                    for i in range(len(clamped) - 1)
                )
                if span >= 5.0:
                    smooth = _catmull_rom_subdivide(clamped, subdivisions=4)
                    n_seg = max(1, len(smooth) - 1)

                    bloom = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
                    bd = ImageDraw.Draw(bloom, "RGBA")
                    for idx in range(n_seg):
                        x0, y0, a0 = smooth[idx]
                        x1, y1, a1 = smooth[idx + 1]
                        age_fade = max(0.0, 1.0 - (0.5 * (a0 + a1) / self.TRAIL_LIFETIME_SEC))
                        pos_t = idx / n_seg
                        taper = (pos_t ** 0.72) * age_fade
                        if taper <= 0.02:
                            continue
                        rgb = _sample_palette([GEMINI_VIOLET, GEMINI_BLUE, ANTIGRAVITY_CYAN], pos_t)
                        bw = max(1, round(11.0 * (taper ** 0.8)))
                        bd.line((x0, y0, x1, y1), fill=(*rgb, int(145 * taper)), width=bw)
                    bloom = bloom.filter(ImageFilter.GaussianBlur(radius=4.2))
                    img = Image.alpha_composite(img, bloom)

                    core2 = Image.new("RGBA", (sz * 2, sz * 2), (0, 0, 0, 0))
                    cd = ImageDraw.Draw(core2, "RGBA")
                    for idx in range(n_seg):
                        x0, y0, a0 = smooth[idx]
                        x1, y1, a1 = smooth[idx + 1]
                        age_fade = max(0.0, 1.0 - (0.5 * (a0 + a1) / self.TRAIL_LIFETIME_SEC))
                        pos_t = idx / n_seg
                        taper = (pos_t ** 0.78) * age_fade
                        if taper <= 0.03:
                            continue
                        rgb = _sample_palette([GEMINI_VIOLET, GEMINI_BLUE, ANTIGRAVITY_CYAN, (240, 249, 255)], pos_t)
                        cw = max(1, round(6.2 * (taper ** 0.95)))
                        cd.line((x0 * 2, y0 * 2, x1 * 2, y1 * 2), fill=(*rgb, int(225 * taper)), width=cw)
                    img = Image.alpha_composite(img, core2.resize((sz, sz), Image.Resampling.BICUBIC))

        return img

    def _render_ripple(self, eff: _RippleEffect, progress: float) -> Image.Image:
        sz = self.RIPPLE_SZ
        s2 = sz * 2
        cx = cy = s2 // 2
        img2 = Image.new("RGBA", (s2, s2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img2, "RGBA")

        ease = 1.0 - (1.0 - progress) ** 4
        fade = max(0.0, (1.0 - progress) ** 1.35)
        alpha = int(210 * fade)

        if eff.kind == "scroll":
            r = round(20 + 48 * ease)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*eff.color, int(22 * fade)), outline=(*eff.color, alpha), width=3)
            off = round(18 * ease)
            if eff.direction == "up":
                pts = [(cx - 14, cy - off + 8), (cx, cy - off - 10), (cx + 14, cy - off + 8)]
            elif eff.direction == "down":
                pts = [(cx - 14, cy + off - 8), (cx, cy + off + 10), (cx + 14, cy + off - 8)]
            elif eff.direction == "left":
                pts = [(cx - off + 8, cy - 14), (cx - off - 10, cy), (cx - off + 8, cy + 14)]
            else:
                pts = [(cx + off - 8, cy - 14), (cx + off + 10, cy), (cx + off - 8, cy + 14)]
            draw.line(pts, fill=(248, 250, 252, alpha), width=4, joint="curve")
            return img2.resize((sz, sz), Image.Resampling.BICUBIC)

        r1 = round(14 + 78 * ease)
        ring_c = _lerp_rgb(eff.color, GEMINI_VIOLET, progress * 0.55)
        draw.ellipse((cx - r1, cy - r1, cx + r1, cy + r1), fill=(*ring_c, int(20 * fade)), outline=(*ring_c, int(195 * fade)), width=3)
        return img2.resize((sz, sz), Image.Resampling.BICUBIC)

    def render_preview_composite(
        self,
        width: int = 1280,
        height: int = 720,
        state: str = "working",
        label: str = "Hesap Makinesi açılıyor",
        cursor_pos: tuple[int, int] = (520, 360),
        show_click: bool = False,
    ) -> Image.Image:
        """Render a synthetic preview composite matching live vignette + dock + fluid cursor."""
        bg = Image.new("RGBA", (width, height), (14, 17, 24, 255))
        bd = ImageDraw.Draw(bg, "RGBA")
        bd.rounded_rectangle((110, 80, width - 110, height - 118), radius=18, fill=(22, 26, 36, 255), outline=(42, 49, 64, 255), width=2)
        bd.text((150, 118), "Antigravity Computer Use Preview", font=self._font_label, fill=(203, 213, 225, 225))

        for strip in self._build_vignette_strips(width, height, state):
            bg.alpha_composite(strip.image, (strip.rel_x, strip.rel_y))

        trail = [
            (cursor_pos[0] + 92.0, cursor_pos[1] - 18.0, 0.21),
            (cursor_pos[0] + 68.0, cursor_pos[1] + 10.0, 0.15),
            (cursor_pos[0] + 40.0, cursor_pos[1] + 6.0, 0.09),
            (cursor_pos[0] + 16.0, cursor_pos[1] - 4.0, 0.04),
            (float(cursor_pos[0]), float(cursor_pos[1]), 0.0),
        ]
        if show_click:
            ripple = self._render_ripple(_RippleEffect(cursor_pos[0], cursor_pos[1], ANTIGRAVITY_CYAN, "click", "", 0.0), 0.34)
            bg.alpha_composite(ripple, (cursor_pos[0] - self.RIPPLE_SZ // 2, cursor_pos[1] - self.RIPPLE_SZ // 2))

        cur = self._render_cursor_halo(
            state, 0.4, cur_x=cursor_pos[0], cur_y=cursor_pos[1], trail=trail, press_amount=0.15 if show_click else 0.0,
        )
        bg.alpha_composite(cur, (cursor_pos[0] - self.CURSOR_SZ // 2, cursor_pos[1] - self.CURSOR_SZ // 2))

        ptr_img, (hx, hy) = build_vector_pointer_sprite(24)
        bg.alpha_composite(ptr_img, (cursor_pos[0] - hx, cursor_pos[1] - hy))

        pill = self._render_pill(state, label, 0.4, hover_target="")
        bg.alpha_composite(pill, ((width - self.PILL_W) // 2, height - self.PILL_H - 4))
        return bg.convert("RGB")

    # -- Win32 Window Lifecycle & Event Handling --------------------------

    def _create_overlay_hwnd(self, cls_name: str, hinst: int, w: int, h: int, transparent: bool) -> wt.HWND | None:
        ex_style = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        if transparent:
            ex_style |= WS_EX_TRANSPARENT
        hwnd = user32.CreateWindowExW(
            ex_style, cls_name, cls_name, WS_POPUP,
            0, 0, w, h, None, None, hinst, None,
        )
        if hwnd:
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        return hwnd

    def _show_topmost(self, hwnd: wt.HWND) -> None:
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _hide_hwnd(self, hwnd: wt.HWND | None) -> None:
        if hwnd:
            user32.ShowWindow(hwnd, SW_HIDE)

    def _dispatch_pill_click(self, action_id: str) -> None:
        if action_id == "takeover":
            cb = self.on_take_control
            self.notify_stopped("Kontrol devralındı")
            if cb:
                threading.Thread(target=cb, daemon=True).start()
        elif action_id == "resume":
            cb = self.on_resume_control
            self.notify_thinking("Hazır")
            if cb:
                threading.Thread(target=cb, daemon=True).start()
        elif action_id == "dismiss":
            self.dismiss()

    def _ui_loop(self) -> None:
        cls_name = f"AntigravityDesktopOverlay_{os.getpid()}"
        hinst = kernel32.GetModuleHandleW(None)
        hand_cursor = user32.LoadCursorW(None, ctypes.cast(IDC_HAND, wt.LPCWSTR))
        arrow_cursor = user32.LoadCursorW(None, ctypes.cast(IDC_ARROW, wt.LPCWSTR))

        def _wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if hwnd != self._status_hwnd:
                if msg == WM_NCHITTEST:
                    return HTTRANSPARENT
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            if msg == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE

            if msg == WM_NCHITTEST:
                sx = ctypes.c_short(lparam & 0xFFFF).value
                sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                with self._lock:
                    px, py = self._pill_win_pos
                    state = self._state
                lx, ly = sx - px, sy - py
                cx1, cy1, cx2, cy2 = self._CAPSULE_RECT
                if cx1 <= lx <= cx2 and cy1 <= ly <= cy2:
                    self._hover_target = self._hit_test_pill_local(lx, ly, state)
                    return HTCLIENT
                self._hover_target = ""
                return HTTRANSPARENT

            if msg == WM_SETCURSOR:
                user32.SetCursor(hand_cursor if self._hover_target else arrow_cursor)
                return 1

            if msg == WM_LBUTTONUP:
                lx = ctypes.c_short(lparam & 0xFFFF).value
                ly = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                with self._lock:
                    state = self._state
                hit = self._hit_test_pill_local(lx, ly, state)
                if hit:
                    self._dispatch_pill_click(hit)
                return 0

            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(_wndproc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = cls_name
        user32.RegisterClassExW(ctypes.byref(wc))

        try:
            self._status_hwnd = self._create_overlay_hwnd(cls_name, hinst, self.PILL_W, self.PILL_H, transparent=False)
            self._cursor_hwnd = self._create_overlay_hwnd(cls_name, hinst, self.CURSOR_SZ, self.CURSOR_SZ, transparent=True)
            self._ripple_hwnd = self._create_overlay_hwnd(cls_name, hinst, self.RIPPLE_SZ, self.RIPPLE_SZ, transparent=True)
            for name in self._vig_hwnds:
                self._vig_hwnds[name] = self._create_overlay_hwnd(cls_name, hinst, 64, 64, transparent=True)
        except Exception:
            self._status_hwnd = None
            self._cursor_hwnd = None
            self._ripple_hwnd = None
            self._vig_hwnds = {k: None for k in self._vig_hwnds}
        finally:
            self._ready.set()

        if not self._status_hwnd:
            return

        msg = wt.MSG()
        while not self._stop_requested:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            while True:
                if msg.message == WM_APP_QUIT:
                    self._stop_requested = True
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
                if not user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    break
            if self._stop_requested:
                break
            self._tick_render()

        self._set_hi_res_timer(False)
        if self._timer_active and self._status_hwnd:
            user32.KillTimer(self._status_hwnd, 1)
            self._timer_active = False
        for h in (*self._vig_hwnds.values(), self._ripple_hwnd, self._cursor_hwnd, self._status_hwnd):
            if h:
                user32.DestroyWindow(h)

    def _hide_all(self) -> None:
        self._set_hi_res_timer(False)
        if self._timer_active and self._status_hwnd:
            user32.KillTimer(self._status_hwnd, 1)
            self._timer_active = False
        if self._pill_visible:
            self._hide_hwnd(self._status_hwnd)
            self._pill_visible = False
        if self._cursor_visible:
            self._hide_hwnd(self._cursor_hwnd)
            self._cursor_visible = False
        if self._ripple_visible:
            self._hide_hwnd(self._ripple_hwnd)
            self._ripple_visible = False
        if self._vig_visible:
            for vh in self._vig_hwnds.values():
                self._hide_hwnd(vh)
            self._vig_visible = False
        self._hover_target = ""

    def _tick_render(self) -> None:
        now = time.monotonic()
        dt = max(0.001, min(0.06, now - self._last_tick_ts))
        self._last_tick_ts = now

        with self._lock:
            enabled = self.enabled
            state = self._state
            label = self._label
            last_act = self._last_activity
            stop_until = self._stop_until
            tx, ty = self._target_cursor
            has_cur = self._has_cursor_pos
            wl, wt_, ww, wh = self._display_work_rect
            bx, by, bw, bh = self._display_bounds
            ripple = self._ripple
            press_down = self._press_down

            if not enabled or (state == "stopped" and now >= stop_until) or (
                state != "idle" and state != "stopped" and (now - last_act) > self.IDLE_HIDE_SEC
            ):
                self._state = "idle"
                state = "idle"
                self._ripple = None
                ripple = None

            if ripple is not None and (now - ripple.started_at) >= ripple.duration_sec:
                self._ripple = None
                ripple = None

            if state != "idle" and has_cur:
                alpha_lerp = 1.0 - math.exp(-dt * 42.0)
                dx = tx - self._vis_x
                dy = ty - self._vis_y
                if math.hypot(dx, dy) < 0.6:
                    self._vis_x, self._vis_y = float(tx), float(ty)
                else:
                    self._vis_x += dx * alpha_lerp
                    self._vis_y += dy * alpha_lerp
                if not self._trail or math.hypot(self._vis_x - self._trail[-1][0], self._vis_y - self._trail[-1][1]) >= 2.0:
                    self._trail.append((self._vis_x, self._vis_y, now))

            target_press = 1.0 if press_down else 0.0
            self._press_anim += (target_press - self._press_anim) * (1.0 - math.exp(-dt * 28.0))
            vis_x, vis_y = self._vis_x, self._vis_y
            press_anim = self._press_anim
            trail = [(ptx, pty, now - ts) for ptx, pty, ts in self._trail if (now - ts) <= self.TRAIL_LIFETIME_SEC]

        if state == "idle":
            self._hide_all()
            return

        if not self._timer_active and self._status_hwnd:
            self._set_hi_res_timer(True)
            user32.SetTimer(self._status_hwnd, 1, 10, None)
            self._timer_active = True

        # 1. Seamless 4-edge full-screen feathered vignette
        vig_alpha = int(172 + 68 * (0.5 + 0.5 * math.sin(now * 2.4)))
        if state == "stopped":
            vig_alpha = 115

        strips = self._build_vignette_strips(bw, bh, state)
        vig_key = (bw, bh, state)
        if vig_key != self._last_vig_key or abs(vig_alpha - self._last_vig_alpha) >= 2:
            for strip in strips:
                vh = self._vig_hwnds.get(strip.name)
                if vh:
                    _blit_layered_bgra(
                        vh, bx + strip.rel_x, by + strip.rel_y,
                        strip.width, strip.height, strip.bgra, source_alpha=vig_alpha,
                    )
                    if not self._vig_visible:
                        self._show_topmost(vh)
            self._vig_visible = True
            self._last_vig_key = vig_key
            self._last_vig_alpha = vig_alpha

        # 2. Bottom-center Obsidian Control Dock with live hover detection
        if self._status_hwnd:
            pill_left = wl + max(6, (ww - self.PILL_W) // 2)
            pill_top = wt_ + max(6, wh - self.PILL_H + 6)
            with self._lock:
                self._pill_win_pos = (pill_left, pill_top)

            pt = wt.POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                self._hover_target = self._hit_test_pill_local(pt.x - pill_left, pt.y - pill_top, state)
            pill_img = self._render_pill(state, label, now, hover_target=self._hover_target)
            _blit_layered_rgba(self._status_hwnd, pill_left, pill_top, pill_img)
            if not self._pill_visible:
                self._show_topmost(self._status_hwnd)
                self._pill_visible = True

        # 3. Fluid Gemini companion pointer + bloom-lit comet ribbon
        if self._cursor_hwnd and has_cur and state != "stopped":
            cur_img = self._render_cursor_halo(
                state, now, cur_x=vis_x, cur_y=vis_y, trail=trail, press_amount=press_anim,
            )
            _blit_layered_rgba(
                self._cursor_hwnd,
                round(vis_x) - self.CURSOR_SZ // 2,
                round(vis_y) - self.CURSOR_SZ // 2,
                cur_img,
            )
            if not self._cursor_visible:
                self._show_topmost(self._cursor_hwnd)
                self._cursor_visible = True
        elif self._cursor_visible:
            self._hide_hwnd(self._cursor_hwnd)
            self._cursor_visible = False

        # 4. Dual-stage Google/Gemini sonar click/scroll ripple
        if self._ripple_hwnd and ripple is not None:
            progress = min(1.0, max(0.0, (now - ripple.started_at) / ripple.duration_sec))
            rip_img = self._render_ripple(ripple, progress)
            _blit_layered_rgba(
                self._ripple_hwnd,
                ripple.x - self.RIPPLE_SZ // 2,
                ripple.y - self.RIPPLE_SZ // 2,
                rip_img,
            )
            if not self._ripple_visible:
                self._show_topmost(self._ripple_hwnd)
                self._ripple_visible = True
        elif self._ripple_visible:
            self._hide_hwnd(self._ripple_hwnd)
            self._ripple_visible = False
