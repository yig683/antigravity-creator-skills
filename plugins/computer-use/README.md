# Fast Computer Use Plugin for Antigravity (Windows)

High-throughput Claude Desktop-style Windows GUI automation plugin (`computer-use` MCP Server) optimized to eliminate multi-turn screenshot bottlenecks.

## Key Performance Upgrades
- **`batch(..., fast=True, ui_after=True, screenshot_after=False)`**: Executes multi-step desktop flows instantaneously without 220ms hover/glide sleeps or per-click full-screen BitBlt overhead, returning compact clickable UIA element names & center coordinates inline as text (zero extra image `read_file` turns).
- **COM UIA Auto-Scroll (`_try_scroll_com_element_into_view`)**: `click_element` and `type_into` automatically scroll offscreen matching controls into the viewport via `IUIAutomationScrollItemPattern.ScrollIntoView()` (with `SetFocus()` fallback), eliminating blind `scroll` + `inspect_ui` loops.
- **Atomic `paste_text` & `file_dialog`**: Clipboard clear+paste and native Windows `#32770` Open/Save file pickers complete in a single batch step (`file_dialog` / `accept_file_dialog`).
- **Enhanced `type_into`**: Supports `mark_id`, `coordinate`, `x`/`y`, `duration_ms`, and `paste="auto"` clipboard acceleration for long/Unicode/Turkish strings.
- **Safety Guardrails**: Per-app access permissions (`request_access`), password field redaction (`[REDACTED_PASSWORD]`), blocked-app protections, local audit logging, and emergency stop.

## Quick Install (Windows)
Unzip into a folder and run **`install.bat`** or:
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
To install into a specific project workspace instead of global `~/.gemini/config/plugins/`:
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WorkspacePath "C:\Path\To\Project"
```
Then restart Antigravity.

## Running Unit Tests
```powershell
.venv\Scripts\python.exe -m pytest server\tests\test_computer_use.py -v
```
