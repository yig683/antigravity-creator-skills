# Makine Studio Scene API & Quality Assurance Guide

## `studio/blender_scene_api.py` Quick Reference

- **`reset_scene(res_x, res_y, fps, samples)`**: Resets Blender, configures GPU EEVEE (`film_transparent = True`, RGBA PNG).
- **`make_material(name, color, metallic, roughness, alpha, emission, emission_strength, noise_bump)`**: Sets `surface_render_method = "BLENDED"` automatically when `alpha < 1.0` to eliminate dithered dot noise on glass.
- **`add_box`, `add_cylinder`, `add_empty`, `set_keyframe`, `set_visibility`**: Core primitive builders and animation helpers.
- **`attach_follow_location(obj, target)`**: Copies world location `(X, Y, Z)` without rotation inheritance — always use this for hanging props (bags, buckets, pendulums) so gravity remains straight down (`-Z`) while limbs swing.
- **`CameraRig(lens)`**: Call `.key(frame, location, target, lens)` for smooth sweeps or hard `cam_cut(...)` shifts every `~2.5–3.5s` (wide <-> macro close-up).
- **`MannequinRig(name, scale_factor)`**: Exposes `.root`, `.hands["L"/"R"]`, `.alert_anchor`, plus `.animate_climb_cycle(..., fps=fps)`, `.animate_pull_rope_cycle(..., fps=fps)`, `.animate_panic(..., fps=fps)`, `.animate_exhausted`, `.animate_relaxed_celebrate(..., fps=fps)`.
  - Local forward is `-Y` (`rot_z=+90°` faces `+X`, `rot_z=-90°` faces `-X`).
- **`HUDTracker()`**: Call `.add(key, anchor_obj, kind, frame_start, frame_end, label, color, offset_px, extra)` where:
  - `kind`: `"callout"` (angled leader line), `"badge"` (compact pill), `"alert"` (`!` icon badge), `"arrow"` (vector arrow pill), `"note"` (music `♫` pill).
  - `color`: `"cyan"`, `"amber"`, `"red"`, `"green"`, `"white"`.

## Built-in SFX Cues (`studio/sfx_synth.py`)

Use inside each beat's `"sfx": [{"name": ..., "offset": sec, "gain": 0.3..0.9}]` — all WAV cues in `assets/sfx/` are trimmed to `0.00 ms` leading dead air at load time:
- `boom`, `pop`, `whoosh`, `riser` (`assets/sfx/bass_boom.wav`, `pop.wav`, `whoosh.wav`, `riser.wav`)
- `alert` (`assets/sfx/alert.wav`, crisp UI warning blip)
- `snap` (`assets/sfx/cable_snap.wav`, steel cable snap impact)
- `clank` (`assets/sfx/clank.wav`, heavy mechanical metal jaw lock)
- `ding` (`assets/sfx/ding.wav`, crystal bell ding)
- `step` (`assets/sfx/step.wav`, concrete footstep foley)
- `motor` (`assets/sfx/motor.wav`, real electric motor actuator whir)
- `muzak` (warm 2s bossa-nova lounge chord punchline)

Narration receives broadcast EQ (`highpass=85`, presence EQ, compression) + `-15 LUFS` leveling; background bed & SFX automatically duck under active speech, and the final mix goes through 2-pass `-14 LUFS` `loudnorm` (`TP=-1.2 dBFS`, `LRA=7`) + `alimiter`.

## Mandatory Visual, Physical & TTS Checklist

1. **Numbers Match Reality:** Whatever floor/gear/stage count narration claims (e.g. `10 kat`) must match exact countable geometry.
2. **Structural Continuity & Headroom:** Stair flights must have solid stringer beams (`Stringer_*`), non-blocking alternating half-landings, and enough clearance (`scale_factor <= 0.74` for `1.60m` story height) so heads never pass through slabs.
3. **Physical Anchoring & Tangents:** Overhead pulleys require bolted clevis hangers (`PulleyHangers`); cables connect cleanly at exact pulley rim tangents (`pulley_x ± r`) and track rotated shackle world coordinates during sway; belt drives connect through real structural hatches cleanly onto driven sheaves.
4. **Clean Cutaways & Reveals:** Keep beat-specific upgrades (e.g. rooftop motor penthouse) hidden until the beat that introduces them.
5. **Zero HUD Collisions:** Whenever multiple callouts overlap around mid-beat motion, inspect timestamp extracts (`chk_17.5.png`, etc.) and spread `offset_px` in opposite quadrants.
6. **Turkish Chatterbox Safety:**
   - Avoid circumflex letters (`dâhice` -> `parlak` / `akıllıca`), nasal `m+b` traps (`cam bir kabin` -> `cam kabin`), and heavy consonant clusters (`gerginlik` -> `yük kesildiği`).
   - Put phonetic spelling in optional `"tts_text"` (e.g., `"Elişa Otis'in"`) while preserving exact Turkish spelling in `"narration"` for subtitles.
7. **Visual Reference Fidelity (`image-generator`):**
   - Always generate visual reference sheets (`references/<slug>/ref_hero.png` / `ref_mechanism.png`) with `image-generator` and inspect them via `read_file` before writing `bmesh`/primitive Blender code.
   - Match silhouette proportions, mechanical fasteners/joints, accent lighting against `#09192D`, and vibrant material contrast shown in the approved references during `--mode preview` QA.
