# Windows Computer Use Reference Guide

## Coordinate System, Multi-Monitor, Set-of-Mark & Fast Image Format

- By default, `screenshot(display_number=1)` captures the **primary monitor** and downscales proportionally inside `1280x800` (for example, `1920x1080` becomes `1280x720`, a clean `1.5x` ratio).
- Default format is crisp 4:4:4 **`jpeg`** (`subsampling=0, quality=86`, ~4–5 ms encode, ~4–8× smaller than PNG). Pass `format="png"` (fast `compress_level=1`) only if exact lossless pixels are required.
- Every coordinate tool (`left_click`, `right_click`, `double_click`, `triple_click`, `middle_click`, `mouse_move`, `left_mouse_down`, `left_mouse_up`, `left_click_drag`, `scroll`, `zoom`, and `batch` steps) expects `[x, y]` in the **active screenshot's coordinate grid** unless `coordinate_space="physical"` is set.
- Standalone pointer tools (`left_click`, `right_click`, `middle_click`, `double_click`, `triple_click`, `mouse_move`, `left_mouse_down`, `left_mouse_up`, `scroll`) also accept `x` + `y`, `mark_id`, `name`, `marks`, and `settle` (plus `screenshot_after`). `left_click_drag` accepts `coordinate`/`end_coordinate`, `x` + `y`, `name`, `to_mark_id`/`end_mark_id` (and `start_coordinate`, `from_mark_id`/`start_mark_id`). `click_element` accepts `mark_id` as well as `name`, plus `display_number`, `marks`, and `settle`.
- **Set-of-Mark (`marks=true` / `annotate="som"`):** Overlays up to `max_marks=95` numbered badges (`[1]..[95]`) placed ruler-safe (`x >= 28`, clear of the left `100px` Y-ruler) with collision avoidance. Top browser chrome (`y - vp_top < 115`) is capped at `32` slots when web-body controls need marks. Once enabled, `marks=true` persists across `screenshot_after=true` actions (`batch`, `click_element`, `type_into`, mouse tools, `type`, `key`, `wait`, `open_application`) until turned off (`marks=false` or `annotate="grid"`/`"none"`).
- On multi-monitor setups (`list_displays`), pass `display_number=2` (or `0` for all monitors) to `screenshot`, or pass `window_title="..."` to automatically focus a window and capture its monitor.
- `zoom(region=[x1, y1, x2, y2])` captures native full-DPI pixels for that region while target coordinates remain in the display's main screenshot coordinate grid.

## Batched & Semantic Actions (`batch`)

Use `batch(actions=[...], screenshot_after=true)` to chain mouse, keyboard, UIA, wait, window, and app-launch steps in a single tool call. Top-level options include `marks=true|false`, `settle=true` (`settle_timeout=5.0` default, range `0.5`–`12.0`), `annotate="none"|"grid"|"som"`, `step_delay_ms=15`, `stop_on_error=true`, and `display_number`.

Accepted step formats (`_normalize_batch_step`):
- Standard: `{"action": "click_element", "mark_id": 30}`
- Type-keyed: `{"type": "click", "x": 420, "y": 300}`
- Shorthand single-key dict: `{"click_element": {"mark_id": 30}}`, `{"left_click": {"x": 100, "y": 200}}`, `{"wait": 0.5}`, `{"key": "Return"}`, `{"type": {"text": "hello"}}`, `{"click_element": "Kaydet"}` / `{"click_element": 30}`
- Aliases: `click` -> `left_click`, `move`/`hover` -> `mouse_move`, `mouse_down` -> `left_mouse_down`, `mouse_up` -> `left_mouse_up`, `hotkey`/`press_key`/`shortcut` -> `key` (also accepts `keys`/`chord`/`shortcut` or list e.g. `["ctrl", "s"]`), `sleep`/`pause` -> `wait` (also accepts `seconds` or `ms`), `drag`/`drag_and_drop` -> `left_click_drag`, `focus` -> `focus_window`, `launch`/`open_app` -> `open_application`.

Supported canonical `action` values:
- `click_element` (`name?`, `mark_id?`, `control_type?`, `target?`, `button?`, `count?`, `modifiers?`, `display_number?`) — fast C++ UIA or `mark_id` lookup + smooth click
- `type_into` (`name`, `text`, `clear?`, `submit_enter?`, `sensitive?`, `control_type?`, `target?`, `interval_ms?`) — focus input, clear, type, submit in one step
- `wait_for` (`name`, `target?`, `control_type?`, `timeout?`) — waits for a matching UIA element (pass `target="window"` to match a window title instead)
- `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click` (`coordinate?`, `x?`, `y?`, `mark_id?`, `name?`, `modifiers?`)
- `mouse_move` (`coordinate?`, `x?`, `y?`, `mark_id?`, `name?`, `duration_ms?`), `left_mouse_down`, `left_mouse_up` (`coordinate?`, `x?`, `y?`, `mark_id?`, `name?`)
- `left_click_drag` (`start_coordinate?`, `start_x?`, `start_y?`, `from_mark_id?`/`start_mark_id?`, `start_name?`, `start?`, `coordinate?`/`end_coordinate?`, `x?`, `y?`, `mark_id?`/`to_mark_id?`/`end_mark_id?`, `name?`, `end?`, `duration_ms?`)
- `scroll` (`scroll_direction`: `up|down|left|right`, `scroll_amount?`, `coordinate?`, `x?`, `y?`, `mark_id?`, `name?`, `modifiers?`)
- `type` (`text`, `interval_ms?`, `submit_enter?`, `sensitive?`), `key` (`key`, `repeat?`), `hold_key` (`key`, `duration`), `wait` (`duration`)
- `open_application` (`name_or_path`, `args?`, `focus_if_running?`, `wait_seconds?`), `manage_window` / `focus_window` (`target`, `window_action?`), `clipboard_set` (`text`)

## Live On-Screen Visual Overlay & Cursor Feedback

- The MCP server runs a capture-excluded (`WDA_EXCLUDEFROMCAPTURE`) Win32 visual overlay (`overlay.py`):
  - **Ambient Edge Vignette:** 4 non-overlapping feathered edge strips (`VIGNETTE_THICK=76` px max) with Google Blue -> Cyan -> Indigo -> Violet glow while working/thinking, shifting to calm champagne-amber when paused/stopped.
  - **Minimal Bottom-Center Obsidian Dock:** Compact frosted capsule (`PILL_W=420`, `PILL_H=82`) with an animated curved chromatic **orbital ring emblem** and single-line **sentence-case** status text (e.g., `"Antigravity hazır"`, `"Ekran inceleniyor..."`, `"Kontrol sizde"` — no ALL-CAPS headers and no red recording dot). Includes non-activating `"Kontrolü al"` when active and Google-Blue `"Devam et"` + dismiss (`×`) when stopped (auto-hides after `IDLE_HIDE_SEC=25.0`s idle or `STOP_HIDE_SEC=18.0`s stopped).
  - **Fluid Cursor & Ripples:** Spring-interpolated cursor aura (`CURSOR_SZ=240`), Catmull-Rom silk comet ribbon (`TRAIL_LIFETIME_SEC=0.24`s), click/scroll sonar ripples (`RIPPLE_SZ=144`), and a `4x` supersampled Obsidian + ice-cyan pointer sprite (`build_vector_pointer_sprite`).
- Automatic cursor moves in `win32_backend.py` use minimum-jerk Fitts glides (`smooth_cursor_ms=220` default in `SafetyPolicy` / `Win32Backend`, configurable `0`–`500` ms via `configure_safety`), clamping duration between `min(smooth_cursor_ms, 70)` ms and `smooth_cursor_ms` (`70–220 ms` by default for moves `>= 8` px).
- Because `WDA_EXCLUDEFROMCAPTURE` excludes the overlay from `BitBlt` screenshots, the user sees clear real-time progress without obstructing captured frames. Both `show_overlay` and `smooth_cursor_ms` persist via `configure_safety`.

## Anti-Loop & Offscreen Recovery

- **Stationary / Blind Click Guard (`loop_detected`):**
  - Targetless clicks (without `coordinate`, `x`/`y`, `mark_id`, `name`, or an immediately preceding `mouse_move`) return `ok: false, missing_target: true` (and `loop_detected: true` on consecutive misses) with a fresh `marks=true` recovery screenshot.
  - Clicking within `8px` (`_LOOP_RADIUS_PX = 8.0`) of the previous two clicks (3rd+ consecutive click) with negligible visual change (`WIN32._mean_fingerprint_diff(...) / 255.0 < 0.008`, i.e., `< 2.04` on `0..255`) stops before clicking and returns `ok: false, loop_detected: true` plus a fresh `marks=true` screenshot.
  - **Recovery:** Never click the same spot again. Inspect the returned `marks=true` frame, pick a new `mark_id` or coordinate, `zoom` in for tiny targets, `scroll`, or use `click_element(name=...)`.
- **Viewport Clipping & Offscreen Hints (`offscreen_matches`):**
  - `uia_backend.py` clips element bounds to the active `viewport_bounds`, sets partially visible click centers to the **visible intersection** center, filters out offscreen or `< 4px` elements (counting `offscreen_matches`), and suppresses oversized container wrappers (`> 88%` viewport width and height) when smaller controls apply.
  - When a `name` lookup finds `0` visible matches and `offscreen_matches > 0`, tools raise a `ToolError` (`"Found N offscreen match(es) — scroll to bring target into view"`).
  - **Recovery:** Call `scroll` to bring the target into view, then retry `click_element(name=...)` or `screenshot(marks=true)`.

## Keyboard & Turkish / Unicode Input

- `type(text=...)` uses `SendInput` with `KEYEVENTF_UNICODE` (UTF-16 code units), so Turkish letters (`ğ, ü, ş, ı, İ, ö, ç`), accented characters, newlines (`\n`), and tabs (`\t`) work reliably regardless of active keyboard layout.
- `key(key=...)` accepts Anthropic/X11 and Windows key names: `Return`/`Enter`, `Escape`/`Esc`, `Tab`, `BackSpace`, `Delete`, `Home`, `End`, `Page_Up`, `Page_Down`, `Up`/`Down`/`Left`/`Right`, `F1`..`F24`, and chords like `ctrl+c`, `ctrl+v`, `ctrl+s`, `ctrl+shift+s`, `alt+Tab`, `win+d`, `win+r`.
- Potentially destructive system shortcuts (`alt+f4`, `ctrl+alt+delete`, `win+l`) are blocked unless `configure_safety(allow_system_shortcuts=true)` is set.

## UI Automation (`inspect_ui`, `click_element`, `type_into`) & Windows Limitations

- `inspect_ui` (`max_elements=60` default, `250` max) queries native C++ COM (`_find_elements_com_sync` with `max_scan=800` when `filter_text` is provided; `_list_interactive_com_sync`, whose own default is `max_elements=95` as used by Set-of-Mark with `timeout_sec=0.8`, including focusable `Custom` controls) and falls back to bounded breadth-first traversal (`1.2s` default timeout) when needed.
- `click_element` and `type_into` (standalone or inside `batch`) locate elements in milliseconds using native C++ UIA matching (with BFS fallback) and automatically fall back cleanly across clickable labels.
- `win32_backend.focus_hwnd` performs a foreground-lock fallback (synthetic extended `VK_MENU` key-up + thread attach + `BringWindowToTop` + retry `SetForegroundWindow`) when Windows foreground locking resists activation.
- Password inputs (`IsPassword`) are redacted automatically (`[REDACTED_PASSWORD]`).
- **Windows UIPI:** Elevated ("Run as Administrator") target windows block synthetic `SendInput` from non-elevated servers; `get_frontmost` reports `is_elevated: true` and input tools return an explicit diagnostic error.
