# Retention Engineering & 1080x1920 Safe-Zone Reference

## 1. Universal 1080x1920 Safe Zones (Shorts / TikTok / Reels)

Design overlays for the intersection of all three platforms rather than optimizing only one:

| Zone (`1080x1920` px) | Obstruction Source | Policy |
| :--- | :--- | :--- |
| **`Y: 0 .. 260`** | TikTok Follow/For You tabs, IG top bar, YT status bar | Leave clear except subtle thin progress bar (`Y: 0..10`) or edge badge |
| **`Y: 260 .. 400`** | Safe upper-mid (corner brand crest, top facecam zone) | Safe for corner logo / upper split-cam feed |
| **`Y: 420 .. 1360`** | **Core Sweet Spot (100% unobstructed across platforms)** | Place opening hook title, rank/speaker pill, primary focal action, and main kinetic captions (`MarginV ~ 600–650`) |
| **`X: 888 .. 1080` (`Y > 750`)** | Right-hand Like / Comment / Share / Remix buttons | Keep critical labels and face details left of `X = 880` |
| **`Y: 1380 .. 1920`** | Creator caption, audio ticker, progress scrubber, CTA bar | Never place essential text or buttons here |

### Hook Visual Hierarchy (Borderless Design)
- Never place a giant dark opaque box over the top 30–40% of the opening frame; viewers swipe instantly if they cannot see motion in the background.
- Render **floating stroke typography** directly over transparent canvas (`stroke_width ~ 10px` at 1x, soft outer glow/shadow):
  1. **Eyebrow Pill** (`small red/magenta pill`): `"TOP 10 ..."` or `"PROJE #01"`
  2. **Focal Hook** (`huge white` + **`blazing yellow pill black bold text`**): max 3–5 words total (`"WHAT DID #1 / JUST DO?!"` or `"HALAT KOPARSA?!"`)
  3. **Tension Subline** (`electric cyan stroked text`): `"WAIT TILL THE END"`

---

## 2. Cold Open & Retention Pacing Blueprint

### First 2.5 Seconds (`Viewed vs Swiped Away`)
1. **Beat 1 (`0.00–0.78s`):** Brightest, highest-contrast action shot + synced impact boom/glitch. Show conflict immediately — zero calm intro, zero fade-in from black.
2. **Beat 2 (`0.78–1.50s`):** Whip transition (`150–160ms` + `-160ms` pre-aligned whoosh) to a contrasting shot/reaction.
3. **Beat 3 (`1.50–2.50s`):** Blurred climax preview + bright padlock badge (`"UNLOCKS AT #1"` / `"REVEALED AT END"`) + tension riser. Creates an **open curiosity loop** that bridges the 3s–30s drop-off zone.

### Mid-Video & Climax Rules
- **Pattern Interrupt Cadence:** Inject a visual shift every `2.5–4.0s` (scene cut, zoom punch `1.0 -> 1.12`, wide <-> macro camera swap, or highlighted caption pop).
- **Duration Targets by Monetization Goal:**
  - **YouTube Shorts / IG Reels:** `40–58s` maximizes `>100%` Average Percentage Viewed (APV) via fast loop replay.
  - **TikTok Creativity / Rewards Program:** **`62–68s`** clears the strict `>60.0s` threshold safely even after `xfade` transition overlaps.
- **Zero-Gap Ending:** Cut trailing silence after the final word/reveal (`<= 0.15s` tail) so viewers loop back to Beat 1 seamlessly.

---

## 3. Source Quality & Anti-Garbage Filtering

Before rendering, programmatically reject defective or off-topic inputs:

1. **SMPTE Color Bars & Flat BRB Slates (`is_broken_screen`):**
   - Resize sampled frames to `(640, 360)` and compute `16x16` block means (`bmean`) and standard deviations (`bstd`).
   - Count **non-black flat blocks**: `(bstd < 1.2) & (bmean >= 28.0)`.
   - Notice: Restricting `bmean >= 28.0` protects legitimate dark/nighttime scenes from false rejection while catching uniform purple/gray "Starting Soon" slates (`>= 0.42`) and SMPTE color bars (`bright_flat >= 0.30` combined with `sat_high >= 0.28` where `S > 180` and `V > 120`).
   - Discard broken clips completely — never place them into backup pools.
2. **Cold-Open Frame Scoring (`_pick_vivid_teaser_start`):**
   - Multiply brightness/saturation/motion scores by `0.05` if `bright_flat >= 0.35`, SMPTE thresholds trigger, or mean value `< 0.20`, so Frame 0 never picks a color bar or dark fade.
3. **Facecam / Layout Priority:**
   - For reaction/gaming compilations, promote verified `split_cam` clips (corner webcam detected across >=3 frames + gameplay motion `>= 12.0`) ahead of `face_center` or `full_center` fallback pools.
4. **3D Scene QA Rules (Explainer Pipelines):**
   - Ensure visual counts match narration claims (e.g., `10 floors` stated = `10` distinct stacked slabs in 3D).
   - Check zero mesh interpenetration, gravity-aligned hanging props (`follow_location` without inheriting parent limb rotation), non-colliding HUD callout quadrants, and phonetically clean TTS wording (`tts_text` override while keeping proper spelling in `narration`).
