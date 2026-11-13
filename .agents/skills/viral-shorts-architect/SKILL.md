---
name: viral-shorts-architect
description: >-
  Audits, upgrades, and verifies automated vertical short-form video pipelines
  (YouTube Shorts, TikTok, Instagram Reels — including clip compilations and
  3D/animated explainers). Use whenever the user asks to boost retention,
  design opening hooks, fix 1080x1920 safe zones, upgrade subtitles, replace
  synthetic audio with real studio SFX, tune loudness/FPS, or enforce visual QA.
---

# Viral Shorts Architect

Use this skill to transform an automated short-form video pipeline from "technically working" into an algorithm-ready, high-retention system for **YouTube Shorts, TikTok, and Instagram Reels** — covering both **streamer/clip compilations** and **3D/animated explainer pipelines** (e.g., Blender EEVEE, Manim, motion graphics).

## Workflow Overview

Execute all four phases in order:

1. **Audit Current Bottlenecks** — Inspect the pipeline's opening `0–2.5s`, frame rate, clip/beat pacing, safe zones, caption legibility, SFX realism/timing, and audio loudness.
2. **Apply Retention & Algorithm Upgrades** — Implement concrete code/config changes using the engineering specs in [references/retention_and_safe_zones.md](./references/retention_and_safe_zones.md).
3. **Upgrade Audio & SFX Pipeline** — Replace synthetic/tonal effects with 0ms-trimmed real studio/foley WAVs and broadcast mastering per [references/audio_and_visual_qa.md](./references/audio_and_visual_qa.md).
4. **Enforce Mandatory Visual & Technical QA Gate** — Generate contact sheets, beat snapshots, `ffprobe`, and loudness metrics; visually inspect every frame before shipping.

---

## Phase 1: Pipeline Audit Checklist

Check these 8 failure points before modifying any code:

- **Weak Cold Open (`0–2.5s`):** Starts with a slow story setup (*"Imagine you live in..."*), dark opaque rectangle blocking footage, fade-in from black, or dead air.
- **UI Collisions (`1080x1920`):** Overlays, titles, or captions sit inside platform UI zones (top bar, bottom description, lower-right like/comment column).
- **Sluggish Pacing:** Single camera angle or clip runs `>6.5s` without a cut, zoom pulse, or pattern interrupt; inter-sentence pauses exceed `0.15–0.24s`.
- **Low Frame Rate / Judder:** Camera pans or 3D motions rendered at `24 fps` instead of `30–60 fps`.
- **Clutter & Small Text:** Micro badges, confusing view counts beside creator handles, or small subtitles illegible on desktop previews and mobile feeds.
- **Synthetic Audio & Late SFX:** Pure sine/noise generated SFX or un-trimmed online MP3s containing `100–1000ms` of leading silence before the transient.
- **Quiet or Clipping Mix:** Final mix under `-16.5 LUFS` (too quiet on mobile speakers) or peaking at `0.0 dB` (digital clipping) without a limiter.
- **Unfiltered Garbage Sources:** SMPTE color bars, "Stream Starting / BRB" slates, off-topic IRL/Just-Chatting streams, or broken RTL subtitle shaping slipping into the timeline.

---

## Phase 2: Tailored Upgrade Rules by Pipeline Type

Consult [references/retention_and_safe_zones.md](./references/retention_and_safe_zones.md) for exact coordinates and thresholds.

### Rule Set A — Clip Compilation Pipelines
1. **3-Beat Neuro-Hook (`~2.5s`):** Beat 1 (`~0.75s`) brightest active clip at frame 0 + borderless stroke-only hook title (`TOP N` + punchy 2–4 word question); Beat 2 (`~0.70s`) high-contrast smash cut; Beat 3 (`~1.00s`) blurred `#1` clip with `"UNLOCKS AT #1"` open-loop padlock.
2. **Fast Countdown Tempo:** Clamp segment slices around audio/motion climax to `4.5–6.4s` (avoid slow `10s+` drags); jump-cut speech pauses `>0.24s`; trigger micro-zoom/shake/flash on peaks (injecting mid-clip pulses if peaks `<2`).
3. **Clean Identity Overlay:** Show only clean rank (`#1`) + `@handle`; remove raw view/like counters unless essential.
4. **Strict Visual & Facecam Gate:** Prioritize verified `split_cam` clips over `full_center`; hard-reject flat BRB slates and SMPTE color bars using non-black local variance detection.

### Rule Set B — 3D / Animated Explainer Pipelines (e.g., Blender / EEVEE)
1. **Invert the Opening Beat (Conflict First):** Never open Beat 1 with calm exposition (`5–7s` setup). Flash `0.8–1.5s` of the core crisis/failure or payoff mechanism first (*"What saves you if this snaps?"*), then cut back to step-by-step invention.
2. **Smooth Vertical Motion (`30–60 fps`):** Upgrade `24 fps` camera flythroughs to `30 fps` minimum (`60 fps` on rapid drops/cuts) so vertical pans do not judder on high-refresh phone screens.
3. **Dual Duration Targets:** Support a tight **`42–55s` profile** (YT Shorts / IG Reels completion loop) and a **`62–65s` profile** (unlocks TikTok Creator Rewards `>60s` requirement).
4. **2.5–3.5s Camera Pattern Interrupts:** Alternate wide structural framing and macro mechanical close-ups via camera keyframes; tighten `pause_after` gaps between beats from `0.25s` down to `0.08–0.12s`.
5. **Real Foley Over Synth:** Replace procedural sine/noise cues (`clank`, `step`, `alert`, `ding`) with trimmed mechanical foley WAVs (`assets/sfx/`), ducked cleanly beneath narration.

---

## Phase 3: Captions & Broadcast Audio Rules

See [references/audio_and_visual_qa.md](./references/audio_and_visual_qa.md) for FFmpeg commands and mastering chains:

- **Kinetic Captions:** Bold geometric sans-serif (`Montserrat Black`), `1–2 words` per card, thick black outline (`12–14px`) + shadow, scale-pop bounce on active word, color alternation (White -> Yellow / Cyan / Neon Green).
- **Subtitle Hygiene:** Skip burned captions automatically if source footage already carries center baked subs, or if text contains unshaped RTL scripts (`ar`, `he`, `fa`, `ur`) when rendering via standard `libass`.
- **0ms-Trimmed Studio SFX:** Download CC0 / Mixkit studio SFX + real foley, detect leading silence via RMS envelope, slice strictly to transient onset (`0ms`), align `whoosh` impacts `-160ms` prior to visual cuts.
- **Loudness Ceiling:** Normalize final mix to **`-14.0` to `-15.0 LUFS`** (`TP=-1.0`) followed by a soft `alimiter` (`limit=0.91`) so punchy impacts never square-clip at `0.0 dBFS`.

---

## Phase 4: Mandatory Verification Before Shipping

Never trust exit codes alone. After every test or full render, run [scripts/qa_check.py](./scripts/qa_check.py) (or the commands in [references/audio_and_visual_qa.md](./references/audio_and_visual_qa.md)):

```bash
python scripts/qa_check.py path/to/output.mp4 --out-dir ./qa_frames
```

Then verify:
1. `ffprobe` metrics (`1080x1920`, target FPS `30` or `60`, stereo `48 kHz`).
2. `volumedetect` (`mean_volume ~ -14..-15.5 dB`, `max_volume < 0.0 dB`).
3. Visually inspect `qa_beat1.png`, `qa_beat2.png`, `qa_beat3.png`, and `qa_sheet.png` to confirm:
   - Frame 0 is unmistakable, bright, and unobstructed.
   - Zero SMPTE color bars, blank screens, clipping avatars, or overlapping HUD text.
   - Every segment matches the topic and renders readable subtitles.
