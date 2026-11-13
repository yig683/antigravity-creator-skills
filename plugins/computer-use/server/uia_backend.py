"""Bounded, timeout-safe Windows UI Automation (UIA) inspector."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import queue
import threading
import time
from typing import Any

import comtypes.gen.UIAutomationClient as uia_gen
import uiautomation as auto
from uiautomation import uiautomation as uia_mod

from win32_backend import ViewportMapping

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_user32.EnumChildWindows.argtypes = [wt.HWND, _WNDENUMPROC, wt.LPARAM]
_user32.EnumChildWindows.restype = wt.BOOL
_user32.IsWindow.argtypes = [wt.HWND]
_user32.IsWindow.restype = wt.BOOL
_user32.IsWindowVisible.argtypes = [wt.HWND]
_user32.IsWindowVisible.restype = wt.BOOL
_user32.SendMessageTimeoutW.argtypes = [
    wt.HWND,
    wt.UINT,
    wt.WPARAM,
    ctypes.c_ssize_t,
    wt.UINT,
    wt.UINT,
    ctypes.POINTER(ctypes.c_size_t),
]
_user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t

_WM_GETOBJECT = 0x003D
_OBJID_CLIENT = -4
_SMTO_ABORTIFHUNG = 0x0002

_NUDGE_LOCK = threading.Lock()
_NUDGED_HWNDS: set[int] = set()

_COM_INTERACTIVE_CONTROL_IDS: tuple[int, ...] = (
    uia_mod.ControlType.ButtonControl,
    uia_mod.ControlType.EditControl,
    uia_mod.ControlType.ComboBoxControl,
    uia_mod.ControlType.CheckBoxControl,
    uia_mod.ControlType.RadioButtonControl,
    uia_mod.ControlType.MenuItemControl,
    uia_mod.ControlType.TabItemControl,
    uia_mod.ControlType.SplitButtonControl,
    uia_mod.ControlType.SliderControl,
    uia_mod.ControlType.SpinnerControl,
)

_COM_WEB_EXTRA_CONTROL_IDS: tuple[int, ...] = (
    uia_mod.ControlType.HyperlinkControl,
    uia_mod.ControlType.ListItemControl,
    uia_mod.ControlType.TreeItemControl,
)


def _iter_target_hwnds(hwnd: int, max_children: int = 24) -> list[int]:
    """Return [hwnd] plus unique visible child HWNDs (e.g. WebView2/Chromium hosts)."""
    targets: list[int] = [hwnd]
    if hwnd <= 0:
        return targets
    try:
        if not _user32.IsWindowVisible(hwnd):
            return targets
        seen = {hwnd}

        def _cb(child_hwnd: int, _lparam: int) -> bool:
            if len(targets) - 1 >= max_children:
                return False
            ch = int(child_hwnd)
            if ch not in seen and _user32.IsWindowVisible(ch):
                seen.add(ch)
                targets.append(ch)
            return True

        cb_fn = _WNDENUMPROC(_cb)
        _user32.EnumChildWindows(hwnd, cb_fn, 0)
    except Exception:
        pass
    return targets


def _wake_chromium_accessibility(hwnds: list[int], force: bool = False) -> bool:
    """Nudge lazy Chromium/WebView2 accessibility providers with a non-blocking WM_GETOBJECT."""
    nudged = False
    res = ctypes.c_size_t(0)
    for h in hwnds:
        if h <= 0:
            continue
        with _NUDGE_LOCK:
            already = h in _NUDGED_HWNDS
            if already and not force:
                continue
            _NUDGED_HWNDS.add(h)
        try:
            _user32.SendMessageTimeoutW(
                h,
                _WM_GETOBJECT,
                0,
                _OBJID_CLIENT,
                _SMTO_ABORTIFHUNG,
                60,
                ctypes.byref(res),
            )
            nudged = True
        except Exception:
            continue
    return nudged

CONTROL_TYPE_NAME_TO_ID: dict[str, int] = {
    "button": uia_mod.ControlType.ButtonControl,
    "checkbox": uia_mod.ControlType.CheckBoxControl,
    "combobox": uia_mod.ControlType.ComboBoxControl,
    "custom": uia_mod.ControlType.CustomControl,
    "document": uia_mod.ControlType.DocumentControl,
    "edit": uia_mod.ControlType.EditControl,
    "group": uia_mod.ControlType.GroupControl,
    "hyperlink": uia_mod.ControlType.HyperlinkControl,
    "image": uia_mod.ControlType.ImageControl,
    "link": uia_mod.ControlType.HyperlinkControl,
    "listitem": uia_mod.ControlType.ListItemControl,
    "menuitem": uia_mod.ControlType.MenuItemControl,
    "pane": uia_mod.ControlType.PaneControl,
    "radiobutton": uia_mod.ControlType.RadioButtonControl,
    "scrollbar": uia_mod.ControlType.ScrollBarControl,
    "slider": uia_mod.ControlType.SliderControl,
    "spinner": uia_mod.ControlType.SpinnerControl,
    "splitbutton": uia_mod.ControlType.SplitButtonControl,
    "tabitem": uia_mod.ControlType.TabItemControl,
    "text": uia_mod.ControlType.TextControl,
    "toolbar": uia_mod.ControlType.ToolBarControl,
    "treeitem": uia_mod.ControlType.TreeItemControl,
}

INTERACTIVE_CONTROL_TYPES = frozenset({
    "Button",
    "CheckBox",
    "ComboBox",
    "Document",
    "Edit",
    "Hyperlink",
    "ListItem",
    "MenuItem",
    "RadioButton",
    "ScrollBar",
    "Slider",
    "Spinner",
    "SplitButton",
    "TabItem",
    "ToolBar",
    "TreeItem",
})


def _clean_control_type(raw_name: str) -> str:
    if raw_name.endswith("Control"):
        return raw_name[:-7]
    return raw_name


def _safe_rect(ctrl: Any) -> tuple[int, int, int, int] | None:
    try:
        rc = ctrl.BoundingRectangle
        if rc is None or rc.width() <= 0 or rc.height() <= 0:
            return None
        return int(rc.left), int(rc.top), int(rc.right), int(rc.bottom)
    except Exception:
        return None


def _safe_value(ctrl: Any, ctrl_type: str) -> str | None:
    try:
        if bool(getattr(ctrl, "IsPassword", False)):
            return "[REDACTED_PASSWORD]"
    except Exception:
        pass

    if ctrl_type not in {"Edit", "ComboBox", "Document", "Slider", "Spinner"}:
        return None

    try:
        pattern = ctrl.GetValuePattern()
        if pattern is not None:
            val = pattern.Value
            if isinstance(val, str):
                return val[:120] + ("..." if len(val) > 120 else "")
    except Exception:
        pass
    return None


def _safe_str_attr(ctrl: Any, attr: str) -> str:
    try:
        return str(getattr(ctrl, attr) or "").strip()
    except Exception:
        return ""


def _safe_bool_attr(ctrl: Any, attr: str, default: bool) -> bool:
    try:
        return bool(getattr(ctrl, attr))
    except Exception:
        return default


_TOP_CHROME_HEIGHT_PX = 115
_TOP_CHROME_MAX_SLOTS = 32


def _viewport_bounds_from_mapping(
    viewport: ViewportMapping,
    viewport_bounds: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int, int]:
    """Return physical (left, top, right, bottom) bounds for the target viewport."""
    if viewport_bounds is not None:
        return (
            int(viewport_bounds[0]),
            int(viewport_bounds[1]),
            int(viewport_bounds[2]),
            int(viewport_bounds[3]),
        )
    return (
        int(viewport.src_left),
        int(viewport.src_top),
        int(viewport.src_left + viewport.src_width),
        int(viewport.src_top + viewport.src_height),
    )


def _clip_rect_to_viewport(
    rect: tuple[int, int, int, int],
    viewport_bounds: tuple[int, int, int, int],
    min_visible_px: int = 4,
) -> tuple[int, int, int, int] | None:
    """Intersect physical rect with viewport_bounds; return None when offscreen or negligible."""
    x1, y1, x2, y2 = rect
    vp_left, vp_top, vp_right, vp_bottom = viewport_bounds
    ix1 = max(x1, vp_left)
    iy1 = max(y1, vp_top)
    ix2 = min(x2, vp_right)
    iy2 = min(y2, vp_bottom)
    if (ix2 - ix1) < min_visible_px or (iy2 - iy1) < min_visible_px:
        return None
    return ix1, iy1, ix2, iy2


def _is_oversized_wrapper(
    rect: tuple[int, int, int, int],
    viewport_bounds: tuple[int, int, int, int],
) -> bool:
    """Return True when element spans >88% of both viewport width and height."""
    vp_w = max(1, viewport_bounds[2] - viewport_bounds[0])
    vp_h = max(1, viewport_bounds[3] - viewport_bounds[1])
    w = rect[2] - rect[0]
    h = rect[3] - rect[1]
    return w > vp_w * 0.88 and h > vp_h * 0.88


def _build_viewport_item(
    ctrl_type: str,
    name: str,
    auto_id: str,
    help_text: str,
    enabled: bool,
    clipped_rect: tuple[int, int, int, int],
    viewport: ViewportMapping,
) -> dict[str, Any]:
    """Build a standard element dictionary from a viewport-clipped physical rectangle."""
    ix1, iy1, ix2, iy2 = clipped_rect
    px = int(ix1 + (ix2 - ix1) // 2)
    py = int(iy1 + (iy2 - iy1) // 2)
    sx1, sy1 = viewport.to_screenshot(ix1, iy1)
    sx2, sy2 = viewport.to_screenshot(ix2, iy2)
    scx, scy = viewport.to_screenshot(px, py)
    item: dict[str, Any] = {
        "type": ctrl_type,
        "name": name,
        "automation_id": auto_id,
        "enabled": enabled,
        "center": [scx, scy],
        "physical_center": [px, py],
        "bounds": [sx1, sy1, sx2, sy2],
    }
    if help_text and help_text != name:
        item["help_text"] = help_text
    return item


def _prioritize_and_sort_elements(
    items: list[dict[str, Any]],
    viewport: ViewportMapping,
    max_elements: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Prevent top chrome from starving web-body controls and sort deterministically top-to-bottom."""
    if max_elements <= 0:
        return [], bool(items)

    def _sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
        bounds = item.get("bounds") or [0, 0, 0, 0]
        center = item.get("center") or [0, 0]
        return (int(center[1]), int(center[0]), int(bounds[1]), int(bounds[0]), str(item.get("name") or ""))

    vp_top = int(viewport.src_top)
    chrome_items: list[dict[str, Any]] = []
    body_items: list[dict[str, Any]] = []
    for item in items:
        phys_center = item.get("physical_center")
        if phys_center and len(phys_center) == 2:
            py = int(phys_center[1])
        else:
            _, py = viewport.to_physical(item["center"][0], item["center"][1])
        if (py - vp_top) < _TOP_CHROME_HEIGHT_PX:
            chrome_items.append(item)
        else:
            body_items.append(item)

    chrome_items.sort(key=_sort_key)
    body_items.sort(key=_sort_key)

    total = len(chrome_items) + len(body_items)
    if total <= max_elements:
        selected = chrome_items + body_items
        selected.sort(key=_sort_key)
        return selected, False

    chrome_cap = min(_TOP_CHROME_MAX_SLOTS, max(1, round(max_elements * 0.34)))
    if not body_items:
        chosen_chrome = chrome_items[:max_elements]
        chosen_body: list[dict[str, Any]] = []
    elif len(chrome_items) <= chrome_cap:
        chosen_chrome = chrome_items
        chosen_body = body_items[: max_elements - len(chosen_chrome)]
    else:
        min_body_reserve = max_elements - chrome_cap
        chosen_body = body_items[:min_body_reserve]
        if len(body_items) < min_body_reserve:
            chosen_chrome = chrome_items[: max_elements - len(chosen_body)]
        else:
            chosen_chrome = chrome_items[:chrome_cap]

    selected = chosen_chrome + chosen_body
    selected.sort(key=_sort_key)
    return selected, True


def _inspect_hwnd_sync(
    hwnd: int,
    viewport: ViewportMapping,
    max_depth: int,
    max_elements: int,
    interactive_only: bool,
    filter_text: str | None,
    include_web_content: bool,
    timeout_sec: float,
    viewport_bounds: tuple[int, int, int, int] | None = None,
    control_type: str | None = None,
) -> dict[str, Any]:
    """Walk the UIA tree breadth-first using ControlViewWalker with strict time/node caps."""
    deadline = time.monotonic() + timeout_sec
    needle = (filter_text or "").strip().lower()
    ct_filter = control_type.strip().lower().removesuffix("control") if control_type else None
    vp_bounds = _viewport_bounds_from_mapping(viewport, viewport_bounds)
    elements: list[dict[str, Any]] = []
    oversized_elements: list[dict[str, Any]] = []
    offscreen_matches = 0
    truncated = False
    collect_cap = min(max_elements, 15) if needle else max(max_elements * 2, 160)

    with auto.UIAutomationInitializerInThread():
        root = auto.ControlFromHandle(hwnd)
        if root is None:
            raise RuntimeError(f"Could not obtain UI Automation control for HWND {hwnd}.")

        bf_queue: list[tuple[Any, int]] = [(root, 0)]
        visited = 0

        while bf_queue:
            if time.monotonic() >= deadline or len(elements) >= collect_cap:
                truncated = True
                break

            ctrl, depth = bf_queue.pop(0)
            visited += 1
            if visited > 900:
                truncated = True
                break

            ctrl_type = _clean_control_type(_safe_str_attr(ctrl, "ControlTypeName"))
            name = _safe_str_attr(ctrl, "Name")
            auto_id = _safe_str_attr(ctrl, "AutomationId")
            help_text = _safe_str_attr(ctrl, "HelpText")
            is_offscreen = _safe_bool_attr(ctrl, "IsOffscreen", False)
            is_enabled = _safe_bool_attr(ctrl, "IsEnabled", True)
            is_focusable = _safe_bool_attr(ctrl, "IsKeyboardFocusable", False)

            rect = _safe_rect(ctrl)
            is_interactive = ctrl_type in INTERACTIVE_CONTROL_TYPES or is_focusable
            has_label = bool(name or auto_id or help_text or ctrl_type in {"Edit", "Document", "ComboBox", "Slider"})
            matches_type = ct_filter is None or ctrl_type.lower() == ct_filter
            matches_needle = True
            if needle:
                hay = f"{name} {auto_id} {help_text} {ctrl_type}".lower()
                matches_needle = needle in hay

            eligible = (
                depth > 0
                and bool(ctrl_type)
                and rect is not None
                and (not interactive_only or is_interactive)
                and has_label
                and matches_type
                and matches_needle
            )

            if eligible and rect is not None:
                clipped = None if is_offscreen else _clip_rect_to_viewport(rect, vp_bounds)
                if clipped is None:
                    offscreen_matches += 1
                else:
                    oversized = _is_oversized_wrapper(rect, vp_bounds)
                    if not (oversized and interactive_only and not needle):
                        item = _build_viewport_item(
                            ctrl_type=ctrl_type,
                            name=name,
                            auto_id=auto_id,
                            help_text=help_text,
                            enabled=is_enabled,
                            clipped_rect=clipped,
                            viewport=viewport,
                        )
                        val = _safe_value(ctrl, ctrl_type)
                        if val is not None:
                            item["value"] = val
                        if oversized:
                            oversized_elements.append(item)
                        else:
                            elements.append(item)

                        if needle and len(elements) >= min(max_elements, 15):
                            break

            # Avoid descending deep into dense browser Document DOM unless requested
            if depth < max_depth and not (ctrl_type == "Document" and not include_web_content and not needle):
                try:
                    child = ctrl.GetFirstChildControl()
                    while child is not None:
                        if time.monotonic() >= deadline:
                            truncated = True
                            break
                        bf_queue.append((child, depth + 1))
                        child = child.GetNextSiblingControl()
                except Exception:
                    continue

        if needle:
            final_elements = elements[:max_elements] if elements else oversized_elements[:max_elements]
        else:
            final_elements, sliced = _prioritize_and_sort_elements(elements, viewport, max_elements)
            truncated = truncated or sliced

        return {
            "hwnd": hwnd,
            "display_number": viewport.display_number,
            "element_count": len(final_elements),
            "truncated": truncated,
            "offscreen_matches": offscreen_matches,
            "elements": final_elements,
        }


def _build_com_cache_request(iuia: Any) -> Any:
    cache_req = iuia.CreateCacheRequest()
    cache_req.TreeScope = uia_gen.TreeScope_Element
    for pid in (
        uia_mod.PropertyId.ControlTypeProperty,
        uia_mod.PropertyId.NameProperty,
        uia_mod.PropertyId.AutomationIdProperty,
        uia_mod.PropertyId.HelpTextProperty,
        uia_mod.PropertyId.BoundingRectangleProperty,
        uia_mod.PropertyId.IsOffscreenProperty,
        uia_mod.PropertyId.IsEnabledProperty,
        uia_mod.PropertyId.IsKeyboardFocusableProperty,
    ):
        cache_req.AddProperty(pid)
    return cache_req


def _or_conditions(iuia: Any, conditions: list[Any]) -> Any:
    combined = conditions[0]
    for cond in conditions[1:]:
        combined = iuia.CreateOrCondition(combined, cond)
    return combined


def _extract_cached_element(
    el: Any,
    viewport: ViewportMapping,
    viewport_bounds: tuple[int, int, int, int] | None = None,
    stats: dict[str, int] | None = None,
    seen_offscreen: set[tuple[int, int, int, int, str, str]] | None = None,
    oversized_ids: set[int] | None = None,
    offscreen_els: list[tuple[Any, str, str, int, bool, bool]] | None = None,
) -> tuple[dict[str, Any], bool, int] | None:
    """Extract and viewport-clip a cached COM element, tracking offscreen rejections."""
    try:
        rc = el.CachedBoundingRectangle
        x1, y1, x2, y2 = int(rc.left), int(rc.top), int(rc.right), int(rc.bottom)
        w = x2 - x1
        h = y2 - y1
        if w <= 1 or h <= 1:
            return None
        raw_ct = uia_mod.ControlTypeNames.get(int(el.CachedControlType), "")
        ct = _clean_control_type(raw_ct)
        if not ct:
            return None
        is_offscreen = bool(el.CachedIsOffscreen)
        focusable = bool(el.CachedIsKeyboardFocusable)
        name = (el.CachedName or "").strip()
        auto_id = (el.CachedAutomationId or "").strip()
        enabled = bool(el.CachedIsEnabled)
    except Exception:
        return None

    try:
        help_text = (el.CachedHelpText or "").strip()
    except Exception:
        help_text = ""

    is_interactive = ct in INTERACTIVE_CONTROL_TYPES or focusable
    vp_bounds = _viewport_bounds_from_mapping(viewport, viewport_bounds)
    clipped = None if is_offscreen else _clip_rect_to_viewport((x1, y1, x2, y2), vp_bounds)
    if clipped is None:
        if stats is not None:
            okey = (x1, y1, x2, y2, ct, name)
            if seen_offscreen is None or okey not in seen_offscreen:
                if seen_offscreen is not None:
                    seen_offscreen.add(okey)
                stats["offscreen_matches"] = stats.get("offscreen_matches", 0) + 1
        if offscreen_els is not None and (name or auto_id or help_text):
            offscreen_els.append((el, name or auto_id or help_text, ct, max(1, w) * max(1, h), enabled, is_interactive))
        return None

    item = _build_viewport_item(
        ctrl_type=ct,
        name=name,
        auto_id=auto_id,
        help_text=help_text,
        enabled=enabled,
        clipped_rect=clipped,
        viewport=viewport,
    )
    if oversized_ids is not None and _is_oversized_wrapper((x1, y1, x2, y2), vp_bounds):
        oversized_ids.add(id(item))
    return item, is_interactive, w * h


def _run_com_findall(
    hwnd: int,
    cond_builder: Any,
    viewport: ViewportMapping,
    max_scan: int = 800,
    min_before_wake: int = 1,
    viewport_bounds: tuple[int, int, int, int] | None = None,
    stats_out: dict[str, int] | None = None,
    oversized_ids: set[int] | None = None,
    offscreen_els_out: list[tuple[Any, str, str, int, bool, bool]] | None = None,
) -> list[tuple[dict[str, Any], bool, int]]:
    """Run FindAllBuildCache across top+child HWNDs, nudging lazy Chromium/WebView2 trees once if empty."""
    if not _user32.IsWindow(hwnd):
        return []

    vp_bounds = _viewport_bounds_from_mapping(viewport, viewport_bounds)
    hwnds = _iter_target_hwnds(hwnd)
    with auto.UIAutomationInitializerInThread():
        client = uia_mod._AutomationClient.instance()
        iuia = client.IUIAutomation
        cache_req = _build_com_cache_request(iuia)
        query_cond = cond_builder(iuia)

        def _probe() -> tuple[
            list[tuple[dict[str, Any], bool, int]],
            dict[str, int],
            set[int],
            list[tuple[Any, str, str, int, bool, bool]],
        ]:
            collected: list[tuple[dict[str, Any], bool, int]] = []
            seen_keys: set[tuple[int, int, str, str]] = set()
            seen_offscreen: set[tuple[int, int, int, int, str, str]] = set()
            probe_stats: dict[str, int] = {"offscreen_matches": 0}
            probe_oversized: set[int] = set()
            probe_offscreen: list[tuple[Any, str, str, int, bool, bool]] = []
            off_sink = probe_offscreen if offscreen_els_out is not None else None
            for target_h in hwnds:
                try:
                    root = iuia.ElementFromHandle(target_h)
                except Exception:
                    root = None
                if not root:
                    continue
                try:
                    found = root.FindAllBuildCache(uia_gen.TreeScope_Descendants, query_cond, cache_req)
                except Exception:
                    continue
                if not found:
                    continue
                limit = min(int(found.Length), max_scan)
                for i in range(limit):
                    parsed = _extract_cached_element(
                        found.GetElement(i),
                        viewport,
                        viewport_bounds=vp_bounds,
                        stats=probe_stats,
                        seen_offscreen=seen_offscreen,
                        oversized_ids=probe_oversized,
                        offscreen_els=off_sink,
                    )
                    if parsed is None:
                        continue
                    item, is_inter, area = parsed
                    dedup_key = (item["center"][0], item["center"][1], item["type"], item["name"])
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    collected.append((item, is_inter, area))
            return collected, probe_stats, probe_oversized, probe_offscreen

        results, final_stats, final_oversized, final_offscreen = _probe()
        if len(results) < min_before_wake and _wake_chromium_accessibility(hwnds):
            time.sleep(0.18)
            retry, retry_stats, retry_oversized, retry_offscreen = _probe()
            if len(retry) > len(results) or (
                not results and retry_stats["offscreen_matches"] > final_stats["offscreen_matches"]
            ):
                results, final_stats, final_oversized, final_offscreen = (
                    retry,
                    retry_stats,
                    retry_oversized,
                    retry_offscreen,
                )

        if stats_out is not None:
            stats_out["offscreen_matches"] = stats_out.get("offscreen_matches", 0) + final_stats["offscreen_matches"]
        if oversized_ids is not None:
            oversized_ids.update(final_oversized)
        if offscreen_els_out is not None:
            offscreen_els_out.extend(final_offscreen)
        return results


def _try_scroll_com_element_into_view(raw_el: Any) -> bool:
    """Ask Windows UIA to scroll an offscreen COM element into the viewport cleanly."""
    if raw_el is None:
        return False
    try:
        if hasattr(raw_el, "GetCurrentPattern"):
            pat = raw_el.GetCurrentPattern(uia_mod.PatternId.ScrollItemPattern)
            if pat:
                scroll_item = pat.QueryInterface(uia_gen.IUIAutomationScrollItemPattern)
                scroll_item.ScrollIntoView()
                return True
    except Exception:
        pass
    try:
        if hasattr(raw_el, "SetFocus"):
            raw_el.SetFocus()
            return True
    except Exception:
        pass
    return False


def _find_elements_com_sync(
    hwnd: int,
    viewport: ViewportMapping,
    query: str,
    control_type: str | None = None,
    max_results: int = 25,
    interactive_only: bool = True,
    allow_non_interactive_fallback: bool = False,
    max_scan: int = 800,
    stats_out: dict[str, int] | None = None,
    auto_scroll: bool = True,
) -> list[dict[str, Any]]:
    """Single-pass native C++ UIAutomation FindAllBuildCache search across Name/AutomationId/HelpText."""
    needle = query.strip()
    if not needle:
        return []

    flags = uia_gen.PropertyConditionFlags_IgnoreCase | uia_gen.PropertyConditionFlags_MatchSubstring

    def _build_query_cond(iuia: Any) -> Any:
        name_cond = iuia.CreatePropertyConditionEx(uia_mod.PropertyId.NameProperty, needle, flags)
        aid_cond = iuia.CreatePropertyConditionEx(uia_mod.PropertyId.AutomationIdProperty, needle, flags)
        help_cond = iuia.CreatePropertyConditionEx(uia_mod.PropertyId.HelpTextProperty, needle, flags)
        qcond = _or_conditions(iuia, [name_cond, aid_cond, help_cond])
        if control_type:
            ct_key = control_type.strip().lower().removesuffix("control")
            ct_id = CONTROL_TYPE_NAME_TO_ID.get(ct_key)
            if ct_id is not None:
                ct_cond = iuia.CreatePropertyCondition(uia_mod.PropertyId.ControlTypeProperty, ct_id)
                qcond = iuia.CreateAndCondition(qcond, ct_cond)
        return qcond

    oversized_ids: set[int] = set()
    offscreen_els: list[tuple[Any, str, str, int, bool, bool]] = []
    raw = _run_com_findall(
        hwnd=hwnd,
        cond_builder=_build_query_cond,
        viewport=viewport,
        max_scan=max_scan,
        min_before_wake=1,
        stats_out=stats_out,
        oversized_ids=oversized_ids,
        offscreen_els_out=offscreen_els if auto_scroll else None,
    )

    needle_low = needle.lower()
    inter_candidates: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []
    other_candidates: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []
    oversized_inter: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []
    oversized_other: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []

    for item, is_inter, area in raw:
        is_oversized = id(item) in oversized_ids
        name_l = item["name"].lower()
        aid_l = item["automation_id"].lower()
        help_l = item.get("help_text", "").lower()
        exact_rank = 0 if needle_low in (name_l, aid_l, help_l) else 1
        enabled_rank = 0 if item["enabled"] else 1
        inter_rank = 0 if item["type"] in INTERACTIVE_CONTROL_TYPES else 1
        oversized_rank = 1 if is_oversized else 0
        entry = ((oversized_rank, exact_rank, enabled_rank, inter_rank, area), item)
        if is_oversized:
            if is_inter:
                oversized_inter.append(entry)
            else:
                oversized_other.append(entry)
        elif is_inter:
            inter_candidates.append(entry)
        else:
            other_candidates.append(entry)

    if interactive_only and not allow_non_interactive_fallback:
        chosen = inter_candidates if inter_candidates else oversized_inter
    elif interactive_only:
        if inter_candidates:
            chosen = inter_candidates
        elif other_candidates:
            chosen = other_candidates
        else:
            chosen = oversized_inter or oversized_other
    else:
        smaller = inter_candidates + other_candidates
        chosen = smaller if smaller else (oversized_inter + oversized_other)

    # Auto-scroll offscreen matching COM controls into view (eliminates blind scroll loops).
    if auto_scroll and offscreen_els and (not chosen or (interactive_only and not inter_candidates)):
        has_exact_onscreen = any(pair[0][1] == 0 and pair[0][0] == 0 for pair in chosen)
        off_interactive = [row for row in offscreen_els if row[5]]
        if not chosen or (interactive_only and not inter_candidates and off_interactive and not has_exact_onscreen):
            offscreen_els.sort(
                key=lambda row: (
                    0 if row[1].lower() == needle_low else 1,
                    0 if row[4] else 1,
                    0 if row[5] else 1,
                    row[3],
                )
            )
            for cand_el, *_ in offscreen_els[:3]:
                if _try_scroll_com_element_into_view(cand_el):
                    time.sleep(0.09)
                    retry = _find_elements_com_sync(
                        hwnd=hwnd,
                        viewport=viewport,
                        query=needle,
                        control_type=control_type,
                        max_results=max_results,
                        interactive_only=interactive_only,
                        allow_non_interactive_fallback=allow_non_interactive_fallback,
                        max_scan=max_scan,
                        stats_out=stats_out,
                        auto_scroll=False,
                    )
                    if retry:
                        return [{**item, "scrolled_into_view": True} for item in retry]

    chosen.sort(key=lambda pair: pair[0])
    return [item for _, item in chosen[:max_results]]


def _list_interactive_com_sync(
    hwnd: int,
    viewport: ViewportMapping,
    max_elements: int = 95,
    interactive_only: bool = True,
    include_web_content: bool = False,
    stats_out: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Deep native C++ COM listing for deep Chrome/Electron/WebView2 trees."""
    type_ids = list(_COM_INTERACTIVE_CONTROL_IDS)
    if include_web_content or not interactive_only:
        type_ids.extend(_COM_WEB_EXTRA_CONTROL_IDS)
    if not interactive_only:
        type_ids.extend((uia_mod.ControlType.TextControl, uia_mod.ControlType.GroupControl))

    def _build_list_cond(iuia: Any) -> Any:
        conds = [
            iuia.CreatePropertyCondition(uia_mod.PropertyId.ControlTypeProperty, cid)
            for cid in type_ids
        ]
        custom_cond = iuia.CreateAndCondition(
            iuia.CreatePropertyCondition(uia_mod.PropertyId.ControlTypeProperty, uia_mod.ControlType.CustomControl),
            iuia.CreatePropertyCondition(uia_mod.PropertyId.IsKeyboardFocusableProperty, True),
        )
        conds.append(custom_cond)
        return _or_conditions(iuia, conds)

    oversized_ids: set[int] = set()
    raw = _run_com_findall(
        hwnd=hwnd,
        cond_builder=_build_list_cond,
        viewport=viewport,
        max_scan=max(450, max_elements * 9),
        min_before_wake=5,
        stats_out=stats_out,
        oversized_ids=oversized_ids,
    )
    items: list[dict[str, Any]] = []
    for item, is_inter, _area in raw:
        if interactive_only and (not is_inter or id(item) in oversized_ids):
            continue
        if not (
            item["name"]
            or item["automation_id"]
            or item.get("help_text")
            or item["type"] in {"Edit", "Document", "ComboBox", "Slider", "Spinner"}
        ):
            continue
        items.append(item)

    prioritized, _ = _prioritize_and_sort_elements(items, viewport, max_elements)
    return prioritized


def find_element_target(
    hwnd: int,
    viewport: ViewportMapping,
    name: str,
    control_type: str | None = None,
    interactive_only: bool = True,
    timeout_sec: float = 1.2,
) -> dict[str, Any] | None:
    """Locate the best matching UI element center on a background thread with timeout."""
    result_q: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            matches: list[dict[str, Any]] = []
            com_stats = {"offscreen_matches": 0}
            bfs_offscreen = 0
            try:
                matches = _find_elements_com_sync(
                    hwnd=hwnd,
                    viewport=viewport,
                    query=name,
                    control_type=control_type,
                    max_results=10,
                    interactive_only=interactive_only,
                    allow_non_interactive_fallback=bool(interactive_only and not control_type),
                    stats_out=com_stats,
                )
            except Exception:
                matches = []
            if not matches:
                # Fallback to bounded BFS walk (handles legacy / mocked controls cleanly)
                bfs = _inspect_hwnd_sync(
                    hwnd=hwnd,
                    viewport=viewport,
                    max_depth=5,
                    max_elements=15,
                    interactive_only=interactive_only,
                    filter_text=name,
                    include_web_content=True,
                    timeout_sec=max(0.3, min(3.0, timeout_sec)),
                    control_type=control_type,
                )
                bfs_offscreen = int(bfs.get("offscreen_matches", 0))
                for el in bfs.get("elements", []):
                    if control_type and control_type.strip().lower().removesuffix("control") != el["type"].lower():
                        continue
                    if "physical_center" not in el:
                        sx, sy = el["center"]
                        px, py = viewport.to_physical(sx, sy)
                        el = {**el, "physical_center": [px, py]}
                    matches.append(el)

            offscreen_matches = max(com_stats["offscreen_matches"], bfs_offscreen)
            if matches:
                best = dict(matches[0])
                best["found"] = True
                best["offscreen_matches"] = offscreen_matches
                result_q.put((True, best))
            elif offscreen_matches > 0:
                result_q.put((
                    True,
                    {
                        "found": False,
                        "offscreen_matches": offscreen_matches,
                        "detail": (
                            f"Found {offscreen_matches} offscreen match(es) — "
                            "scroll to bring target into view"
                        ),
                    },
                ))
            else:
                result_q.put((True, None))
        except Exception as exc:
            result_q.put((False, exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    try:
        ok, payload = result_q.get(timeout=timeout_sec + 0.4)
    except queue.Empty:
        return None
    if not ok:
        raise payload
    return payload


def inspect_window_ui(
    hwnd: int,
    viewport: ViewportMapping,
    max_depth: int = 3,
    max_elements: int = 60,
    interactive_only: bool = True,
    filter_text: str | None = None,
    include_web_content: bool = False,
    timeout_sec: float = 1.2,
) -> dict[str, Any]:
    """Run UIA tree inspection on a daemon thread so slow browser DOMs never block MCP."""
    result_q: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)
    capped_elements = max(1, min(250, int(max_elements)))

    def _worker() -> None:
        try:
            com_stats = {"offscreen_matches": 0}
            # Fast native C++ COM lookup whenever filtering by element text/name
            if filter_text and filter_text.strip():
                try:
                    fast_items = _find_elements_com_sync(
                        hwnd=hwnd,
                        viewport=viewport,
                        query=filter_text,
                        max_results=min(100, capped_elements),
                        interactive_only=bool(interactive_only),
                        allow_non_interactive_fallback=bool(interactive_only),
                        stats_out=com_stats,
                    )
                except Exception:
                    fast_items = []
                if fast_items:
                    result_q.put((
                        True,
                        {
                            "hwnd": hwnd,
                            "display_number": viewport.display_number,
                            "element_count": len(fast_items),
                            "truncated": len(fast_items) >= capped_elements,
                            "offscreen_matches": com_stats["offscreen_matches"],
                            "elements": fast_items,
                        },
                    ))
                    return
            else:
                try:
                    listed = _list_interactive_com_sync(
                        hwnd=hwnd,
                        viewport=viewport,
                        max_elements=capped_elements,
                        interactive_only=bool(interactive_only),
                        include_web_content=bool(include_web_content),
                        stats_out=com_stats,
                    )
                except Exception:
                    listed = []
                if listed:
                    result_q.put((
                        True,
                        {
                            "hwnd": hwnd,
                            "display_number": viewport.display_number,
                            "element_count": len(listed),
                            "truncated": len(listed) >= capped_elements,
                            "offscreen_matches": com_stats["offscreen_matches"],
                            "elements": listed,
                        },
                    ))
                    return

            data = _inspect_hwnd_sync(
                hwnd=hwnd,
                viewport=viewport,
                max_depth=max(1, min(8, int(max_depth))),
                max_elements=capped_elements,
                interactive_only=bool(interactive_only),
                filter_text=filter_text,
                include_web_content=bool(include_web_content),
                timeout_sec=max(0.3, min(5.0, float(timeout_sec))),
            )
            data["offscreen_matches"] = max(int(data.get("offscreen_matches", 0)), com_stats["offscreen_matches"])
            result_q.put((True, data))
        except Exception as exc:
            result_q.put((False, exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    try:
        ok, payload = result_q.get(timeout=timeout_sec + 0.5)
    except queue.Empty as exc:
        raise TimeoutError(
            f"UI Automation timed out after {timeout_sec + 0.5:.1f}s for HWND {hwnd}. "
            "Use screenshot and zoom for visual inspection instead."
        ) from exc

    if not ok:
        raise payload
    return payload
