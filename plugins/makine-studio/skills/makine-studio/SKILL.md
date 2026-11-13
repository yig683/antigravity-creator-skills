---
name: makine-studio
description: >-
  Produces automated 3D blueprint engineering explainer Shorts and horizontal videos
  ("Nasıl İcat Edersin?" style) using Blender EEVEE, Turkish neural voiceover
  (Chatterbox GPU or Edge-TTS) with Whisper alignment, procedural SFX, and 2D
  blueprint HUD overlays. Use whenever the user asks to create, preview, debug,
  or render a 3D mechanical explainer video or blueprint Short.
---

# Makine Studio

Use this skill to design, build, verify, and render procedural 3D engineering explainer videos powered by the bundled runtime in [../../engine/](../../engine/).

## 1. Locate Engine & Check Prerequisites

The bundled Python engine sits two levels above this file at `../../engine/` (containing `studio/`, `assets/`, `episodes/template_episode.py`, and `episodes/asansor_icat.py`).

Verify available runtime tools in the user's environment before building:
1. **Python packages:** `numpy`, `pillow`, `edge-tts`, `faster-whisper` (if missing, instruct or run `../../engine/setup_env.ps1`).
2. **Blender (`4.2+` / `5.x`) & FFmpeg:** Auto-detected by `studio/config.py`, or configurable via `MAKINE_BLENDER_EXE`.
3. **Optional local GPU TTS:** If `../../engine/.venv_tts` exists, `--tts-provider auto` automatically uses GPU **Chatterbox Multilingual** (`language_id="tr"`); otherwise `--tts-provider auto` cleanly uses **Edge-TTS** (`tr-TR-AhmetNeural`). `--tts-provider external --narration-dir <dir>` accepts user-recorded `beat_00..beat_NN.wav` files.

## 2. Generate Visual References & Author a New Episode in the User's Workspace

Keep the plugin directory clean: place visual references under `<workspace>/makine_studio/references/<slug>/`, every new episode under `episodes/<slug>.py`, and renders under `<workspace>/output`.

1. **Generate Concept / Blueprint References (`image-generator`):** Before writing Blender geometry (`bmesh`/primitives), invoke the `image-generator` subagent to generate 1–2 high-clarity visual reference images (`<workspace>/makine_studio/references/<slug>/ref_hero.png` for overall scene layout/silhouette + `#09192D` blueprint contrast, and `ref_mechanism.png` for key mechanical joints/cutaways/materials) and inspect them via `read_file`. Use these references directly to govern proportions, color contrast, joint continuity, and camera angles.
2. Copy [template_episode.py](../../engine/episodes/template_episode.py) as the structural scaffold, and study [asansor_icat.py](../../engine/episodes/asansor_icat.py) as the reference standard.
2. Design a tight **6–9 beat** high-retention visual story (`48–55s` for `shorts`, or `61–64s` for `tiktok` via `get_beats(profile="tiktok")`) with crisp `0.08–0.12s` `pause_after` cadence and camera cuts/angles shifting every `~2.5–3.5s`:
   - Beat 1 (`0.8–1.5s` shock hook): Start directly at crisis/climax macro (`shock_hook`) before flashing back to step 1!
   - Beat 2–3: Problem setup & everyday pain / failure (`*_pain`, `*_fail`)
   - Beat 4–6: Step-by-step engineering breakthroughs & physical safety fixes
   - Optional TikTok depth beat (`~10–12s`): Redundancy/second safety layer pushing runtime cleanly into `61–64s` (`--profile tiktok`)
   - Final Beat: Modern full system payoff + short playful punchline
3. Follow all physics, geometry, framing, HUD, and Turkish narration guardrails in [references/scene_and_qa_guide.md](./references/scene_and_qa_guide.md).

## 3. Execute Preview -> Inspect -> Full Render

Always pass `PYTHONPATH=<plugin_engine_dir>` and explicit `--episode-file` + `--output-dir` paths so output lands cleanly in the user's workspace (default `30 fps`, or pass `--fps 60` for ultra-smooth 60 FPS motion):

### Step A: Fast Preview Render
```powershell
$env:PYTHONPATH = "<plugin_dir>/engine"
python -m studio.pipeline `
  --episode-file "<workspace>/episodes/<slug>.py" `
  --output-dir "<workspace>/output" `
  --profile shorts `
  --mode preview `
  --tts-provider auto
```
> Use `--profile tiktok` for the `61–64s` cut (`target_min_sec = 61.5`) or add `--fps 60` for 60 FPS action smoothness.

### Step B: Mandatory Visual & Audio QA Gate
Before starting a full render:
1. Open EVERY generated PNG in `<output>/<slug>_shorts/preview/` (`preview_*.png` and `cover_preview_shorts.png`) using `read_file` and check:
   - **Reference Alignment:** Proportions, material contrast, key silhouettes, and camera angles hold up against the generated `references/<slug>/` concept images (upgrading `bmesh`/materials/lighting if any prop looks flat, boxy, or low-contrast).
   - Physical geometry accuracy (stated counts match actual geometry, e.g., 10 floors = 10 stacked floors).
   - Zero inter-object intersections (person clipping stairs/ceilings, cables passing through beams, dangling props defying gravity).
   - Non-overlapping HUD badges/callouts/arrows and clean transparent glass (`alpha < 1.0`).
2. Inspect `[Whisper]` log lines and listen to `<output>/<slug>_shorts/work/master_audio.wav` (plus problem beat WAVs) via `read_file`. If a Turkish word slurs in Chatterbox, use crisp wording or `"tts_text"` override alongside canonical subtitle `"narration"`.

### Step C: Full Render (Reusing Verified Audio)
```powershell
$env:PYTHONPATH = "<plugin_dir>/engine"
python -m studio.pipeline `
  --episode-file "<workspace>/episodes/<slug>.py" `
  --output-dir "<workspace>/output" `
  --profile shorts `
  --mode full `
  --skip-tts
```
- If only 2D HUD label `offset_px`, headlines, or subtitles changed (no 3D geometry/camera edits), re-export HUD tracks into `work/hud_tracks.json` and run `--mode full --recomposite-only`.

### Step D: Final Deliverable Verification
Run `ffprobe` and `ebur128` loudness check on `<slug>_shorts.mp4`, extract 5–7 evenly spaced frames with `ffmpeg`, inspect those extracted frames and `cover_shorts.png` via `read_file`, and confirm `subtitles.srt` + `metadata.json` exist.

### Step E: Direct YouTube Upload (Optional)
Requires a user-supplied Google Cloud Desktop OAuth JSON (`~/.gemini/config/makine_studio/youtube_client_secret.json` or `MAKINE_YT_CLIENT_SECRETS`):
1. Authorize once interactively (opens browser for Google account sign-in):
```powershell
$env:PYTHONPATH = "<plugin_dir>/engine"
python -m studio.youtube_uploader --auth-only
```
2. Upload directly after `--mode full`, or upload an already-verified build with `--upload-only` (defaults to `--privacy private`):
```powershell
python -m studio.pipeline `
  --episode "<slug>" `
  --output-dir "<workspace>/output" `
  --profile shorts `
  --upload-only `
  --privacy private
```
- Also supports `--publish-at "YYYY-MM-DDTHH:MM:SSZ"`, `--upload-thumbnail`, `--post-comment`, and `--client-secrets <path>`. Never copy `client_secret*.json` or `youtube_token.json` inside `<workspace>` or the plugin folder.
