---
name: computer-use
description: >-
  Claude Desktop-style native Windows Computer Use via the bundled computer-use MCP
  server: DPI-aware multi-monitor screenshots, region zoom, batched mouse/keyboard
  actions, Unicode/Turkish typing, window/app launching, UI Automation inspection,
  clipboard helpers, and per-app safety controls. Activate when controlling native
  desktop applications, inspecting the live screen visually, or automating GUI
  workflows where direct shell/file or browser tools are insufficient.
---

# Computer Use (Desktop Control)

Use this skill to operate the Windows desktop visually and structurally using the bundled `computer-use` MCP server, following the same tiered Cowork + Vision-Action architecture as Claude Desktop.

## 1. Execution Hierarchy (Fastest & Most Reliable First)

1. **Direct Files / CLI / Connectors:** If the task only reads/edits files or runs commands, use workspace tools (`read_file`, `write_file`, `run_command`) instead of driving a GUI.
2. **Web Pages:** If the task is strictly inside a web browser and needs DOM interaction, prefer the built-in `browser` subagent or `chrome-devtools`; use `computer-use` for OS dialogs, native apps, or when explicitly requested for desktop UI.
3. **Desktop Computer Use (`computer-use_desktop` MCP):** Use screen, pointer, keyboard, window, and UI Automation tools for native Windows apps and visual desktop control.

## 2. Human-Speed Vision-Action Loop (Minimize Turns!)

Every lazy MCP call + offloaded image `read_file` adds model latency. Keep workflows near human speed:

1. **Delegate GUI Loops (`Model="flash_lite"`):** For desktop tasks needing 2+ visual observe-act iterations, delegate the GUI execution loop with `invoke_subagent(TypeName="self", Model="flash_lite", Role="Desktop UI Operator")` (~1–2s per image turn with full `computer-use_desktop` + `read_file` access; escalate to `Model="flash"` only if a task stalls or requires complex reasoning).
2. **Orient Once (`grid` / `marks=true`):** Call `screenshot(display_number=1)` (add `marks=true` for up to `95` ruler-safe Set-of-Mark UIA badges `[1], [2]...` with web-body priority over browser chrome, or `window_title=...` to focus and capture) and inspect the returned image (`100px` coordinate grid is drawn automatically; `marks=true` persists across post-action screenshots until disabled with `marks=false`).
3. **Authorize (When Needed):** If touching a sensitive or unrequested app, call `request_access(app_names=[...], reason=...)` or confirm with the user first.
4. **Target Cleanly & Batch Actions (`batch`):**
   - Chain as many deterministic actions as possible into **`batch`** (`fast=true` skips 220ms glide delays inside batches).
   - **Avoid 2-turn PNG `read_file` overhead:** on intermediate `batch` calls set `screenshot_after=false, ui_after=true` to receive compact clickable UIA elements + coordinates inline in JSON text (`0` extra turns!). Set `screenshot_after=true` (and `settle=true`, `marks=true`) ONLY on initial orientation or final visual verification.
   - Valid `batch` step formats: standard `{"action": "click_element", "mark_id": 30}`, type-keyed `{"type": "click", "x": 420, "y": 300}`, or shorthand `{"click_element": {"mark_id": 30}}`, `{"paste_text": {"name": "Başlık", "text": "..."}}`, `{"file_dialog": "C:\\path\\video.mp4"}`, plus aliases (`click`, `move`, `hotkey`/`press_key`, `sleep`, `drag`, `paste`, `fill`, `select_file`).
   - Standalone tools are equally flexible: `click_element` accepts `mark_id` or `name` (and auto-scrolls offscreen UIA matches into view via `ScrollItemPattern`); `type_into` accepts `name`, `mark_id`, `coordinate`, or `x`+`y` (with `paste="auto"`); mouse tools accept `mark_id`, `x`+`y`, `name`, `coordinate`, `marks`, and `settle`.
   - Use **`paste_text`** (instead of standalone `clipboard_set` turns) and **`file_dialog`** (instead of manually clicking Windows `#32770` Open pickers) and **`wait_for`** (`wait_for(name="OAuth", target="window")` for window titles) inside `batch`!
   - Never call an extra `screenshot` immediately after `batch(..., screenshot_after=true)`, `wait(..., screenshot_after=true)`, or `click_element(..., screenshot_after=true)`.
   - Human-like curved cursor glide (`~70–220 ms` minimum-jerk Fitts motion at `smooth_cursor_ms=220` default), silk comet trail, click ripples, ambient edge vignette, and the slim bottom-center Obsidian control dock (`WDA_EXCLUDEFROMCAPTURE`, orbital ring emblem + sentence-case status and clickable **"Kontrolü al"** / **"Devam et"** handover, without ALL-CAPS or red recording dots) render automatically (`configure_safety(show_overlay=..., smooth_cursor_ms=...)`), so do not add visibility delays.
5. **Precision When Needed:**
   - Use `inspect_ui(filter_text=...)` (fast native C++ UIA COM query) for buttons, menus, tabs, or inputs.
   - Use `zoom(region=[x1, y1, x2, y2])` when text or icons are too small to read reliably.
6. **Anti-Loop, Offscreen Recovery & Clean Handover:**
   - **No Blind / Repeat Clicks (`loop_detected`):** Clicking without a target (when `mouse_move` was not just called) or clicking the same spot (`<= 8px`) 3+ times without visual change triggers `loop_detected: true` (`ok: false`) and returns a fresh `marks=true` screenshot. Never repeat the same pixel — inspect the returned `marks` frame, pick a new `mark_id` / coordinate, `zoom`, or `click_element(name=...)`.
   - **Offscreen Elements (`offscreen_matches`):** If `click_element` / `type_into` / `left_click(name=...)` reports `"Found N offscreen match(es) — scroll to bring target into view"`, `scroll` the view toward the target and then call `click_element(name=...)` or `screenshot(marks=true)`.
   - If progress stalls, check `get_frontmost` (did focus move or is the window elevated under Administrator UIPI?). Clicking **"Kontrolü al"**, double-tapping `Esc`, pressing `Pause/Break`, or calling `emergency_stop()` hands control back immediately.

## 3. Tool Reference

For coordinate mapping rules, multi-monitor notes, key names, and UIA behavior, see [references/windows_computer_use_guide.md](./references/windows_computer_use_guide.md).
