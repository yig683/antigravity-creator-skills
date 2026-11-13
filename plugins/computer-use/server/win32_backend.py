"""DPI-aware Win32 desktop automation, capture, window, and clipboard backend."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import io
import json
import math
import os
import shutil
import subprocess
import time
import winreg
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# Win32 Constants & DPI Initialization
# ---------------------------------------------------------------------------

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0
BI_RGB = 0

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
WHEEL_DELTA = 120

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_RESTORE = 9
SW_SHOW = 5

WM_CLOSE = 0x0010
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
DWMWA_CLOAKED = 14
MONITORINFOF_PRIMARY = 1
MDT_EFFECTIVE_DPI = 0

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION = 20

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:
    shcore = None
try:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
except OSError:
    dwmapi = None
try:
    winmm = ctypes.WinDLL("winmm", use_last_error=True)
except OSError:
    winmm = None
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

AI_INPUT_TAG = 0x41475549  # "AGUI" tag to distinguish AI synthetic inputs


def init_dpi_awareness() -> None:
    """Enable per-monitor DPI awareness v2 so all coordinates are true physical pixels."""
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
        if user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return
    except Exception:
        pass
    if shcore is not None:
        try:
            shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


init_dpi_awareness()


# ---------------------------------------------------------------------------
# Win32 Structures (64-bit safe)
# ---------------------------------------------------------------------------


class BITMAPINFOHEADER(ctypes.Structure):
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


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
        ("szDevice", wt.WCHAR * 32),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wt.DWORD),
        ("wParamL", wt.WORD),
        ("wParamH", wt.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("union", INPUT_UNION)]


class TOKEN_ELEVATION_STRUCT(ctypes.Structure):
    _fields_ = [("TokenIsElevated", wt.DWORD)]


user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wt.UINT
user32.GetDoubleClickTime.restype = wt.UINT
user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
user32.MapVirtualKeyW.restype = wt.UINT
user32.VkKeyScanW.argtypes = [wt.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), ctypes.c_void_p, wt.LPARAM]
user32.EnumDisplayMonitors.restype = wt.BOOL
user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.c_void_p]
user32.GetMonitorInfoW.restype = wt.BOOL
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetCursorPos.restype = wt.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wt.BOOL
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.IsIconic.argtypes = [wt.HWND]
user32.IsIconic.restype = wt.BOOL
user32.IsZoomed.argtypes = [wt.HWND]
user32.IsZoomed.restype = wt.BOOL
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowRect.restype = wt.BOOL
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wt.LONG
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wt.HWND
user32.EnumWindows.argtypes = [ctypes.c_void_p, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.EnumChildWindows.argtypes = [wt.HWND, ctypes.c_void_p, wt.LPARAM]
user32.EnumChildWindows.restype = wt.BOOL
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.BringWindowToTop.restype = wt.BOOL
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.MoveWindow.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.BOOL]
user32.MoveWindow.restype = wt.BOOL
user32.OpenClipboard.argtypes = [wt.HWND]
user32.OpenClipboard.restype = wt.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wt.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wt.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wt.UINT]
user32.IsClipboardFormatAvailable.restype = wt.BOOL
user32.GetClipboardData.argtypes = [wt.UINT]
user32.GetClipboardData.restype = wt.HANDLE
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.SetClipboardData.restype = wt.HANDLE
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteObject.restype = wt.BOOL
gdi32.BitBlt.argtypes = [
    wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD,
]
gdi32.BitBlt.restype = wt.BOOL
gdi32.GetDIBits.argtypes = [
    wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int

kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
kernel32.GlobalUnlock.restype = wt.BOOL
kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
kernel32.GlobalFree.restype = wt.HGLOBAL
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wt.DWORD

advapi32.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
advapi32.OpenProcessToken.restype = wt.BOOL
advapi32.GetTokenInformation.argtypes = [
    wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD),
]
advapi32.GetTokenInformation.restype = wt.BOOL

if shcore is not None:
    shcore.GetDpiForMonitor.argtypes = [
        wt.HMONITOR, ctypes.c_int, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT),
    ]
    shcore.GetDpiForMonitor.restype = ctypes.c_long

if dwmapi is not None:
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


# ---------------------------------------------------------------------------
# Key Mapping (Anthropic X11 keysyms + Windows aliases)
# ---------------------------------------------------------------------------

EXTENDED_VKS = frozenset({
    0x21,  # PageUp
    0x22,  # PageDown
    0x23,  # End
    0x24,  # Home
    0x25,  # Left
    0x26,  # Up
    0x27,  # Right
    0x28,  # Down
    0x2D,  # Insert
    0x2E,  # Delete
    0x5B,  # LWin
    0x5C,  # RWin
    0x5D,  # Apps
    0xA3,  # RControl
    0xA5,  # RMenu
})

KEY_MAP: dict[str, int] = {
    "return": 0x0D,
    "enter": 0x0D,
    "kp_enter": 0x0D,
    "tab": 0x09,
    "iso_left_tab": 0x09,
    "escape": 0x1B,
    "esc": 0x1B,
    "backspace": 0x08,
    "space": 0x20,
    " ": 0x20,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "page_up": 0x21,
    "pageup": 0x21,
    "prior": 0x21,
    "page_down": 0x22,
    "pagedown": 0x22,
    "next": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "caps_lock": 0x14,
    "capslock": 0x14,
    "num_lock": 0x90,
    "numlock": 0x90,
    "scroll_lock": 0x91,
    "print": 0x2C,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "pause": 0x13,
    "apps": 0x5D,
    "menu": 0x5D,
    # Modifiers
    "ctrl": 0x11,
    "control": 0x11,
    "control_l": 0xA2,
    "lctrl": 0xA2,
    "control_r": 0xA3,
    "rctrl": 0xA3,
    "alt": 0x12,
    "alt_l": 0xA4,
    "lalt": 0xA4,
    "alt_r": 0xA5,
    "ralt": 0xA5,
    "shift": 0x10,
    "shift_l": 0xA0,
    "lshift": 0xA0,
    "shift_r": 0xA1,
    "rshift": 0xA1,
    "win": 0x5B,
    "lwin": 0x5B,
    "super": 0x5B,
    "super_l": 0x5B,
    "cmd": 0x5B,
    "command": 0x5B,
    "meta": 0x5B,
    "super_r": 0x5C,
    "rwin": 0x5C,
    # Media / Browser
    "audio_mute": 0xAD,
    "volumemute": 0xAD,
    "audio_lower_volume": 0xAE,
    "volumedown": 0xAE,
    "audio_raise_volume": 0xAF,
    "volumeup": 0xAF,
    "audio_play": 0xB3,
    "mediaplaypause": 0xB3,
    "audio_next": 0xB0,
    "medianext": 0xB0,
    "audio_prev": 0xB1,
    "mediaprev": 0xB1,
}
for _i in range(1, 25):
    KEY_MAP[f"f{_i}"] = 0x6F + _i


APP_ALIASES: dict[str, dict[str, Any]] = {
    "notepad": {"exe": "notepad.exe", "proc": "notepad.exe"},
    "not defteri": {"exe": "notepad.exe", "proc": "notepad.exe"},
    "calc": {"exe": "calc.exe", "proc": "calculatorapp.exe"},
    "calculator": {"exe": "calc.exe", "proc": "calculatorapp.exe"},
    "hesap makinesi": {"exe": "calc.exe", "proc": "calculatorapp.exe"},
    "paint": {"exe": "mspaint.exe", "proc": "mspaint.exe"},
    "mspaint": {"exe": "mspaint.exe", "proc": "mspaint.exe"},
    "explorer": {"exe": "explorer.exe", "proc": "explorer.exe"},
    "dosya gezgini": {"exe": "explorer.exe", "proc": "explorer.exe"},
    "cmd": {"exe": "cmd.exe", "proc": "cmd.exe"},
    "powershell": {"exe": "powershell.exe", "proc": "powershell.exe"},
    "pwsh": {"exe": "pwsh.exe", "proc": "pwsh.exe"},
    "terminal": {"exe": "wt.exe", "proc": "windowsterminal.exe"},
    "wt": {"exe": "wt.exe", "proc": "windowsterminal.exe"},
    "windows terminal": {"exe": "wt.exe", "proc": "windowsterminal.exe"},
    "chrome": {"exe": "chrome.exe", "proc": "chrome.exe"},
    "google chrome": {"exe": "chrome.exe", "proc": "chrome.exe"},
    "edge": {"exe": "msedge.exe", "proc": "msedge.exe"},
    "msedge": {"exe": "msedge.exe", "proc": "msedge.exe"},
    "firefox": {"exe": "firefox.exe", "proc": "firefox.exe"},
    "code": {"exe": "code.cmd", "proc": "code.exe"},
    "vscode": {"exe": "code.cmd", "proc": "code.exe"},
    "word": {"exe": "winword.exe", "proc": "winword.exe"},
    "excel": {"exe": "excel.exe", "proc": "excel.exe"},
    "powerpoint": {"exe": "powerpnt.exe", "proc": "powerpnt.exe"},
    "outlook": {"exe": "olk.exe", "proc": "olk.exe"},
    "taskmgr": {"exe": "taskmgr.exe", "proc": "taskmgr.exe"},
    "task manager": {"exe": "taskmgr.exe", "proc": "taskmgr.exe"},
    "settings": {"uri": "ms-settings:", "proc": "systemsettings.exe"},
    "ayarlar": {"uri": "ms-settings:", "proc": "systemsettings.exe"},
    "snipping tool": {"exe": "snippingtool.exe", "proc": "snippingtool.exe"},
}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class DisplayInfo:
    display_number: int
    device_name: str
    is_primary: bool
    left: int
    top: int
    width: int
    height: int
    work_area: dict[str, int]
    dpi_x: int
    dpi_y: int
    scale_percent: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ViewportMapping:
    display_number: int
    src_left: int
    src_top: int
    src_width: int
    src_height: int
    img_width: int
    img_height: int

    @property
    def scale_x(self) -> float:
        return self.src_width / max(1, self.img_width)

    @property
    def scale_y(self) -> float:
        return self.src_height / max(1, self.img_height)

    def to_physical(self, x: float, y: float) -> tuple[int, int]:
        px = round(self.src_left + (x * self.src_width) / max(1, self.img_width))
        py = round(self.src_top + (y * self.src_height) / max(1, self.img_height))
        px = max(self.src_left, min(self.src_left + self.src_width - 1, px))
        py = max(self.src_top, min(self.src_top + self.src_height - 1, py))
        return int(px), int(py)

    def to_screenshot(self, px: float, py: float) -> tuple[int, int]:
        sx = round(((px - self.src_left) * self.img_width) / max(1, self.src_width))
        sy = round(((py - self.src_top) * self.img_height) / max(1, self.src_height))
        return int(sx), int(sy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_number": self.display_number,
            "physical_bounds": {
                "left": self.src_left,
                "top": self.src_top,
                "width": self.src_width,
                "height": self.src_height,
            },
            "image_size": [self.img_width, self.img_height],
            "scale_x": round(self.scale_x, 4),
            "scale_y": round(self.scale_y, 4),
        }


# ---------------------------------------------------------------------------
# Win32 Backend Implementation
# ---------------------------------------------------------------------------


class Win32Backend:
    """Thread-safe native Win32 desktop automation and screenshot backend."""

    DISPLAY_CACHE_TTL_SEC = 5.0
    PROC_CACHE_TTL_SEC = 10.0

    def __init__(
        self,
        screenshots_dir: Path,
        overlay: Any = None,
        smooth_cursor_ms: int = 220,
        annotate_mode: str = "grid",
        on_synthetic_escape: Callable[[], None] | None = None,
        on_user_interrupt: Callable[[str], None] | None = None,
    ) -> None:
        self.screenshots_dir = screenshots_dir
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.overlay = overlay
        self.smooth_cursor_ms = max(0, min(500, int(smooth_cursor_ms)))
        self.annotate_mode = annotate_mode if annotate_mode in {"none", "grid", "som"} else "grid"
        self.on_synthetic_escape = on_synthetic_escape
        self.on_user_interrupt = on_user_interrupt
        self.last_marks: dict[int, dict[str, Any]] = {}
        self.active_viewport: ViewportMapping | None = None
        self.last_viewports_by_display: dict[int, ViewportMapping] = {}
        self._displays_cache: tuple[float, list[DisplayInfo]] | None = None
        self._proc_cache: dict[int, tuple[float, str, str, bool | None]] = {}
        self._shot_counter = 0
        self._arc_polarity = 1
        self.current_elevated = self.is_process_elevated(os.getpid())
        try:
            self._ui_font = ImageFont.truetype("segoeui.ttf", 11)
        except Exception:
            self._ui_font = ImageFont.load_default()

    def sync_overlay_display(self, display_number: int | None = None) -> None:
        if not self.overlay:
            return
        displays = self.list_displays()
        target = display_number or (self.active_viewport.display_number if self.active_viewport else 1)
        for d in displays:
            if d.display_number == target or target == 0:
                wk = d.work_area
                self.overlay.set_display_rect(
                    wk["left"],
                    wk["top"],
                    wk["width"],
                    wk["height"],
                    bounds=(d.left, d.top, d.width, d.height),
                )
                return

    # -- Process & Privilege Introspection --------------------------------

    @staticmethod
    def is_process_elevated(pid: int) -> bool:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        token = wt.HANDLE()
        try:
            if not advapi32.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(token)):
                return False
            elevation = TOKEN_ELEVATION_STRUCT()
            ret_len = wt.DWORD()
            ok = advapi32.GetTokenInformation(
                token,
                TOKEN_ELEVATION,
                ctypes.byref(elevation),
                ctypes.sizeof(elevation),
                ctypes.byref(ret_len),
            )
            return bool(ok and elevation.TokenIsElevated)
        finally:
            if token:
                kernel32.CloseHandle(token)
            kernel32.CloseHandle(handle)

    @classmethod
    def is_current_process_elevated(cls) -> bool:
        return cls.is_process_elevated(os.getpid())

    def get_process_meta(self, pid: int, include_elevation: bool = True) -> tuple[str, str, bool]:
        """Get (exe_path, process_name, is_elevated) with short TTL caching."""
        if pid <= 0:
            return "", "", False
        now = time.monotonic()
        cached = self._proc_cache.get(pid)
        if cached and (now - cached[0]) < self.PROC_CACHE_TTL_SEC:
            _, c_path, c_name, c_elev = cached
            if not include_elevation or c_elev is not None:
                return c_path, c_name, bool(c_elev)

        exe_path, proc_name = self.get_process_path_and_name(pid)
        elevated: bool | None = cached[3] if (cached and (now - cached[0]) < self.PROC_CACHE_TTL_SEC) else None
        if include_elevation and elevated is None:
            elevated = self.is_process_elevated(pid)

        self._proc_cache[pid] = (now, exe_path, proc_name, elevated)
        if len(self._proc_cache) > 256:
            cutoff = now - self.PROC_CACHE_TTL_SEC
            self._proc_cache = {k: v for k, v in self._proc_cache.items() if v[0] >= cutoff}
        return exe_path, proc_name, bool(elevated)

    @staticmethod
    def get_process_path_and_name(pid: int) -> tuple[str, str]:
        if pid <= 0:
            return "", ""
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return "", ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wt.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                full_path = buf.value
                return full_path, Path(full_path).name
            return "", ""
        finally:
            kernel32.CloseHandle(handle)

    # -- Displays & Coordinate Mapping ------------------------------------

    @staticmethod
    def get_virtual_desktop_rect() -> tuple[int, int, int, int]:
        vx = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
        vy = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
        vw = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
        vh = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
        return vx, vy, vw, vh

    def list_displays(self, force_refresh: bool = False) -> list[DisplayInfo]:
        """Enumerate connected displays (cached briefly); primary is always display_number 1."""
        now = time.monotonic()
        if not force_refresh and self._displays_cache is not None:
            cached_at, cached_list = self._displays_cache
            if (now - cached_at) < self.DISPLAY_CACHE_TTL_SEC:
                return cached_list

        raw_monitors: list[dict[str, Any]] = []

        monitor_cb_type = ctypes.WINFUNCTYPE(
            wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM
        )

        def _cb(hmon: int, _hdc: int, _rect: Any, _lparam: int) -> bool:
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                dpi_x = wt.UINT(96)
                dpi_y = wt.UINT(96)
                if shcore is not None:
                    try:
                        shcore.GetDpiForMonitor(
                            hmon, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
                        )
                    except Exception:
                        pass
                rc = info.rcMonitor
                wk = info.rcWork
                raw_monitors.append({
                    "is_primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    "device_name": info.szDevice,
                    "left": int(rc.left),
                    "top": int(rc.top),
                    "width": int(rc.right - rc.left),
                    "height": int(rc.bottom - rc.top),
                    "work_area": {
                        "left": int(wk.left),
                        "top": int(wk.top),
                        "width": int(wk.right - wk.left),
                        "height": int(wk.bottom - wk.top),
                    },
                    "dpi_x": int(dpi_x.value),
                    "dpi_y": int(dpi_y.value),
                    "scale_percent": round(dpi_x.value * 100 / 96),
                })
            return True

        cb = monitor_cb_type(_cb)
        user32.EnumDisplayMonitors(None, None, cb, 0)

        raw_monitors.sort(key=lambda m: (0 if m["is_primary"] else 1, m["left"], m["top"]))
        displays = [
            DisplayInfo(display_number=idx + 1, **m)
            for idx, m in enumerate(raw_monitors)
        ]
        self._displays_cache = (now, displays)
        return displays

    def _display_rect(self, display_number: int | None) -> tuple[int, int, int, int, int]:
        """Resolve display_number (1..N, or 0 for all displays) to rect + normalized display_number."""
        displays = self.list_displays()
        if display_number == 0:
            vx, vy, vw, vh = self.get_virtual_desktop_rect()
            return 0, vx, vy, vw, vh
        if display_number is None:
            display_number = self.active_viewport.display_number if self.active_viewport else 1
        for disp in displays:
            if disp.display_number == display_number:
                return disp.display_number, disp.left, disp.top, disp.width, disp.height
        if displays:
            d0 = displays[0]
            return d0.display_number, d0.left, d0.top, d0.width, d0.height
        vx, vy, vw, vh = self.get_virtual_desktop_rect()
        return 1, vx, vy, vw, vh

    def _ensure_viewport(self, display_number: int | None = None) -> ViewportMapping:
        if display_number is not None:
            if display_number in self.last_viewports_by_display:
                return self.last_viewports_by_display[display_number]
            num, left, top, width, height = self._display_rect(display_number)
            img_w, img_h = self._fit_dimensions(width, height, 1280, 800)
            return ViewportMapping(num, left, top, width, height, img_w, img_h)
        if self.active_viewport is not None:
            return self.active_viewport
        num, left, top, width, height = self._display_rect(1)
        img_w, img_h = self._fit_dimensions(width, height, 1280, 800)
        return ViewportMapping(num, left, top, width, height, img_w, img_h)

    @staticmethod
    def _fit_dimensions(src_w: int, src_h: int, max_w: int, max_h: int) -> tuple[int, int]:
        if src_w <= 0 or src_h <= 0:
            return 1, 1
        scale = min(max_w / src_w, max_h / src_h, 1.0)
        return max(1, round(src_w * scale)), max(1, round(src_h * scale))

    def resolve_coordinate(
        self,
        x: float,
        y: float,
        display_number: int | None = None,
        coordinate_space: str = "screenshot",
    ) -> tuple[int, int]:
        """Convert screenshot (or physical) coordinate into clamped physical pixel coordinates."""
        if coordinate_space == "physical":
            vx, vy, vw, vh = self.get_virtual_desktop_rect()
            px = max(vx, min(vx + vw - 1, round(x)))
            py = max(vy, min(vy + vh - 1, round(y)))
            return int(px), int(py)
        viewport = self._ensure_viewport(display_number)
        return viewport.to_physical(x, y)

    def display_for_point(self, px: int, py: int) -> int:
        for disp in self.list_displays():
            if disp.left <= px < disp.left + disp.width and disp.top <= py < disp.top + disp.height:
                return disp.display_number
        return 1

    # -- Screen Capture & Zoom --------------------------------------------

    @staticmethod
    def capture_region_pil(left: int, top: int, width: int, height: int) -> Image.Image:
        """Capture a physical screen rectangle directly into a PIL RGB Image."""
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid capture dimensions: {width}x{height}")

        screen_dc = user32.GetDC(None)
        if not screen_dc:
            raise RuntimeError("Failed to acquire desktop device context.")
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        hbmp = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        old_obj = gdi32.SelectObject(mem_dc, hbmp)
        try:
            ok = gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, SRCCOPY | CAPTUREBLT)
            if not ok:
                err = ctypes.get_last_error()
                raise RuntimeError(
                    f"BitBlt screen capture failed (Win32 error {err}); the desktop may be locked, "
                    "isolated/headless, or showing a secure UAC prompt."
                )

            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # Top-down scanlines
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB

            buf = ctypes.create_string_buffer(width * height * 4)
            lines = gdi32.GetDIBits(mem_dc, hbmp, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
            if lines == 0:
                raise RuntimeError("GetDIBits failed while reading captured screen bitmap.")

            return Image.frombytes("RGB", (width, height), buf.raw, "raw", "BGRX")
        finally:
            if old_obj:
                gdi32.SelectObject(mem_dc, old_obj)
            if hbmp:
                gdi32.DeleteObject(hbmp)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(None, screen_dc)

    @staticmethod
    def _draw_cursor_indicator(img: Image.Image, rel_x: int, rel_y: int) -> None:
        """Draw a smooth radial glow + 4x supersampled Obsidian pointer at (rel_x, rel_y)."""
        from overlay import build_vector_pointer_sprite

        glow_r = max(16, round(min(img.width, img.height) * 0.026))
        glow_patch = Image.new("RGBA", (glow_r * 2 + 4, glow_r * 2 + 4), (0, 0, 0, 0))
        gc = glow_r + 2
        gd = ImageDraw.Draw(glow_patch, "RGBA")
        gd.ellipse((gc - glow_r, gc - glow_r, gc + glow_r, gc + glow_r), fill=(56, 189, 248, 38))
        gd.ellipse((gc - glow_r // 2, gc - glow_r // 2, gc + glow_r // 2, gc + glow_r // 2), fill=(165, 243, 252, 62))
        glow_patch = glow_patch.filter(ImageFilter.GaussianBlur(radius=max(3.5, glow_r * 0.35)))
        img.paste(glow_patch, (rel_x - gc, rel_y - gc), glow_patch)

        h_px = max(20, round(min(img.width, img.height) * 0.032))
        ptr_img, (hx, hy) = build_vector_pointer_sprite(h_px)
        img.paste(ptr_img, (rel_x - hx, rel_y - hy), ptr_img)

    def _save_shot(self, img: Image.Image, prefix: str, fmt: str = "jpeg") -> tuple[Path, bytes, str]:
        fmt_norm = "png" if fmt.lower() == "png" else "jpeg"
        ext = "png" if fmt_norm == "png" else "jpg"
        stamp = f"{time.strftime('%Y%m%d_%H%M%S')}_{int((time.time() % 1) * 1000):03d}"
        out_path = self.screenshots_dir / f"{prefix}_{stamp}.{ext}"

        buf = io.BytesIO()
        if fmt_norm == "png":
            img.save(buf, format="PNG", compress_level=1)
        else:
            img.save(buf, format="JPEG", quality=86, subsampling=0)
        raw_bytes = buf.getvalue()
        out_path.write_bytes(raw_bytes)
        self._shot_counter += 1
        if self._shot_counter % 10 == 0:
            self._prune_old_screenshots(keep=40)
        return out_path, raw_bytes, fmt_norm

    def _prune_old_screenshots(self, keep: int = 40) -> None:
        try:
            files = sorted(
                self.screenshots_dir.glob("*.*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in files[keep:]:
                old.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _frame_fingerprint(img: Image.Image) -> Image.Image:
        """Downscale to a 64x64 grayscale fingerprint for fast UI-change checks."""
        return img.convert("L").resize((64, 64), Image.Resampling.BILINEAR)

    @staticmethod
    def _mean_fingerprint_diff(fp_a: Image.Image, fp_b: Image.Image) -> float:
        """Mean absolute per-pixel difference (0..255) between two fingerprints."""
        hist = ImageChops.difference(fp_a, fp_b).histogram()
        total = sum(i * c for i, c in enumerate(hist))
        count = sum(hist)
        return (total / count) if count else 0.0

    def _draw_coordinate_grid(self, img: Image.Image) -> None:
        """Overlay a faint 100px Google/Antigravity Obsidian coordinate grid + ruler numbers."""
        w, h = img.size
        draw = ImageDraw.Draw(img, "RGBA")
        line_rgba = (66, 133, 244, 46)
        sub_rgba = (56, 189, 248, 88)
        pill_fill = (14, 17, 23, 205)
        pill_border = (66, 133, 244, 185)
        text_fill = (224, 242, 254, 248)

        for x in range(50, w, 50):
            if x % 100 == 0:
                draw.line((x, 0, x, h), fill=line_rgba, width=1)
                lbl = str(x)
                lx = max(2, min(w - 30, x - 12))
                draw.rounded_rectangle((lx, 2, lx + len(lbl) * 6 + 6, 16), radius=3, fill=pill_fill, outline=pill_border, width=1)
                draw.text((lx + 3, 2), lbl, font=self._ui_font, fill=text_fill)
            else:
                draw.line((x, 0, x, 6), fill=sub_rgba, width=1)

        for y in range(50, h, 50):
            if y % 100 == 0:
                draw.line((0, y, w, y), fill=line_rgba, width=1)
                lbl = str(y)
                ly = max(20, min(h - 16, y - 7))
                draw.rounded_rectangle((2, ly, len(lbl) * 6 + 8, ly + 14), radius=3, fill=pill_fill, outline=pill_border, width=1)
                draw.text((5, ly), lbl, font=self._ui_font, fill=text_fill)
            else:
                draw.line((0, y, 6, y), fill=sub_rgba, width=1)

    @staticmethod
    def _place_mark_badge(
        bx1: int,
        by1: int,
        bx2: int,
        by2: int,
        tw: int,
        th: int,
        img_w: int,
        img_h: int,
        placed_badges: list[tuple[int, int, int, int]],
    ) -> tuple[int, int]:
        """Choose a ruler-safe (x >= 28), non-overlapping badge origin near element bounds."""
        min_px1 = 28 if img_w > (28 + tw + 1) else 0
        max_px1 = max(min_px1, img_w - tw - 1)
        max_py1 = max(0, img_h - th - 1)

        base_x = max(min_px1, min(max_px1, bx1))
        base_y = max(0, by1 - (th + 1)) if by1 >= (th + 1) else min(max_py1, by1)

        step_x = tw + 3
        step_y = th + 2
        candidates: list[tuple[int, int]] = [(base_x, base_y)]
        for k in range(1, 6):
            candidates.append((max(min_px1, min(max_px1, base_x + k * step_x)), base_y))
        candidates.append((base_x, min(max_py1, by1 + 2)))
        candidates.append((base_x, max(0, min(max_py1, by2 - th))))
        for dy in (step_y, -step_y, 2 * step_y, -2 * step_y):
            cy = max(0, min(max_py1, base_y + dy))
            for k in range(0, 3):
                candidates.append((max(min_px1, min(max_px1, base_x + k * step_x)), cy))

        def _overlap_area(cx1: int, cy1: int) -> int:
            cx2, cy2 = cx1 + tw, cy1 + th
            area = 0
            for ox1, oy1, ox2, oy2 in placed_badges:
                ox = min(cx2 + 1, ox2 + 1) - max(cx1, ox1)
                oy = min(cy2 + 1, oy2 + 1) - max(cy1, oy1)
                if ox > 0 and oy > 0:
                    area += ox * oy
            return area

        best_pos = (base_x, base_y)
        best_area: int | None = None
        seen_cands: set[tuple[int, int]] = set()
        for cx1, cy1 in candidates:
            if (cx1, cy1) in seen_cands:
                continue
            seen_cands.add((cx1, cy1))
            area = _overlap_area(cx1, cy1)
            if area == 0:
                best_pos = (cx1, cy1)
                break
            if best_area is None or area < best_area:
                best_area = area
                best_pos = (cx1, cy1)

        placed_badges.append((best_pos[0], best_pos[1], best_pos[0] + tw, best_pos[1] + th))
        return best_pos

    def _draw_set_of_mark(
        self,
        img: Image.Image,
        elements: list[dict[str, Any]],
        max_marks: int = 95,
    ) -> list[dict[str, Any]]:
        """Draw numbered Set-of-Mark badges on interactive UIA controls and record exact click targets."""
        if max_marks <= 0 or not elements:
            self.last_marks = {}
            return []
        w, h = img.size
        draw = ImageDraw.Draw(img, "RGBA")
        palette = [
            (66, 133, 244),   # Google Blue
            (56, 189, 248),   # Antigravity Cyan
            (52, 168, 83),    # Google Green
            (251, 188, 5),    # Google Amber
            (168, 85, 247),   # Gemini Violet
        ]
        marks_list: list[dict[str, Any]] = []
        marks_map: dict[int, dict[str, Any]] = {}
        seen_centers: set[tuple[int, int]] = set()
        placed_badges: list[tuple[int, int, int, int]] = []

        for el in elements:
            bounds = el.get("bounds")
            center = el.get("center")
            if not bounds or not center or len(bounds) != 4 or len(center) != 2:
                continue
            x1, y1, x2, y2 = int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3])
            cx, cy = int(center[0]), int(center[1])
            if cx < 0 or cy < 0 or cx >= w or cy >= h or (x2 - x1) < 4 or (y2 - y1) < 4:
                continue
            bucket = (cx // 6, cy // 6)
            if bucket in seen_centers:
                continue
            seen_centers.add(bucket)

            idx = len(marks_list) + 1
            rgb = palette[(idx - 1) % len(palette)]
            bx1, by1 = max(0, x1), max(0, y1)
            bx2, by2 = min(w - 1, x2), min(h - 1, y2)
            draw.rectangle((bx1, by1, bx2, by2), outline=(*rgb, 205), width=2)

            tag = str(idx)
            tw = len(tag) * 7 + 8
            th = 14
            px1, py1 = self._place_mark_badge(bx1, by1, bx2, by2, tw, th, w, h, placed_badges)
            draw.rounded_rectangle((px1, py1, px1 + tw, py1 + th), radius=3, fill=(*rgb, 240))
            draw.text((px1 + 4, py1), tag, font=self._ui_font, fill=(15, 23, 42, 255))

            entry = {
                "id": idx,
                "type": str(el.get("type") or ""),
                "name": str(el.get("name") or el.get("help_text") or ""),
                "center": [cx, cy],
            }
            marks_list.append(entry)
            marks_map[idx] = entry
            if len(marks_list) >= max_marks:
                break

        self.last_marks = marks_map
        return marks_list

    def _finalize_screenshot(
        self,
        img: Image.Image,
        disp_num: int,
        left: int,
        top: int,
        src_w: int,
        src_h: int,
        max_width: int,
        max_height: int,
        show_cursor: bool,
        fmt: str,
        include_displays: bool,
        annotate_mode: str | None = None,
        marks_provider: Callable[[ViewportMapping], list[dict[str, Any]]] | None = None,
        max_marks: int = 95,
    ) -> dict[str, Any]:
        cur_px, cur_py = self.get_cursor_pos_physical()
        if show_cursor and left <= cur_px < left + src_w and top <= cur_py < top + src_h:
            self._draw_cursor_indicator(img, cur_px - left, cur_py - top)

        out_w, out_h = self._fit_dimensions(src_w, src_h, max_width, max_height)
        if (out_w, out_h) != (src_w, src_h):
            img = img.resize((out_w, out_h), Image.Resampling.BICUBIC)

        viewport = ViewportMapping(disp_num, left, top, src_w, src_h, out_w, out_h)
        self.active_viewport = viewport
        self.last_viewports_by_display[disp_num] = viewport
        self.sync_overlay_display(disp_num)

        eff_mode = annotate_mode if annotate_mode in {"none", "grid", "som"} else self.annotate_mode
        if eff_mode in {"grid", "som"}:
            self._draw_coordinate_grid(img)

        marks_list: list[dict[str, Any]] | None = None
        if marks_provider is not None:
            raw_els = marks_provider(viewport)
            if raw_els:
                marks_list = self._draw_set_of_mark(img, raw_els, max_marks=max_marks)
            else:
                self.last_marks = {}

        out_path, raw_bytes, fmt_norm = self._save_shot(img, f"shot_d{disp_num}", fmt=fmt)
        cur_sx, cur_sy = viewport.to_screenshot(cur_px, cur_py)

        result: dict[str, Any] = {
            "image": img,
            "image_bytes": raw_bytes,
            "image_format": fmt_norm,
            "image_path": str(out_path),
            "mime_type": "image/jpeg" if fmt_norm == "jpeg" else "image/png",
            "viewport": viewport.to_dict(),
            "cursor_screenshot_pos": [cur_sx, cur_sy],
            "cursor_physical_pos": [cur_px, cur_py],
            "frontmost_window": self.get_frontmost_window(include_elevation=False),
        }
        if marks_list:
            result["marks"] = marks_list
        if include_displays:
            result["displays"] = [d.to_dict() for d in self.list_displays()]
        return result

    def capture_screenshot(
        self,
        display_number: int | None = 1,
        max_width: int = 1280,
        max_height: int = 800,
        show_cursor: bool = True,
        fmt: str = "jpeg",
        include_displays: bool = False,
        annotate_mode: str | None = None,
        marks_provider: Callable[[ViewportMapping], list[dict[str, Any]]] | None = None,
        max_marks: int = 95,
    ) -> dict[str, Any]:
        """Capture display screenshot, resize cleanly, update viewport mapping, and return bytes + path."""
        disp_num, left, top, src_w, src_h = self._display_rect(display_number)
        img = self.capture_region_pil(left, top, src_w, src_h)
        return self._finalize_screenshot(
            img=img,
            disp_num=disp_num,
            left=left,
            top=top,
            src_w=src_w,
            src_h=src_h,
            max_width=max_width,
            max_height=max_height,
            show_cursor=show_cursor,
            fmt=fmt,
            include_displays=include_displays,
            annotate_mode=annotate_mode,
            marks_provider=marks_provider,
            max_marks=max_marks,
        )

    def capture_screenshot_when_stable(
        self,
        display_number: int | None = 1,
        max_width: int = 1280,
        max_height: int = 800,
        show_cursor: bool = True,
        fmt: str = "jpeg",
        include_displays: bool = False,
        timeout_sec: float = 5.0,
        poll_interval_sec: float = 0.05,
        stability_period_sec: float = 0.14,
        diff_threshold: float = 2.5,
        on_poll: Callable[[], None] | None = None,
        annotate_mode: str | None = None,
        marks_provider: Callable[[ViewportMapping], list[dict[str, Any]]] | None = None,
        max_marks: int = 95,
    ) -> dict[str, Any]:
        """Poll BitBlt display frames until visuals stop changing, then return one settled screenshot."""
        disp_num, left, top, src_w, src_h = self._display_rect(display_number)
        t0 = time.perf_counter()
        timeout = max(0.2, min(15.0, float(timeout_sec)))
        poll_sleep = max(0.01, float(poll_interval_sec))
        stable_needed = max(0.02, float(stability_period_sec))

        if on_poll is not None:
            on_poll()
        last = self.capture_region_pil(left, top, src_w, src_h)
        last_fp = self._frame_fingerprint(last)
        stable_since: float | None = None
        frames = 1
        stabilized = False

        while (time.perf_counter() - t0) < timeout:
            time.sleep(poll_sleep)
            if on_poll is not None:
                on_poll()
            cur = self.capture_region_pil(left, top, src_w, src_h)
            frames += 1
            cur_fp = self._frame_fingerprint(cur)
            diff = self._mean_fingerprint_diff(last_fp, cur_fp)
            last, last_fp = cur, cur_fp
            now = time.perf_counter()

            if diff > diff_threshold:
                stable_since = None
            elif stable_since is None:
                stable_since = now
            elif (now - stable_since) >= stable_needed:
                stabilized = True
                break

        result = self._finalize_screenshot(
            img=last,
            disp_num=disp_num,
            left=left,
            top=top,
            src_w=src_w,
            src_h=src_h,
            max_width=max_width,
            max_height=max_height,
            show_cursor=show_cursor,
            fmt=fmt,
            include_displays=include_displays,
            annotate_mode=annotate_mode,
            marks_provider=marks_provider,
            max_marks=max_marks,
        )
        result["settle"] = {
            "stabilized": stabilized,
            "waited_ms": round((time.perf_counter() - t0) * 1000, 1),
            "frames": frames,
        }
        return result

    def capture_zoom(
        self,
        region: list[int],
        display_number: int | None = None,
        fmt: str = "jpeg",
    ) -> dict[str, Any]:
        """Capture a native-resolution zoomed crop for region [x1, y1, x2, y2] in screenshot space."""
        if len(region) != 4:
            raise ValueError("region must be [x1, y1, x2, y2].")
        x1, y1, x2, y2 = region
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        viewport = self._ensure_viewport(display_number)
        px1, py1 = viewport.to_physical(x1, y1)
        px2, py2 = viewport.to_physical(x2, y2)

        crop_w = max(8, px2 - px1)
        crop_h = max(8, py2 - py1)
        crop_w = min(crop_w, viewport.src_left + viewport.src_width - px1)
        crop_h = min(crop_h, viewport.src_top + viewport.src_height - py1)

        img = self.capture_region_pil(px1, py1, crop_w, crop_h)
        upscale = 1
        if max(crop_w, crop_h) < 280:
            upscale = 2
            img = img.resize((crop_w * 2, crop_h * 2), Image.Resampling.BICUBIC)
        elif crop_w > 1280 or crop_h > 800:
            fit_w, fit_h = self._fit_dimensions(crop_w, crop_h, 1280, 800)
            img = img.resize((fit_w, fit_h), Image.Resampling.BICUBIC)

        out_path, raw_bytes, fmt_norm = self._save_shot(img, f"zoom_d{viewport.display_number}", fmt=fmt)
        return {
            "image": img,
            "image_bytes": raw_bytes,
            "image_format": fmt_norm,
            "image_path": str(out_path),
            "mime_type": "image/jpeg" if fmt_norm == "jpeg" else "image/png",
            "display_number": viewport.display_number,
            "screenshot_region": [x1, y1, x2, y2],
            "physical_region": [px1, py1, px1 + crop_w, py1 + crop_h],
            "image_size": [img.width, img.height],
            "upscale_factor": upscale,
            "note": "Target click coordinates still use the main screenshot coordinate space of this display.",
        }

    # -- Mouse Controls ---------------------------------------------------

    @staticmethod
    def get_cursor_pos_physical() -> tuple[int, int]:
        pt = wt.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return 0, 0
        return int(pt.x), int(pt.y)

    def get_cursor_info(self) -> dict[str, Any]:
        px, py = self.get_cursor_pos_physical()
        disp_num = self.display_for_point(px, py)
        viewport = self._ensure_viewport(disp_num)
        sx, sy = viewport.to_screenshot(px, py)
        hwnd = user32.WindowFromPoint(wt.POINT(px, py))
        root_hwnd = user32.GetAncestor(hwnd, 2) if hwnd else 0  # GA_ROOT = 2
        win = self.get_window_info(root_hwnd or hwnd) if hwnd else None
        return {
            "screenshot_pos": [sx, sy],
            "physical_pos": [px, py],
            "display_number": disp_num,
            "viewport": viewport.to_dict(),
            "window_under_cursor": win,
        }

    @staticmethod
    def _send_inputs(inputs: list[INPUT]) -> None:
        if not inputs:
            return
        arr = (INPUT * len(inputs))(*inputs)
        sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
        if sent == 0:
            err = ctypes.get_last_error()
            raise RuntimeError(f"SendInput failed with Win32 error {err}.")

    @classmethod
    def _mouse_input(cls, flags: int, mouse_data: int = 0) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi = MOUSEINPUT(dx=0, dy=0, mouseData=mouse_data, dwFlags=flags, time=0, dwExtraInfo=AI_INPUT_TAG)
        return inp

    @staticmethod
    def _precise_sleep(seconds: float) -> None:
        if seconds <= 0.0:
            return
        deadline = time.perf_counter() + seconds
        if seconds > 0.0025:
            time.sleep(seconds - 0.0018)
        while time.perf_counter() < deadline:
            pass

    @staticmethod
    def _compute_human_glide_path(
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        steps: int,
        arc_sign: int = 1,
    ) -> list[tuple[int, int]]:
        """Generate a human-like minimum-jerk trajectory with subtle perpendicular Bezier curvature."""
        dx = end_x - start_x
        dy = end_y - start_y
        dist = math.hypot(dx, dy)
        if steps <= 1 or dist < 1.0:
            return [(int(end_x), int(end_y))]

        nx = -dy / dist
        ny = dx / dist
        arc_amp = (min(22.0, dist * 0.045) * (1 if arc_sign >= 0 else -1)) if dist >= 40.0 else 0.0

        pts: list[tuple[int, int]] = []
        for idx in range(1, steps + 1):
            t = idx / steps
            # Minimum-jerk polynomial (zero velocity & acceleration at both ends)
            s = (10.0 * t ** 3) - (15.0 * t ** 4) + (6.0 * t ** 5)
            arc = 4.0 * t * (1.0 - t) * arc_amp
            ix = round(start_x + dx * s + nx * arc)
            iy = round(start_y + dy * s + ny * arc)
            pts.append((ix, iy))
        pts[-1] = (int(end_x), int(end_y))
        return pts

    @classmethod
    def _move_physical_instant(cls, px: int, py: int) -> None:
        user32.SetCursorPos(int(px), int(py))
        # Zero-delta relative move wakes hover listeners cleanly without rounding drift.
        cls._send_inputs([cls._mouse_input(MOUSEEVENTF_MOVE)])

    def _glide_to(
        self,
        px: int,
        py: int,
        duration_ms: int | None = None,
        label: str | None = None,
    ) -> None:
        cur_x, cur_y = self.get_cursor_pos_physical()
        dist = math.hypot(px - cur_x, py - cur_y)
        if duration_ms is None:
            if dist < 8 or self.smooth_cursor_ms <= 0:
                duration_ms = 0
            else:
                floor_ms = min(self.smooth_cursor_ms, 70)
                duration_ms = max(floor_ms, min(self.smooth_cursor_ms, round(38 + 8.8 * math.sqrt(dist))))

        if duration_ms <= 0:
            self._move_physical_instant(px, py)
            if self.overlay:
                self.overlay.notify_cursor(px, py, label=label)
            return

        steps = max(6, min(42, round(duration_ms / 8)))
        self._arc_polarity *= -1
        path = self._compute_human_glide_path(cur_x, cur_y, px, py, steps, arc_sign=self._arc_polarity)
        step_sec = (duration_ms / 1000.0) / len(path)

        prev_sent = (cur_x, cur_y)
        override_hits = 0
        hi_res = False
        if winmm is not None:
            try:
                winmm.timeBeginPeriod(1)
                hi_res = True
            except Exception:
                hi_res = False
        try:
            for idx, (ix, iy) in enumerate(path, start=1):
                if self.on_user_interrupt is not None and dist >= 90 and idx >= 2:
                    ax, ay = self.get_cursor_pos_physical()
                    if math.hypot(ax - prev_sent[0], ay - prev_sent[1]) > 120 and math.hypot(ax - px, ay - py) > 120:
                        override_hits += 1
                        if override_hits >= 2:
                            self.on_user_interrupt("Kullanıcı fare ile kontrolü devraldı")
                            raise RuntimeError("Kullanıcı fare ile kontrolü devraldı")
                    else:
                        override_hits = 0
                self._move_physical_instant(ix, iy)
                prev_sent = (ix, iy)
                if self.overlay:
                    self.overlay.notify_cursor(ix, iy, label=label if idx == 1 else None)
                self._precise_sleep(step_sec)
        finally:
            if hi_res and winmm is not None:
                try:
                    winmm.timeEndPeriod(1)
                except Exception:
                    pass

    def move_mouse(self, px: int, py: int, duration_ms: int = 0) -> tuple[int, int]:
        eff_dur = None if duration_ms <= 0 else duration_ms
        self._glide_to(px, py, duration_ms=eff_dur, label="İmleç taşınıyor")
        return self.get_cursor_pos_physical()

    def click(
        self,
        px: int | None = None,
        py: int | None = None,
        button: str = "left",
        count: int = 1,
        modifiers: str | None = None,
        duration_ms: int | None = None,
    ) -> tuple[int, int]:
        flags_map = {
            "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
            "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
            "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        }
        if button not in flags_map:
            raise ValueError(f"Unsupported mouse button: {button}")
        down_flag, up_flag = flags_map[button]

        mod_vks = self._parse_key_spec(modifiers) if modifiers else []
        try:
            for vk in mod_vks:
                self._send_inputs([self._key_input(vk, up=False)])
            if mod_vks:
                time.sleep(0.015)

            if px is not None and py is not None:
                self._glide_to(px, py, duration_ms=duration_ms)
                if duration_ms != 0:
                    self._precise_sleep(0.008)

            fx, fy = self.get_cursor_pos_physical()
            if self.overlay:
                self.overlay.notify_click(fx, fy, button=button, count=count)

            press_sec = 0.008 if duration_ms == 0 else 0.022
            gap_sec = 0.015 if duration_ms == 0 else 0.032
            for i in range(max(1, count)):
                if self.overlay:
                    self.overlay.notify_press(True, fx, fy)
                self._send_inputs([self._mouse_input(down_flag)])
                self._precise_sleep(press_sec)
                self._send_inputs([self._mouse_input(up_flag)])
                if self.overlay:
                    self.overlay.notify_press(False, fx, fy)
                if i + 1 < count:
                    self._precise_sleep(gap_sec)
        finally:
            for vk in reversed(mod_vks):
                self._send_inputs([self._key_input(vk, up=True)])

        return self.get_cursor_pos_physical()

    def mouse_button(self, button: str, down: bool, px: int | None = None, py: int | None = None) -> tuple[int, int]:
        if px is not None and py is not None:
            self._glide_to(px, py)
            time.sleep(0.01)
        flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
        if button == "right":
            flag = MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
        elif button == "middle":
            flag = MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP
        self._send_inputs([self._mouse_input(flag)])
        return self.get_cursor_pos_physical()

    def drag(
        self,
        start_px: int | None,
        start_py: int | None,
        end_px: int,
        end_py: int,
        duration_ms: int = 260,
    ) -> tuple[int, int]:
        if start_px is not None and start_py is not None:
            self._glide_to(start_px, start_py, label="Sürükleme başlıyor")
            self._precise_sleep(0.018)
        sx, sy = self.get_cursor_pos_physical()
        if self.overlay:
            self.overlay.notify_press(True, sx, sy)
        self._send_inputs([self._mouse_input(MOUSEEVENTF_LEFTDOWN)])
        try:
            self._precise_sleep(0.024)
            steps = max(12, min(90, max(24, duration_ms) // 8))
            step_sec = max(0.004, (duration_ms / 1000.0) / steps)
            path = self._compute_human_glide_path(sx, sy, end_px, end_py, steps, arc_sign=1)
            for ix, iy in path:
                self._move_physical_instant(ix, iy)
                if self.overlay:
                    self.overlay.notify_cursor(ix, iy)
                self._precise_sleep(step_sec)
            self._precise_sleep(0.018)
        finally:
            self._send_inputs([self._mouse_input(MOUSEEVENTF_LEFTUP)])
            if self.overlay:
                self.overlay.notify_press(False, end_px, end_py)
        fx, fy = self.get_cursor_pos_physical()
        if self.overlay:
            self.overlay.notify_click(fx, fy, button="left", count=1)
        return fx, fy

    def scroll(
        self,
        direction: str,
        amount: int = 3,
        px: int | None = None,
        py: int | None = None,
        modifiers: str | None = None,
        duration_ms: int | None = None,
    ) -> tuple[int, int]:
        direction = direction.strip().lower()
        if direction not in {"up", "down", "left", "right"}:
            raise ValueError("scroll_direction must be one of: up, down, left, right")
        amount = max(1, min(100, int(amount)))

        mod_vks = self._parse_key_spec(modifiers) if modifiers else []
        try:
            for vk in mod_vks:
                self._send_inputs([self._key_input(vk, up=False)])
            if px is not None and py is not None:
                self._glide_to(px, py, duration_ms=duration_ms)
                if duration_ms != 0:
                    time.sleep(0.01)

            fx, fy = self.get_cursor_pos_physical()
            if self.overlay:
                self.overlay.notify_scroll(fx, fy, direction)

            if direction in {"up", "down"}:
                flag = MOUSEEVENTF_WHEEL
                delta = WHEEL_DELTA if direction == "up" else -WHEEL_DELTA
            else:
                flag = MOUSEEVENTF_HWHEEL
                delta = WHEEL_DELTA if direction == "right" else -WHEEL_DELTA

            step_sleep = 0.003 if duration_ms == 0 else 0.012
            for _ in range(amount):
                self._send_inputs([self._mouse_input(flag, mouse_data=delta & 0xFFFFFFFF)])
                if step_sleep > 0:
                    time.sleep(step_sleep)
        finally:
            for vk in reversed(mod_vks):
                self._send_inputs([self._key_input(vk, up=True)])

        return self.get_cursor_pos_physical()

    # -- Keyboard Controls (Unicode / Turkish-safe) -----------------------

    @classmethod
    def _key_input(cls, vk: int, up: bool = False) -> INPUT:
        scan = user32.MapVirtualKeyW(vk, 0)
        flags = KEYEVENTF_KEYUP if up else 0
        if vk in EXTENDED_VKS:
            flags |= KEYEVENTF_EXTENDEDKEY
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=AI_INPUT_TAG)
        return inp

    @classmethod
    def _unicode_char_inputs(cls, ch: str) -> list[INPUT]:
        if ch == "\n":
            return [cls._key_input(0x0D, up=False), cls._key_input(0x0D, up=True)]
        if ch == "\t":
            return [cls._key_input(0x09, up=False), cls._key_input(0x09, up=True)]

        utf16 = ch.encode("utf-16-le")
        inputs: list[INPUT] = []
        for idx in range(0, len(utf16), 2):
            code_unit = int.from_bytes(utf16[idx : idx + 2], "little")
            down = INPUT()
            down.type = INPUT_KEYBOARD
            down.union.ki = KEYBDINPUT(
                wVk=0, wScan=code_unit, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0
            )
            up = INPUT()
            up.type = INPUT_KEYBOARD
            up.union.ki = KEYBDINPUT(
                wVk=0,
                wScan=code_unit,
                dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=0,
            )
            inputs.extend([down, up])
        return inputs

    @classmethod
    def _resolve_single_vk(cls, token: str) -> int:
        raw = token.strip()
        if not raw:
            raise ValueError("Empty key token.")
        low = raw.lower()
        if low in KEY_MAP:
            return KEY_MAP[low]
        if len(raw) == 1:
            if "a" <= low <= "z":
                return ord(low.upper())
            if "0" <= raw <= "9":
                return ord(raw)
            vk_scan = user32.VkKeyScanW(raw)
            if vk_scan != -1:
                return vk_scan & 0xFF
        raise ValueError(f"Unknown key name: '{token}'")

    @classmethod
    def _parse_key_spec(cls, spec: str) -> list[int]:
        parts = [p for p in spec.replace("-", "+").split("+") if p]
        if not parts:
            raise ValueError("Key specification cannot be empty.")
        return [cls._resolve_single_vk(p) for p in parts]

    def type_text(self, text: str, interval_ms: int = 0) -> int:
        """Type arbitrary Unicode text (including Turkish characters and emojis)."""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if interval_ms <= 0:
            batch: list[INPUT] = []
            for ch in normalized:
                batch.extend(self._unicode_char_inputs(ch))
                if len(batch) >= 256:
                    self._send_inputs(batch)
                    batch.clear()
                    time.sleep(0.002)
            if batch:
                self._send_inputs(batch)
        else:
            delay = interval_ms / 1000.0
            for ch in normalized:
                self._send_inputs(self._unicode_char_inputs(ch))
                time.sleep(delay)
        return len(normalized)

    def send_key(self, key_spec: str, repeat: int = 1) -> None:
        vks = self._parse_key_spec(key_spec)
        if 0x1B in vks and self.on_synthetic_escape:
            self.on_synthetic_escape()
        repeat = max(1, min(100, int(repeat)))
        for idx in range(repeat):
            try:
                for vk in vks:
                    self._send_inputs([self._key_input(vk, up=False)])
                time.sleep(0.012)
            finally:
                for vk in reversed(vks):
                    self._send_inputs([self._key_input(vk, up=True)])
            if idx + 1 < repeat:
                time.sleep(0.02)

    def hold_key(self, key_spec: str, duration: float, stop_check: Any = None) -> float:
        vks = self._parse_key_spec(key_spec)
        if 0x1B in vks and self.on_synthetic_escape:
            self.on_synthetic_escape()
        duration = max(0.05, min(300.0, float(duration)))
        start = time.monotonic()
        try:
            for vk in vks:
                self._send_inputs([self._key_input(vk, up=False)])
            while True:
                if stop_check is not None:
                    stopped, msg = stop_check()
                    if stopped:
                        raise RuntimeError(msg)
                elapsed = time.monotonic() - start
                if elapsed >= duration:
                    break
                time.sleep(min(0.1, duration - elapsed))
        finally:
            for vk in reversed(vks):
                self._send_inputs([self._key_input(vk, up=True)])
        return round(time.monotonic() - start, 3)

    # -- Window Management & App Launching --------------------------------

    def get_window_info(self, hwnd: int, include_elevation: bool = True) -> dict[str, Any] | None:
        if not hwnd or not user32.IsWindow(hwnd):
            return None

        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, title_buf, len(title_buf))
        title = title_buf.value

        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe_path, proc_name, is_elevated = self.get_process_meta(
            pid.value, include_elevation=include_elevation
        )

        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        bounds_phys = {
            "left": int(rect.left),
            "top": int(rect.top),
            "width": int(rect.right - rect.left),
            "height": int(rect.bottom - rect.top),
        }

        center_x = rect.left + (rect.right - rect.left) // 2
        center_y = rect.top + (rect.bottom - rect.top) // 2
        disp_num = self.display_for_point(center_x, center_y)

        viewport = self.last_viewports_by_display.get(disp_num) or self.active_viewport
        bounds_shot = None
        if viewport and viewport.display_number == disp_num:
            sx1, sy1 = viewport.to_screenshot(rect.left, rect.top)
            sx2, sy2 = viewport.to_screenshot(rect.right, rect.bottom)
            bounds_shot = {"left": sx1, "top": sy1, "width": max(0, sx2 - sx1), "height": max(0, sy2 - sy1)}

        fg = user32.GetForegroundWindow()
        info: dict[str, Any] = {
            "hwnd": int(hwnd),
            "title": title,
            "pid": int(pid.value),
            "process_name": proc_name,
            "exe_path": exe_path,
            "display_number": disp_num,
            "bounds_physical": bounds_phys,
            "bounds_screenshot": bounds_shot,
            "is_minimized": bool(user32.IsIconic(hwnd)),
            "is_maximized": bool(user32.IsZoomed(hwnd)),
            "is_foreground": int(hwnd) == int(fg),
        }
        if include_elevation:
            info["is_elevated"] = is_elevated
        return info

    @staticmethod
    def _is_window_cloaked(hwnd: int) -> bool:
        if dwmapi is None:
            return False
        cloaked = wt.DWORD(0)
        res = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        return res == 0 and cloaked.value != 0

    def list_windows(
        self,
        include_minimized: bool = False,
        filter_text: str | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        enum_cb_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        needle = (filter_text or "").strip().lower()

        def _cb(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            if self._is_window_cloaked(hwnd):
                return True
            is_min = bool(user32.IsIconic(hwnd))
            if is_min and not include_minimized:
                return True

            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if (ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW):
                return True

            info = self.get_window_info(hwnd, include_elevation=False)
            if not info or not info["title"].strip():
                return True
            if not is_min and (info["bounds_physical"]["width"] < 20 or info["bounds_physical"]["height"] < 20):
                return True

            if needle:
                hay = f"{info['title']} {info['process_name']}".lower()
                if needle not in hay:
                    return True
            results.append(info)
            return True

        cb = enum_cb_type(_cb)
        user32.EnumWindows(cb, 0)
        return results

    def get_frontmost_window(self, include_elevation: bool = True) -> dict[str, Any] | None:
        fg = user32.GetForegroundWindow()
        return self.get_window_info(fg, include_elevation=include_elevation) if fg else None

    def _resolve_window_hwnd(self, target: str | int | None) -> int:
        if target is None:
            fg = user32.GetForegroundWindow()
            if not fg:
                raise RuntimeError("No active foreground window found.")
            return int(fg)

        if isinstance(target, int) or (isinstance(target, str) and target.strip().isdigit()):
            hwnd = int(target)
            if not user32.IsWindow(hwnd):
                raise ValueError(f"Window handle {hwnd} does not exist.")
            return hwnd

        needle = str(target).strip().lower()
        windows = self.list_windows(include_minimized=True)
        for win in windows:
            if needle in win["title"].lower() or needle in win["process_name"].lower():
                return int(win["hwnd"])
        raise ValueError(f"No matching open window found for '{target}'.")

    def focus_hwnd(self, hwnd: int) -> None:
        """Bring hwnd to foreground with a safe Windows foreground-lock fallback."""
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        fg = user32.GetForegroundWindow()
        if fg == hwnd:
            user32.BringWindowToTop(hwnd)
            return

        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)
        cur_tid = kernel32.GetCurrentThreadId()

        def _try_activate(attach_tid: int) -> bool:
            attached = False
            try:
                if attach_tid and attach_tid != cur_tid:
                    attached = bool(user32.AttachThreadInput(cur_tid, attach_tid, True))
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                return user32.GetForegroundWindow() == hwnd
            finally:
                if attached:
                    user32.AttachThreadInput(cur_tid, attach_tid, False)

        if _try_activate(fg_tid):
            return

        # Windows foreground-lock fallback: harmless extended Alt key-up + retry
        try:
            alt_up = INPUT()
            alt_up.type = INPUT_KEYBOARD
            alt_up.union.ki = KEYBDINPUT(
                wVk=0x12,  # VK_MENU
                wScan=user32.MapVirtualKeyW(0x12, 0),
                dwFlags=KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=AI_INPUT_TAG,
            )
            self._send_inputs([alt_up])
        except Exception:
            pass

        if target_tid and target_tid not in (0, fg_tid):
            if _try_activate(target_tid):
                return
        _try_activate(fg_tid)

    def manage_window(
        self,
        action: str,
        target: str | int | None = None,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        hwnd = self._resolve_window_hwnd(target)
        act = action.strip().lower()
        if act == "focus":
            self.focus_hwnd(hwnd)
        elif act == "minimize":
            user32.ShowWindow(hwnd, SW_SHOWMINIMIZED)
        elif act == "maximize":
            self.focus_hwnd(hwnd)
            user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
        elif act == "restore":
            user32.ShowWindow(hwnd, SW_RESTORE)
            self.focus_hwnd(hwnd)
        elif act == "close":
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            time.sleep(0.2)
            return {"closed_hwnd": hwnd, "still_exists": bool(user32.IsWindow(hwnd))}
        elif act == "move_resize":
            rect = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            nx = int(x) if x is not None else int(rect.left)
            ny = int(y) if y is not None else int(rect.top)
            nw = int(width) if width is not None else int(rect.right - rect.left)
            nh = int(height) if height is not None else int(rect.bottom - rect.top)
            user32.MoveWindow(hwnd, nx, ny, max(50, nw), max(50, nh), True)
        else:
            raise ValueError(f"Unsupported window action: '{action}'")

        time.sleep(0.15)
        return self.get_window_info(hwnd) or {"hwnd": hwnd}

    @staticmethod
    def _lookup_app_paths_registry(exe_name: str) -> str | None:
        candidates = [exe_name] if exe_name.lower().endswith(".exe") else [f"{exe_name}.exe", exe_name]
        subkey_base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for cand in candidates:
                try:
                    with winreg.OpenKey(root, f"{subkey_base}\\{cand}") as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and Path(val.strip('"')).exists():
                            return val.strip('"')
                except OSError:
                    continue
        return None

    @staticmethod
    def _lookup_start_menu_shortcut(query: str) -> Path | None:
        needle = query.strip().lower()
        roots = [
            Path(os.environ.get("ProgramData", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]
        exact_match: Path | None = None
        partial_match: Path | None = None
        for root in roots:
            if not root.exists():
                continue
            for lnk in root.rglob("*.lnk"):
                stem = lnk.stem.lower()
                if stem == needle:
                    exact_match = lnk
                    break
                if needle in stem and partial_match is None:
                    partial_match = lnk
            if exact_match:
                break
        return exact_match or partial_match

    @staticmethod
    def _lookup_uwp_app_id(query: str) -> str | None:
        ps_cmd = (
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return None
            items = json.loads(proc.stdout)
            if isinstance(items, dict):
                items = [items]
            needle = query.strip().lower()
            for item in items:
                if str(item.get("Name", "")).strip().lower() == needle:
                    return str(item["AppID"])
            for item in items:
                if needle in str(item.get("Name", "")).strip().lower():
                    return str(item["AppID"])
        except Exception:
            return None
        return None

    def open_application(
        self,
        name_or_path: str,
        args: list[str] | None = None,
        focus_if_running: bool = True,
        wait_seconds: float = 4.0,
    ) -> dict[str, Any]:
        """Launch or focus a Windows application cleanly by alias, executable path, shortcut, or UWP name."""
        raw = name_or_path.strip()
        low = raw.lower()
        alias = APP_ALIASES.get(low)
        proc_hint = alias["proc"] if alias else low

        if focus_if_running and not args:
            for win in self.list_windows(include_minimized=True):
                hay = f"{win['process_name']} {win['title']}".lower()
                if proc_hint in hay or low in hay:
                    self.focus_hwnd(int(win["hwnd"]))
                    time.sleep(0.15)
                    return {
                        "launched": False,
                        "focused_existing": True,
                        "window": self.get_window_info(int(win["hwnd"])),
                    }

        before_hwnds = {w["hwnd"] for w in self.list_windows(include_minimized=True)}
        launch_method = ""

        target_path = Path(raw)
        if target_path.exists():
            if target_path.suffix.lower() in {".lnk", ".url"} or target_path.is_dir():
                os.startfile(str(target_path))  # noqa: S606
                launch_method = "startfile"
            else:
                subprocess.Popen([str(target_path), *(args or [])])  # noqa: S603
                launch_method = "direct_exe"
        elif alias and "uri" in alias:
            os.startfile(alias["uri"])  # noqa: S606
            launch_method = "uri"
        else:
            exe_candidate = alias["exe"] if alias and "exe" in alias else raw
            found = shutil.which(exe_candidate) or self._lookup_app_paths_registry(exe_candidate)
            if found:
                subprocess.Popen([found, *(args or [])])  # noqa: S603
                launch_method = "resolved_exe"
            else:
                shortcut = self._lookup_start_menu_shortcut(raw)
                if shortcut is not None:
                    os.startfile(str(shortcut))  # noqa: S606
                    launch_method = "start_menu_shortcut"
                else:
                    uwp_id = self._lookup_uwp_app_id(raw)
                    if uwp_id:
                        os.startfile(f"shell:AppsFolder\\{uwp_id}")  # noqa: S606
                        launch_method = "uwp_appsfolder"
                    else:
                        raise FileNotFoundError(
                            f"Could not locate application '{name_or_path}' via PATH, App Paths, Start Menu, or StartApps."
                        )

        deadline = time.monotonic() + max(0.2, min(15.0, wait_seconds))
        new_win: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            time.sleep(0.10)
            windows = self.list_windows(include_minimized=False)
            for win in windows:
                if win["hwnd"] not in before_hwnds:
                    new_win = win
                    break
            if new_win is not None:
                break
            for win in windows:
                if proc_hint in win["process_name"].lower() or low in win["title"].lower():
                    new_win = win
                    break
            if new_win is not None:
                break

        return {
            "launched": True,
            "launch_method": launch_method,
            "window": new_win or self.get_frontmost_window(),
        }

    @staticmethod
    def get_window_class(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        n = user32.GetClassNameW(hwnd, buf, len(buf))
        return buf.value[:n] if n > 0 else ""

    def _find_open_file_dialog(self) -> dict[str, Any] | None:
        title_hints = ("aç", "open", "dosya", "file", "select", "seç", "choose", "upload")
        fg = int(user32.GetForegroundWindow() or 0)
        candidates = self.list_windows(include_minimized=False)
        ranked: list[tuple[int, dict[str, Any]]] = []
        for win in candidates:
            hwnd = int(win["hwnd"])
            cls = self.get_window_class(hwnd)
            t_low = (win.get("title") or "").strip().lower()
            is_fg = hwnd == fg
            if cls == "#32770":
                score = 0 if is_fg else 1
                if any(h in t_low for h in title_hints):
                    score -= 1
                ranked.append((score, {**win, "window_class": cls}))
            elif any(h == t_low or t_low.startswith(h + " ") or ("dosya" in t_low) for h in title_hints):
                ranked.append((2 if is_fg else 3, {**win, "window_class": cls}))
        if not ranked:
            return None
        ranked.sort(key=lambda pair: pair[0])
        return ranked[0][1]

    def _find_dialog_edit_center(self, dlg_hwnd: int) -> tuple[int, int] | None:
        edits: list[tuple[int, int, int]] = []
        cb_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def _cb(child: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(child):
                return True
            if self.get_window_class(int(child)).lower() == "edit":
                rect = wt.RECT()
                if user32.GetWindowRect(int(child), ctypes.byref(rect)):
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 40 and 10 <= h <= 80:
                        edits.append((rect.bottom, rect.left + w // 2, rect.top + h // 2))
            return True

        cb_fn = cb_type(_cb)
        user32.EnumChildWindows(dlg_hwnd, cb_fn, 0)
        if not edits:
            return None
        # Filename box in #32770 sits near the bottom of the dialog; address bar sits at the top.
        edits.sort(key=lambda row: row[0], reverse=True)
        return edits[0][1], edits[0][2]

    def accept_file_dialog(
        self,
        file_path: str,
        timeout_sec: float = 5.0,
        safety_check: Any = None,
    ) -> dict[str, Any]:
        """Wait for a Windows Open/File dialog (#32770), paste an absolute path, and confirm with Enter."""
        resolved_path = str(Path(file_path))
        if not Path(resolved_path).exists():
            raise FileNotFoundError(f"File does not exist for file_dialog: {resolved_path}")

        t0 = time.perf_counter()
        deadline = time.monotonic() + max(0.3, min(20.0, float(timeout_sec)))
        dlg: dict[str, Any] | None = None
        while True:
            dlg = self._find_open_file_dialog()
            if dlg is not None:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out after {timeout_sec:.1f}s waiting for Windows file dialog.")
            time.sleep(0.05)

        if safety_check is not None:
            safety_check(dlg)

        dlg_hwnd = int(dlg["hwnd"])
        self.focus_hwnd(dlg_hwnd)
        time.sleep(0.03)

        edit_pt = self._find_dialog_edit_center(dlg_hwnd)
        if edit_pt is not None:
            self.click(px=edit_pt[0], py=edit_pt[1], button="left", count=1, duration_ms=0)
            time.sleep(0.02)
        else:
            self.send_key("alt+n", repeat=1)
            time.sleep(0.03)

        self.set_clipboard_text(resolved_path)
        self.send_key("ctrl+a", repeat=1)
        time.sleep(0.015)
        self.send_key("ctrl+v", repeat=1)
        time.sleep(0.04)
        self.send_key("Return", repeat=1)

        close_deadline = time.monotonic() + 1.5
        closed = False
        while time.monotonic() < close_deadline:
            if not user32.IsWindow(dlg_hwnd) or not user32.IsWindowVisible(dlg_hwnd):
                closed = True
                break
            time.sleep(0.04)

        return {
            "ok": True,
            "action": "file_dialog",
            "path": resolved_path,
            "dialog_title": dlg.get("title"),
            "dialog_hwnd": dlg_hwnd,
            "closed": closed,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    # -- Native Unicode Clipboard -----------------------------------------

    @staticmethod
    def get_clipboard_text() -> str:
        for _ in range(8):
            if user32.OpenClipboard(None):
                try:
                    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                        return ""
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if not handle:
                        return ""
                    ptr = kernel32.GlobalLock(handle)
                    if not ptr:
                        return ""
                    try:
                        return ctypes.wstring_at(ptr)
                    finally:
                        kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
            time.sleep(0.025)
        raise RuntimeError("Failed to open Windows clipboard (locked by another application).")

    @staticmethod
    def set_clipboard_text(text: str) -> int:
        encoded = (text + "\0").encode("utf-16-le")
        for _ in range(8):
            if user32.OpenClipboard(None):
                hmem = None
                try:
                    user32.EmptyClipboard()
                    hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                    if not hmem:
                        raise MemoryError("GlobalAlloc failed for clipboard text.")
                    ptr = kernel32.GlobalLock(hmem)
                    if not ptr:
                        raise RuntimeError("GlobalLock failed for clipboard text.")
                    try:
                        ctypes.memmove(ptr, encoded, len(encoded))
                    finally:
                        kernel32.GlobalUnlock(hmem)
                    if not user32.SetClipboardData(CF_UNICODETEXT, hmem):
                        raise RuntimeError("SetClipboardData failed.")
                    hmem = None  # Clipboard now owns memory
                    return len(text)
                finally:
                    if hmem:
                        kernel32.GlobalFree(hmem)
                    user32.CloseClipboard()
            time.sleep(0.025)
        raise RuntimeError("Failed to open Windows clipboard for writing.")
