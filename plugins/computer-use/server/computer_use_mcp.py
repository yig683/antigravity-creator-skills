"""Claude Desktop-style high-speed Computer Use MCP server for Windows."""

from __future__ import annotations

import json
import math
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from overlay import DesktopOverlay  # noqa: E402
from safety import SafetyManager, resolve_data_dir  # noqa: E402
from uia_backend import find_element_target, inspect_window_ui  # noqa: E402
from win32_backend import Win32Backend  # noqa: E402

DATA_DIR = resolve_data_dir()
SAFETY = SafetyManager(DATA_DIR)


def _on_overlay_take_control() -> None:
    SAFETY.set_emergency_stop(True, "Kullanıcı kontrolü devraldı")
    SAFETY.audit("user_takeover", {"source": "overlay_button"}, ok=True)


def _on_overlay_resume_control() -> None:
    SAFETY.set_emergency_stop(False, "Kullanıcı kontrolü Antigravity'ye devretti")
    SAFETY.audit("user_handover", {"source": "overlay_button"}, ok=True)


def _on_user_interrupt(reason: str) -> None:
    SAFETY.set_emergency_stop(True, reason)
    OVERLAY.notify_stopped(reason)
    SAFETY.audit("user_takeover", {"source": "mouse_grab", "reason": reason}, ok=True)


OVERLAY = DesktopOverlay(
    enabled=SAFETY.policy.show_overlay,
    on_take_control=_on_overlay_take_control,
    on_resume_control=_on_overlay_resume_control,
)
WIN32 = Win32Backend(
    DATA_DIR / "screenshots",
    overlay=OVERLAY,
    smooth_cursor_ms=SAFETY.policy.smooth_cursor_ms,
    annotate_mode=SAFETY.policy.annotate_mode,
    on_synthetic_escape=SAFETY.mark_synthetic_escape,
    on_user_interrupt=_on_user_interrupt,
)
try:
    WIN32.sync_overlay_display(1)
except Exception:
    pass

INSTRUCTIONS = """\
High-speed Windows Computer Use MCP server modeled after Claude Desktop / Cowork.
Performance & UX rules:
1. Chain 2+ actions in ONE `batch` (`left_click`, `click_element`, `type`, `type_into`, `paste_text`, `file_dialog`, `key`, `wait_for`, `scroll`) with `fast=true` (instant pointer transitions inside batches).
2. Avoid double-turn image offload overhead: during intermediate steps set `screenshot_after=false, ui_after=true` (returns compact clickable UI elements + coordinates as text in 0 extra image `read_file` turns!). Use `screenshot_after=true` + `settle=true` + `marks=true` ONLY for initial orientation or final/visual checks.
3. Prefer `paste_text` (or `type_into`/`type` with `paste=true` or `mark_id`) for multi-line/long text instead of standalone `clipboard_set` turns, and use `file_dialog` for Windows Open/Aç pickers. `click_element` automatically scrolls offscreen UIA matches into view via `ScrollItemPattern` when supported.
4. `batch` accepts `{"action": "..."}`, `{"type": "..."}`, or shorthand `{"click_element": {"mark_id": 30}}`, `{"paste_text": "..."}`, `{"file_dialog": "C:\\path\\file.mp4"}`, plus aliases (`click`, `move`, `hotkey`/`press_key`, `sleep`, `drag`, `paste`, `fill`, `select_file`).
5. Never call a duplicate `screenshot` right after a tool with `screenshot_after=true` already returned one; default format is crisp 4:4:4 `jpeg`.
"""

_RECENT_CLICKS: deque[tuple[int, int, int, Any]] = deque(maxlen=6)
_CURSOR_POSITIONED_BY_MOVE: bool = False
_NO_TARGET_CLICK_STREAK: int = 0
_LAST_MARKS_ENABLED: bool = bool(SAFETY.policy.annotate_mode == "som")
_LAST_WIN32_ID: int = id(WIN32)

_LOOP_RADIUS_PX = 8.0
# Win32Backend._mean_fingerprint_diff returns mean per-pixel delta on [0..255]; 0.008 * 255 = 2.04.
_LOOP_FINGERPRINT_NORM_THRESHOLD = 0.008

mcp = MCPServer(
    "computer-use",
    title="Computer Use (Desktop Control)",
    instructions=INSTRUCTIONS,
)


# ---------------------------------------------------------------------------
# Shared Helpers
# ---------------------------------------------------------------------------


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _compact_window(win: dict[str, Any] | None) -> dict[str, Any] | None:
    if not win:
        return None
    return {
        "hwnd": win.get("hwnd"),
        "process": win.get("process_name"),
        "title": win.get("title"),
        "display": win.get("display_number"),
    }


def _format_screenshot_result(shot: dict[str, Any], extra: dict[str, Any] | None = None) -> list[Any]:
    vp = shot["viewport"]
    meta: dict[str, Any] = {
        "image_path": shot["image_path"],
        "display": vp["display_number"],
        "size": vp["image_size"],
        "scale": [vp["scale_x"], vp["scale_y"]],
        "cursor": shot["cursor_screenshot_pos"],
        "frontmost": _compact_window(shot.get("frontmost_window")),
    }
    if "displays" in shot:
        meta["displays"] = shot["displays"]
    if "settle" in shot:
        meta["settle"] = shot["settle"]
    if "marks" in shot:
        meta["marks"] = shot["marks"]
    if extra:
        meta.update(extra)
    return [Image(data=shot["image_bytes"], format=shot["image_format"]), _json_text(meta)]


def _make_marks_provider(enabled: bool):
    if not enabled:
        return None

    def _collect(viewport: Any) -> list[dict[str, Any]]:
        try:
            win = WIN32.get_frontmost_window(include_elevation=False)
            if not win or not win.get("hwnd"):
                return []
            info = inspect_window_ui(
                hwnd=int(win["hwnd"]),
                viewport=viewport,
                max_depth=5,
                max_elements=95,
                interactive_only=True,
                include_web_content=True,
                timeout_sec=0.8,
            )
            return list(info.get("elements") or [])
        except Exception:
            return []

    return _collect


def _clear_click_streak() -> None:
    """Clear recent click history and move-arming flags without changing marks preference."""
    global _CURSOR_POSITIONED_BY_MOVE, _NO_TARGET_CLICK_STREAK
    _RECENT_CLICKS.clear()
    _CURSOR_POSITIONED_BY_MOVE = False
    _NO_TARGET_CLICK_STREAK = 0


def _reset_click_state(*, reset_marks: bool = True) -> None:
    """Reset module-level loop/marks tracking state cleanly (for tests or WIN32 swaps)."""
    global _LAST_MARKS_ENABLED, _LAST_WIN32_ID
    _clear_click_streak()
    _LAST_WIN32_ID = id(WIN32)
    if reset_marks:
        _LAST_MARKS_ENABLED = bool(SAFETY.policy.annotate_mode == "som")


def _sync_runtime_win32() -> None:
    """Auto-reset module tracking if WIN32 instance was replaced in tests."""
    if id(WIN32) != _LAST_WIN32_ID:
        _reset_click_state(reset_marks=True)


def _active_display_number(display_number: int | None = None) -> int:
    if display_number is not None:
        return int(display_number)
    if WIN32.active_viewport is not None:
        return int(WIN32.active_viewport.display_number)
    return 1


def _resolve_marks_flag(marks: bool | None, annotate: str | None = None) -> bool:
    """Resolve whether Set-of-Mark badges should be drawn and persist explicit user/agent choices."""
    global _LAST_MARKS_ENABLED
    _sync_runtime_win32()
    if marks is not None:
        _LAST_MARKS_ENABLED = bool(marks)
        return bool(marks or annotate == "som")
    if annotate == "som":
        _LAST_MARKS_ENABLED = True
        return True
    if annotate in {"none", "grid"}:
        return False
    return bool(_LAST_MARKS_ENABLED or SAFETY.policy.annotate_mode == "som")


def _capture_display(
    display_number: int | None = 1,
    max_width: int = 1280,
    max_height: int = 800,
    show_cursor: bool = True,
    fmt: str = "jpeg",
    settle: bool = False,
    settle_timeout: float = 5.0,
    marks: bool | None = None,
    annotate: str | None = None,
) -> dict[str, Any]:
    eff_annotate = annotate if annotate in {"none", "grid", "som"} else SAFETY.policy.annotate_mode
    use_marks = _resolve_marks_flag(marks, annotate=annotate)
    provider = _make_marks_provider(use_marks)
    if settle:
        OVERLAY.notify_action("Ekran durulması bekleniyor...", state="thinking")
        return WIN32.capture_screenshot_when_stable(
            display_number=display_number,
            max_width=max_width,
            max_height=max_height,
            show_cursor=show_cursor,
            fmt=fmt,
            timeout_sec=settle_timeout,
            on_poll=_abort_if_stopped,
            annotate_mode=eff_annotate,
            marks_provider=provider,
        )
    return WIN32.capture_screenshot(
        display_number=display_number,
        max_width=max_width,
        max_height=max_height,
        show_cursor=show_cursor,
        fmt=fmt,
        annotate_mode=eff_annotate,
        marks_provider=provider,
    )


def _abort_if_stopped() -> None:
    SAFETY.mark_ai_activity()
    stopped, msg = SAFETY.is_emergency_stopped()
    if stopped:
        OVERLAY.notify_stopped(msg)
        raise ToolError(msg)


def _parse_xy(coordinate: list[int] | None, required: bool = False) -> tuple[int | None, int | None]:
    if coordinate is None:
        if required:
            raise ToolError("coordinate [x, y] is required for this action.")
        return None, None
    if len(coordinate) != 2:
        raise ToolError("coordinate must be a 2-element list [x, y].")
    return int(coordinate[0]), int(coordinate[1])


def _physical_to_screenshot_xy(px: int, py: int, display_number: int | None = None) -> tuple[int, int]:
    try:
        vp = (
            WIN32.active_viewport
            if (display_number is None and WIN32.active_viewport is not None)
            else WIN32._ensure_viewport(display_number)
        )
        return vp.to_screenshot(px, py)
    except Exception:
        return int(px), int(py)


def _capture_fingerprint(display_number: int | None = None) -> tuple[int, Any]:
    target_disp = _active_display_number(display_number)
    try:
        if hasattr(WIN32, "_display_rect"):
            disp_num, left, top, src_w, src_h = WIN32._display_rect(target_disp)
        elif WIN32.active_viewport is not None:
            vp = WIN32.active_viewport
            disp_num, left, top, src_w, src_h = vp.display_number, vp.src_left, vp.src_top, vp.src_width, vp.src_height
        else:
            return target_disp, None
        img = WIN32.capture_region_pil(left, top, src_w, src_h)
        return int(disp_num), WIN32._frame_fingerprint(img)
    except Exception:
        return target_disp, None


def _guard_input(
    tool_name: str,
    args: dict[str, Any],
    key_combo: str | None = None,
) -> dict[str, Any] | None:
    SAFETY.mark_ai_activity()
    frontmost = WIN32.get_frontmost_window(include_elevation=True)
    allowed, reason = SAFETY.check_input_allowed(
        action_name=tool_name,
        frontmost=frontmost,
        current_elevated=WIN32.current_elevated,
        key_combo=key_combo,
    )
    if not allowed:
        OVERLAY.notify_stopped(reason)
        SAFETY.audit(tool_name, args, ok=False, frontmost=frontmost, error=reason)
        raise ToolError(reason)
    return frontmost


def _finish_input(
    tool_name: str,
    args: dict[str, Any],
    frontmost: dict[str, Any] | None,
    payload: dict[str, Any],
    screenshot_after: bool = False,
    display_number: int | None = None,
    redact_text: bool = False,
    delay_ms: int = 75,
    marks: bool | None = None,
    settle: bool = False,
    settle_timeout: float = 5.0,
    extra_meta: dict[str, Any] | None = None,
) -> list[Any]:
    SAFETY.audit(tool_name, args, ok=True, frontmost=frontmost, redact_text=redact_text)
    if marks is not None:
        _resolve_marks_flag(marks)
    if screenshot_after:
        if not settle and delay_ms > 0:
            time.sleep(min(2.0, delay_ms / 1000.0))
        target_disp = _active_display_number(display_number)
        resolved_marks = _resolve_marks_flag(marks)
        shot = _capture_display(
            display_number=target_disp,
            settle=settle,
            settle_timeout=settle_timeout,
            marks=resolved_marks,
        )
        OVERLAY.notify_thinking("Ekran inceleniyor...")
        extra: dict[str, Any] = {"action_result": payload}
        if extra_meta:
            extra.update(extra_meta)
        return _format_screenshot_result(shot, extra=extra)
    OVERLAY.notify_thinking("Sonraki adım bekleniyor...")
    return [_json_text(payload)]


def _resolve_element_for_window(
    name: str,
    target: str | None = None,
    control_type: str | None = None,
    interactive_only: bool = True,
    timeout_sec: float = 1.2,
    display_number: int | None = None,
) -> dict[str, Any]:
    hwnd = WIN32._resolve_window_hwnd(target)
    win = WIN32.get_window_info(hwnd, include_elevation=False)
    if win:
        blocked, block_reason = SAFETY.is_blocked_target(win["process_name"], win["title"])
        if blocked:
            OVERLAY.notify_stopped(block_reason)
            raise ToolError(block_reason)
    disp = int(display_number or (win or {}).get("display_number") or 1)
    viewport = WIN32._ensure_viewport(disp)
    found = find_element_target(
        hwnd=hwnd,
        viewport=viewport,
        name=name,
        control_type=control_type,
        interactive_only=interactive_only,
        timeout_sec=timeout_sec,
    )
    if isinstance(found, dict) and found.get("found") is False:
        detail = found.get("detail") or (
            f"Found {found.get('offscreen_matches', 0)} offscreen match(es) — scroll to bring target into view."
        )
        raise RuntimeError(
            f"UI element '{name}' is offscreen in window"
            f"{' ' + target if target else ''}: {detail}"
        )
    if not found or "physical_center" not in found:
        raise RuntimeError(
            f"UI element '{name}' not found in window"
            f"{' ' + target if target else ''}. Use screenshot(marks=true) or inspect_ui to verify exact label."
        )
    return found


def _resolve_action_target(
    *,
    coordinate: list[int] | None = None,
    x: int | None = None,
    y: int | None = None,
    mark_id: int | None = None,
    name: str | None = None,
    control_type: str | None = None,
    target: str | None = None,
    display_number: int | None = None,
    coordinate_space: Literal["screenshot", "physical"] = "screenshot",
    required: bool = False,
    interactive_only: bool = True,
) -> dict[str, Any]:
    """Resolve coordinate, x/y, mark_id, or UI element name via one unified code path."""
    clean_name = name.strip() if isinstance(name, str) and name.strip() else None

    if coordinate is not None:
        sx, sy = _parse_xy(coordinate, required=False)
        assert sx is not None and sy is not None
        px, py = WIN32.resolve_coordinate(sx, sy, display_number=display_number, coordinate_space=coordinate_space)
        norm_sx, norm_sy = (
            _physical_to_screenshot_xy(px, py, display_number) if coordinate_space == "physical" else (sx, sy)
        )
        return {
            "has_target": True,
            "source": "coordinate",
            "sx": norm_sx,
            "sy": norm_sy,
            "px": px,
            "py": py,
            "mark": None,
            "element": None,
        }

    if x is not None or y is not None:
        if x is None or y is None:
            raise ToolError("Both 'x' and 'y' must be provided together (or pass coordinate=[x, y]).")
        sx, sy = int(x), int(y)
        px, py = WIN32.resolve_coordinate(sx, sy, display_number=display_number, coordinate_space=coordinate_space)
        norm_sx, norm_sy = (
            _physical_to_screenshot_xy(px, py, display_number) if coordinate_space == "physical" else (sx, sy)
        )
        return {
            "has_target": True,
            "source": "xy",
            "sx": norm_sx,
            "sy": norm_sy,
            "px": px,
            "py": py,
            "mark": None,
            "element": None,
        }

    if mark_id is not None:
        mid = int(mark_id)
        mark = WIN32.last_marks.get(mid)
        if not mark:
            if not WIN32.last_marks:
                raise ToolError(
                    f"Unknown or stale mark_id={mid}: no active marks cached. "
                    "Call screenshot(marks=true) first to generate Set-of-Mark badges."
                )
            avail = sorted(WIN32.last_marks.keys())
            raise ToolError(
                f"Unknown or stale mark_id={mid} (valid marks: {avail[0]}..{avail[-1]}). "
                "Call screenshot(marks=true) to refresh Set-of-Mark badges."
            )
        center = mark.get("center")
        if not center or len(center) != 2:
            raise ToolError(f"Cached mark_id={mid} is missing center coordinates. Call screenshot(marks=true) first.")
        sx, sy = int(center[0]), int(center[1])
        px, py = WIN32.resolve_coordinate(sx, sy, display_number=display_number, coordinate_space="screenshot")
        return {
            "has_target": True,
            "source": "mark_id",
            "sx": sx,
            "sy": sy,
            "px": px,
            "py": py,
            "mark": mark,
            "element": None,
        }

    if clean_name is not None:
        try:
            el = _resolve_element_for_window(
                name=clean_name,
                target=target,
                control_type=control_type,
                interactive_only=interactive_only,
                display_number=display_number,
            )
        except RuntimeError as exc:
            raise ToolError(str(exc)) from exc
        px, py = int(el["physical_center"][0]), int(el["physical_center"][1])
        center = el.get("center")
        if center and len(center) == 2:
            sx, sy = int(center[0]), int(center[1])
        else:
            sx, sy = _physical_to_screenshot_xy(px, py, display_number)
        return {
            "has_target": True,
            "source": "name",
            "sx": sx,
            "sy": sy,
            "px": px,
            "py": py,
            "mark": None,
            "element": el,
        }

    if required:
        raise ToolError("A target (coordinate, x/y, mark_id, or name) is required for this action.")
    return {
        "has_target": False,
        "source": None,
        "sx": None,
        "sy": None,
        "px": None,
        "py": None,
        "mark": None,
        "element": None,
    }


def _prepare_click_or_detect_loop(
    tool_name: str,
    sx: int | None,
    sy: int | None,
    has_explicit_target: bool,
    display_number: int | None = None,
    *,
    fast_batch: bool = False,
) -> tuple[dict[str, Any] | None, tuple[int, int, int, Any] | None]:
    """Prevent blind targetless clicks and 3rd+ stationary no-effect repeat-click loops."""
    global _CURSOR_POSITIONED_BY_MOVE, _NO_TARGET_CLICK_STREAK
    _sync_runtime_win32()

    if not has_explicit_target and not _CURSOR_POSITIONED_BY_MOVE:
        _NO_TARGET_CLICK_STREAK += 1
        return {
            "ok": False,
            "action": tool_name,
            "missing_target": True,
            "loop_detected": _NO_TARGET_CLICK_STREAK >= 2,
            "error": (
                f"No click target provided to {tool_name} (pass coordinate, x/y, mark_id, or name — "
                "or call mouse_move first). Inspect the returned marks screenshot to choose a valid target."
            ),
        }, None

    _CURSOR_POSITIONED_BY_MOVE = False
    _NO_TARGET_CLICK_STREAK = 0

    if sx is None or sy is None:
        cpx, cpy = WIN32.get_cursor_pos_physical()
        sx, sy = _physical_to_screenshot_xy(cpx, cpy, display_number)

    if fast_batch and has_explicit_target:
        disp_num = _active_display_number(display_number)
        if not _RECENT_CLICKS or _RECENT_CLICKS[-1][0] != disp_num or (
            math.hypot(sx - _RECENT_CLICKS[-1][1], sy - _RECENT_CLICKS[-1][2]) > _LOOP_RADIUS_PX
        ):
            _RECENT_CLICKS.clear()
            return None, (disp_num, sx, sy, None)

    disp_num, cur_fp = _capture_fingerprint(display_number)
    if _RECENT_CLICKS and _RECENT_CLICKS[-1][0] != disp_num:
        _RECENT_CLICKS.clear()

    if cur_fp is not None and _RECENT_CLICKS:
        prev_fp = _RECENT_CLICKS[-1][3]
        if prev_fp is not None:
            raw_diff = float(WIN32._mean_fingerprint_diff(prev_fp, cur_fp))
            norm_diff = raw_diff / 255.0
            if norm_diff >= _LOOP_FINGERPRINT_NORM_THRESHOLD:
                _RECENT_CLICKS.clear()
            elif len(_RECENT_CLICKS) >= 2 and all(
                math.hypot(sx - px_prev, sy - py_prev) <= _LOOP_RADIUS_PX
                for _, px_prev, py_prev, _ in list(_RECENT_CLICKS)[-2:]
            ):
                return {
                    "ok": False,
                    "action": tool_name,
                    "loop_detected": True,
                    "repeated_pos": [sx, sy],
                    "fingerprint_diff": round(norm_diff, 5),
                    "error": (
                        f"Stationary repeat-click loop detected: {tool_name} targeted [{sx}, {sy}] "
                        f"{len(_RECENT_CLICKS) + 1} times with no visual screen change "
                        f"(diff={norm_diff:.4f} < {_LOOP_FINGERPRINT_NORM_THRESHOLD}). "
                        "Do not click the same spot again — inspect the returned marks screenshot, "
                        "zoom in with zoom(), use click_element(name=...) / mark_id, scroll, or pick a new coordinate."
                    ),
                }, None
        if _RECENT_CLICKS and math.hypot(sx - _RECENT_CLICKS[-1][1], sy - _RECENT_CLICKS[-1][2]) > _LOOP_RADIUS_PX:
            _RECENT_CLICKS.clear()

    return None, (disp_num, sx, sy, cur_fp)


def _capture_loop_recovery_result(
    err_payload: dict[str, Any],
    display_number: int | None = None,
    settle: bool = False,
) -> list[Any]:
    target_disp = _active_display_number(display_number)
    try:
        shot = _capture_display(
            display_number=target_disp,
            settle=settle,
            marks=True,
        )
        OVERLAY.notify_thinking("Hedef yenileniyor...")
        return _format_screenshot_result(shot, extra={**err_payload, "action_result": err_payload})
    except Exception:
        return [_json_text(err_payload)]


def _run_click_action(
    tool_name: str,
    button: str,
    count: int,
    *,
    coordinate: list[int] | None = None,
    x: int | None = None,
    y: int | None = None,
    mark_id: int | None = None,
    name: str | None = None,
    modifiers: str | None = None,
    display_number: int | None = None,
    coordinate_space: Literal["screenshot", "physical"] = "screenshot",
    frontmost: dict[str, Any] | None = None,
    args: dict[str, Any] | None = None,
    duration_ms: int | None = None,
    fast_batch: bool = False,
) -> dict[str, Any]:
    resolved = _resolve_action_target(
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        display_number=display_number,
        coordinate_space=coordinate_space,
        required=False,
    )
    loop_err, click_record = _prepare_click_or_detect_loop(
        tool_name=tool_name,
        sx=resolved["sx"],
        sy=resolved["sy"],
        has_explicit_target=bool(resolved["has_target"]),
        display_number=display_number,
        fast_batch=fast_batch,
    )
    if loop_err is not None:
        SAFETY.audit(tool_name, args or {}, ok=False, frontmost=frontmost, error=loop_err["error"])
        return loop_err

    if resolved["sx"] is not None and resolved["sy"] is not None:
        OVERLAY.notify_action(f"Tıklanıyor [{resolved['sx']}, {resolved['sy']}]", state="working")
    else:
        OVERLAY.notify_action("Mevcut konumda tıklanıyor", state="working")

    click_kwargs: dict[str, Any] = {
        "px": resolved["px"],
        "py": resolved["py"],
        "button": button,
        "count": count,
        "modifiers": modifiers,
    }
    if duration_ms is not None:
        click_kwargs["duration_ms"] = int(duration_ms)
    final_px, final_py = WIN32.click(**click_kwargs)
    if click_record is not None:
        _RECENT_CLICKS.append(click_record)

    payload: dict[str, Any] = {
        "ok": True,
        "action": tool_name,
        "physical_pos": [final_px, final_py],
        "frontmost": _compact_window(WIN32.get_frontmost_window(include_elevation=False)),
    }
    if resolved["mark"] is not None:
        payload["mark"] = resolved["mark"]
    elif resolved["element"] is not None:
        el = resolved["element"]
        payload["element"] = {"name": el.get("name"), "type": el.get("type"), "center": el.get("center")}
    return payload


def _perform_click(
    tool_name: str,
    button: str,
    count: int,
    coordinate: list[int] | None,
    modifiers: str | None,
    display_number: int | None,
    coordinate_space: Literal["screenshot", "physical"],
    screenshot_after: bool,
    *,
    x: int | None = None,
    y: int | None = None,
    mark_id: int | None = None,
    name: str | None = None,
    marks: bool | None = None,
    settle: bool = False,
) -> list[Any]:
    args = {
        "coordinate": coordinate,
        "x": x,
        "y": y,
        "mark_id": mark_id,
        "name": name,
        "modifiers": modifiers,
        "display_number": display_number,
        "coordinate_space": coordinate_space,
    }
    frontmost = _guard_input(tool_name, args)
    payload = _run_click_action(
        tool_name,
        button,
        count,
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        modifiers=modifiers,
        display_number=display_number,
        coordinate_space=coordinate_space,
        frontmost=frontmost,
        args=args,
    )
    if payload.get("ok") is False:
        return _capture_loop_recovery_result(payload, display_number=display_number, settle=settle)
    return _finish_input(
        tool_name,
        args,
        frontmost,
        payload,
        screenshot_after=screenshot_after,
        display_number=display_number,
        marks=marks,
        settle=settle,
    )


def _run_move_action(
    *,
    coordinate: list[int] | None = None,
    x: int | None = None,
    y: int | None = None,
    mark_id: int | None = None,
    name: str | None = None,
    duration_ms: int = 0,
    display_number: int | None = None,
    coordinate_space: Literal["screenshot", "physical"] = "screenshot",
) -> dict[str, Any]:
    global _CURSOR_POSITIONED_BY_MOVE, _NO_TARGET_CLICK_STREAK
    _sync_runtime_win32()
    resolved = _resolve_action_target(
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        display_number=display_number,
        coordinate_space=coordinate_space,
        required=True,
    )
    assert resolved["px"] is not None and resolved["py"] is not None
    OVERLAY.notify_action(f"İmleç taşınıyor [{resolved['sx']}, {resolved['sy']}]", state="working")
    final_px, final_py = WIN32.move_mouse(resolved["px"], resolved["py"], duration_ms=int(duration_ms))
    _CURSOR_POSITIONED_BY_MOVE = True
    _NO_TARGET_CLICK_STREAK = 0
    return {"action": "mouse_move", "ok": True, "physical_pos": [final_px, final_py]}


def _run_mouse_button_action(
    action_name: str,
    down: bool,
    *,
    coordinate: list[int] | None = None,
    x: int | None = None,
    y: int | None = None,
    mark_id: int | None = None,
    name: str | None = None,
    display_number: int | None = None,
    coordinate_space: Literal["screenshot", "physical"] = "screenshot",
) -> dict[str, Any]:
    global _CURSOR_POSITIONED_BY_MOVE
    _sync_runtime_win32()
    resolved = _resolve_action_target(
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        display_number=display_number,
        coordinate_space=coordinate_space,
        required=False,
    )
    final_px, final_py = WIN32.mouse_button("left", down=down, px=resolved["px"], py=resolved["py"])
    _CURSOR_POSITIONED_BY_MOVE = False
    return {"action": action_name, "ok": True, "physical_pos": [final_px, final_py]}


def _run_drag_action(
    *,
    coordinate: list[int] | None = None,
    x: int | None = None,
    y: int | None = None,
    mark_id: int | None = None,
    name: str | None = None,
    start_coordinate: list[int] | None = None,
    start_x: int | None = None,
    start_y: int | None = None,
    start_mark_id: int | None = None,
    start_name: str | None = None,
    duration_ms: int = 300,
    display_number: int | None = None,
    coordinate_space: Literal["screenshot", "physical"] = "screenshot",
) -> dict[str, Any]:
    _sync_runtime_win32()
    end_t = _resolve_action_target(
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        display_number=display_number,
        coordinate_space=coordinate_space,
        required=True,
    )
    start_t = _resolve_action_target(
        coordinate=start_coordinate,
        x=start_x,
        y=start_y,
        mark_id=start_mark_id,
        name=start_name,
        display_number=display_number,
        coordinate_space=coordinate_space,
        required=False,
    )
    assert end_t["px"] is not None and end_t["py"] is not None
    OVERLAY.notify_action(f"Sürükleniyor -> [{end_t['sx']}, {end_t['sy']}]", state="working")
    final_px, final_py = WIN32.drag(
        start_t["px"],
        start_t["py"],
        end_t["px"],
        end_t["py"],
        duration_ms=int(duration_ms),
    )
    _clear_click_streak()
    return {"action": "left_click_drag", "ok": True, "physical_pos": [final_px, final_py]}


def _run_scroll_action(
    *,
    scroll_direction: str,
    scroll_amount: int = 3,
    coordinate: list[int] | None = None,
    x: int | None = None,
    y: int | None = None,
    mark_id: int | None = None,
    name: str | None = None,
    modifiers: str | None = None,
    display_number: int | None = None,
    coordinate_space: Literal["screenshot", "physical"] = "screenshot",
    duration_ms: int | None = None,
) -> dict[str, Any]:
    _sync_runtime_win32()
    resolved = _resolve_action_target(
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        display_number=display_number,
        coordinate_space=coordinate_space,
        required=False,
    )
    OVERLAY.notify_action(f"Kaydırılıyor: {scroll_direction}", state="working")
    scroll_kwargs: dict[str, Any] = {
        "direction": scroll_direction,
        "amount": int(scroll_amount),
        "px": resolved["px"],
        "py": resolved["py"],
        "modifiers": modifiers,
    }
    if duration_ms is not None:
        scroll_kwargs["duration_ms"] = int(duration_ms)
    final_px, final_py = WIN32.scroll(**scroll_kwargs)
    _clear_click_streak()
    return {
        "ok": True,
        "action": "scroll",
        "scroll_direction": scroll_direction,
        "scroll_amount": int(scroll_amount),
        "physical_pos": [final_px, final_py],
    }


def _sleep_interruptible(seconds: float) -> None:
    deadline = time.monotonic() + max(0.0, float(seconds))
    while True:
        stopped, msg = SAFETY.is_emergency_stopped()
        if stopped:
            OVERLAY.notify_stopped(msg)
            raise ToolError(msg)
        rem = deadline - time.monotonic()
        if rem <= 0:
            break
        time.sleep(min(0.2, rem))


def _click_element_action(
    name: str | None = None,
    control_type: str | None = None,
    target: str | None = None,
    button: str = "left",
    count: int = 1,
    modifiers: str | None = None,
    mark_id: int | None = None,
    display_number: int | None = None,
    duration_ms: int | None = None,
    fast_batch: bool = False,
) -> dict[str, Any]:
    clean_name = name.strip() if isinstance(name, str) and name.strip() else None
    if mark_id is None and clean_name is None:
        raise ValueError("click_element requires 'name' or 'mark_id'.")

    label = f"#{mark_id}" if mark_id is not None else f'"{clean_name}"'
    OVERLAY.notify_action(f"Öğe aranıyor: {label}", state="working")
    resolved = _resolve_action_target(
        mark_id=mark_id,
        name=clean_name,
        control_type=control_type,
        target=target,
        display_number=display_number,
        required=True,
    )
    loop_err, click_record = _prepare_click_or_detect_loop(
        tool_name="click_element",
        sx=resolved["sx"],
        sy=resolved["sy"],
        has_explicit_target=True,
        display_number=display_number,
        fast_batch=fast_batch,
    )
    if loop_err is not None:
        return loop_err

    el = resolved["element"]
    mark = resolved["mark"]
    disp_label = (el or {}).get("name") or (mark or {}).get("name") or clean_name or f"mark #{mark_id}"
    OVERLAY.notify_action(f'Tıklanıyor: "{disp_label}"', state="working")
    click_kwargs: dict[str, Any] = {
        "px": resolved["px"],
        "py": resolved["py"],
        "button": button,
        "count": count,
        "modifiers": modifiers,
    }
    if duration_ms is not None:
        click_kwargs["duration_ms"] = int(duration_ms)
    fx, fy = WIN32.click(**click_kwargs)
    if click_record is not None:
        _RECENT_CLICKS.append(click_record)

    if el is not None:
        el_meta: dict[str, Any] = {"name": el.get("name"), "type": el.get("type"), "center": el.get("center")}
        if el.get("scrolled_into_view"):
            el_meta["scrolled_into_view"] = True
    else:
        el_meta = {
            "id": mark.get("id", int(mark_id)),
            "name": mark.get("name"),
            "type": mark.get("type"),
            "center": mark.get("center"),
        }
    return {
        "action": "click_element",
        "ok": True,
        "element": el_meta,
        "physical_pos": [fx, fy],
    }


def _send_text_fast(
    text: str,
    *,
    interval_ms: int = 0,
    sensitive: bool = False,
    paste: bool | Literal["auto"] = "auto",
) -> tuple[int, str]:
    """Input Unicode text via fast clipboard paste for long/multiline non-sensitive strings or direct SendInput."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    should_paste = (
        not sensitive
        and interval_ms <= 0
        and len(normalized) > 0
        and (paste is True or (paste == "auto" and ("\n" in normalized or len(normalized) > 48)))
    )
    if should_paste:
        try:
            WIN32.set_clipboard_text(normalized)
            time.sleep(0.01)
            WIN32.send_key("ctrl+v", repeat=1)
            return len(normalized), "clipboard"
        except Exception:
            pass
    chars = WIN32.type_text(normalized, interval_ms=int(interval_ms))
    return chars, "sendinput"


def _run_type_action(
    *,
    text: str,
    interval_ms: int = 0,
    submit_enter: bool = False,
    sensitive: bool = False,
    paste: bool | Literal["auto"] = "auto",
) -> dict[str, Any]:
    global _CURSOR_POSITIONED_BY_MOVE
    _sync_runtime_win32()
    _CURSOR_POSITIONED_BY_MOVE = False
    preview = "•••••" if sensitive else (text[:18] + ("..." if len(text) > 18 else ""))
    OVERLAY.notify_action(f'Yazılıyor: "{preview}"', state="working")
    chars, method = _send_text_fast(text, interval_ms=int(interval_ms), sensitive=sensitive, paste=paste)
    if submit_enter:
        time.sleep(0.015)
        WIN32.send_key("Return", repeat=1)
    return {
        "action": "type",
        "ok": True,
        "method": method,
        "characters_typed": chars,
        "submitted_enter": bool(submit_enter),
    }


def _run_key_action(*, key_spec: str, repeat: int = 1) -> dict[str, Any]:
    global _CURSOR_POSITIONED_BY_MOVE
    _sync_runtime_win32()
    _CURSOR_POSITIONED_BY_MOVE = False
    OVERLAY.notify_action(f"Kısayol: {key_spec}", state="working")
    WIN32.send_key(key_spec, repeat=int(repeat))
    return {"action": "key", "ok": True, "key": key_spec, "repeat": int(repeat)}


def _run_hold_key_action(*, key_spec: str, duration: float) -> dict[str, Any]:
    global _CURSOR_POSITIONED_BY_MOVE
    _sync_runtime_win32()
    _CURSOR_POSITIONED_BY_MOVE = False
    OVERLAY.notify_action(f"Tuş tutuluyor: {key_spec}", state="working")
    held = WIN32.hold_key(key_spec, duration=float(duration), stop_check=SAFETY.is_emergency_stopped)
    return {"action": "hold_key", "ok": True, "key": key_spec, "held_seconds": held}


def _type_into_action(
    name: str | None = None,
    text: str = "",
    control_type: str | None = None,
    target: str | None = None,
    clear: bool = False,
    submit_enter: bool = False,
    sensitive: bool = False,
    interval_ms: int = 0,
    mark_id: int | None = None,
    coordinate: list[int] | None = None,
    x: int | None = None,
    y: int | None = None,
    display_number: int | None = None,
    coordinate_space: Literal["screenshot", "physical"] = "screenshot",
    paste: bool | Literal["auto"] = "auto",
    duration_ms: int | None = None,
) -> dict[str, Any]:
    clean_name = name.strip() if isinstance(name, str) and name.strip() else None
    label = f"#{mark_id}" if mark_id is not None else (f'"{clean_name}"' if clean_name else f"[{x}, {y}]")
    OVERLAY.notify_action(f"Alan bulunuyor: {label}", state="working")
    resolved = _resolve_action_target(
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=clean_name,
        control_type=control_type,
        target=target,
        display_number=display_number,
        coordinate_space=coordinate_space,
        required=True,
    )
    el = resolved["element"]
    mark = resolved["mark"]
    disp_label = (el or {}).get("name") or (mark or {}).get("name") or label
    preview = "•••••" if sensitive else (text[:18] + ("..." if len(text) > 18 else ""))
    OVERLAY.notify_action(f'Yazılıyor ({disp_label}): "{preview}"', state="working")
    click_kwargs: dict[str, Any] = {"px": resolved["px"], "py": resolved["py"], "button": "left", "count": 1}
    if duration_ms is not None:
        click_kwargs["duration_ms"] = int(duration_ms)
    WIN32.click(**click_kwargs)
    if clear:
        time.sleep(0.015)
        WIN32.send_key("ctrl+a", repeat=1)
        time.sleep(0.015)
    chars, method = _send_text_fast(text, interval_ms=interval_ms, sensitive=sensitive, paste=paste)
    if submit_enter:
        time.sleep(0.015)
        WIN32.send_key("Return", repeat=1)
    _clear_click_streak()
    el_meta = (
        {"name": el.get("name"), "type": el.get("type"), "center": el.get("center")}
        if el is not None
        else (
            {"id": mark.get("id", mark_id), "name": mark.get("name"), "type": mark.get("type"), "center": mark.get("center")}
            if mark is not None
            else {"center": [resolved["sx"], resolved["sy"]]}
        )
    )
    return {
        "action": "type_into",
        "ok": True,
        "method": method,
        "element": el_meta,
        "characters_typed": chars,
    }


def _run_paste_text_action(
    *,
    text: str | None = None,
    coordinate: list[int] | None = None,
    x: int | None = None,
    y: int | None = None,
    mark_id: int | None = None,
    name: str | None = None,
    control_type: str | None = None,
    target: str | None = None,
    clear: bool | None = None,
    submit_enter: bool = False,
    sensitive: bool = False,
    display_number: int | None = None,
    coordinate_space: Literal["screenshot", "physical"] = "screenshot",
    duration_ms: int | None = None,
) -> dict[str, Any]:
    _sync_runtime_win32()
    resolved = _resolve_action_target(
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        control_type=control_type,
        target=target,
        display_number=display_number,
        coordinate_space=coordinate_space,
        required=False,
    )
    should_clear = bool(resolved["has_target"]) if clear is None else bool(clear)
    if resolved["has_target"]:
        click_kwargs: dict[str, Any] = {"px": resolved["px"], "py": resolved["py"], "button": "left", "count": 1}
        if duration_ms is not None:
            click_kwargs["duration_ms"] = int(duration_ms)
        WIN32.click(**click_kwargs)
        time.sleep(0.015)
    if should_clear:
        WIN32.send_key("ctrl+a", repeat=1)
        time.sleep(0.012)

    written = 0
    if text is not None:
        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
        preview = "•••••" if sensitive else (normalized[:18] + ("..." if len(normalized) > 18 else ""))
        OVERLAY.notify_action(f'Yapıştırılıyor: "{preview}"', state="working")
        written = WIN32.set_clipboard_text(normalized)
        time.sleep(0.01)
    else:
        OVERLAY.notify_action("Pano yapıştırılıyor...", state="working")

    WIN32.send_key("ctrl+v", repeat=1)
    if submit_enter:
        time.sleep(0.015)
        WIN32.send_key("Return", repeat=1)
    _clear_click_streak()
    return {
        "action": "paste_text",
        "ok": True,
        "characters_pasted": written,
        "submitted_enter": bool(submit_enter),
    }


def _run_file_dialog_action(
    *,
    file_path: str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    _sync_runtime_win32()
    OVERLAY.notify_action(f"Dosya seçiliyor: {Path(file_path).name}", state="working")

    def _check_dialog(win: dict[str, Any]) -> None:
        allowed, reason = SAFETY.check_input_allowed(
            action_name="file_dialog",
            frontmost=win,
            current_elevated=WIN32.current_elevated,
        )
        if not allowed:
            OVERLAY.notify_stopped(reason)
            raise ToolError(reason)

    res = WIN32.accept_file_dialog(file_path=file_path, timeout_sec=float(timeout), safety_check=_check_dialog)
    _clear_click_streak()
    return res


def _wait_for_action(
    name: str,
    target: str | None = None,
    control_type: str | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.2, min(30.0, float(timeout)))
    start = time.monotonic()
    OVERLAY.notify_action(f'Bekleniyor: "{name}"', state="working")
    needle = name.strip().lower()
    want_window_only = isinstance(target, str) and target.strip().lower() == "window"
    last_err = ""
    while True:
        stopped, msg = SAFETY.is_emergency_stopped()
        if stopped:
            OVERLAY.notify_stopped(msg)
            raise ToolError(msg)

        if needle:
            if want_window_only:
                wins = WIN32.list_windows(include_minimized=False, filter_text=name)
                if wins:
                    return {
                        "action": "wait_for",
                        "ok": True,
                        "matched_window": wins[0].get("title"),
                        "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
                    }
            else:
                try:
                    el = _resolve_element_for_window(
                        name=name, target=target, control_type=control_type, timeout_sec=0.45
                    )
                    return {
                        "action": "wait_for",
                        "ok": True,
                        "matched": el.get("name") or name,
                        "center": el.get("center"),
                        "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
                    }
                except (RuntimeError, ValueError) as exc:
                    last_err = str(exc)

        if time.monotonic() >= deadline:
            suffix = f" ({last_err})" if last_err else ""
            raise TimeoutError(f"Timed out after {timeout:.1f}s waiting for '{name}'{suffix}.")
        time.sleep(0.12)


_CANONICAL_BATCH_ACTIONS = frozenset({
    "left_click",
    "right_click",
    "middle_click",
    "double_click",
    "triple_click",
    "click_element",
    "type_into",
    "paste_text",
    "file_dialog",
    "wait_for",
    "mouse_move",
    "left_mouse_down",
    "left_mouse_up",
    "left_click_drag",
    "scroll",
    "type",
    "key",
    "hold_key",
    "wait",
    "open_application",
    "manage_window",
    "focus_window",
    "clipboard_set",
})

_BATCH_ACTION_ALIASES: dict[str, str] = {
    "click": "left_click",
    "move": "mouse_move",
    "hover": "mouse_move",
    "mouse_down": "left_mouse_down",
    "mouse_up": "left_mouse_up",
    "hotkey": "key",
    "press_key": "key",
    "shortcut": "key",
    "sleep": "wait",
    "pause": "wait",
    "drag": "left_click_drag",
    "drag_and_drop": "left_click_drag",
    "focus": "focus_window",
    "launch": "open_application",
    "open_app": "open_application",
    "paste": "paste_text",
    "clipboard_paste": "paste_text",
    "select_file": "file_dialog",
    "open_file_dialog": "file_dialog",
    "upload_file": "file_dialog",
    "fill": "type_into",
}


def _canonical_batch_action(raw: str) -> str:
    key = raw.strip().lower()
    return _BATCH_ACTION_ALIASES.get(key, key)


def _apply_drag_endpoint(out: dict[str, Any], raw_val: Any, *, is_start: bool) -> None:
    if raw_val is None:
        return
    if isinstance(raw_val, list):
        out["start_coordinate" if is_start else "coordinate"] = raw_val
        return
    if isinstance(raw_val, dict):
        if "coordinate" in raw_val:
            out["start_coordinate" if is_start else "coordinate"] = raw_val["coordinate"]
        if raw_val.get("x") is not None and raw_val.get("y") is not None:
            out["start_x" if is_start else "x"] = raw_val["x"]
            out["start_y" if is_start else "y"] = raw_val["y"]
        if raw_val.get("mark_id") is not None:
            out["start_mark_id" if is_start else "mark_id"] = raw_val["mark_id"]
        if raw_val.get("name") is not None:
            out["start_name" if is_start else "name"] = raw_val["name"]


def _normalize_batch_step(raw_step: dict[str, Any]) -> dict[str, Any]:
    """Normalize standard, type-keyed, shorthand action-keyed, and aliased batch steps."""
    if not isinstance(raw_step, dict):
        raise ValueError("Each batch step must be a dictionary.")

    out: dict[str, Any] = dict(raw_step)
    action_raw = out.get("action")
    if isinstance(action_raw, str) and action_raw.strip():
        action = _canonical_batch_action(action_raw)
    elif "type" in out and isinstance(out["type"], str) and out["type"].strip():
        action = _canonical_batch_action(str(out.pop("type")))
    else:
        matched_key: str | None = None
        for k in out:
            if not isinstance(k, str):
                continue
            cand = _canonical_batch_action(k)
            if cand in _CANONICAL_BATCH_ACTIONS:
                matched_key = k
                action = cand
                break
        if matched_key is None:
            raise ValueError("Each batch step must include an 'action' string.")

        payload = out.pop(matched_key)
        if isinstance(payload, dict):
            # Nested payload overrides top-level action key while preserving outer metadata
            out = {**out, **payload}
        elif action == "wait" and isinstance(payload, (int, float)) and not isinstance(payload, bool):
            out["duration"] = float(payload)
        elif action == "key" and isinstance(payload, str):
            out["key"] = payload
        elif action in {"type", "paste_text", "clipboard_set"} and isinstance(payload, str):
            out["text"] = payload
        elif action == "file_dialog" and isinstance(payload, str):
            out["path"] = payload
        elif action == "click_element" and isinstance(payload, str):
            out["name"] = payload
        elif action == "click_element" and isinstance(payload, int) and not isinstance(payload, bool):
            out["mark_id"] = payload
        else:
            raise ValueError(f"Shorthand batch step '{matched_key}' must map to an object of arguments.")

    out["action"] = action

    if action == "key":
        if not out.get("key"):
            for k_alias in ("keys", "chord", "shortcut"):
                if out.get(k_alias):
                    out["key"] = out[k_alias]
                    break
        if isinstance(out.get("key"), list):
            out["key"] = "+".join(str(part).strip() for part in out["key"] if str(part).strip())

    elif action == "scroll":
        if "scroll_amount" not in out and out.get("amount") is not None:
            out["scroll_amount"] = out["amount"]

    elif action == "wait":
        if "duration" not in out:
            if out.get("seconds") is not None:
                out["duration"] = out["seconds"]
            elif out.get("ms") is not None:
                out["duration"] = float(out["ms"]) / 1000.0

    elif action == "file_dialog":
        if not out.get("path"):
            out["path"] = out.get("file_path") or out.get("file") or out.get("text")

    elif action == "left_click_drag":
        if "start" in out:
            _apply_drag_endpoint(out, out.pop("start"), is_start=True)
        if "end" in out:
            _apply_drag_endpoint(out, out.pop("end"), is_start=False)
        if "end_coordinate" in out and "coordinate" not in out:
            out["coordinate"] = out["end_coordinate"]
        if out.get("from_mark_id") is not None and out.get("start_mark_id") is None:
            out["start_mark_id"] = out["from_mark_id"]
        if out.get("to_mark_id") is not None and out.get("mark_id") is None:
            out["mark_id"] = out["to_mark_id"]
        if out.get("end_mark_id") is not None and out.get("mark_id") is None:
            out["mark_id"] = out["end_mark_id"]

    return out


def _execute_batch_step(
    raw_step: dict[str, Any],
    default_display: int | None,
    *,
    fast: bool = True,
) -> dict[str, Any]:
    step = _normalize_batch_step(raw_step)
    action = str(step.get("action") or "").strip().lower()
    if not action:
        raise ValueError("Each batch step must include an 'action' string.")

    disp = step.get("display_number", default_display)
    coord_space: Literal["screenshot", "physical"] = (
        "physical" if step.get("coordinate_space") == "physical" else "screenshot"
    )
    step_dur: int | None = int(step["duration_ms"]) if step.get("duration_ms") is not None else (0 if fast else None)

    if action in {"left_click", "right_click", "middle_click", "double_click", "triple_click"}:
        frontmost = _guard_input(action, step)
        btn = "right" if action == "right_click" else ("middle" if action == "middle_click" else "left")
        cnt = 2 if action == "double_click" else (3 if action == "triple_click" else 1)
        return _run_click_action(
            action,
            btn,
            cnt,
            coordinate=step.get("coordinate"),
            x=step.get("x"),
            y=step.get("y"),
            mark_id=step.get("mark_id"),
            name=step.get("name"),
            modifiers=step.get("modifiers"),
            display_number=disp,
            coordinate_space=coord_space,
            frontmost=frontmost,
            args=step,
            duration_ms=step_dur,
            fast_batch=fast,
        )

    if action == "click_element":
        name = str(step.get("name") or step.get("text") or "").strip() or None
        mark_id = step.get("mark_id")
        if name is None and mark_id is None:
            raise ValueError("click_element requires 'name' or 'mark_id'.")
        _guard_input("click_element", step)
        return _click_element_action(
            name=name,
            control_type=step.get("control_type"),
            target=step.get("target"),
            button=str(step.get("button") or "left"),
            count=int(step.get("count", 1)),
            modifiers=step.get("modifiers"),
            mark_id=mark_id,
            display_number=disp,
            duration_ms=step_dur,
            fast_batch=fast,
        )

    if action == "type_into":
        name = str(step.get("name") or "").strip() or None
        mark_id = step.get("mark_id")
        coordinate = step.get("coordinate")
        x = step.get("x")
        y = step.get("y")
        if name is None and mark_id is None and coordinate is None and (x is None or y is None):
            raise ValueError("type_into requires 'name', 'mark_id', 'coordinate', or 'x'+'y'.")
        _guard_input("type_into", step)
        paste_mode = step.get("paste", step.get("use_clipboard", "auto"))
        return _type_into_action(
            name=name,
            text=str(step.get("text", "")),
            control_type=step.get("control_type"),
            target=step.get("target"),
            clear=bool(step.get("clear", False)),
            submit_enter=bool(step.get("submit_enter", False)),
            sensitive=bool(step.get("sensitive", False)),
            interval_ms=int(step.get("interval_ms", 0)),
            mark_id=mark_id,
            coordinate=coordinate,
            x=x,
            y=y,
            display_number=disp,
            coordinate_space=coord_space,
            paste=paste_mode,
            duration_ms=step_dur,
        )

    if action == "paste_text":
        _guard_input("paste_text", step)
        return _run_paste_text_action(
            text=step.get("text"),
            coordinate=step.get("coordinate"),
            x=step.get("x"),
            y=step.get("y"),
            mark_id=step.get("mark_id"),
            name=str(step.get("name") or "").strip() or None,
            control_type=step.get("control_type"),
            target=step.get("target"),
            clear=step.get("clear"),
            submit_enter=bool(step.get("submit_enter", False)),
            sensitive=bool(step.get("sensitive", False)),
            display_number=disp,
            coordinate_space=coord_space,
            duration_ms=step_dur,
        )

    if action == "file_dialog":
        file_path = str(step.get("path") or "").strip()
        if not file_path:
            raise ValueError("file_dialog requires 'path'.")
        _abort_if_stopped()
        return _run_file_dialog_action(file_path=file_path, timeout=float(step.get("timeout", 5.0)))

    if action == "wait_for":
        name = str(step.get("name") or "").strip()
        if not name:
            raise ValueError("wait_for requires 'name'.")
        return _wait_for_action(
            name=name,
            target=step.get("target"),
            control_type=step.get("control_type"),
            timeout=float(step.get("timeout", 8.0)),
        )

    if action == "mouse_move":
        _guard_input("mouse_move", step)
        return _run_move_action(
            coordinate=step.get("coordinate"),
            x=step.get("x"),
            y=step.get("y"),
            mark_id=step.get("mark_id"),
            name=step.get("name"),
            duration_ms=int(step.get("duration_ms", 0)),
            display_number=disp,
            coordinate_space=coord_space,
        )

    if action in {"left_mouse_down", "left_mouse_up"}:
        _guard_input(action, step)
        return _run_mouse_button_action(
            action,
            down=(action == "left_mouse_down"),
            coordinate=step.get("coordinate"),
            x=step.get("x"),
            y=step.get("y"),
            mark_id=step.get("mark_id"),
            name=step.get("name"),
            display_number=disp,
            coordinate_space=coord_space,
        )

    if action == "left_click_drag":
        _guard_input("left_click_drag", step)
        drag_dur = int(step["duration_ms"]) if step.get("duration_ms") is not None else (80 if fast else 300)
        return _run_drag_action(
            coordinate=step.get("coordinate"),
            x=step.get("x") if step.get("end_x") is None else step.get("end_x"),
            y=step.get("y") if step.get("end_y") is None else step.get("end_y"),
            mark_id=step.get("mark_id"),
            name=step.get("name") if step.get("end_name") is None else step.get("end_name"),
            start_coordinate=step.get("start_coordinate"),
            start_x=step.get("start_x"),
            start_y=step.get("start_y"),
            start_mark_id=step.get("start_mark_id"),
            start_name=step.get("start_name"),
            duration_ms=drag_dur,
            display_number=disp,
            coordinate_space=coord_space,
        )

    if action == "scroll":
        _guard_input("scroll", step)
        direction = str(step.get("scroll_direction") or step.get("direction") or "down")
        amount = int(step.get("scroll_amount", 3))
        return _run_scroll_action(
            scroll_direction=direction,
            scroll_amount=amount,
            coordinate=step.get("coordinate"),
            x=step.get("x"),
            y=step.get("y"),
            mark_id=step.get("mark_id"),
            name=step.get("name"),
            modifiers=step.get("modifiers"),
            display_number=disp,
            coordinate_space=coord_space,
            duration_ms=step_dur,
        )

    if action == "type":
        text = str(step.get("text", ""))
        _guard_input("type", step)
        paste_mode = step.get("paste", step.get("use_clipboard", "auto"))
        return _run_type_action(
            text=text,
            interval_ms=int(step.get("interval_ms", 0)),
            submit_enter=bool(step.get("submit_enter", False)),
            sensitive=bool(step.get("sensitive", False)),
            paste=paste_mode,
        )

    if action == "key":
        key_spec = str(step.get("key") or step.get("text") or "")
        _guard_input("key", step, key_combo=key_spec)
        return _run_key_action(key_spec=key_spec, repeat=int(step.get("repeat", 1)))

    if action == "hold_key":
        key_spec = str(step.get("key") or "")
        dur = float(step.get("duration", 0.5))
        _guard_input("hold_key", step, key_combo=key_spec)
        return _run_hold_key_action(key_spec=key_spec, duration=dur)

    if action == "wait":
        dur = min(300.0, max(0.02, float(step.get("duration", 0.5))))
        OVERLAY.notify_action(f"Bekleniyor ({dur:.1f}s)...", state="working")
        _sleep_interruptible(dur)
        return {"action": action, "ok": True, "waited_seconds": dur}

    if action == "open_application":
        name_or_path = str(step.get("name_or_path") or "")
        blocked, reason = SAFETY.is_blocked_target(name_or_path, name_or_path)
        if blocked:
            OVERLAY.notify_stopped(reason)
            raise ToolError(reason)
        OVERLAY.notify_action(f"Açılıyor: {name_or_path}", state="working")
        res = WIN32.open_application(
            name_or_path=name_or_path,
            args=step.get("args"),
            focus_if_running=bool(step.get("focus_if_running", True)),
            wait_seconds=float(step.get("wait_seconds", 4.0)),
        )
        _clear_click_streak()
        return {"action": action, "ok": True, "window": _compact_window(res.get("window"))}

    if action in {"manage_window", "focus_window"}:
        win_act = "focus" if action == "focus_window" else str(step.get("window_action") or "focus")
        OVERLAY.notify_action(f"Pencere ({win_act}): {step.get('target') or 'aktif'}", state="working")
        info = WIN32.manage_window(
            action=win_act,
            target=step.get("target"),
            x=step.get("x"),
            y=step.get("y"),
            width=step.get("width"),
            height=step.get("height"),
        )
        _clear_click_streak()
        return {"action": action, "ok": True, "window": _compact_window(info if isinstance(info, dict) else None)}

    if action == "clipboard_set":
        written = WIN32.set_clipboard_text(str(step.get("text", "")))
        return {"action": action, "ok": True, "characters_copied": written}

    raise ValueError(f"Unsupported batch action: '{action}'")


def _collect_compact_ui_snapshot(display_number: int | None = None) -> dict[str, Any]:
    """Capture a lightweight text-only UIA element list (0 image offload / 0 read_file turns)."""
    try:
        hwnd = WIN32._resolve_window_hwnd(None)
        win = WIN32.get_window_info(hwnd, include_elevation=False)
        disp = int(display_number or (win or {}).get("display_number") or 1)
        viewport = WIN32._ensure_viewport(disp)
        raw = inspect_window_ui(
            hwnd=hwnd,
            viewport=viewport,
            max_depth=4,
            max_elements=65,
            interactive_only=True,
            include_web_content=True,
            timeout_sec=0.8,
        )
        compact_els: list[dict[str, Any]] = []
        for el in raw.get("elements", []):
            item: dict[str, Any] = {
                "type": el.get("type"),
                "name": el.get("name"),
                "center": el.get("center"),
            }
            if el.get("automation_id"):
                item["id"] = el["automation_id"]
            if el.get("value"):
                item["value"] = str(el["value"])[:60]
            compact_els.append(item)
        return {
            "window": _compact_window(win),
            "element_count": len(compact_els),
            "offscreen_matches": int(raw.get("offscreen_matches", 0)),
            "elements": compact_els,
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# 1. High-Speed Batched Action Pipeline
# ---------------------------------------------------------------------------


@mcp.tool(structured_output=False)
def batch(
    actions: list[dict[str, Any]] = Field(
        description=(
            "Sequential steps executed in one turn. Supports standard {'action': ..., ...}, {'type': ..., ...}, "
            "or shorthand {'click_element': {'mark_id': 30}}, {'paste_text': '...'}, {'file_dialog': 'C:\\...'}, "
            "plus aliases (click, move, hotkey/press_key, sleep, drag, paste, fill, select_file). "
            "Steps: left_click/right_click/double_click/triple_click/middle_click (coordinate?, x?, y?, mark_id?, name?, modifiers?), "
            "click_element (name?, mark_id?, control_type?, target?, button?, count?), "
            "type_into (name?/mark_id?/coordinate?, text, clear?, paste?, submit_enter?, sensitive?, target?), "
            "paste_text (text?, name?/mark_id?/coordinate?, clear?, submit_enter?, sensitive?), "
            "file_dialog (path, timeout?), wait_for (name, target?, timeout?), "
            "mouse_move (coordinate?, x?, y?, mark_id?, name?, duration_ms?), "
            "left_click_drag (start_coordinate?/start?/from_mark_id?, coordinate?/end_coordinate?/end?/to_mark_id?), "
            "scroll (scroll_direction, scroll_amount?, coordinate?, x?, y?, mark_id?, name?, modifiers?), "
            "type (text, paste?, submit_enter?, sensitive?), key (key, repeat?), hold_key (key, duration), "
            "wait (duration), open_application (name_or_path), manage_window/focus_window (target, window_action?), "
            "clipboard_set (text)."
        ),
    ),
    screenshot_after: bool = Field(
        default=True,
        description="Capture and return ONE fresh screenshot after all steps complete (set false + ui_after=true on intermediate steps to avoid image read_file turns).",
    ),
    ui_after: bool = Field(
        default=False,
        description="When screenshot_after=false, return compact clickable UIA elements + centers inline as text (zero extra image turns).",
    ),
    fast: bool = Field(
        default=True,
        description="Skip 220ms pointer glide animations inside batched steps for instant throughput.",
    ),
    display_number: int | None = Field(
        default=None,
        description="Optional monitor override for coordinates and final screenshot.",
    ),
    step_delay_ms: int = Field(
        default=5,
        ge=0,
        le=2000,
        description="Brief pause in ms between consecutive steps.",
    ),
    stop_on_error: bool = Field(
        default=True,
        description="Abort remaining steps immediately if a step fails or is blocked by safety.",
    ),
    settle: bool = Field(
        default=False,
        description="Wait adaptively until the display stops changing (page load/UI animation) before capturing screenshot_after.",
    ),
    settle_timeout: float = Field(
        default=5.0,
        ge=0.5,
        le=12.0,
        description="Maximum seconds to wait for visuals to stabilize when settle=true.",
    ),
    marks: bool | None = Field(
        default=None,
        description="Overlay numbered Set-of-Mark UIA badges ([1], [2], ...); omit to preserve last marks state.",
    ),
    annotate: Literal["none", "grid", "som"] | None = Field(
        default=None,
        description="Override screenshot annotation ('grid'=100px ruler, 'som'=grid+UIA marks, 'none'=raw image).",
    ),
) -> list[Any]:
    """Execute multiple desktop actions sequentially in a single fast MCP call."""
    _abort_if_stopped()
    if not actions:
        raise ToolError("actions list cannot be empty.")

    t_start = time.perf_counter()
    results: list[dict[str, Any]] = []
    normalized_steps: list[dict[str, Any]] = []
    loop_failure: dict[str, Any] | None = None

    for idx, raw_step in enumerate(actions):
        try:
            norm_step = _normalize_batch_step(raw_step)
            normalized_steps.append(norm_step)
            res = _execute_batch_step(norm_step, default_display=display_number, fast=fast)
            results.append(res)
            if res.get("ok") is False:
                loop_failure = res
                break
        except ToolError as exc:
            SAFETY.audit("batch", {"step_index": idx, "step": raw_step}, ok=False, error=str(exc))
            if stop_on_error:
                raise
            act_name = raw_step.get("action") if isinstance(raw_step, dict) else None
            results.append({"index": idx, "action": act_name, "ok": False, "error": str(exc)})
        except (ValueError, RuntimeError, FileNotFoundError, TimeoutError, OSError) as exc:
            SAFETY.audit("batch", {"step_index": idx, "step": raw_step}, ok=False, error=str(exc))
            if stop_on_error:
                raise ToolError(f"Batch step {idx} failed: {exc}") from exc
            act_name = raw_step.get("action") if isinstance(raw_step, dict) else None
            results.append({"index": idx, "action": act_name, "ok": False, "error": str(exc)})

        if step_delay_ms > 0 and idx + 1 < len(actions):
            time.sleep(step_delay_ms / 1000.0)

    has_sensitive = any(bool(s.get("sensitive")) for s in normalized_steps) or any(
        isinstance(s, dict) and bool(s.get("sensitive")) for s in actions
    )
    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 1)

    if loop_failure is not None:
        SAFETY.audit(
            "batch",
            {"count": len(actions), "actions": [s.get("action") for s in normalized_steps], "elapsed_ms": elapsed_ms},
            ok=False,
            frontmost=WIN32.get_frontmost_window(include_elevation=False),
            error=str(loop_failure.get("error") or "Batch click loop detected"),
            redact_text=has_sensitive,
        )
        target_disp = _active_display_number(display_number)
        err_extra: dict[str, Any] = {
            "ok": False,
            "loop_detected": bool(loop_failure.get("loop_detected")),
            "error": loop_failure.get("error"),
            "batch_results": results,
            "elapsed_ms": elapsed_ms,
        }
        if loop_failure.get("missing_target"):
            err_extra["missing_target"] = True
        try:
            shot = _capture_display(
                display_number=target_disp,
                settle=settle,
                settle_timeout=settle_timeout,
                marks=True,
                annotate=annotate,
            )
            OVERLAY.notify_thinking("Hedef yenileniyor...")
            return _format_screenshot_result(shot, extra=err_extra)
        except Exception:
            return [_json_text(err_extra)]

    SAFETY.audit(
        "batch",
        {"count": len(actions), "actions": [s.get("action") for s in normalized_steps], "elapsed_ms": elapsed_ms, "settle": settle},
        ok=True,
        frontmost=WIN32.get_frontmost_window(include_elevation=False),
        redact_text=has_sensitive,
    )

    if marks is not None:
        _resolve_marks_flag(marks, annotate=annotate)

    if screenshot_after:
        last_action = str(normalized_steps[-1].get("action") or "").strip().lower() if normalized_steps else ""
        target_disp = _active_display_number(display_number)
        if not settle and last_action not in {"wait", "wait_for", "file_dialog"}:
            time.sleep(0.02 if fast else 0.065)
        shot = _capture_display(
            display_number=target_disp,
            settle=settle,
            settle_timeout=settle_timeout,
            marks=marks,
            annotate=annotate,
        )
        OVERLAY.notify_thinking("Ekran inceleniyor...")
        return _format_screenshot_result(shot, extra={"batch_results": results, "elapsed_ms": elapsed_ms})
    payload: dict[str, Any] = {"ok": True, "batch_results": results, "elapsed_ms": elapsed_ms}
    if ui_after:
        payload["ui_after"] = _collect_compact_ui_snapshot(display_number=display_number)
    OVERLAY.notify_thinking("Sonraki adım bekleniyor...")
    return [_json_text(payload)]


# ---------------------------------------------------------------------------
# 2. Perception & Zoom Tools
# ---------------------------------------------------------------------------


@mcp.tool(structured_output=False)
def screenshot(
    display_number: int | None = Field(
        default=1,
        description="Monitor index (1 = primary, 2..N = secondary, 0 = all monitors virtual screen).",
    ),
    window_title: str | None = Field(
        default=None,
        description="Optional window title/process filter; focuses matching window and captures its display.",
    ),
    show_cursor: bool = Field(
        default=True,
        description="Draw a visible cursor indicator on the screenshot at the current mouse position.",
    ),
    max_width: int = Field(
        default=1280,
        ge=320,
        le=3840,
        description="Maximum screenshot width in pixels (aspect-preserving downscale).",
    ),
    max_height: int = Field(
        default=800,
        ge=240,
        le=2160,
        description="Maximum screenshot height in pixels (aspect-preserving downscale).",
    ),
    format: Literal["jpeg", "png"] = Field(
        default="jpeg",
        description="Image format: crisp 4:4:4 'jpeg' (fast, default) or lossless 'png'.",
    ),
    settle: bool = Field(
        default=False,
        description="Wait adaptively until the display stops changing before capturing.",
    ),
    settle_timeout: float = Field(
        default=5.0,
        ge=0.5,
        le=12.0,
        description="Maximum seconds to wait for visuals to stabilize when settle=true.",
    ),
    marks: bool | None = Field(
        default=None,
        description="Overlay numbered Set-of-Mark UIA badges ([1], [2], ...); omit to preserve last marks state.",
    ),
    annotate: Literal["none", "grid", "som"] | None = Field(
        default=None,
        description="Override screenshot annotation ('grid'=100px ruler, 'som'=grid+UIA marks, 'none'=raw image).",
    ),
) -> list[Any]:
    """Capture a screenshot of the desktop or specific monitor and return image + coordinate metadata."""
    _abort_if_stopped()

    target_display = display_number
    try:
        if window_title:
            win = WIN32.manage_window("focus", target=window_title)
            target_display = int(win.get("display_number") or 1)
            time.sleep(0.08)

        shot = _capture_display(
            display_number=target_display,
            max_width=max_width,
            max_height=max_height,
            show_cursor=show_cursor,
            fmt=format,
            settle=settle,
            settle_timeout=settle_timeout,
            marks=marks,
            annotate=annotate,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        raise ToolError(str(exc)) from exc

    SAFETY.audit(
        "screenshot",
        {"display_number": target_display, "window_title": window_title, "format": format, "settle": settle},
        ok=True,
        frontmost=shot["frontmost_window"],
    )
    OVERLAY.notify_thinking("Ekran inceleniyor...")
    return _format_screenshot_result(shot)


@mcp.tool(structured_output=False)
def zoom(
    region: list[int] = Field(
        description="Bounding box [x1, y1, x2, y2] in the active screenshot's pixel coordinates.",
    ),
    display_number: int | None = Field(
        default=None,
        description="Optional monitor override; defaults to the most recently captured display.",
    ),
    format: Literal["jpeg", "png"] = Field(
        default="jpeg",
        description="Image format for cropped zoom image.",
    ),
) -> list[Any]:
    """Capture a high-resolution crop of a screen region [x1, y1, x2, y2] to read small text or icons."""
    stopped, msg = SAFETY.is_emergency_stopped()
    if stopped:
        raise ToolError(msg)
    try:
        res = WIN32.capture_zoom(region=region, display_number=display_number, fmt=format)
    except (RuntimeError, ValueError, OSError) as exc:
        raise ToolError(str(exc)) from exc

    SAFETY.audit("zoom", {"region": region, "display_number": display_number}, ok=True)
    meta = {k: v for k, v in res.items() if k not in {"image", "image_bytes", "image_format", "mime_type"}}
    return [Image(data=res["image_bytes"], format=res["image_format"]), _json_text(meta)]


@mcp.tool(structured_output=False)
def cursor_position() -> str:
    """Return the current cursor coordinates in both screenshot and physical pixels, plus window under cursor."""
    return _json_text(WIN32.get_cursor_info())


# ---------------------------------------------------------------------------
# 3. Mouse Control Tools (Claude computer_toolset parity)
# ---------------------------------------------------------------------------


@mcp.tool(structured_output=False)
def left_click(
    coordinate: list[int] | None = Field(default=None, description="Optional [x, y] target in screenshot coordinates."),
    modifiers: str | None = Field(default=None, description="Optional modifier key(s) to hold, e.g. 'ctrl', 'shift', 'ctrl+shift'."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after clicking."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    x: int | None = Field(default=None, description="Optional target X coordinate (alternative to coordinate=[x, y])."),
    y: int | None = Field(default=None, description="Optional target Y coordinate (alternative to coordinate=[x, y])."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id to click in the foreground window."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Perform a left mouse click at coordinate, x/y, mark_id, element name, or after mouse_move."""
    return _perform_click(
        "left_click",
        "left",
        1,
        coordinate,
        modifiers,
        display_number,
        coordinate_space,
        screenshot_after,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def right_click(
    coordinate: list[int] | None = Field(default=None, description="Optional [x, y] target in screenshot coordinates."),
    modifiers: str | None = Field(default=None, description="Optional modifier key(s) to hold during click."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after clicking."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    x: int | None = Field(default=None, description="Optional target X coordinate (alternative to coordinate=[x, y])."),
    y: int | None = Field(default=None, description="Optional target Y coordinate (alternative to coordinate=[x, y])."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id to right-click."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Perform a right mouse click (context menu) at coordinate, x/y, mark_id, element name, or after mouse_move."""
    return _perform_click(
        "right_click",
        "right",
        1,
        coordinate,
        modifiers,
        display_number,
        coordinate_space,
        screenshot_after,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def middle_click(
    coordinate: list[int] | None = Field(default=None, description="Optional [x, y] target in screenshot coordinates."),
    modifiers: str | None = Field(default=None, description="Optional modifier key(s) to hold during click."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after clicking."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    x: int | None = Field(default=None, description="Optional target X coordinate (alternative to coordinate=[x, y])."),
    y: int | None = Field(default=None, description="Optional target Y coordinate (alternative to coordinate=[x, y])."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id to middle-click."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Perform a middle mouse click at coordinate, x/y, mark_id, element name, or after mouse_move."""
    return _perform_click(
        "middle_click",
        "middle",
        1,
        coordinate,
        modifiers,
        display_number,
        coordinate_space,
        screenshot_after,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def double_click(
    coordinate: list[int] | None = Field(default=None, description="Optional [x, y] target in screenshot coordinates."),
    modifiers: str | None = Field(default=None, description="Optional modifier key(s) to hold during double click."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after clicking."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    x: int | None = Field(default=None, description="Optional target X coordinate (alternative to coordinate=[x, y])."),
    y: int | None = Field(default=None, description="Optional target Y coordinate (alternative to coordinate=[x, y])."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id to double-click."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Perform a left double-click at coordinate, x/y, mark_id, element name, or after mouse_move."""
    return _perform_click(
        "double_click",
        "left",
        2,
        coordinate,
        modifiers,
        display_number,
        coordinate_space,
        screenshot_after,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def triple_click(
    coordinate: list[int] | None = Field(default=None, description="Optional [x, y] target in screenshot coordinates."),
    modifiers: str | None = Field(default=None, description="Optional modifier key(s) to hold during triple click."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after clicking."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    x: int | None = Field(default=None, description="Optional target X coordinate (alternative to coordinate=[x, y])."),
    y: int | None = Field(default=None, description="Optional target Y coordinate (alternative to coordinate=[x, y])."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id to triple-click."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Perform a left triple-click (select line/paragraph) at coordinate, x/y, mark_id, element name, or after mouse_move."""
    return _perform_click(
        "triple_click",
        "left",
        3,
        coordinate,
        modifiers,
        display_number,
        coordinate_space,
        screenshot_after,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def mouse_move(
    coordinate: list[int] | None = Field(default=None, description="Target [x, y] coordinates."),
    duration_ms: int = Field(default=0, ge=0, le=5000, description="Optional smooth move duration in milliseconds."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    x: int | None = Field(default=None, description="Optional target X coordinate."),
    y: int | None = Field(default=None, description="Optional target Y coordinate."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id to hover over."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after moving."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Move the mouse cursor to coordinate, x/y, mark_id, or element name without clicking."""
    args = {
        "coordinate": coordinate,
        "x": x,
        "y": y,
        "mark_id": mark_id,
        "name": name,
        "duration_ms": duration_ms,
        "display_number": display_number,
    }
    frontmost = _guard_input("mouse_move", args)
    payload = _run_move_action(
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        duration_ms=duration_ms,
        display_number=display_number,
        coordinate_space=coordinate_space,
    )
    return _finish_input(
        "mouse_move",
        args,
        frontmost,
        payload,
        screenshot_after=screenshot_after,
        display_number=display_number,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def left_mouse_down(
    coordinate: list[int] | None = Field(default=None, description="Optional [x, y] target before pressing button."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    x: int | None = Field(default=None, description="Optional target X coordinate."),
    y: int | None = Field(default=None, description="Optional target Y coordinate."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after pressing."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Press and hold the left mouse button."""
    args = {"coordinate": coordinate, "x": x, "y": y, "mark_id": mark_id, "name": name, "display_number": display_number}
    frontmost = _guard_input("left_mouse_down", args)
    payload = _run_mouse_button_action(
        "left_mouse_down",
        down=True,
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        display_number=display_number,
        coordinate_space=coordinate_space,
    )
    return _finish_input(
        "left_mouse_down",
        args,
        frontmost,
        payload,
        screenshot_after=screenshot_after,
        display_number=display_number,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def left_mouse_up(
    coordinate: list[int] | None = Field(default=None, description="Optional [x, y] target before releasing button."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    x: int | None = Field(default=None, description="Optional target X coordinate."),
    y: int | None = Field(default=None, description="Optional target Y coordinate."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after releasing."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Release the left mouse button."""
    args = {"coordinate": coordinate, "x": x, "y": y, "mark_id": mark_id, "name": name, "display_number": display_number}
    frontmost = _guard_input("left_mouse_up", args)
    payload = _run_mouse_button_action(
        "left_mouse_up",
        down=False,
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        display_number=display_number,
        coordinate_space=coordinate_space,
    )
    return _finish_input(
        "left_mouse_up",
        args,
        frontmost,
        payload,
        screenshot_after=screenshot_after,
        display_number=display_number,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def left_click_drag(
    coordinate: list[int] | None = Field(default=None, description="Destination [x, y] coordinates where drag releases."),
    start_coordinate: list[int] | None = Field(default=None, description="Starting [x, y] coordinates; defaults to current cursor."),
    duration_ms: int = Field(default=300, ge=50, le=5000, description="Smooth drag duration in milliseconds."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of coordinates."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after dragging."),
    end_coordinate: list[int] | None = Field(default=None, description="Alias for destination [x, y] coordinates."),
    from_mark_id: int | None = Field(default=None, description="Optional starting Set-of-Mark badge ID."),
    to_mark_id: int | None = Field(default=None, description="Optional destination Set-of-Mark badge ID."),
    start_mark_id: int | None = Field(default=None, description="Alias for from_mark_id."),
    end_mark_id: int | None = Field(default=None, description="Alias for to_mark_id."),
    x: int | None = Field(default=None, description="Optional destination X coordinate."),
    y: int | None = Field(default=None, description="Optional destination Y coordinate."),
    name: str | None = Field(default=None, description="Optional destination accessible element name/id."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Click and drag smoothly from start_coordinate/from_mark_id (or current cursor) to destination target."""
    end_coord = coordinate if coordinate is not None else end_coordinate
    resolved_start_mark = from_mark_id if from_mark_id is not None else start_mark_id
    resolved_end_mark = to_mark_id if to_mark_id is not None else end_mark_id
    args = {
        "start_coordinate": start_coordinate,
        "coordinate": end_coord,
        "start_mark_id": resolved_start_mark,
        "end_mark_id": resolved_end_mark,
        "x": x,
        "y": y,
        "name": name,
        "duration_ms": duration_ms,
        "display_number": display_number,
    }
    frontmost = _guard_input("left_click_drag", args)
    payload = _run_drag_action(
        coordinate=end_coord,
        x=x,
        y=y,
        mark_id=resolved_end_mark,
        name=name,
        start_coordinate=start_coordinate,
        start_mark_id=resolved_start_mark,
        duration_ms=duration_ms,
        display_number=display_number,
        coordinate_space=coordinate_space,
    )
    return _finish_input(
        "left_click_drag",
        args,
        frontmost,
        payload,
        screenshot_after=screenshot_after,
        display_number=display_number,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def scroll(
    scroll_direction: Literal["up", "down", "left", "right"] = Field(description="Direction to scroll."),
    scroll_amount: int = Field(default=3, ge=1, le=100, description="Number of scroll wheel notches."),
    coordinate: list[int] | None = Field(default=None, description="Optional [x, y] cursor target before scrolling."),
    modifiers: str | None = Field(default=None, description="Optional modifier key(s) to hold, e.g. 'ctrl' for zoom."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    coordinate_space: Literal["screenshot", "physical"] = Field(default="screenshot", description="Coordinate system of [x, y]."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after scrolling."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID to position cursor before scrolling."),
    x: int | None = Field(default=None, description="Optional cursor target X coordinate before scrolling."),
    y: int | None = Field(default=None, description="Optional cursor target Y coordinate before scrolling."),
    name: str | None = Field(default=None, description="Optional accessible UI element name/id to scroll over."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Scroll up, down, left, or right at the optional coordinate, x/y, mark_id, or element name."""
    args = {
        "scroll_direction": scroll_direction,
        "scroll_amount": scroll_amount,
        "coordinate": coordinate,
        "x": x,
        "y": y,
        "mark_id": mark_id,
        "name": name,
        "modifiers": modifiers,
        "display_number": display_number,
    }
    frontmost = _guard_input("scroll", args)
    payload = _run_scroll_action(
        scroll_direction=scroll_direction,
        scroll_amount=scroll_amount,
        coordinate=coordinate,
        x=x,
        y=y,
        mark_id=mark_id,
        name=name,
        modifiers=modifiers,
        display_number=display_number,
        coordinate_space=coordinate_space,
    )
    return _finish_input(
        "scroll",
        args,
        frontmost,
        payload,
        screenshot_after=screenshot_after,
        display_number=display_number,
        marks=marks,
        settle=settle,
    )


# ---------------------------------------------------------------------------
# 4. Keyboard & Timing Tools
# ---------------------------------------------------------------------------


@mcp.tool(structured_output=False)
def type(  # noqa: A001 - matches Anthropic computer_toolset tool name
    text: str = Field(description="Unicode text to type (supports Turkish characters, symbols, newlines, tabs)."),
    interval_ms: int = Field(default=0, ge=0, le=500, description="Optional delay in ms between characters."),
    submit_enter: bool = Field(default=False, description="Press Enter/Return immediately after typing."),
    sensitive: bool = Field(default=False, description="If true, redact typed text from audit logs."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after typing."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Type literal Unicode text into the currently focused application."""
    args = {"text": text, "interval_ms": interval_ms, "submit_enter": submit_enter}
    frontmost = _guard_input("type", args)
    payload = _run_type_action(
        text=text,
        interval_ms=interval_ms,
        submit_enter=submit_enter,
        sensitive=sensitive,
    )
    return _finish_input(
        "type",
        args,
        frontmost,
        payload,
        screenshot_after=screenshot_after,
        redact_text=sensitive,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def key(
    key: str = Field(description="Key or chord to press, e.g. 'Return', 'Escape', 'Tab', 'ctrl+c', 'ctrl+shift+s', 'alt+Tab', 'F5'."),
    repeat: int = Field(default=1, ge=1, le=100, description="Number of times to press the key/chord."),
    screenshot_after: bool = Field(default=False, description="Capture and return a fresh screenshot after key press."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Press a key or key combination chord."""
    args = {"key": key, "repeat": repeat}
    frontmost = _guard_input("key", args, key_combo=key)
    try:
        payload = _run_key_action(key_spec=key, repeat=repeat)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return _finish_input(
        "key",
        args,
        frontmost,
        payload,
        screenshot_after=screenshot_after,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def hold_key(
    key: str = Field(description="Key or chord to hold down."),
    duration: float = Field(gt=0.0, le=300.0, description="Hold duration in seconds (0 < duration <= 300)."),
) -> list[Any]:
    """Hold a key down for the specified duration in seconds and release it safely."""
    args = {"key": key, "duration": duration}
    frontmost = _guard_input("hold_key", args, key_combo=key)
    try:
        payload = _run_hold_key_action(key_spec=key, duration=duration)
    except (ValueError, RuntimeError) as exc:
        raise ToolError(str(exc)) from exc
    return _finish_input("hold_key", args, frontmost, payload)


@mcp.tool(structured_output=False)
def wait(
    duration: float = Field(default=1.0, gt=0.0, le=300.0, description="Seconds to wait (up to 300)."),
    screenshot_after: bool = Field(default=True, description="Capture and return a fresh screenshot when wait completes."),
    display_number: int | None = Field(default=None, description="Optional monitor index for post-wait screenshot."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Pause execution for duration seconds and optionally capture a fresh screenshot."""
    stopped, msg = SAFETY.is_emergency_stopped()
    if stopped:
        OVERLAY.notify_stopped(msg)
        raise ToolError(msg)

    OVERLAY.notify_action(f"Bekleniyor ({duration:.1f}s)...", state="working")
    _sleep_interruptible(duration)
    payload = {"ok": True, "action": "wait", "waited_seconds": duration}
    return _finish_input(
        "wait",
        {"duration": duration, "screenshot_after": screenshot_after},
        frontmost=None,
        payload=payload,
        screenshot_after=screenshot_after,
        display_number=display_number,
        delay_ms=0,
        marks=marks,
        settle=settle,
        extra_meta={"waited_seconds": duration},
    )


# ---------------------------------------------------------------------------
# 5. Desktop, Window, App & UI Automation Tools (Claude Cowork Parity)
# ---------------------------------------------------------------------------


@mcp.tool(structured_output=False)
def list_displays() -> str:
    """List all connected monitors with display_number, pixel bounds, work area, and DPI scale."""
    return _json_text({"displays": [d.to_dict() for d in WIN32.list_displays(force_refresh=True)]})


@mcp.tool(structured_output=False)
def list_windows(
    include_minimized: bool = Field(default=False, description="Include minimized windows."),
    filter_text: str | None = Field(default=None, description="Optional case-insensitive title or process filter."),
) -> str:
    """List visible desktop application windows with bounds, process name, HWND, and foreground status."""
    windows = WIN32.list_windows(include_minimized=include_minimized, filter_text=filter_text)
    return _json_text({"count": len(windows), "windows": windows})


@mcp.tool(structured_output=False)
def get_frontmost() -> str:
    """Get details of the currently active foreground window and whether it is blocked or elevated."""
    win = WIN32.get_frontmost_window(include_elevation=True)
    if not win:
        return _json_text({"frontmost_window": None})
    blocked, block_reason = SAFETY.is_blocked_target(win["process_name"], win["title"])
    return _json_text({
        "frontmost_window": win,
        "is_blocked": blocked,
        "block_reason": block_reason or None,
        "server_is_elevated": WIN32.current_elevated,
    })


@mcp.tool(structured_output=False)
def open_application(
    name_or_path: str = Field(description="App name/alias (e.g. 'notepad', 'calc', 'chrome', 'explorer'), executable path, or Start Menu name."),
    args: list[str] | None = Field(default=None, description="Optional command-line arguments."),
    focus_if_running: bool = Field(default=True, description="Bring existing window to foreground if already running."),
    wait_seconds: float = Field(default=4.0, ge=0.2, le=15.0, description="Seconds to wait for window creation."),
    screenshot_after: bool = Field(default=False, description="Capture a fresh screenshot after launching/focusing."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Launch or focus a Windows desktop application safely without shell command injection."""
    stopped, msg = SAFETY.is_emergency_stopped()
    if stopped:
        raise ToolError(msg)

    blocked, block_reason = SAFETY.is_blocked_target(name_or_path, name_or_path)
    if blocked:
        raise ToolError(block_reason)

    try:
        res = WIN32.open_application(
            name_or_path=name_or_path,
            args=args,
            focus_if_running=focus_if_running,
            wait_seconds=wait_seconds,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc

    _clear_click_streak()
    SAFETY.audit("open_application", {"name_or_path": name_or_path, "args": args}, ok=True, frontmost=res.get("window"))
    if marks is not None:
        _resolve_marks_flag(marks)
    if screenshot_after:
        disp = int((res.get("window") or {}).get("display_number") or 1)
        shot = _capture_display(display_number=disp, marks=marks, settle=settle)
        return _format_screenshot_result(shot, extra={"launch_result": res})
    return [_json_text({"ok": True, **res})]


@mcp.tool(structured_output=False)
def manage_window(
    action: Literal["focus", "minimize", "maximize", "restore", "close", "move_resize"] = Field(
        description="Window management operation."
    ),
    target: str | None = Field(default=None, description="Window HWND as string or title/process substring; defaults to foreground window."),
    x: int | None = Field(default=None, description="Physical X coordinate for move_resize."),
    y: int | None = Field(default=None, description="Physical Y coordinate for move_resize."),
    width: int | None = Field(default=None, description="Width in physical pixels for move_resize."),
    height: int | None = Field(default=None, description="Height in physical pixels for move_resize."),
) -> str:
    """Focus, minimize, maximize, restore, close, or move/resize a desktop window."""
    stopped, msg = SAFETY.is_emergency_stopped()
    if stopped:
        raise ToolError(msg)
    try:
        info = WIN32.manage_window(action=action, target=target, x=x, y=y, width=width, height=height)
    except (ValueError, RuntimeError) as exc:
        raise ToolError(str(exc)) from exc
    SAFETY.audit("manage_window", {"action": action, "target": target}, ok=True, frontmost=info if isinstance(info, dict) else None)
    return _json_text({"ok": True, "action": action, "window": info})


@mcp.tool(structured_output=False)
def inspect_ui(
    target: str | None = Field(default=None, description="Optional window HWND or title/process substring; defaults to foreground window."),
    max_depth: int = Field(default=3, ge=1, le=8, description="Maximum UI Automation tree traversal depth."),
    max_elements: int = Field(default=60, ge=1, le=250, description="Maximum accessible elements to return."),
    interactive_only: bool = Field(default=True, description="Only include interactive/focusable elements (buttons, inputs, tabs, menus)."),
    filter_text: str | None = Field(default=None, description="Optional substring filter on element name, automation_id, or control type."),
    include_web_content: bool = Field(default=False, description="Traverse inside browser Document DOM nodes (slower on complex web pages)."),
) -> str:
    """Inspect Windows UI Automation accessibility elements and exact screenshot center coordinates of a window."""
    stopped, msg = SAFETY.is_emergency_stopped()
    if stopped:
        raise ToolError(msg)
    try:
        hwnd = WIN32._resolve_window_hwnd(target)
        win = WIN32.get_window_info(hwnd, include_elevation=False)
        if win:
            blocked, block_reason = SAFETY.is_blocked_target(win["process_name"], win["title"])
            if blocked:
                raise ToolError(block_reason)
        disp = int((win or {}).get("display_number") or 1)
        viewport = WIN32._ensure_viewport(disp)
        result = inspect_window_ui(
            hwnd=hwnd,
            viewport=viewport,
            max_depth=max_depth,
            max_elements=max_elements,
            interactive_only=interactive_only,
            filter_text=filter_text,
            include_web_content=include_web_content,
        )
        result["window"] = _compact_window(win)
        SAFETY.audit("inspect_ui", {"target": target, "filter_text": filter_text}, ok=True, frontmost=win)
        return _json_text(result)
    except (ValueError, RuntimeError, TimeoutError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(structured_output=False)
def clipboard_get() -> str:
    """Read current Unicode text from the Windows clipboard."""
    stopped, msg = SAFETY.is_emergency_stopped()
    if stopped:
        raise ToolError(msg)
    try:
        text = WIN32.get_clipboard_text()
    except (RuntimeError, OSError) as exc:
        raise ToolError(str(exc)) from exc
    SAFETY.audit("clipboard_get", {"length": len(text)}, ok=True)
    return _json_text({"ok": True, "length": len(text), "text": text})


@mcp.tool(structured_output=False)
def clipboard_set(
    text: str = Field(description="Unicode text to place onto the Windows clipboard."),
    sensitive: bool = Field(default=False, description="Redact details in audit logs."),
) -> str:
    """Write Unicode text to the Windows clipboard."""
    stopped, msg = SAFETY.is_emergency_stopped()
    if stopped:
        raise ToolError(msg)
    try:
        written = WIN32.set_clipboard_text(text)
    except (RuntimeError, MemoryError, OSError) as exc:
        raise ToolError(str(exc)) from exc
    SAFETY.audit("clipboard_set", {"text": text}, ok=True, redact_text=sensitive)
    return _json_text({"ok": True, "characters_copied": written})


# ---------------------------------------------------------------------------
# 6. Permission, Access & Emergency Guardrail Tools
# ---------------------------------------------------------------------------


@mcp.tool(structured_output=False)
def request_access(
    app_names: list[str] = Field(description="Application names or executables to request session access for."),
    reason: str = Field(description="Clear explanation of why access to these applications is needed."),
    allow_clipboard: bool = Field(default=False, description="Whether clipboard access is also requested for this workflow."),
) -> str:
    """Register session-scoped permission grants for non-blocked desktop applications."""
    result = SAFETY.request_access(app_names=app_names, reason=reason, allow_clipboard=allow_clipboard)
    SAFETY.audit("request_access", {"app_names": app_names, "reason": reason}, ok=True)
    return _json_text(result)


@mcp.tool(structured_output=False)
def list_granted_applications() -> str:
    """List applications granted Computer Use access in the current session."""
    return _json_text({
        "require_app_grant": SAFETY.policy.require_app_grant,
        "allow_system_shortcuts": SAFETY.policy.allow_system_shortcuts,
        "blocked_processes": sorted(SAFETY.policy.blocked_processes),
        "granted_apps": SAFETY.list_granted_applications(),
    })


@mcp.tool(structured_output=False)
def revoke_access(
    app_names: list[str] | None = Field(default=None, description="Applications to revoke; omit or pass empty list to clear all grants."),
) -> str:
    """Revoke session access grants for specific applications or all applications."""
    res = SAFETY.revoke_access(app_names=app_names)
    SAFETY.audit("revoke_access", {"app_names": app_names}, ok=True)
    return _json_text({"ok": True, **res})


@mcp.tool(structured_output=False)
def click_element(
    name: str | None = Field(default=None, description="Visible label or automation_id substring of the UI element to click."),
    control_type: str | None = Field(default=None, description="Optional UIA type filter, e.g. 'Button', 'Hyperlink', 'MenuItem', 'TabItem', 'Edit'."),
    target: str | None = Field(default=None, description="Optional window HWND or title/process substring; defaults to foreground window."),
    button: Literal["left", "right", "middle"] = Field(default="left", description="Mouse button to click."),
    count: int = Field(default=1, ge=1, le=3, description="Click count (1=single, 2=double, 3=triple)."),
    modifiers: str | None = Field(default=None, description="Optional modifiers like 'ctrl', 'shift'."),
    screenshot_after: bool = Field(default=True, description="Capture a fresh screenshot after clicking."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Find a UI control by accessible name/id or mark_id and click its center smoothly without coordinate guessing."""
    args = {
        "name": name,
        "mark_id": mark_id,
        "control_type": control_type,
        "target": target,
        "button": button,
        "count": count,
    }
    frontmost = _guard_input("click_element", args)
    try:
        res = _click_element_action(
            name=name,
            control_type=control_type,
            target=target,
            button=button,
            count=count,
            modifiers=modifiers,
            mark_id=mark_id,
            display_number=display_number,
        )
    except (ValueError, RuntimeError, TimeoutError) as exc:
        raise ToolError(str(exc)) from exc
    if res.get("ok") is False:
        SAFETY.audit("click_element", args, ok=False, frontmost=frontmost, error=str(res.get("error") or ""))
        return _capture_loop_recovery_result(res, display_number=display_number, settle=settle)
    return _finish_input(
        "click_element",
        args,
        frontmost,
        res,
        screenshot_after=screenshot_after,
        display_number=display_number,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def type_into(
    name: str | None = Field(default=None, description="Visible label, placeholder, or automation_id of the target input field."),
    text: str = Field(default="", description="Unicode text to type or paste into the matched element."),
    clear: bool = Field(default=False, description="Select all (Ctrl+A) inside the element before entering text."),
    submit_enter: bool = Field(default=False, description="Press Enter immediately after entering text."),
    sensitive: bool = Field(default=False, description="Redact text from audit logs and on-screen HUD."),
    control_type: str | None = Field(default=None, description="Optional UIA type filter, e.g. 'Edit', 'ComboBox'."),
    target: str | None = Field(default=None, description="Optional target window title/process/HWND."),
    mark_id: int | None = Field(default=None, description="Optional Set-of-Mark badge ID from screenshot(marks=true)."),
    coordinate: list[int] | None = Field(default=None, description="Optional target [x, y] in screenshot space."),
    x: int | None = Field(default=None, description="Alternative target X coordinate (use with y)."),
    y: int | None = Field(default=None, description="Alternative target Y coordinate (use with x)."),
    display_number: int | None = Field(default=None, description="Optional monitor index override."),
    paste: bool | Literal["auto"] = Field(default="auto", description="Use clipboard Ctrl+V ('auto' uses clipboard for >48 chars or multiline text)."),
    screenshot_after: bool = Field(default=False, description="Capture a fresh screenshot after entering text."),
    marks: bool | None = Field(default=None, description="Override Set-of-Mark badges on screenshot_after; omit to preserve last state."),
    settle: bool = Field(default=False, description="Wait until display stabilizes before capturing screenshot_after."),
) -> list[Any]:
    """Focus a UI element (by name, mark_id, or coordinate), optionally clear it, enter Unicode text fast, and optionally press Enter."""
    args = {"name": name, "mark_id": mark_id, "coordinate": coordinate, "x": x, "y": y, "text": text, "clear": clear, "submit_enter": submit_enter}
    frontmost = _guard_input("type_into", args)
    try:
        res = _type_into_action(
            name=name,
            text=text,
            control_type=control_type,
            target=target,
            clear=clear,
            submit_enter=submit_enter,
            sensitive=sensitive,
            mark_id=mark_id,
            coordinate=coordinate,
            x=x,
            y=y,
            display_number=display_number,
            paste=paste,
        )
    except (ValueError, RuntimeError, TimeoutError) as exc:
        raise ToolError(str(exc)) from exc
    return _finish_input(
        "type_into",
        args,
        frontmost,
        res,
        screenshot_after=screenshot_after,
        display_number=display_number,
        redact_text=sensitive,
        marks=marks,
        settle=settle,
    )


@mcp.tool(structured_output=False)
def configure_safety(
    require_app_grant: bool | None = Field(default=None, description="If true, block input to apps until request_access is called."),
    allow_system_shortcuts: bool | None = Field(default=None, description="If true, allow Alt+F4 / Win+L style system shortcuts."),
    show_overlay: bool | None = Field(default=None, description="Show live click-through visual cursor halo, click ripples, and floating HUD pill."),
    smooth_cursor_ms: int | None = Field(default=None, ge=0, le=500, description="Max glide time in ms for automatic cursor moves (0=instant, 220=fluid human-like)."),
    annotate_mode: Literal["none", "grid", "som"] | None = Field(default=None, description="Screenshot annotation mode ('grid'=100px ruler, 'som'=grid+UIA marks, 'none'=raw)."),
) -> str:
    """Update persistent Computer Use safety and visual feedback settings."""
    global _LAST_MARKS_ENABLED
    if require_app_grant is not None:
        SAFETY.policy.require_app_grant = bool(require_app_grant)
    if allow_system_shortcuts is not None:
        SAFETY.policy.allow_system_shortcuts = bool(allow_system_shortcuts)
    if show_overlay is not None:
        SAFETY.policy.show_overlay = bool(show_overlay)
        OVERLAY.set_enabled(SAFETY.policy.show_overlay)
    if smooth_cursor_ms is not None:
        SAFETY.policy.smooth_cursor_ms = max(0, min(500, int(smooth_cursor_ms)))
        WIN32.smooth_cursor_ms = SAFETY.policy.smooth_cursor_ms
    if annotate_mode is not None:
        SAFETY.policy.annotate_mode = annotate_mode
        WIN32.annotate_mode = annotate_mode
        _LAST_MARKS_ENABLED = annotate_mode == "som"
    SAFETY.save_policy()
    SAFETY.audit(
        "configure_safety",
        {
            "require_app_grant": require_app_grant,
            "allow_system_shortcuts": allow_system_shortcuts,
            "show_overlay": show_overlay,
            "smooth_cursor_ms": smooth_cursor_ms,
            "annotate_mode": annotate_mode,
        },
        ok=True,
    )
    return _json_text({
        "ok": True,
        "require_app_grant": SAFETY.policy.require_app_grant,
        "allow_system_shortcuts": SAFETY.policy.allow_system_shortcuts,
        "show_overlay": SAFETY.policy.show_overlay,
        "smooth_cursor_ms": SAFETY.policy.smooth_cursor_ms,
        "annotate_mode": SAFETY.policy.annotate_mode,
    })


@mcp.tool(structured_output=False)
def emergency_stop(
    reset: bool = Field(default=False, description="Set true to clear an active emergency stop and resume automation."),
    reason: str = Field(default="Emergency stop requested", description="Reason for stopping or resuming."),
) -> str:
    """Immediately halt all Computer Use input actions, or reset an active stop lock."""
    res = SAFETY.set_emergency_stop(active=not reset, reason=reason)
    if reset:
        OVERLAY.notify_action("Otomasyon devam ediyor", state="working")
    else:
        OVERLAY.notify_stopped(reason)
    SAFETY.audit("emergency_stop", {"reset": reset, "reason": reason}, ok=True)
    return _json_text(res)


if __name__ == "__main__":
    mcp.run(transport="stdio")
