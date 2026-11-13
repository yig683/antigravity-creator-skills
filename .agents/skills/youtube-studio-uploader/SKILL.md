---
name: youtube-studio-uploader
description: >-
  Automates preparing unique SEO titles, descriptions, tags, pinned comments, and
  uploading queued YouTube Shorts from output/ready/ to LEONIDA TOP via Computer Use
  inside Chrome YouTube Studio (avoiding YouTube Data API v3 unverified private locks).
---

# YouTube Studio Fast Uploader (LEONIDA TOP)

## Why Chrome YouTube Studio (Not Unverified OAuth API)
New Google Cloud projects without a multi-week YouTube API Compliance Audit lock all `videos.insert` uploads to `private`. Driving the user's already-authenticated Chrome session (`studio.youtube.com`) publishes Shorts as `Public` or `Scheduled` with full metadata and zero OAuth audit waits.

## Two-Tier Speed Architecture (Target: ~30–90 Seconds Total)

1. **Sync & Inspect Queue:**
   ```powershell
   python main.py --prepare-uploads
   ```
   Generates unique non-duplicate Shorts titles, rich descriptions (hook + chapters + creator credits + hashtags), `<450`-char SEO tags, pinned comments, and writes `output/ready/upload_queue.json`.

2. **Tier 1 — Instant CDP Code Mode (`~15–30s / video`, 1 turn total — Try First!):**
   Check if Chrome remote debugging is active (`chrome://inspect/#remote-debugging` enabled once OR Chrome launched with `--remote-debugging-port=9222`):
   ```powershell
   node .agents/skills/youtube-studio-uploader/scripts/cdp_studio_upload.mjs --queue output/ready/upload_queue.json
   ```
   - Uses Node 24 built-in WebSocket + CDP `DOM.setFileInputFiles` directly on YouTube Studio's `<input type="file">` (bypassing the Windows `#32770` File Open dialog completely!) and injects Title, Description, Made-for-Kids, Altered Content, Tags, Visibility, and Publish in **1 script (~15–30s per video, 0 screenshot turns)**.
   - Mark each returned `{stem, video_url}` complete via `python main.py --mark-uploaded <stem> --upload-status published --upload-url "<url>"`.
   - If the script exits with code `2` (`CDP_UNAVAILABLE`), proceed to Tier 2 / Tier 3 (and remind the user to toggle `chrome://inspect/#remote-debugging` ON in Chrome).

3. **Tier 2 — `chrome-devtools` MCP (`--autoConnect`, Live Browser DOM Fallback):**
   If interactive Studio debugging/UI adjustments are needed without OS pixel clicks, use the `chrome-devtools` MCP tools (`list_pages`, `take_snapshot` [text a11y tree, zero images], `upload_file`, `fill`, `click`, `evaluate_script`) attached directly to the logged-in Chrome session.

4. **Tier 3 — Turbo `computer-use` `batch` Mode (`~60–90s / video`, ~4–6 turns fallback):**
   - Call `request_access(app_names=["chrome.exe", "explorer.exe"], allow_clipboard=true, reason=...)` once per session.
   - Delegate via `invoke_subagent(TypeName="self", Model="flash_lite", Role="Desktop UI Operator")` passing the pending entries from `output/ready/upload_queue.json`.
   - **Critical Latency Rules (prevents the 41-min / 219-turn anti-pattern):**
     - **NEVER use `screenshot_after=true` on intermediate batches** (every MCP image forces an extra `read_file` turn!). Use `batch(..., fast=true, screenshot_after=false, ui_after=true)` to get compact text coordinates with 0 image turns.
     - **NEVER separate `clipboard_set` turns or manual `#32770` Open dialog loops.** Use `paste_text` / `type_into(use_clipboard=true)` and `file_dialog` directly inside `batch`!
     - **`click_element` auto-scrolls offscreen UIA elements into view via `ScrollItemPattern`** — call `click_element` directly by accessible name instead of blind `scroll` + `left_click_drag` loops.
   - **4-Batch Choreography per Video:**
     - **Batch 1 (Open + Attach File):** Focus Chrome `studio.youtube.com` -> `click_element("Oluştur")` -> `wait_for("Video yükle")` -> `click_element("Video yükle")` -> `click_element("Dosya seç")` -> `file_dialog(path=video_path)` -> `wait_for("Başlık", timeout=12)` (`screenshot_after=false, ui_after=true`).
     - **Batch 2 (Details + Kids + Expand):** `paste_text(name="Başlık", text=title, clear=true)` -> `paste_text(name="Açıklama", text=description, clear=true)` -> `click_element("Hayır, çocuklara özel değil")` -> `click_element("Daha fazla göster")` (`screenshot_after=false, ui_after=true`).
     - **Batch 3 (Compliance + Tags + Advance):** `click_element("Hayır, yapay zeka kullanılmadı")` -> `paste_text(name="Etiket ekle", text=tags_csv, submit_enter=true)` -> `click_element("İleri")` x3 (`screenshot_after=false, ui_after=true`).
     - **Batch 4 (Visibility + Publish):** `click_element("Herkese açık")` -> `wait_for("Yayınla", timeout=15)` -> `click_element("Yayınla")` (`screenshot_after=true, settle=true`) to verify published Shorts URL.

5. **Mark Complete:**
   ```powershell
   python main.py --mark-uploaded <stem> --upload-status published --upload-url "<url>"
   ```
