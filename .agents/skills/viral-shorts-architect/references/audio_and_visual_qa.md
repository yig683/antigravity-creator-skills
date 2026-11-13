# Studio Audio, SFX Sync & Visual QA Reference

## 1. Studio SFX & Real Foley Rules

Pure code-synthesized audio (`sin()`, raw white noise sweeps) triggers viewer fatigue and feels artificial. Always source clean royalty-free/CC0 WAVs (e.g., **Mixkit**, **Freesound CC0**, **Internet Archive CC0**):

- **Core Transition & UI Pack:**
  - `bass_boom.wav` (~0.8s sub hit for Beat 1 frame 0 & #1 reveal)
  - `whoosh.wav` (~0.4s whip transition bed)
  - `glitch.wav` (~0.45s digital texture hit for Beat 1 & mid-video pattern reset)
  - `lock_clack.wav` (~0.35s latch click on open-loop padlock Beat 3)
  - `pop.wav` (~0.18s subtle UI highlight cue)
  - `riser.wav` (~1.2s crescendo leading directly into the climax unlock)
  - `hype_bed.wav` (continuous loop-friendly underscore, trimmed past intro buildup straight into the beat drop)
- **Explainer / 3D Mechanical Foley Replacements:**
  - Swap sine tones with real **metallic jaw latch / ratchet (`clank`)**, **steel cable creak**, **elevator bell chime (`ding`)**, **heavy footsteps (`step`)**, and **hydraulic servo hum (`motor`)**.

### Mandatory 0ms Leading-Silence Trim
Downloaded web MP3/WAV files frequently start with `80–1200ms` of near-zero silence, making impacts sound late:

1. Convert input to `48 kHz` WAV and measure block RMS energy (`5ms` windows).
2. Find the first sample where RMS exceeds `5%` of clip peak (back off `<= 5ms` to preserve transient attack).
3. Trim from that exact onset, normalize (`loudnorm=I=-16:TP=-1.5`), and verify peak offset in milliseconds before bundling into `assets/sfx/`.

---

## 2. Broadcast Mixing & Timing Alignment

- **SFX Timing Offsets:**
  - Pre-trigger **`whoosh.wav`** at `cut_time - 0.16s` so peak rush lands squarely on the visual wipe/cut.
  - Pre-trigger **`riser.wav`** at `climax_time - 1.15s` so the crescendo cuts sharply into a `~200ms` audio duck right before the `#1` bass impact (`climax_time - 0.03s`).
- **Speech EQ & Ducking (Narration Pipelines):**
  - Voice chain: `highpass=f=85, equalizer=f=210:t=q:w=1.2:g=1.8, equalizer=f=3100:t=q:w=1.5:g=2.0, acompressor=threshold=-20dB:ratio=2.5:attack=12:release=150:makeup=1.5`
  - Duck background music under speech (`~-18` to `-22 dB` relative bed level, `volume ~ 0.15–0.18`).
- **Final Master Chain (No Clipping):**
  ```text
  loudnorm=I=-14.0:TP=-1.0:LRA=9,alimiter=limit=0.91:attack=5:release=50
  ```
  - Targets mobile-competitive **`-14.0` to `-15.5 LUFS`** while clamping transient stacks safely below `0.0 dBFS` (`max_volume ~ -0.2..-0.8 dB`).

---

## 3. Kinetic Subtitle Specification

- **Font:** `Montserrat Black` (or bold geometric equivalent), single-word or max `2 words` (`max_chars <= 11`), aligned center-mid (`PlayRes 1080x1920`, `MarginV ~ 620`, safely above platform caption bars).
- **Scale & Stroke:** `Fontsize=150..154`, `Outline=13..14`, `Shadow=6`, `BorderStyle=1`.
- **Bounce Micro-Animation (ASS):** `\fscx85\fscy85\t(0,65,\fscx130\fscy130)\t(65,130,\fscx106\fscy106)`
- **Safety Guards:**
  - Detect existing large center burned subtitles (`avg_tog >= 0.032` & `max_tog >= 0.060` in `y=[0.58..0.78]`) and suppress duplicate captions cleanly.
  - Suppress ASS output for right-to-left (`ar`, `he`, `fa`, `ur`) tokens when using non-HarfBuzz fonts so disconnected/reversed glyphs never render on screen.

---

## 4. Mandatory Verification Commands

Or run the single bundled script [../scripts/qa_check.py](../scripts/qa_check.py):
```bash
python scripts/qa_check.py output.mp4 --out-dir qa_frames
```

Equivalent manual checks after every build (**open the generated PNGs visually**):

### Probe Technical & Audio Spec
```bash
ffprobe -v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -show_entries format=duration,bit_rate -of default=noprint_wrappers=1 output.mp4

ffmpeg -y -i output.mp4 -af volumedetect -f null - 2>&1
```

### Extract Beat Snaps + Full Contact Sheet
```bash
ffmpeg -y -ss 0.35 -i output.mp4 -frames:v 1 qa_beat1.png
ffmpeg -y -ss 1.05 -i output.mp4 -frames:v 1 qa_beat2.png
ffmpeg -y -ss 1.95 -i output.mp4 -frames:v 1 qa_beat3.png
ffmpeg -y -i output.mp4 -vf "fps=1/3.8,scale=270:480,tile=6x3" -frames:v 1 qa_sheet.png
```

Confirm before marking ready:
- [ ] `qa_beat1.png` has no dark blocking rectangle, SMPTE bars, or off-topic frames.
- [ ] Every caption and badge sits inside `Y: 420..1360`, away from right-side buttons, with zero collisions.
- [ ] `volumedetect` shows `mean_volume` around `-14.0..-15.5 dB` and `max_volume < 0.0 dB`.
- [ ] `duration` matches target tier (`<60s` Shorts/Reels OR `>60.5s` TikTok Rewards).
