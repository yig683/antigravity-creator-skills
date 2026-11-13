"""Comprehensive tests for Windows Computer Use backend, safety policy, UIA, and MCP server."""

from __future__ import annotations

import asyncio
import base64
import ctypes
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PIL import Image as PILImage

SERVER_DIR = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SERVER_DIR.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from safety import SafetyManager  # noqa: E402
from win32_backend import INPUT, ViewportMapping, Win32Backend, wt  # noqa: E402


def test_win32_input_struct_size_and_point_call() -> None:
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(INPUT) == expected
    # Verify WindowFromPoint accepts WT.POINT by value on 64-bit Windows without ArgumentError
    _ = ctypes.windll.user32.WindowFromPoint(wt.POINT(0, 0))


def test_displays_and_coordinate_roundtrip(tmp_path: Path) -> None:
    backend = Win32Backend(tmp_path / "screenshots")
    displays = backend.list_displays()
    assert len(displays) >= 1
    assert displays[0].display_number == 1
    assert displays[0].is_primary is True
    assert displays[0].width > 0 and displays[0].height > 0

    vp = ViewportMapping(
        display_number=1,
        src_left=0,
        src_top=0,
        src_width=1920,
        src_height=1080,
        img_width=1280,
        img_height=720,
    )
    assert vp.to_physical(640, 360) == (960, 540)
    assert vp.to_screenshot(960, 540) == (640, 360)

    vp2 = ViewportMapping(
        display_number=2,
        src_left=1920,
        src_top=0,
        src_width=1920,
        src_height=1080,
        img_width=1280,
        img_height=720,
    )
    assert vp2.to_physical(100, 100) == (2070, 150)
    assert vp2.to_screenshot(2070, 150) == (100, 100)


def test_screenshot_and_zoom_pipeline_mocked_capture(tmp_path: Path) -> None:
    backend = Win32Backend(tmp_path / "screenshots")

    def fake_capture(left: int, top: int, width: int, height: int) -> PILImage.Image:
        return PILImage.new("RGB", (width, height), color=(24, 48, 72))

    with patch.object(Win32Backend, "capture_region_pil", staticmethod(fake_capture)):
        shot = backend.capture_screenshot(display_number=1, max_width=1280, max_height=800, show_cursor=True)
        shot_path = Path(shot["image_path"])
        assert shot_path.exists()
        assert shot["image_bytes"].startswith(b"\xff\xd8\xff")
        with PILImage.open(shot_path) as im:
            assert im.width <= 1280
            assert im.height <= 800
            assert im.mode == "RGB"

        zoom = backend.capture_zoom(region=[100, 100, 300, 220], display_number=1, fmt="png")
        zoom_path = Path(zoom["image_path"])
        assert zoom_path.exists()
        assert zoom["image_bytes"].startswith(b"\x89PNG")
        assert zoom["physical_region"][2] > zoom["physical_region"][0]
        assert zoom["physical_region"][3] > zoom["physical_region"][1]


def test_cursor_info_and_window_enumeration(tmp_path: Path) -> None:
    backend = Win32Backend(tmp_path / "screenshots")
    cursor = backend.get_cursor_info()
    assert len(cursor["screenshot_pos"]) == 2
    assert len(cursor["physical_pos"]) == 2
    assert cursor["display_number"] >= 1
    windows = backend.list_windows(include_minimized=True)
    assert isinstance(windows, list)


def test_key_parsing_and_turkish_unicode_inputs(tmp_path: Path) -> None:
    backend = Win32Backend(tmp_path / "screenshots")
    assert backend._parse_key_spec("Return") == [0x0D]
    assert backend._parse_key_spec("ctrl+shift+s") == [0x11, 0x10, ord("S")]
    assert backend._parse_key_spec("Super_L+r") == [0x5B, ord("R")]
    assert backend._parse_key_spec("Page_Down") == [0x22]

    for ch in ("ğ", "ü", "ş", "ı", "İ", "ö", "ç", "🚀"):
        inputs = backend._unicode_char_inputs(ch)
        assert len(inputs) >= 2
        assert all(inp.type == 1 for inp in inputs)


def test_safety_policy_blocks_grants_audit_and_emergency(tmp_path: Path) -> None:
    safety = SafetyManager(data_dir=tmp_path)

    blocked, _ = safety.is_blocked_target("1Password.exe", "1Password")
    assert blocked is True
    blocked_uac, _ = safety.is_blocked_target("consent.exe", "User Account Control")
    assert blocked_uac is True

    ok, _ = safety.check_input_allowed(
        "key",
        {"process_name": "notepad.exe", "title": "Untitled", "is_elevated": False},
        False,
        key_combo="alt+F4",
    )
    assert ok is False

    ok_uipi, msg_uipi = safety.check_input_allowed(
        "left_click",
        {"process_name": "regedit.exe", "title": "Registry Editor", "is_elevated": True},
        current_elevated=False,
    )
    assert ok_uipi is False
    assert "UIPI" in msg_uipi

    res = safety.request_access(["notepad.exe", "1password.exe"], reason="Test editing")
    assert res["granted"] == ["notepad.exe"]
    assert len(res["denied"]) == 1

    safety.policy.require_app_grant = True
    ok_calc, _ = safety.check_input_allowed(
        "left_click",
        {"process_name": "calc.exe", "title": "Calculator", "is_elevated": False},
        False,
    )
    assert ok_calc is False
    ok_np, _ = safety.check_input_allowed(
        "left_click",
        {"process_name": "notepad.exe", "title": "Notepad", "is_elevated": False},
        False,
    )
    assert ok_np is True

    safety.set_emergency_stop(True, "test halt")
    ok_stopped, _ = safety.check_input_allowed(
        "left_click",
        {"process_name": "notepad.exe", "title": "Notepad", "is_elevated": False},
        False,
    )
    assert ok_stopped is False
    safety.set_emergency_stop(False, "resume")

    safety.audit("type", {"text": "supersecret123"}, ok=True, redact_text=True)
    log_text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "supersecret123" not in log_text
    assert "<REDACTED len=14>" in log_text


def test_mcp_stdio_end_to_end(tmp_path: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    venv_python = PLUGIN_ROOT / ".venv" / "Scripts" / "python.exe"
    python_exe = venv_python if venv_python.exists() else Path(sys.executable)
    server_script = SERVER_DIR / "computer_use_mcp.py"

    async def _run() -> None:
        params = StdioServerParameters(
            command=str(python_exe),
            args=[str(server_script)],
            env={"COMPUTER_USE_DATA_DIR": str(tmp_path / "data"), "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_resp = await session.list_tools()
                names = {t.name for t in tools_resp.tools}
                expected_tools = {
                    "batch",
                    "screenshot",
                    "zoom",
                    "cursor_position",
                    "left_click",
                    "right_click",
                    "middle_click",
                    "double_click",
                    "triple_click",
                    "mouse_move",
                    "left_mouse_down",
                    "left_mouse_up",
                    "left_click_drag",
                    "scroll",
                    "type",
                    "key",
                    "hold_key",
                    "wait",
                    "list_displays",
                    "list_windows",
                    "get_frontmost",
                    "open_application",
                    "manage_window",
                    "inspect_ui",
                    "click_element",
                    "type_into",
                    "clipboard_get",
                    "clipboard_set",
                    "request_access",
                    "list_granted_applications",
                    "revoke_access",
                    "configure_safety",
                    "emergency_stop",
                }
                assert expected_tools == names

                batch_res = await session.call_tool(
                    "batch",
                    {
                        "actions": [{"action": "wait", "duration": 0.05}],
                        "screenshot_after": False,
                    },
                )
                assert not batch_res.is_error
                batch_json = json.loads(batch_res.content[0].text)
                assert batch_json["ok"] is True
                assert batch_json["elapsed_ms"] >= 0
                assert batch_json["batch_results"][0]["action"] == "wait"

                cfg_res = await session.call_tool(
                    "configure_safety",
                    {"show_overlay": True, "smooth_cursor_ms": 80},
                )
                assert not cfg_res.is_error
                cfg_json = json.loads(cfg_res.content[0].text)
                assert cfg_json["show_overlay"] is True
                assert cfg_json["smooth_cursor_ms"] == 80

                blocked_batch = await session.call_tool(
                    "batch",
                    {
                        "actions": [{"action": "key", "key": "alt+F4"}],
                        "screenshot_after": False,
                    },
                )
                assert blocked_batch.is_error is True

                disp_res = await session.call_tool("list_displays", {})
                assert not disp_res.is_error
                disp_json = json.loads(disp_res.content[0].text)
                assert len(disp_json["displays"]) >= 1

                cur_res = await session.call_tool("cursor_position", {})
                assert not cur_res.is_error
                cur_json = json.loads(cur_res.content[0].text)
                assert len(cur_json["physical_pos"]) == 2

                acc_res = await session.call_tool(
                    "request_access",
                    {"app_names": ["notepad", "1password"], "reason": "automated test"},
                )
                assert not acc_res.is_error
                acc_json = json.loads(acc_res.content[0].text)
                assert acc_json["granted"] == ["notepad"]
                assert len(acc_json["denied"]) == 1

                list_acc = await session.call_tool("list_granted_applications", {})
                assert not list_acc.is_error
                assert len(json.loads(list_acc.content[0].text)["granted_apps"]) == 1

                rev_res = await session.call_tool("revoke_access", {})
                assert not rev_res.is_error
                assert json.loads(rev_res.content[0].text)["granted_apps"] == []

                blocked_key = await session.call_tool("key", {"key": "alt+F4"})
                assert blocked_key.is_error is True

                stop_res = await session.call_tool("emergency_stop", {"reset": False, "reason": "test"})
                assert not stop_res.is_error
                blocked_wait = await session.call_tool("wait", {"duration": 0.1})
                assert blocked_wait.is_error is True
                resume_res = await session.call_tool("emergency_stop", {"reset": True, "reason": "done"})
                assert not resume_res.is_error

                # Verify screenshot tool error handling (or live capture if desktop DC is accessible)
                shot_res = await session.call_tool("screenshot", {"display_number": 1})
                if not shot_res.is_error:
                    assert shot_res.content[0].type == "image"
                    assert shot_res.content[0].mime_type == "image/jpeg"
                    raw_img = base64.b64decode(shot_res.content[0].data)
                    assert raw_img.startswith(b"\xff\xd8\xff")
                else:
                    assert "BitBlt screen capture failed" in shot_res.content[0].text

    asyncio.run(_run())


def test_uia_backend_inspect_hwnd_sync_and_document_skip() -> None:
    import uia_backend

    class FakeRect:
        def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
            self.left = left
            self.top = top
            self.right = right
            self.bottom = bottom

        def width(self) -> int:
            return self.right - self.left

        def height(self) -> int:
            return self.bottom - self.top

    class FakeControl:
        def __init__(
            self,
            ctrl_type: str,
            name: str,
            rect: FakeRect,
            auto_id: str = "",
            is_password: bool = False,
            children: list[FakeControl] | None = None,
        ) -> None:
            self.ControlTypeName = ctrl_type
            self.Name = name
            self.AutomationId = auto_id
            self.IsOffscreen = False
            self.IsEnabled = True
            self.IsKeyboardFocusable = ctrl_type in {"ButtonControl", "EditControl"}
            self.IsPassword = is_password
            self.BoundingRectangle = rect
            self._children = children or []
            self._next_sibling: FakeControl | None = None
            for idx in range(len(self._children) - 1):
                self._children[idx]._next_sibling = self._children[idx + 1]

        def GetFirstChildControl(self) -> FakeControl | None:
            return self._children[0] if self._children else None

        def GetNextSiblingControl(self) -> FakeControl | None:
            return self._next_sibling

        def GetValuePattern(self) -> None:
            return None

    class DummyInit:
        def __enter__(self) -> DummyInit:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    deep_link = FakeControl("HyperlinkControl", "Deep Link", FakeRect(200, 200, 400, 250))
    doc = FakeControl("DocumentControl", "Web Page", FakeRect(0, 100, 1920, 1080), children=[deep_link])
    save_btn = FakeControl("ButtonControl", "Save", FakeRect(15, 15, 135, 75), auto_id="btnSave")
    root = FakeControl("WindowControl", "Chrome", FakeRect(0, 0, 1920, 1080), children=[save_btn, doc])

    viewport = ViewportMapping(
        display_number=1,
        src_left=0,
        src_top=0,
        src_width=1920,
        src_height=1080,
        img_width=1280,
        img_height=720,
    )

    with (
        patch.object(uia_backend.auto, "UIAutomationInitializerInThread", DummyInit),
        patch.object(uia_backend.auto, "ControlFromHandle", return_value=root),
    ):
        res_default = uia_backend.inspect_window_ui(hwnd=1234, viewport=viewport, max_depth=3, interactive_only=True)
        names_default = [el["name"] for el in res_default["elements"]]
        assert "Save" in names_default
        assert "Deep Link" not in names_default
        save_el = next(el for el in res_default["elements"] if el["name"] == "Save")
        # 1920x1080 -> 1280x720 (factor 2/3): (15,15)-(135,75) -> (10,10)-(90,50), center (50,30)
        assert save_el["bounds"] == [10, 10, 90, 50]
        assert save_el["center"] == [50, 30]

        res_web = uia_backend.inspect_window_ui(
            hwnd=1234,
            viewport=viewport,
            max_depth=3,
            interactive_only=True,
            include_web_content=True,
        )
        names_web = [el["name"] for el in res_web["elements"]]
        assert "Save" in names_web
        assert "Deep Link" in names_web

        res_filtered = uia_backend.inspect_window_ui(
            hwnd=1234,
            viewport=viewport,
            max_depth=3,
            filter_text="save",
        )
        assert [el["name"] for el in res_filtered["elements"]] == ["Save"]

        target_btn = uia_backend.find_element_target(
            hwnd=1234,
            viewport=viewport,
            name="Save",
            control_type="Button",
        )
        assert target_btn is not None
        assert target_btn["center"] == [50, 30]
        assert target_btn["physical_center"] == [75, 45]


def test_desktop_overlay_rendering_and_lifecycle() -> None:
    import time
    from overlay import DesktopOverlay, _RippleEffect

    events: list[str] = []
    ov = DesktopOverlay(
        enabled=True,
        on_take_control=lambda: events.append("take"),
        on_resume_control=lambda: events.append("resume"),
    )
    try:
        ov.set_display_rect(0, 0, 1920, 1040, bounds=(0, 0, 1920, 1080))
        strips = ov._build_vignette_strips(1920, 1080, "working")
        assert [s.name for s in strips] == ["top", "bottom", "left", "right"]
        # Inner edge of top vignette fades smoothly near zero so no hard seam appears
        top_strip = strips[0].image
        assert top_strip.getpixel((960, top_strip.height - 1))[3] <= 3

        ov.notify_cursor(500, 300, label="İmleç hareketi")
        ov.notify_cursor(525, 312)
        ov.notify_press(True, 545, 322)
        ov.notify_action("Tıklanıyor [545, 322]", px=545, py=322)
        ov.notify_press(False, 545, 322)
        ov.notify_click(545, 322, button="left", count=2)
        ov.notify_thinking("Düşünüyor...")
        ov.notify_stopped("Kontrol sizde")

        # Hit-testing & one-click handover callbacks
        assert ov._hit_test_pill_local(335, 41, "working") == "takeover"
        assert ov._hit_test_pill_local(300, 41, "stopped") == "resume"
        assert ov._hit_test_pill_local(370, 41, "stopped") == "dismiss"
        ov._dispatch_pill_click("takeover")
        ov._dispatch_pill_click("resume")
        time.sleep(0.05)
        assert events == ["take", "resume"]

        pill_work = ov._render_pill("working", 'Yazılıyor: "Merhaba dünya"', 0.5)
        pill_stop = ov._render_pill("stopped", "Kontrol sizde", 0.5, hover_target="resume")
        halo_trail = ov._render_cursor_halo(
            "working",
            0.5,
            cur_x=540,
            cur_y=320,
            trail=[(500, 300, 0.08), (520, 310, 0.04), (540, 320, 0.0)],
            press_amount=0.4,
        )
        rip = ov._render_ripple(_RippleEffect(100, 100, (56, 189, 248), "click", "", time.monotonic()), 0.35)
        preview = ov.render_preview_composite(width=960, height=540, state="working")
        assert pill_work.size == (ov.PILL_W, ov.PILL_H)
        assert pill_stop.size == (ov.PILL_W, ov.PILL_H)
        assert halo_trail.size == (ov.CURSOR_SZ, ov.CURSOR_SZ)
        assert halo_trail.getbbox() is not None
        assert rip.size == (ov.RIPPLE_SZ, ov.RIPPLE_SZ)
        assert preview.size == (960, 540)
    finally:
        ov.close()


def test_uia_backend_resilient_child_traversal_and_helptext() -> None:
    import uia_backend

    class FakeRect:
        def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
            self.left, self.top, self.right, self.bottom = left, top, right, bottom

        def width(self) -> int:
            return self.right - self.left

        def height(self) -> int:
            return self.bottom - self.top

    class FlakyPane:
        ControlTypeName = "PaneControl"
        Name = ""
        AutomationId = "chromeWrapper"
        HelpText = ""
        IsOffscreen = False
        IsEnabled = True
        IsPassword = False
        BoundingRectangle = FakeRect(0, 0, 1920, 1080)

        def __init__(self, children: list[Any]) -> None:
            self._children = children
            self._next_sibling = None

        @property
        def IsKeyboardFocusable(self) -> bool:
            raise RuntimeError("transient COM property error")

        def GetFirstChildControl(self) -> Any:
            return self._children[0] if self._children else None

        def GetNextSiblingControl(self) -> Any:
            return self._next_sibling

    class SearchEdit:
        ControlTypeName = "EditControl"
        Name = ""
        AutomationId = "searchBox"
        HelpText = "Herhangi bir soru sorun"
        IsOffscreen = False
        IsEnabled = True
        IsKeyboardFocusable = True
        IsPassword = False
        BoundingRectangle = FakeRect(300, 450, 900, 510)
        _next_sibling = None

        def GetFirstChildControl(self) -> None:
            return None

        def GetNextSiblingControl(self) -> None:
            return None

        def GetValuePattern(self) -> None:
            return None

    class RootWin:
        ControlTypeName = "WindowControl"
        Name = "Gemini"
        AutomationId = ""
        HelpText = ""
        IsOffscreen = False
        IsEnabled = True
        IsKeyboardFocusable = False
        IsPassword = False
        BoundingRectangle = FakeRect(0, 0, 1920, 1080)

        def __init__(self, child: Any) -> None:
            self._child = child

        def GetFirstChildControl(self) -> Any:
            return self._child

        def GetNextSiblingControl(self) -> None:
            return None

    class DummyInit:
        def __enter__(self) -> DummyInit:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    viewport = ViewportMapping(
        display_number=1,
        src_left=0,
        src_top=0,
        src_width=1920,
        src_height=1080,
        img_width=1280,
        img_height=720,
    )
    root = RootWin(FlakyPane([SearchEdit()]))

    with (
        patch.object(uia_backend.auto, "UIAutomationInitializerInThread", DummyInit),
        patch.object(uia_backend.auto, "ControlFromHandle", return_value=root),
    ):
        found = uia_backend.find_element_target(hwnd=1234, viewport=viewport, name="soru sorun")
        assert found is not None
        assert found["automation_id"] == "searchBox"
        assert found["help_text"] == "Herhangi bir soru sorun"


def test_capture_screenshot_when_stable_and_timeout(tmp_path: Path) -> None:
    backend = Win32Backend(tmp_path / "shots")
    colors = [
        (220, 40, 40),
        (30, 120, 230),
        (30, 120, 230),
        (30, 120, 230),
        (30, 120, 230),
    ]
    idx = {"n": 0}

    def fake_grab(_l: int, _t: int, w: int, h: int) -> PILImage.Image:
        pos = min(idx["n"], len(colors) - 1)
        idx["n"] += 1
        return PILImage.new("RGB", (w, h), colors[pos])

    polls = {"count": 0}

    def on_poll() -> None:
        polls["count"] += 1

    with (
        patch.object(Win32Backend, "capture_region_pil", staticmethod(fake_grab)),
        patch.object(backend, "get_cursor_pos_physical", return_value=(100, 100)),
        patch.object(backend, "get_frontmost_window", return_value=None),
    ):
        settled = backend.capture_screenshot_when_stable(
            display_number=1,
            show_cursor=False,
            timeout_sec=1.5,
            poll_interval_sec=0.01,
            stability_period_sec=0.02,
            on_poll=on_poll,
        )
        assert settled["settle"]["stabilized"] is True
        assert settled["settle"]["frames"] >= 3
        assert polls["count"] >= 3
        assert settled["image"].getpixel((10, 10))[2] > 180

    toggle = {"val": 0}

    def always_changing(_l: int, _t: int, w: int, h: int) -> PILImage.Image:
        toggle["val"] = 1 - toggle["val"]
        return PILImage.new("RGB", (w, h), (255, 255, 255) if toggle["val"] else (0, 0, 0))

    with (
        patch.object(Win32Backend, "capture_region_pil", staticmethod(always_changing)),
        patch.object(backend, "get_cursor_pos_physical", return_value=(100, 100)),
        patch.object(backend, "get_frontmost_window", return_value=None),
    ):
        timed_out = backend.capture_screenshot_when_stable(
            display_number=1,
            show_cursor=False,
            timeout_sec=0.08,
            poll_interval_sec=0.015,
            stability_period_sec=0.04,
        )
        assert timed_out["settle"]["stabilized"] is False
        assert timed_out["settle"]["frames"] >= 2


def test_coordinate_grid_and_set_of_mark_annotation(tmp_path: Path) -> None:
    backend = Win32Backend(tmp_path / "shots", annotate_mode="grid")
    mgr = SafetyManager(tmp_path / "data")
    assert mgr.policy.annotate_mode == "grid"
    mgr.policy.annotate_mode = "som"
    mgr.save_policy()
    assert SafetyManager(tmp_path / "data").policy.annotate_mode == "som"

    def fake_capture(_l: int, _t: int, w: int, h: int) -> PILImage.Image:
        return PILImage.new("RGB", (w, h), (20, 24, 34))

    fake_elements = [
        {"type": "Button", "name": "New Conversation", "center": [85, 61], "bounds": [10, 48, 160, 74]},
        {"type": "Edit", "name": "Search", "center": [600, 120], "bounds": [400, 100, 800, 140]},
    ]

    with patch.object(Win32Backend, "capture_region_pil", staticmethod(fake_capture)):
        shot = backend.capture_screenshot(
            display_number=1,
            show_cursor=False,
            annotate_mode="som",
            marks_provider=lambda _vp: fake_elements,
        )
    assert "marks" in shot
    assert len(shot["marks"]) == 2
    assert shot["marks"][0] == {"id": 1, "type": "Button", "name": "New Conversation", "center": [85, 61]}
    assert backend.last_marks[2]["center"] == [600, 120]
    # Verify grid line at x=200 altered pixel color subtly above base (20, 24, 34)
    px200 = shot["image"].getpixel((200, 350))
    assert px200[2] > 34


def test_human_curved_glide_and_smooth_default(tmp_path: Path) -> None:
    import math
    mgr = SafetyManager(tmp_path / "data")
    assert mgr.policy.smooth_cursor_ms == 220

    # Curved minimum-jerk path starts softly, curves slightly off-chord, and lands strictly on target
    pts = Win32Backend._compute_human_glide_path(100, 200, 700, 200, steps=20, arc_sign=1)
    assert len(pts) == 20
    assert pts[-1] == (700, 200)
    first_step = pts[0][0] - 100
    mid_step = pts[10][0] - pts[9][0]
    last_step = pts[-1][0] - pts[-2][0]
    assert mid_step > first_step
    assert mid_step > last_step
    max_y_dev = max(abs(y - 200) for _x, y in pts)
    assert max_y_dev >= 8

    # Synthetic Escape suppression prevents AI shortcuts from tripping emergency stop
    mgr.mark_ai_activity(10.0)
    mgr.mark_synthetic_escape(0.5)
    assert mgr._last_esc_tap_ts == 0.0
    stopped, _ = mgr.is_emergency_stopped()
    # Physical keyboard isn't mocked pressed here, verify safe false
    assert math.isfinite(mgr._ai_active_until) and stopped is False


class _NoopOverlay:
    enabled = False

    def notify_action(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def notify_thinking(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def notify_stopped(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def notify_cursor(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def notify_press(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def notify_click(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def notify_scroll(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def set_display_rect(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def set_enabled(self, *_args: Any, **_kwargs: Any) -> None:
        pass


def _make_isolated_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Win32Backend]:
    """Import computer_use_mcp with isolated DATA_DIR, disabled live overlay, and deterministic viewport."""
    data_dir = tmp_path / "mcp_data"
    monkeypatch.setenv("COMPUTER_USE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("COMPUTER_USE_OVERLAY", "0")

    import computer_use_mcp as mcp_mod

    safety = SafetyManager(data_dir=data_dir)
    win32 = Win32Backend(tmp_path / "mcp_shots", overlay=None)
    vp = ViewportMapping(
        display_number=1,
        src_left=0,
        src_top=0,
        src_width=1920,
        src_height=1080,
        img_width=1280,
        img_height=720,
    )
    win32.active_viewport = vp
    win32.last_viewports_by_display[1] = vp

    fake_win = {
        "hwnd": 101,
        "title": "Test Browser",
        "pid": 4242,
        "process_name": "chrome.exe",
        "exe_path": "chrome.exe",
        "display_number": 1,
        "bounds_physical": {"left": 0, "top": 0, "width": 1920, "height": 1080},
        "bounds_screenshot": {"left": 0, "top": 0, "width": 1280, "height": 720},
        "is_minimized": False,
        "is_maximized": True,
        "is_foreground": True,
        "is_elevated": False,
    }
    monkeypatch.setattr(win32, "get_frontmost_window", lambda include_elevation=True: dict(fake_win))
    monkeypatch.setattr(win32, "get_window_info", lambda _hwnd, include_elevation=True: dict(fake_win))
    monkeypatch.setattr(win32, "_resolve_window_hwnd", lambda _target=None: 101)
    monkeypatch.setattr(win32, "_display_rect", lambda _disp=1: (1, 0, 0, 1920, 1080))
    monkeypatch.setattr(win32, "get_cursor_pos_physical", staticmethod(lambda: (960, 540)))

    monkeypatch.setattr(mcp_mod, "SAFETY", safety)
    monkeypatch.setattr(mcp_mod, "WIN32", win32)
    monkeypatch.setattr(mcp_mod, "OVERLAY", _NoopOverlay())
    mcp_mod._reset_click_state(reset_marks=True)
    return mcp_mod, win32


def _call_mcp(mcp_mod: Any, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    return asyncio.run(mcp_mod.mcp.call_tool(tool_name, arguments or {}))


def test_click_tools_target_resolution_mark_xy_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    mcp_mod, win32 = _make_isolated_mcp(tmp_path, monkeypatch)
    clicks: list[tuple[int | None, int | None, str, int]] = []

    def fake_click(
        px: int | None = None,
        py: int | None = None,
        button: str = "left",
        count: int = 1,
        modifiers: str | None = None,
        duration_ms: int | None = None,
    ) -> tuple[int, int]:
        clicks.append((px, py, button, count))
        return (px or 0, py or 0)

    monkeypatch.setattr(win32, "click", fake_click)
    monkeypatch.setattr(
        Win32Backend,
        "capture_region_pil",
        staticmethod(lambda _l, _t, w, h: PILImage.new("RGB", (w, h), (15, 25, 45))),
    )

    win32.last_marks = {
        7: {"id": 7, "type": "Button", "name": "Upload", "center": [200, 100]},
    }
    res_mark = json.loads(_call_mcp(mcp_mod, "left_click", {"mark_id": 7}).content[0].text)
    assert res_mark["ok"] is True
    assert res_mark["mark"]["id"] == 7
    assert clicks[-1] == (300, 150, "left", 1)

    res_xy = json.loads(_call_mcp(mcp_mod, "left_click", {"x": 400, "y": 300}).content[0].text)
    assert res_xy["ok"] is True
    assert clicks[-1] == (600, 450, "left", 1)

    monkeypatch.setattr(
        mcp_mod,
        "find_element_target",
        lambda **_kw: {
            "found": True,
            "type": "Button",
            "name": "Next",
            "center": [500, 400],
            "physical_center": [750, 600],
            "offscreen_matches": 0,
        },
    )
    res_name = json.loads(_call_mcp(mcp_mod, "left_click", {"name": "Next"}).content[0].text)
    assert res_name["ok"] is True
    assert res_name["element"]["name"] == "Next"
    assert clicks[-1] == (750, 600, "left", 1)

    res_ce = json.loads(
        _call_mcp(mcp_mod, "click_element", {"mark_id": 7, "screenshot_after": False}).content[0].text
    )
    assert res_ce["ok"] is True
    assert res_ce["element"]["id"] == 7
    assert res_ce["element"]["name"] == "Upload"
    assert clicks[-1] == (300, 150, "left", 1)

    with pytest.raises(ToolError, match="screenshot\\(marks=true\\)"):
        _call_mcp(mcp_mod, "left_click", {"mark_id": 999})

    with pytest.raises(ToolError, match="Both 'x' and 'y'"):
        _call_mcp(mcp_mod, "left_click", {"x": 100})


def test_stationary_no_effect_repeat_click_loop_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mcp_mod, win32 = _make_isolated_mcp(tmp_path, monkeypatch)
    click_calls: list[tuple[int | None, int | None]] = []

    def fake_click(
        px: int | None = None,
        py: int | None = None,
        button: str = "left",
        count: int = 1,
        modifiers: str | None = None,
        duration_ms: int | None = None,
    ) -> tuple[int, int]:
        click_calls.append((px, py))
        return (px or 0, py or 0)

    monkeypatch.setattr(win32, "click", fake_click)
    monkeypatch.setattr(win32, "move_mouse", lambda px, py, duration_ms=0: (px, py))
    monkeypatch.setattr(
        Win32Backend,
        "capture_region_pil",
        staticmethod(lambda _l, _t, w, h: PILImage.new("RGB", (w, h), (30, 40, 50))),
    )
    monkeypatch.setattr(
        mcp_mod,
        "inspect_window_ui",
        lambda **_kw: {
            "elements": [
                {"type": "Button", "name": "Recovered", "center": [300, 220], "bounds": [260, 200, 340, 240]},
            ]
        },
    )

    # Targetless click without preceding mouse_move is rejected and returns a fresh marks frame
    missing_res = _call_mcp(mcp_mod, "left_click", {}).content
    assert len(missing_res) == 2
    assert missing_res[0].type == "image"
    assert base64.b64decode(missing_res[0].data).startswith(b"\xff\xd8\xff")
    missing_meta = json.loads(missing_res[1].text)
    assert missing_meta["ok"] is False
    assert missing_meta["missing_target"] is True
    assert len(click_calls) == 0

    # Preceding mouse_move arms a single targetless click cleanly
    _call_mcp(mcp_mod, "mouse_move", {"x": 100, "y": 100})
    armed_meta = json.loads(_call_mcp(mcp_mod, "left_click", {}).content[0].text)
    assert armed_meta["ok"] is True
    assert len(click_calls) == 1

    # 3rd stationary click within <=8px without screen change triggers loop_detected + fresh marks frame
    mcp_mod._reset_click_state(reset_marks=False)
    click_calls.clear()
    assert json.loads(_call_mcp(mcp_mod, "left_click", {"x": 240, "y": 180}).content[0].text)["ok"] is True
    assert json.loads(_call_mcp(mcp_mod, "left_click", {"x": 242, "y": 181}).content[0].text)["ok"] is True
    assert len(click_calls) == 2

    third_res = _call_mcp(mcp_mod, "left_click", {"x": 240, "y": 180}).content
    assert len(click_calls) == 2  # 3rd click blocked before dispatch
    assert len(third_res) == 2
    assert third_res[0].type == "image"
    assert base64.b64decode(third_res[0].data).startswith(b"\xff\xd8\xff")
    third_meta = json.loads(third_res[1].text)
    assert third_meta["ok"] is False
    assert third_meta["loop_detected"] is True
    assert third_meta["action_result"]["loop_detected"] is True
    assert third_meta["marks"][0]["name"] == "Recovered"
    assert win32.last_marks[1]["name"] == "Recovered"

    # Visual screen changes between clicks allow repeated clicks at the same coordinate
    mcp_mod._reset_click_state(reset_marks=False)
    click_calls.clear()
    flip = {"v": 0}

    def changing_screen(_l: int, _t: int, w: int, h: int) -> PILImage.Image:
        flip["v"] = 1 - flip["v"]
        c = (240, 240, 240) if flip["v"] else (10, 10, 10)
        return PILImage.new("RGB", (w, h), c)

    monkeypatch.setattr(Win32Backend, "capture_region_pil", staticmethod(changing_screen))
    for _ in range(4):
        ok_meta = json.loads(_call_mcp(mcp_mod, "left_click", {"x": 240, "y": 180}).content[0].text)
        assert ok_meta["ok"] is True
    assert len(click_calls) == 4


def test_batch_normalization_and_execution_aliases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mcp_mod, win32 = _make_isolated_mcp(tmp_path, monkeypatch)

    step_type = mcp_mod._normalize_batch_step({"type": "click", "x": 120, "y": 240})
    assert step_type == {"action": "left_click", "x": 120, "y": 240}

    step_shorthand = mcp_mod._normalize_batch_step({"click_element": {"mark_id": 30}, "button": "right"})
    assert step_shorthand == {"action": "click_element", "mark_id": 30, "button": "right"}

    step_drag = mcp_mod._normalize_batch_step({"action": "drag", "from_mark_id": 1, "to_mark_id": 2})
    assert step_drag["action"] == "left_click_drag"
    assert step_drag["start_mark_id"] == 1
    assert step_drag["mark_id"] == 2

    step_drag_pts = mcp_mod._normalize_batch_step({"action": "drag", "start": [10, 20], "end": [100, 200]})
    assert step_drag_pts["action"] == "left_click_drag"
    assert step_drag_pts["start_coordinate"] == [10, 20]
    assert step_drag_pts["coordinate"] == [100, 200]

    assert mcp_mod._normalize_batch_step({"action": "move", "x": 5, "y": 6})["action"] == "mouse_move"
    assert mcp_mod._normalize_batch_step({"action": "hotkey", "chord": ["ctrl", "s"]}) == {
        "action": "key",
        "chord": ["ctrl", "s"],
        "key": "ctrl+s",
    }
    assert mcp_mod._normalize_batch_step({"action": "press_key", "key": "Return"})["action"] == "key"
    assert mcp_mod._normalize_batch_step({"action": "sleep", "ms": 250})["duration"] == 0.25
    assert mcp_mod._normalize_batch_step({"sleep": 0.05}) == {"action": "wait", "duration": 0.05}
    assert mcp_mod._normalize_batch_step({"key": "Return"}) == {"action": "key", "key": "Return"}

    events: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        win32,
        "click",
        lambda px=None, py=None, button="left", count=1, modifiers=None, duration_ms=None: (
            events.append(("click", px, py, button, count)) or (px or 0, py or 0)
        ),
    )
    monkeypatch.setattr(
        win32,
        "drag",
        lambda sx, sy, ex, ey, duration_ms=260: (
            events.append(("drag", sx, sy, ex, ey)) or (ex, ey)
        ),
    )
    monkeypatch.setattr(win32, "send_key", lambda spec, repeat=1: events.append(("key", spec, repeat)))
    monkeypatch.setattr(
        Win32Backend,
        "capture_region_pil",
        staticmethod(lambda _l, _t, w, h: PILImage.new("RGB", (w, h), (20, 30, 40))),
    )

    win32.last_marks = {
        1: {"id": 1, "type": "Button", "name": "Start", "center": [100, 100]},
        2: {"id": 2, "type": "Button", "name": "End", "center": [300, 300]},
        30: {"id": 30, "type": "Button", "name": "Save", "center": [400, 200]},
    }
    res = _call_mcp(
        mcp_mod,
        "batch",
        {
            "actions": [
                {"type": "click", "x": 120, "y": 240},
                {"click_element": {"mark_id": 30}},
                {"action": "drag", "from_mark_id": 1, "to_mark_id": 2},
                {"action": "hotkey", "key": "ctrl+s"},
                {"action": "sleep", "duration": 0.02},
            ],
            "screenshot_after": True,
            "step_delay_ms": 0,
        },
    ).content
    assert len(res) == 2
    assert res[0].type == "image"
    meta = json.loads(res[1].text)
    assert len(meta["batch_results"]) == 5
    assert events == [
        ("click", 180, 360, "left", 1),
        ("click", 600, 300, "left", 1),
        ("drag", 150, 150, 450, 450),
        ("key", "ctrl+s", 1),
    ]


def test_finish_input_routes_through_capture_display_and_preserves_marks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mcp_mod, win32 = _make_isolated_mcp(tmp_path, monkeypatch)
    monkeypatch.setattr(win32, "click", lambda px=None, py=None, **_kw: (px or 0, py or 0))
    monkeypatch.setattr(win32, "type_text", lambda text, **_kw: len(text))
    monkeypatch.setattr(win32, "send_key", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        Win32Backend,
        "capture_region_pil",
        staticmethod(lambda _l, _t, w, h: PILImage.new("RGB", (w, h), (18, 22, 30))),
    )

    frames = [
        [{"type": "Button", "name": "FirstBtn", "center": [120, 80], "bounds": [80, 60, 160, 100]}],
        [{"type": "Button", "name": "SecondBtn", "center": [500, 320], "bounds": [440, 300, 560, 340]}],
    ]
    call_idx = {"n": 0}

    def fake_inspect(**_kw: Any) -> dict[str, Any]:
        idx = min(call_idx["n"], len(frames) - 1)
        call_idx["n"] += 1
        return {"elements": frames[idx]}

    monkeypatch.setattr(mcp_mod, "inspect_window_ui", fake_inspect)

    # Enable marks on initial screenshot
    shot_res = _call_mcp(mcp_mod, "screenshot", {"display_number": 1, "marks": True}).content
    shot_meta = json.loads(shot_res[1].text)
    assert shot_meta["marks"][0]["name"] == "FirstBtn"
    assert win32.last_marks[1]["name"] == "FirstBtn"
    assert mcp_mod._LAST_MARKS_ENABLED is True

    # Spy on _capture_display to prove _finish_input routes through it and preserves marks=True
    captured_calls: list[dict[str, Any]] = []
    orig_capture_display = mcp_mod._capture_display

    def spy_capture_display(**kwargs: Any) -> dict[str, Any]:
        captured_calls.append(kwargs)
        return orig_capture_display(**kwargs)

    monkeypatch.setattr(mcp_mod, "_capture_display", spy_capture_display)

    click_res = _call_mcp(mcp_mod, "left_click", {"mark_id": 1, "screenshot_after": True}).content
    assert len(click_res) == 2
    click_meta = json.loads(click_res[1].text)
    assert captured_calls[-1]["marks"] is True
    assert click_meta["marks"][0]["name"] == "SecondBtn"
    assert win32.last_marks[1]["name"] == "SecondBtn"

    # Explicit marks=False disables persistence cleanly
    type_res = _call_mcp(mcp_mod, "type", {"text": "hi", "screenshot_after": True, "marks": False}).content
    type_meta = json.loads(type_res[1].text)
    assert captured_calls[-1]["marks"] is False
    assert "marks" not in type_meta
    assert mcp_mod._LAST_MARKS_ENABLED is False

    # settle=True routes through _capture_display -> capture_screenshot_when_stable
    key_res = _call_mcp(mcp_mod, "key", {"key": "Return", "screenshot_after": True, "settle": True}).content
    key_meta = json.loads(key_res[1].text)
    assert captured_calls[-1]["settle"] is True
    assert "settle" in key_meta


def test_uia_backend_viewport_clipping_offscreen_wrapper_and_chrome_priority() -> None:
    import uia_backend
    from uia_backend import uia_mod

    class FakeRect:
        def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
            self.left, self.top, self.right, self.bottom = left, top, right, bottom

        def width(self) -> int:
            return self.right - self.left

        def height(self) -> int:
            return self.bottom - self.top

    class FakeBFSControl:
        def __init__(
            self,
            ctrl_type: str,
            name: str,
            rect: FakeRect,
            *,
            is_offscreen: bool = False,
            focusable: bool | None = None,
            children: list[FakeBFSControl] | None = None,
        ) -> None:
            self.ControlTypeName = ctrl_type
            self.Name = name
            self.AutomationId = ""
            self.HelpText = ""
            self.IsOffscreen = is_offscreen
            self.IsEnabled = True
            self.IsKeyboardFocusable = (
                focusable if focusable is not None else ctrl_type in {"ButtonControl", "EditControl"}
            )
            self.IsPassword = False
            self.BoundingRectangle = rect
            self._children = children or []
            self._next_sibling: FakeBFSControl | None = None
            for i in range(len(self._children) - 1):
                self._children[i]._next_sibling = self._children[i + 1]

        def GetFirstChildControl(self) -> FakeBFSControl | None:
            return self._children[0] if self._children else None

        def GetNextSiblingControl(self) -> FakeBFSControl | None:
            return self._next_sibling

        def GetValuePattern(self) -> None:
            return None

    class DummyInit:
        def __enter__(self) -> DummyInit:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    viewport = ViewportMapping(
        display_number=1,
        src_left=0,
        src_top=0,
        src_width=1920,
        src_height=1080,
        img_width=1280,
        img_height=720,
    )

    # 1. BFS path: offscreen rejection + diagnostic hint, partial viewport clamping, oversized wrapper filtering
    offscreen_scroll = FakeBFSControl("ButtonControl", "Scrolled Target", FakeRect(200, 1400, 420, 1450))
    offscreen_flag = FakeBFSControl("ButtonControl", "Hidden Target", FakeRect(200, 300, 420, 350), is_offscreen=True)
    partial_left = FakeBFSControl("ButtonControl", "Left Edge", FakeRect(-60, 100, 140, 200))
    partial_bottom_right = FakeBFSControl("ButtonControl", "Corner Edge", FakeRect(1800, 1000, 2100, 1200))
    oversized_wrapper = FakeBFSControl("PaneControl", "Main Wrapper", FakeRect(0, 0, 1900, 1060), focusable=True)
    small_action = FakeBFSControl("ButtonControl", "Main Action", FakeRect(400, 400, 520, 460))
    root = FakeBFSControl(
        "WindowControl",
        "App",
        FakeRect(0, 0, 1920, 1080),
        children=[offscreen_scroll, offscreen_flag, partial_left, partial_bottom_right, oversized_wrapper, small_action],
    )

    with (
        patch.object(uia_backend.auto, "UIAutomationInitializerInThread", DummyInit),
        patch.object(uia_backend.auto, "ControlFromHandle", return_value=root),
        patch.object(uia_backend, "_find_elements_com_sync", return_value=[]),
        patch.object(uia_backend, "_list_interactive_com_sync", return_value=[]),
    ):
        listed = uia_backend.inspect_window_ui(hwnd=1234, viewport=viewport, max_depth=3, interactive_only=True)
        assert listed["offscreen_matches"] == 2
        by_name = {el["name"]: el for el in listed["elements"]}
        assert "Scrolled Target" not in by_name
        assert "Hidden Target" not in by_name
        assert "Main Wrapper" not in by_name
        assert "Main Action" in by_name
        # (-60, 100, 140, 200) clipped to (0, 100, 140, 200) -> physical center (70, 150)
        assert by_name["Left Edge"]["physical_center"] == [70, 150]
        assert by_name["Left Edge"]["bounds"] == [0, 67, 93, 133]
        # (1800, 1000, 2100, 1200) clipped to (1800, 1000, 1920, 1080) -> physical center (1860, 1040)
        assert by_name["Corner Edge"]["physical_center"] == [1860, 1040]

        missing_hint = uia_backend.find_element_target(hwnd=1234, viewport=viewport, name="Scrolled Target")
        assert missing_hint is not None
        assert missing_hint["found"] is False
        assert missing_hint["offscreen_matches"] >= 1
        assert "scroll" in missing_hint["detail"].lower()

        chosen_action = uia_backend.find_element_target(hwnd=1234, viewport=viewport, name="Main")
        assert chosen_action is not None
        assert chosen_action["found"] is True
        assert chosen_action["name"] == "Main Action"

    # 2. COM FindAllBuildCache path: top-chrome cap + web-body priority + focusable Custom under max_elements=95
    class FakeCachedEl:
        def __init__(
            self,
            ct_id: int,
            name: str,
            rect: FakeRect,
            *,
            focusable: bool = False,
            offscreen: bool = False,
        ) -> None:
            self.CachedControlType = ct_id
            self.CachedName = name
            self.CachedAutomationId = ""
            self.CachedHelpText = ""
            self.CachedBoundingRectangle = rect
            self.CachedIsOffscreen = offscreen
            self.CachedIsEnabled = True
            self.CachedIsKeyboardFocusable = focusable

    class FakeElementArray:
        def __init__(self, items: list[FakeCachedEl]) -> None:
            self._items = items
            self.Length = len(items)

        def GetElement(self, idx: int) -> FakeCachedEl:
            return self._items[idx]

    class FakeCacheReq:
        TreeScope = 0

        def AddProperty(self, _pid: int) -> None:
            pass

    class FakeComRoot:
        def __init__(self, items: list[FakeCachedEl]) -> None:
            self._items = items

        def FindAllBuildCache(self, *_args: Any) -> FakeElementArray:
            return FakeElementArray(self._items)

    class FakeIUIAutomation:
        def __init__(self, items: list[FakeCachedEl]) -> None:
            self._root = FakeComRoot(items)

        def CreateCacheRequest(self) -> FakeCacheReq:
            return FakeCacheReq()

        def CreatePropertyCondition(self, *_args: Any) -> object:
            return object()

        def CreatePropertyConditionEx(self, *_args: Any) -> object:
            return object()

        def CreateOrCondition(self, *_args: Any) -> object:
            return object()

        def CreateAndCondition(self, *_args: Any) -> object:
            return object()

        def ElementFromHandle(self, _hwnd: int) -> FakeComRoot:
            return self._root

    com_items: list[FakeCachedEl] = [
        FakeCachedEl(uia_mod.ControlType.PaneControl, "Fullscreen Container", FakeRect(0, 0, 1900, 1060), focusable=True),
        FakeCachedEl(uia_mod.ControlType.ButtonControl, "Below Fold", FakeRect(400, 1300, 540, 1350)),
    ]
    for i in range(60):
        com_items.append(
            FakeCachedEl(
                uia_mod.ControlType.ButtonControl,
                f"ChromeTab {i}",
                FakeRect(30 + (i % 15) * 100, 20 + (i // 15) * 20, 110 + (i % 15) * 100, 38 + (i // 15) * 20),
            )
        )
    for i in range(65):
        label = "Video yükle" if i == 10 else f"BodyBtn {i}"
        com_items.append(
            FakeCachedEl(
                uia_mod.ControlType.ButtonControl,
                label,
                FakeRect(80 + (i % 10) * 160, 180 + (i // 10) * 90, 210 + (i % 10) * 160, 230 + (i // 10) * 90),
            )
        )
    com_items.append(
        FakeCachedEl(uia_mod.ControlType.CustomControl, "Custom Focusable", FakeRect(900, 600, 1040, 650), focusable=True)
    )

    class FakeClient:
        IUIAutomation = FakeIUIAutomation(com_items)

    with (
        patch.object(uia_backend.auto, "UIAutomationInitializerInThread", DummyInit),
        patch.object(uia_backend._user32, "IsWindow", return_value=1),
        patch.object(uia_backend, "_iter_target_hwnds", return_value=[1234]),
        patch.object(uia_mod._AutomationClient, "instance", return_value=FakeClient()),
    ):
        com_res = uia_backend.inspect_window_ui(
            hwnd=1234, viewport=viewport, max_elements=95, interactive_only=True
        )
        assert com_res["element_count"] == 95
        assert com_res["offscreen_matches"] == 1
        chrome_count = sum(1 for el in com_res["elements"] if el["physical_center"][1] < 115)
        assert chrome_count <= 32
        names = {el["name"] for el in com_res["elements"]}
        assert "Video yükle" in names
        assert "Custom Focusable" in names
        assert "Fullscreen Container" not in names


def test_win32_set_of_mark_capacity_and_ruler_safe_badges(tmp_path: Path) -> None:
    backend = Win32Backend(tmp_path / "shots")
    elements_105: list[dict[str, Any]] = []
    for i in range(105):
        col = i % 15
        row = i // 15
        cx = 60 + col * 80
        cy = 60 + row * 90
        elements_105.append({
            "type": "Button",
            "name": f"Btn {i + 1}",
            "center": [cx, cy],
            "bounds": [cx - 30, cy - 15, cx + 30, cy + 15],
        })

    def fake_capture(_l: int, _t: int, w: int, h: int) -> PILImage.Image:
        return PILImage.new("RGB", (w, h), (20, 24, 34))

    with patch.object(Win32Backend, "capture_region_pil", staticmethod(fake_capture)):
        shot = backend.capture_screenshot(
            display_number=1,
            show_cursor=False,
            annotate_mode="som",
            marks_provider=lambda _vp: elements_105,
        )
        assert len(shot["marks"]) == 95
        assert len(backend.last_marks) == 95
        assert backend.last_marks[95]["name"] == "Btn 95"

        # When marks_provider yields empty list, stale last_marks must be cleared
        shot_empty = backend.capture_screenshot(
            display_number=1,
            show_cursor=False,
            annotate_mode="som",
            marks_provider=lambda _vp: [],
        )
        assert "marks" not in shot_empty
        assert backend.last_marks == {}

    # Verify ruler-safe (x >= 28) and zero pairwise badge overlap on stacked left-edge elements
    placed_boxes: list[tuple[int, int, int, int]] = []
    placed_track: list[tuple[int, int, int, int]] = []
    tw, th = 22, 14
    for i in range(12):
        by1 = 100 + i * 15
        px1, py1 = Win32Backend._place_mark_badge(4, by1, 24, by1 + 14, tw, th, 1280, 720, placed_track)
        assert px1 >= 28
        placed_boxes.append((px1, py1, px1 + tw, py1 + th))

    for i in range(len(placed_boxes)):
        ax1, ay1, ax2, ay2 = placed_boxes[i]
        for j in range(i + 1, len(placed_boxes)):
            bx1, by1, bx2, by2 = placed_boxes[j]
            overlaps = max(ax1, bx1) < min(ax2, bx2) and max(ay1, by1) < min(ay2, by2)
            assert overlaps is False

    # Verify actual rendered SoM image keeps Y-ruler margin (x < 28) clean of badge fill while preserving click centers
    canvas = PILImage.new("RGB", (1280, 720), (20, 24, 34))
    left_els = [
        {"type": "Button", "name": f"Sidebar {i}", "center": [14, 110 + i * 16], "bounds": [4, 102 + i * 16, 24, 118 + i * 16]}
        for i in range(4)
    ]
    drawn = backend._draw_set_of_mark(canvas, left_els)
    assert len(drawn) == 4
    assert drawn[0]["center"] == [14, 110]
    # Badge 1 sits above by1=102 -> shifted right to x >= 28, leaving x=10, y=92 untouched background
    assert canvas.getpixel((10, 92)) == (20, 24, 34)
    assert canvas.getpixel((32, 92)) != (20, 24, 34)


def test_wait_for_action_does_not_exit_on_window_title_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mcp_mod, win32 = _make_isolated_mcp(tmp_path, monkeypatch)

    monkeypatch.setattr(
        win32,
        "list_windows",
        lambda include_minimized=False, filter_text=None: [
            {"hwnd": 555, "title": "YouTube Studio - Upload Video", "process_name": "chrome.exe", "display_number": 1}
        ],
    )

    # Case A: Window title matches "Upload", but UI element never appears -> must time out rather than exit early
    monkeypatch.setattr(
        mcp_mod,
        "_resolve_element_for_window",
        lambda **_kw: (_ for _ in ()).throw(RuntimeError("UI element 'Upload' not found")),
    )
    with pytest.raises(TimeoutError, match="Upload"):
        mcp_mod._wait_for_action(name="Upload", timeout=0.28)

    # Case B: UI element appears on 3rd poll -> succeeds once element is found
    attempts = {"n": 0}

    def appear_later(**_kw: Any) -> dict[str, Any]:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("not ready yet")
        return {"name": "Upload", "center": [640, 360], "physical_center": [960, 540]}

    monkeypatch.setattr(mcp_mod, "_resolve_element_for_window", appear_later)
    ok_el = mcp_mod._wait_for_action(name="Upload", timeout=2.0)
    assert ok_el["ok"] is True
    assert ok_el["matched"] == "Upload"
    assert attempts["n"] == 3

    # Case C: target="window" explicitly matches window title
    ok_win = mcp_mod._wait_for_action(name="Upload", target="window", timeout=1.0)
    assert ok_win["ok"] is True
    assert ok_win["matched_window"] == "YouTube Studio - Upload Video"


def test_uia_com_auto_scroll_into_view() -> None:
    import uia_backend
    from uiautomation import uiautomation as uia_mod

    class FakeRect:
        def __init__(self, l: int, t: int, r: int, b: int) -> None:
            self.left, self.top, self.right, self.bottom = l, t, r, b

    class DummyInit:
        def __enter__(self) -> DummyInit:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    state = {"scrolled": False}

    class FakeScrollPattern:
        def QueryInterface(self, _iface: Any) -> FakeScrollPattern:
            return self

        def ScrollIntoView(self) -> None:
            state["scrolled"] = True
            target_el.CachedIsOffscreen = False
            target_el.CachedBoundingRectangle = FakeRect(300, 420, 620, 470)

    class FakeOffscreenEl:
        def __init__(self) -> None:
            self.CachedControlType = uia_mod.ControlType.RadioButtonControl
            self.CachedName = "Hayır, çocuklara özel değil"
            self.CachedAutomationId = "not-for-kids"
            self.CachedHelpText = ""
            self.CachedBoundingRectangle = FakeRect(300, 1450, 620, 1500)
            self.CachedIsOffscreen = True
            self.CachedIsEnabled = True
            self.CachedIsKeyboardFocusable = True

        def GetCurrentPattern(self, pid: int) -> Any:
            if pid == uia_mod.PatternId.ScrollItemPattern:
                return FakeScrollPattern()
            return None

    target_el = FakeOffscreenEl()

    class FakeElementArray:
        def __init__(self, items: list[Any]) -> None:
            self._items = items
            self.Length = len(items)

        def GetElement(self, idx: int) -> Any:
            return self._items[idx]

    class FakeCacheReq:
        TreeScope = 0

        def AddProperty(self, _pid: int) -> None:
            pass

    class FakeRoot:
        def FindAllBuildCache(self, *_args: Any) -> FakeElementArray:
            return FakeElementArray([target_el])

    class FakeClient:
        class IUIAutomation:
            @staticmethod
            def CreateCacheRequest() -> FakeCacheReq:
                return FakeCacheReq()

            @staticmethod
            def CreatePropertyCondition(*_a: Any) -> object:
                return object()

            @staticmethod
            def CreatePropertyConditionEx(*_a: Any) -> object:
                return object()

            @staticmethod
            def CreateOrCondition(*_a: Any) -> object:
                return object()

            @staticmethod
            def CreateAndCondition(*_a: Any) -> object:
                return object()

            @staticmethod
            def ElementFromHandle(_hwnd: int) -> FakeRoot:
                return FakeRoot()

    vp = ViewportMapping(
        display_number=1, src_left=0, src_top=0, src_width=1920, src_height=1080, img_width=1280, img_height=720
    )
    with (
        patch.object(uia_backend.auto, "UIAutomationInitializerInThread", DummyInit),
        patch.object(uia_backend._user32, "IsWindow", return_value=1),
        patch.object(uia_backend, "_iter_target_hwnds", return_value=[1234]),
        patch.object(uia_mod._AutomationClient, "instance", return_value=FakeClient()),
    ):
        hit = uia_backend.find_element_target(hwnd=1234, viewport=vp, name="çocuklara özel değil")
        assert state["scrolled"] is True
        assert hit is not None
        assert hit["found"] is True
        assert hit["scrolled_into_view"] is True
        assert hit["physical_center"] == [460, 445]


def test_batch_paste_text_type_into_mark_id_and_fast_ui_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mcp_mod, win32 = _make_isolated_mcp(tmp_path, monkeypatch)

    assert mcp_mod._normalize_batch_step({"paste_text": "Merhaba"}) == {"action": "paste_text", "text": "Merhaba"}
    assert mcp_mod._normalize_batch_step({"file_dialog": "C:\\vids\\out.mp4"}) == {
        "action": "file_dialog",
        "path": "C:\\vids\\out.mp4",
    }
    assert mcp_mod._normalize_batch_step({"fill": {"mark_id": 7, "text": "abc"}}) == {
        "action": "type_into",
        "mark_id": 7,
        "text": "abc",
    }

    click_durs: list[int | None] = []
    pasted: list[str] = []
    keys: list[str] = []
    bitblt_calls = {"n": 0}

    def fake_click(
        px: int | None = None,
        py: int | None = None,
        button: str = "left",
        count: int = 1,
        modifiers: str | None = None,
        duration_ms: int | None = None,
    ) -> tuple[int, int]:
        click_durs.append(duration_ms)
        return (px or 0, py or 0)

    def fake_cap(_l: int, _t: int, w: int, h: int) -> PILImage.Image:
        bitblt_calls["n"] += 1
        return PILImage.new("RGB", (w, h), (10, 20, 30))

    monkeypatch.setattr(win32, "click", fake_click)
    monkeypatch.setattr(win32, "set_clipboard_text", lambda text: (pasted.append(text) or len(text)))
    monkeypatch.setattr(win32, "send_key", lambda spec, repeat=1: keys.append(spec))
    monkeypatch.setattr(Win32Backend, "capture_region_pil", staticmethod(fake_cap))
    monkeypatch.setattr(
        mcp_mod,
        "inspect_window_ui",
        lambda **_kw: {
            "offscreen_matches": 0,
            "elements": [{"type": "Button", "name": "İleri", "center": [980, 680], "automation_id": "next-button"}],
        },
    )

    win32.last_marks = {
        7: {"id": 7, "type": "Edit", "name": "Başlık", "center": [300, 240]},
        8: {"id": 8, "type": "Button", "name": "Devam", "center": [500, 420]},
    }

    res = _call_mcp(
        mcp_mod,
        "batch",
        {
            "actions": [
                {"paste_text": {"mark_id": 7, "text": "Yeni Başlık"}},
                {"action": "type_into", "mark_id": 7, "text": "Satır 1\nSatır 2", "clear": True},
                {"click_element": {"mark_id": 8}},
            ],
            "fast": True,
            "screenshot_after": False,
            "ui_after": True,
            "step_delay_ms": 0,
        },
    ).content

    assert len(res) == 1
    assert res[0].type == "text"
    data = json.loads(res[0].text)
    assert data["ok"] is True
    assert click_durs == [0, 0, 0]
    assert bitblt_calls["n"] == 0
    assert pasted == ["Yeni Başlık", "Satır 1\nSatır 2"]
    assert "ctrl+v" in keys
    assert data["ui_after"]["elements"][0]["name"] == "İleri"


def test_accept_file_dialog_helper_and_batch_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mcp_mod, win32 = _make_isolated_mcp(tmp_path, monkeypatch)
    fake_video = tmp_path / "short.mp4"
    fake_video.write_bytes(b"mp4data")

    events: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        win32,
        "_find_open_file_dialog",
        lambda: {"hwnd": 777, "title": "Aç", "process_name": "chrome.exe", "pid": 4242, "is_elevated": False},
    )
    monkeypatch.setattr(win32, "focus_hwnd", lambda hwnd: events.append(("focus", hwnd)))
    monkeypatch.setattr(win32, "_find_dialog_edit_center", lambda _hwnd: (350, 620))
    monkeypatch.setattr(win32, "click", lambda **kw: (events.append(("click", kw.get("px"), kw.get("py"), kw.get("duration_ms"))) or (350, 620)))
    monkeypatch.setattr(win32, "set_clipboard_text", lambda txt: (events.append(("clip", txt)) or len(txt)))
    monkeypatch.setattr(win32, "send_key", lambda k, repeat=1: events.append(("key", k)))

    import win32_backend as wb

    orig_is_vis = wb.user32.IsWindowVisible
    monkeypatch.setattr(wb.user32, "IsWindowVisible", lambda hwnd: 0 if hwnd == 777 else orig_is_vis(hwnd))

    out = _call_mcp(
        mcp_mod,
        "batch",
        {
            "actions": [{"file_dialog": str(fake_video)}],
            "screenshot_after": False,
        },
    ).content
    payload = json.loads(out[0].text)
    assert payload["ok"] is True
    assert payload["batch_results"][0]["closed"] is True
    assert ("focus", 777) in events
    assert ("click", 350, 620, 0) in events
    assert ("clip", str(fake_video)) in events
    assert ("key", "Return") in events
