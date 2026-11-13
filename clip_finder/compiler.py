from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from clip_finder.audio_fx import analyze_audio, ensure_sfx_pack
from clip_finder.captions import generate_wspeed_captions
from clip_finder.downloader import ClipDownloader
from clip_finder.editor import (
    EditConfig,
    _run_ffmpeg,
    _video_encoder_args,
    jump_cut_dead_air,
    probe_video,
    render_wspeed_edit,
)
from clip_finder.engine import ClipFinderEngine, SortBy
from clip_finder.facecam import detect_framing_plan
from clip_finder.graphics import (
    _format_views,
    render_gta_logo_png,
    render_hook_card_png,
    render_mystery_lock_png,
    render_progress_bar_layers,
    render_rank_pill_png,
)
from clip_finder.history import ClipHistory
from clip_finder.models import Clip
from clip_finder.providers.base import Period
from clip_finder.uploader import sync_upload_queue


@dataclass
class CompilationResult:
    output_path: Path
    metadata_path: Path
    duration_seconds: float
    clips_used: list[Clip]
    title: str
    description: str
    hashtags: list[str]
    monetization_checks: dict[str, bool]


async def _save_edge_tts(text: str, voice: str, rate: str, out_path: Path) -> None:
    import edge_tts

    comm = edge_tts.Communicate(text, voice, rate=rate)
    await comm.save(str(out_path))


def synthesize_narration(text: str, out_path: Path, lang: str = "en") -> Path:
    """Synthesize clean commentary voiceover with edge-tts."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if lang.lower().startswith("tr"):
        voice = "tr-TR-AhmetNeural"
        rate = "+8%"
    else:
        voice = "en-US-AndrewMultilingualNeural"
        rate = "+6%"
    asyncio.run(_save_edge_tts(text, voice, rate, out_path))
    return out_path


def _format_mmss(sec: float) -> str:
    sec_i = max(int(round(sec)), 0)
    return f"{sec_i // 60:02d}:{sec_i % 60:02d}"


def _extract_slug_handle(clip: Clip) -> str:
    """Extract ASCII creator handle from Twitch/Kick channel/clip URL as safe fallback."""
    from urllib.parse import urlparse

    for raw_url in (clip.channel_url, clip.url):
        if not raw_url:
            continue
        parts = [p for p in urlparse(raw_url).path.split("/") if p]
        if parts:
            slug = parts[0]
            if slug and all(ord(c) <= 0x024F for c in slug):
                return slug
    return ""


def _probe_audio_duration(media_path: Path) -> float:
    """Return container/audio duration via ffprobe without requiring a video stream."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float((proc.stdout or "0").strip() or 0.0)


def _pick_vivid_teaser_start(video_path: Path, peak_hint: float, seg_dur: float) -> tuple[float, float]:
    """Score candidate slice starts by brightness, saturation, motion, and audio climax proximity."""
    try:
        import cv2
        import numpy as np
    except Exception:
        return max(peak_hint - seg_dur * 0.45, 0.0), 0.5

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return max(peak_hint - seg_dur * 0.45, 0.0), 0.5

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        dur = n_frames / fps if n_frames > 0 else max(peak_hint + seg_dur, seg_dur + 1.0)
        max_start = max(dur - seg_dur - 0.05, 0.0)
        if max_start <= 0.1:
            candidates = [0.0]
        else:
            candidates = [
                max(0.0, min(max_start, peak_hint - seg_dur * 0.45)),
                max(0.0, min(max_start, peak_hint * 0.85)),
                *[max(0.0, min(max_start, dur * frac)) for frac in (0.12, 0.28, 0.45, 0.62, 0.78)],
            ]

        best_t = candidates[0]
        best_score = -1.0
        seen_t: set[int] = set()
        for t in candidates:
            bucket = int(round(t * 4))
            if bucket in seen_t:
                continue
            seen_t.add(bucket)

            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok1, f1 = cap.read()
            cap.set(cv2.CAP_PROP_POS_MSEC, min(t + 0.16, max(dur - 0.05, 0.0)) * 1000.0)
            ok2, f2 = cap.read()
            if not ok1 or f1 is None:
                continue

            h, w = f1.shape[:2]
            roi1 = f1[int(h * 0.32):]
            gray_roi = cv2.cvtColor(cv2.resize(roi1, (320, 160)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            blocks = gray_roi.reshape(10, 16, 20, 16).swapaxes(1, 2).reshape(-1, 256)
            bmean = np.mean(blocks, axis=1)
            bstd = np.std(blocks, axis=1)
            bright_flat = float(np.mean((bstd < 1.2) & (bmean >= 28.0)))

            hsv = cv2.cvtColor(roi1, cv2.COLOR_BGR2HSV)
            sat = float(np.mean(hsv[:, :, 1])) / 255.0
            sat_high = float(np.mean((hsv[:, :, 1] > 180) & (hsv[:, :, 2] > 120)))
            val = float(np.mean(hsv[:, :, 2])) / 255.0
            bright_bonus = val if val >= 0.25 else val * 0.20

            if ok2 and f2 is not None and f2.shape == f1.shape:
                roi2 = f2[int(h * 0.32):]
                mot = float(np.mean(cv2.absdiff(roi1, roi2))) / 64.0
            else:
                mot = 0.25

            prox = 1.18 if abs(t - max(peak_hint - seg_dur * 0.45, 0.0)) < 1.2 else 1.0
            # Reject flat BRB banners, SMPTE TV color bars, or near-black fades as cold-open shots
            quality_mult = 0.05 if (bright_flat >= 0.35 or (bright_flat >= 0.24 and sat_high >= 0.28) or val < 0.20) else 1.0
            score = (0.42 * bright_bonus + 0.33 * sat + 0.25 * min(mot, 1.5)) * prox * quality_mult
            if score > best_score:
                best_score = score
                best_t = t
        return best_t, max(best_score, 0.0)
    finally:
        cap.release()


def _build_teaser_segment(
    teaser_shots: list[tuple[Path, float, object]],
    out_path: Path,
    *,
    hook_badge: str = "TOP 7 GTA 6",
    hook_title: str = "WHAT DID #1 JUST SEE?!",
    hook_sub: str = "EVERY STREAMER LOST IT",
    lock_title: str = "UNLOCKS AT #1",
    lock_sub: str = "WATCH TO END FOR REVEAL",
    narration_audio: Path | None = None,
    config: EditConfig | None = None,
    use_nvenc: bool = True,
) -> float:
    """Build a 3-beat neuro-retention cold-open: bright vivid action -> smash cut -> blurred #1 open loop."""
    with tempfile.TemporaryDirectory(prefix="teaser_") as td:
        tmp = Path(td)
        narration_dur = (
            _probe_audio_duration(narration_audio)
            if narration_audio and narration_audio.exists()
            else 0.0
        )
        shots = teaser_shots[:3] if teaser_shots else []
        if not shots:
            raise RuntimeError("Teaser için kaynak klip bulunamadı.")

        base_durs = [0.78, 0.72, 1.00] if len(shots) == 3 else ([0.95, 1.15] if len(shots) == 2 else [2.20])
        target_total = min(max(narration_dur + 0.35 if narration_dur > 0 else sum(base_durs), sum(base_durs)), 4.4)
        scale = target_total / max(sum(base_durs), 0.1)
        beat_durs = [round(d * scale, 2) for d in base_durs]

        t_cfg = config or EditConfig(punch_zoom=True, camera_shake=True, impact_flash=True, rgb_split=True, add_sfx=False, use_nvenc=use_nvenc)

        shot_paths: list[Path] = []
        shot_is_split: list[bool] = []
        any_split = False
        for s_idx, (src_clip, peak_t, s_framing) in enumerate(shots):
            info = probe_video(src_clip)
            cur_dur = min(beat_durs[s_idx], max(info.duration - 0.1, 0.55))
            if s_idx < len(shots) - 1 or len(shots) == 1:
                start_t, _ = _pick_vivid_teaser_start(src_clip, peak_t, cur_dur)
            else:
                start_t = max(0.0, min(peak_t - cur_dur * 0.48, max(info.duration - cur_dur, 0.0)))
            is_split = getattr(s_framing, "mode", None) == "split_cam"
            shot_is_split.append(is_split)
            if is_split:
                any_split = True

            raw_slice = tmp / f"shot_raw_{s_idx}.mp4"
            slice_cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{start_t:.3f}", "-t", f"{cur_dur:.3f}",
                "-i", str(src_clip),
                *_video_encoder_args(use_nvenc),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                str(raw_slice),
            ]
            slice_fb = (
                [
                    "ffmpeg", "-y", "-v", "error",
                    "-ss", f"{start_t:.3f}", "-t", f"{cur_dur:.3f}",
                    "-i", str(src_clip),
                    *_video_encoder_args(False),
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    str(raw_slice),
                ]
                if use_nvenc
                else None
            )
            _run_ffmpeg(slice_cmd, slice_fb)

            edited_shot = tmp / f"shot_ed_{s_idx}.mp4"
            render_wspeed_edit(
                raw_slice,
                edited_shot,
                analyze_audio(raw_slice),
                ass_path=None,
                framing=s_framing,
                config=EditConfig(
                    layout=t_cfg.layout,
                    cam_corner=t_cfg.cam_corner,
                    cut_dead_air=False,
                    punch_zoom=True,
                    camera_shake=True,
                    impact_flash=True,
                    rgb_split=t_cfg.rgb_split,
                    add_sfx=False,
                    use_nvenc=use_nvenc,
                    target_fps=t_cfg.target_fps,
                ),
                overlay_png_path=None,
            )
            shot_paths.append(edited_shot)

        actual_durs = [probe_video(sp).duration for sp in shot_paths]
        total_t_dur = max(sum(actual_durs), 1.0)
        n_shots = len(shot_paths)
        has_mystery = n_shots >= 2

        hook_png = render_hook_card_png(hook_badge, hook_title, hook_sub, tmp / "hook_card.png") if hook_title.strip() else None
        lock_png = render_mystery_lock_png(lock_title, lock_sub, tmp / "mystery_lock.png") if has_mystery else None

        inputs: list[str] = []
        for sp in shot_paths:
            inputs.extend(["-i", str(sp)])
        next_idx = n_shots

        lock_idx: int | None = None
        if has_mystery and lock_png and lock_png.exists():
            lock_idx = next_idx
            inputs.extend(["-loop", "1", "-t", f"{actual_durs[-1] + 0.50:.3f}", "-i", str(lock_png)])
            next_idx += 1

        filters: list[str] = []
        streams: list[str] = []
        for idx in range(n_shots):
            if has_mystery and idx == n_shots - 1 and lock_idx is not None:
                # Open-loop cliffhanger: keep top reaction face crisp, neon-bright blur bottom + giant lock card
                blur_y = 648 if shot_is_split[idx] else 680
                blur_h = 1920 - blur_y
                filters.append(
                    f"[{idx}:v]fps={t_cfg.target_fps},setsar=1,setpts=PTS-STARTPTS,split[ms_base][ms_src]"
                )
                filters.append(
                    f"[ms_src]crop=1080:{blur_h}:0:{blur_y},boxblur=16:2,"
                    f"eq=brightness=0.18:contrast=1.30:saturation=1.70,"
                    f"colorbalance=rs=0.14:bs=0.22[ms_blur]"
                )
                filters.append(f"[ms_base][ms_blur]overlay=0:{blur_y}[ms_bg]")
                filters.append(
                    f"[{lock_idx}:v]fps={t_cfg.target_fps},format=rgba,fade=t=in:st=0:d=0.10:alpha=1[ms_ov]"
                )
                filters.append(
                    f"[ms_bg][ms_ov]overlay=x='(W-w)/2':"
                    f"y='if(lt(t,0.16),920+48*pow(1-t/0.16,3),920)':shortest=1[sv{idx}]"
                )
                filters.append(
                    f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
                    f"lowpass=f=2400,asetpts=PTS-STARTPTS[sa{idx}]"
                )
            else:
                filters.append(f"[{idx}:v]fps={t_cfg.target_fps},setsar=1,setpts=PTS-STARTPTS[sv{idx}]")
                filters.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[sa{idx}]")
            streams.append(f"[sv{idx}][sa{idx}]")

        filters.append(f"{''.join(streams)}concat=n={n_shots}:v=1:a=1[vcat][acat]")

        if hook_png and hook_png.exists():
            hook_y = 435 if any_split else 145
            hook_end = sum(actual_durs[:-1]) if has_mystery else total_t_dur
            fade_out = max(hook_end - 0.10, 0.35)
            inputs.extend(["-loop", "1", "-t", f"{total_t_dur + 0.50:.3f}", "-i", str(hook_png)])
            filters.append(
                f"[{next_idx}:v]fps={t_cfg.target_fps},format=rgba,fade=t=in:st=0:d=0.06:alpha=1,"
                f"fade=t=out:st={fade_out:.2f}:d=0.10:alpha=1[ov]"
            )
            filters.append(
                f"[vcat][ov]overlay=x='(W-w)/2':"
                f"y='if(lt(t,0.14),{hook_y}+38*pow(1-t/0.14,3),{hook_y})':shortest=1,setsar=1[vout]"
            )
            next_idx += 1
        else:
            filters.append("[vcat]setsar=1[vout]")

        sfx = ensure_sfx_pack()
        mix_labels: list[str] = []
        if narration_audio and narration_audio.exists():
            inputs.extend(["-i", str(narration_audio)])
            vo_idx = next_idx
            next_idx += 1
            filters.append(f"[acat]volume=0.22[bg]")
            filters.append(f"[{vo_idx}:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={total_t_dur:.3f}[vo]")
            mix_labels.extend(["[bg]", "[vo]"])
        else:
            filters.append("[acat]volume=0.90[bg]")
            mix_labels.append("[bg]")

        # Frame-0 Studio Boom + Glitch scroll-stop slam (60ms boom peak)
        inputs.extend(["-i", str(sfx["bass_boom"])])
        filters.append(
            f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay=5:all=1,volume=0.58[open_hit]"
        )
        mix_labels.append("[open_hit]")
        next_idx += 1

        if sfx.get("glitch") and sfx["glitch"].exists():
            inputs.extend(["-i", str(sfx["glitch"])])
            filters.append(
                f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay=10:all=1,volume=0.38[open_gl]"
            )
            mix_labels.append("[open_gl]")
            next_idx += 1

        if n_shots >= 3:
            w_ms = max(int((actual_durs[0] - 0.16) * 1000), 10)
            inputs.extend(["-i", str(sfx["whoosh"])])
            filters.append(
                f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={w_ms}:all=1,volume=0.55[wh_cut]"
            )
            mix_labels.append("[wh_cut]")
            next_idx += 1

        if has_mystery:
            lock_ms = max(int((sum(actual_durs[:-1]) - 0.02) * 1000), 10)
            inputs.extend(["-i", str(sfx["lock_clack"])])
            filters.append(
                f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={lock_ms}:all=1,volume=0.62[lk_snap]"
            )
            mix_labels.append("[lk_snap]")
            next_idx += 1

            if sfx.get("glitch") and sfx["glitch"].exists():
                inputs.extend(["-i", str(sfx["glitch"])])
                filters.append(
                    f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={lock_ms}:all=1,volume=0.38[lk_gl]"
                )
                mix_labels.append("[lk_gl]")
                next_idx += 1

        riser_delay = max(int((total_t_dur - 1.15) * 1000), 20)
        inputs.extend(["-i", str(sfx["riser"])])
        filters.append(
            f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={riser_delay}:all=1,volume=0.46[rs]"
        )
        mix_labels.append("[rs]")
        next_idx += 1

        filters.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:normalize=0[aout]")

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]",
            *_video_encoder_args(use_nvenc),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            str(out_path),
        ]
        fb = [
            "ffmpeg", "-y", "-v", "error",
            *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]",
            *_video_encoder_args(False),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            str(out_path),
        ] if use_nvenc else None
        _run_ffmpeg(cmd, fb)
        return probe_video(out_path).duration


def _overlay_voice_at_start(
    segment_path: Path,
    voice_path: Path,
    out_path: Path,
    *,
    use_nvenc: bool = True,
) -> Path:
    """Mix a short transition narration cue cleanly over the beginning of a segment."""
    v_dur = _probe_audio_duration(voice_path)
    filter_str = (
        f"[0:a]volume='if(lt(t,{v_dur:.2f}),0.28,1.0)':eval=frame[bg];"
        f"[1:a]aresample=48000,aformat=channel_layouts=stereo,apad[vo];"
        f"[bg][vo]amix=inputs=2:duration=first:normalize=0[aout]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(segment_path),
        "-i", str(voice_path),
        "-filter_complex", filter_str,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        str(out_path),
    ]
    _run_ffmpeg(base_cmd)
    return out_path


def _concat_segments(
    segment_paths: list[Path],
    output_path: Path,
    *,
    fps: int = 60,
    fade_d: float = 0.16,
    show_gta_corner: bool = False,
    use_nvenc: bool = True,
) -> tuple[Path, float]:
    """Chain 1080x1920@60fps clips via directional xfade/acrossfade, corner logo, hype pulse, and -13.5 LUFS."""
    seg_durs = [probe_video(sp).duration for sp in segment_paths]
    n = len(segment_paths)
    eff_fade = min(fade_d, min(seg_durs) * 0.25) if n >= 2 else 0.0

    inputs: list[str] = []
    filters: list[str] = []
    for idx, sp in enumerate(segment_paths):
        inputs.extend(["-i", str(sp)])
        filters.append(f"[{idx}:v]fps={fps},setsar=1,settb=AVTB,setpts=PTS-STARTPTS[vn{idx}]")
        filters.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[an{idx}]")

    boundary_times: list[float] = []
    if n == 1:
        final_v = "vn0"
        final_a = "an0"
        total_dur = max(seg_durs[0], 1.0)
    else:
        transitions = ["slideleft", "smoothleft", "slideright", "smoothright"]
        prev_v = "vn0"
        prev_a = "an0"
        cum_dur = seg_durs[0]
        for b_idx in range(n - 1):
            offset = max(cum_dur - eff_fade, 0.1)
            boundary_times.append(offset)
            tr = transitions[b_idx % len(transitions)]
            out_v = f"vx{b_idx}"
            out_a = f"ax{b_idx}"
            filters.append(
                f"[{prev_v}][vn{b_idx + 1}]xfade=transition={tr}:duration={eff_fade:.3f}:offset={offset:.3f}[{out_v}]"
            )
            filters.append(
                f"[{prev_a}][an{b_idx + 1}]acrossfade=d={eff_fade:.3f}:c1=tri:c2=tri[{out_a}]"
            )
            prev_v = out_v
            prev_a = out_a
            cum_dur = cum_dur + seg_durs[b_idx + 1] - eff_fade
        final_v = prev_v
        final_a = prev_a
        total_dur = max(cum_dur, 1.0)

    # Gradient animated retention progress bar across the top edge (9px high)
    track_png, fill_png = render_progress_bar_layers(width=1080, height=9, out_dir="assets/ui")
    next_idx = n
    idx_track = next_idx
    inputs.extend(["-loop", "1", "-t", f"{total_dur + 0.40:.3f}", "-i", str(track_png)])
    next_idx += 1
    idx_fill = next_idx
    inputs.extend(["-loop", "1", "-t", f"{total_dur + 0.40:.3f}", "-i", str(fill_png)])
    next_idx += 1

    filters.append(f"[{final_v}][{idx_track}:v]overlay=0:0:shortest=1[vtr]")
    if show_gta_corner:
        corner_logo = render_gta_logo_png("assets/ui/gtavi_corner.png", width=265)
        idx_logo = next_idx
        inputs.extend(["-loop", "1", "-t", f"{total_dur + 0.40:.3f}", "-i", str(corner_logo)])
        next_idx += 1
        filters.append(
            f"[vtr][{idx_fill}:v]overlay=x='-1080+1080*min(t/{total_dur:.3f},1)':y=0:shortest=1[vbar]"
        )
        filters.append(
            f"[{idx_logo}:v]fps={fps},format=rgba[lg]"
        )
        filters.append(
            f"[vbar][lg]overlay=x=792:y=20:enable='gte(t,2.35)':shortest=1,setsar=1[vout]"
        )
    else:
        filters.append(
            f"[vtr][{idx_fill}:v]overlay=x='-1080+1080*min(t/{total_dur:.3f},1)':y=0:shortest=1,setsar=1[vout]"
        )

    # Mix real studio Mixkit SFX, Silence-Trick #1 drop, midpoint pattern-interrupt, & Trap Electro bed
    sfx = ensure_sfx_pack()
    bt_last = boundary_times[-1] if boundary_times else -1.0
    if bt_last > 1.2:
        filters.append(
            f"[{final_a}]volume='if(between(t,{bt_last - 0.22:.3f},{bt_last - 0.03:.3f}),0.16,1.0)':eval=frame[main_duck]"
        )
        mix_labels = ["[main_duck]"]
    else:
        mix_labels = [f"[{final_a}]"]

    bed_path = sfx.get("hype_bed")
    if bed_path and bed_path.exists():
        inputs.extend(["-stream_loop", "-1", "-t", f"{total_dur + 0.25:.3f}", "-i", str(bed_path)])
        if bt_last > 1.2:
            filters.append(
                f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total_dur:.3f},"
                f"volume='if(between(t,{bt_last - 0.22:.3f},{bt_last - 0.02:.3f}),0.02,0.17)':eval=frame[bed]"
            )
        else:
            filters.append(
                f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total_dur:.3f},volume=0.17[bed]"
            )
        mix_labels.append("[bed]")
        next_idx += 1

    mid_idx = len(boundary_times) // 2 if len(boundary_times) >= 4 else -1
    for b_idx, bt in enumerate(boundary_times):
        # 200ms Swoosh peak aligns cleanly right on the clip wipe
        w_ms = max(int((bt - 0.16) * 1000), 0)
        inputs.extend(["-i", str(sfx["whoosh"])])
        filters.append(
            f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={w_ms}:all=1,volume=0.55[wh_{b_idx}]"
        )
        mix_labels.append(f"[wh_{b_idx}]")
        next_idx += 1

        if b_idx == mid_idx and sfx.get("glitch") and sfx["glitch"].exists():
            gl_ms = max(int((bt - 0.02) * 1000), 0)
            inputs.extend(["-i", str(sfx["glitch"])])
            filters.append(
                f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={gl_ms}:all=1,volume=0.42[mid_gl]"
            )
            mix_labels.append("[mid_gl]")
            next_idx += 1

        if b_idx == len(boundary_times) - 1 and bt > 1.0:
            # 1180ms Riser crescendo lands cleanly on #1 unlock cut
            r_ms = max(int((bt - 1.15) * 1000), 0)
            inputs.extend(["-i", str(sfx["riser"])])
            filters.append(
                f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={r_ms}:all=1,volume=0.54[riser_1]"
            )
            mix_labels.append("[riser_1]")
            next_idx += 1

            hit_ms = max(int((bt - 0.03) * 1000), 0)
            inputs.extend(["-i", str(sfx["bass_boom"])])
            filters.append(
                f"[{next_idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={hit_ms}:all=1,volume=0.62[unlock_hit]"
            )
            mix_labels.append("[unlock_hit]")
            next_idx += 1

    if len(mix_labels) == 1:
        filters.append(f"[{final_a}]loudnorm=I=-13.5:TP=-1.0:LRA=10,alimiter=limit=0.91:attack=5:release=50[aout]")
    else:
        filters.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:normalize=0,"
            "loudnorm=I=-13.5:TP=-1.0:LRA=10,alimiter=limit=0.91:attack=5:release=50[aout]"
        )

    filter_str = ";".join(filters)
    base_cmd = [
        "ffmpeg", "-y", "-v", "error",
        *inputs,
        "-filter_complex", filter_str,
        "-map", "[vout]", "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
    ]
    cmd = [*base_cmd, *_video_encoder_args(use_nvenc), str(output_path)]
    fb = [*base_cmd, *_video_encoder_args(False), str(output_path)] if use_nvenc else None
    _run_ffmpeg(cmd, fb)
    return output_path, eff_fade


_OFFTOPIC_GTA6_KEYWORDS = (
    "fivem",
    "roleplay",
    "nopixel",
    "no pixel",
    "warzone",
    "call of duty",
    "valorant",
    "fortnite",
    "cs2",
    "apex legends",
    "pre order",
    "pre-order",
    "geri sayım",
    "geri sayim",
    "new id",
)


def _is_offtopic_title(clip: Clip, category: str) -> bool:
    """Filter obvious wrong-game or spam-tagged titles when querying GTA VI."""
    if "grand theft auto vi" not in (category or "").lower():
        return False
    title_low = f" {(clip.title or '').lower()} "
    if any(kw in title_low for kw in _OFFTOPIC_GTA6_KEYWORDS):
        return True
    if " cod " in title_low or " rp " in title_low or " f1 " in title_low:
        return True
    return False


class CompilationPipeline:
    """Builds 62s–110s countdown compilations with intro hook & narration for monetization."""

    def __init__(
        self,
        *,
        engine: ClipFinderEngine | None = None,
        history: ClipHistory | None = None,
        downloader: ClipDownloader | None = None,
        output_dir: str | Path = "output/ready",
    ) -> None:
        self.engine = engine or ClipFinderEngine()
        self.history = history or ClipHistory()
        self.downloader = downloader or ClipDownloader()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_compilation(
        self,
        *,
        category: str = "Grand Theft Auto VI",
        platforms: list[str] | None = None,
        period: Period = "week",
        sort_by: SortBy = "views",
        min_views: int = 0,
        language: str | None = None,
        keywords: list[str] | None = None,
        target_min_duration: float = 63.0,
        target_max_duration: float = 76.0,
        max_per_clip: float = 6.4,
        min_clip_count: int = 3,
        max_clip_count: int = 14,
        whisper_model: str = "base",
        narration_lang: str | None = None,
        intro_audio_path: str | Path | None = None,
        edit_config: EditConfig | None = None,
        force: bool = False,
    ) -> CompilationResult:
        search_res = self.engine.search(
            category=category,
            platforms=platforms,
            period=period,
            limit_per_platform=60,
            min_views=min_views,
            max_duration=120.0,
            language=language,
            keywords=keywords,
            sort_by=sort_by,
        )

        def _is_compiled_or_rejected(c_item: Clip) -> bool:
            c_key = f"{c_item.platform}:{c_item.clip_id}"
            if self.history.is_processed("compiled", c_key):
                return True
            entry = self.history.get("compiled", c_key)
            return bool(entry and entry.get("status") == "rejected")

        candidates = [
            c
            for c in search_res.clips
            if not _is_offtopic_title(c, category)
            and (force or not _is_compiled_or_rejected(c))
        ]
        if not candidates:
            candidates = [c for c in search_res.clips if not _is_offtopic_title(c, category)] or search_res.clips

        if len(candidates) < 2:
            raise RuntimeError(
                f"Derleme için yeterli klip bulunamadı ({len(candidates)} klip bulundu). "
                "Zaman aralığını (--period all) veya minimum izlenmeyi düşürmeyi deneyin."
            )

        # Ensure compilation clears 62+s cleanly after xfade overlaps even if few clips exist
        eff_per_clip = max_per_clip
        if len(candidates) <= 9:
            eff_per_clip = max(
                max_per_clip,
                min(19.0, ((target_min_duration + 2.5) / max(len(candidates), 2)) + 1.2),
            )

        cfg = edit_config or EditConfig(
            punch_zoom=True,
            camera_shake=True,
            impact_flash=True,
            rgb_split=True,
            add_sfx=True,
        )
        seg_cfg = EditConfig(
            layout=cfg.layout,
            cam_corner=cfg.cam_corner,
            cut_dead_air=cfg.cut_dead_air,
            max_duration=eff_per_clip,
            punch_zoom=cfg.punch_zoom,
            camera_shake=cfg.camera_shake,
            impact_flash=cfg.impact_flash,
            rgb_split=cfg.rgb_split,
            add_sfx=cfg.add_sfx,
            music_path=cfg.music_path,
            music_volume=cfg.music_volume,
            use_nvenc=cfg.use_nvenc,
            target_fps=cfg.target_fps,
        )

        framing_cache: dict[Path, object] = {}

        def _pace_clip(c_idx: int, raw: Path, out_paced: Path) -> tuple[Path, float, object | None]:
            raw_info = probe_video(raw)
            if not seg_cfg.cut_dead_air:
                fp = detect_framing_plan(raw) if seg_cfg.layout == "auto" else None
                if fp is not None:
                    framing_cache[raw] = fp
                return raw, raw_info.duration, fp
            init_analysis = analyze_audio(raw)
            start_off = 0.0
            if raw_info.duration > eff_per_clip + 1.0:
                climax = init_analysis.climax_time or (raw_info.duration * 0.60)
                start_off = max(0.0, min(climax - eff_per_clip * 0.72, raw_info.duration - eff_per_clip))
            paced_path = jump_cut_dead_air(
                raw,
                init_analysis.segments,
                out_paced,
                raw_info,
                start_offset=start_off,
                max_duration=eff_per_clip,
                use_nvenc=cfg.use_nvenc,
            )
            if seg_cfg.layout == "auto":
                paced_fp = detect_framing_plan(paced_path)
                framing_cache[paced_path] = paced_fp
                return paced_path, probe_video(paced_path).duration, paced_fp
            return paced_path, probe_video(paced_path).duration, None

        with tempfile.TemporaryDirectory(prefix="compile_") as td:
            tmp = Path(td)
            # Pass 1: download, prefer unique split-cam streamers + active textured frames, slice around climax
            paced_items: list[tuple[Clip, Path, float]] = []
            non_split_backup: list[tuple[Clip, Path, float]] = []
            low_motion_backup: list[tuple[Clip, Path, float]] = []
            dup_channel_backup: list[tuple[int, Clip]] = []
            seen_channels: set[str] = set()
            running_dur = 2.50  # opening teaser hook duration

            for idx, clip in enumerate(candidates):
                if len(paced_items) >= max_clip_count:
                    break
                if running_dur >= target_min_duration and len(paced_items) >= min_clip_count:
                    break
                if running_dur >= target_max_duration - 4.0:
                    break

                chan_key = clip.channel_name.strip().lower()
                if chan_key in seen_channels and len(candidates) - idx > 2:
                    dup_channel_backup.append((idx, clip))
                    continue

                print(
                    f"[1/3] Klip hazirlaniyor #{idx + 1}: {clip.channel_name} ({clip.views:,} izlenme)...",
                    flush=True,
                )
                try:
                    raw = self.downloader.download(clip, overwrite=force)
                    paced_path, paced_dur, paced_fp = _pace_clip(idx, raw, tmp / f"paced_{idx}.mp4")
                except Exception as exc:
                    print(f"      Atlandi ({clip.channel_name}): {exc}", flush=True)
                    continue

                if getattr(paced_fp, "is_broken_screen", False):
                    print(f"      -> Bozuk/renk-bar/BRB ekrani elendi ({clip.channel_name})", flush=True)
                    continue

                mot_score = getattr(paced_fp, "motion_score", 15.0) if paced_fp is not None else 15.0
                is_split = (seg_cfg.layout != "auto") or (getattr(paced_fp, "mode", None) == "split_cam")

                if not is_split and idx < len(candidates) - 1:
                    non_split_backup.append((clip, paced_path, paced_dur))
                    print(
                        f"      -> Yuz kamerasi/split_cam yok ({getattr(paced_fp, 'mode', 'unknown')}), yedege alindi",
                        flush=True,
                    )
                    continue

                if (mot_score < 3.5 or paced_dur < 3.5) and idx < len(candidates) - 1:
                    low_motion_backup.append((clip, paced_path, paced_dur))
                    print(
                        f"      -> Dusuk tempo/hareket (mot={mot_score:.1f}, {paced_dur:.1f}s), yedege alindi",
                        flush=True,
                    )
                    continue

                seen_channels.add(chan_key)
                paced_items.append((clip, paced_path, paced_dur))
                running_dur += max(paced_dur - 0.16, 0.5)
                print(
                    f"      -> {paced_dur:.1f}s (split={is_split}, mot={mot_score:.1f}, toplam ~{running_dur:.1f}s)",
                    flush=True,
                )

            # Fallback 1: un-downloaded same-channel candidates with verified split_cam + motion
            for b_idx, b_clip in dup_channel_backup:
                if (running_dur >= target_min_duration and len(paced_items) >= min_clip_count) or len(paced_items) >= max_clip_count:
                    break
                try:
                    b_raw = self.downloader.download(b_clip, overwrite=force)
                    b_paced, b_dur, b_fp = _pace_clip(b_idx, b_raw, tmp / f"paced_dup_{b_idx}.mp4")
                    if getattr(b_fp, "is_broken_screen", False):
                        continue
                    b_mot = getattr(b_fp, "motion_score", 15.0) if b_fp is not None else 15.0
                    b_split = (seg_cfg.layout != "auto") or (getattr(b_fp, "mode", None) == "split_cam")
                    if not b_split:
                        non_split_backup.append((b_clip, b_paced, b_dur))
                    elif b_mot < 3.5 or b_dur < 3.5:
                        low_motion_backup.append((b_clip, b_paced, b_dur))
                    else:
                        paced_items.append((b_clip, b_paced, b_dur))
                        running_dur += max(b_dur - 0.16, 0.5)
                        print(f"      + Ek klip ({b_clip.channel_name}): {b_dur:.1f}s -> ~{running_dur:.1f}s", flush=True)
                except Exception:
                    continue

            # Fallback 2: non-split active clips before low-motion clips, only if still short
            for backup_pool in (non_split_backup, low_motion_backup):
                while backup_pool and (
                    running_dur < target_min_duration or len(paced_items) < min_clip_count
                ) and len(paced_items) < max_clip_count:
                    clip, paced_path, paced_dur = backup_pool.pop(0)
                    paced_items.append((clip, paced_path, paced_dur))
                    running_dur += max(paced_dur - 0.16, 0.5)
                    print(
                        f"      + Yedek eklendi ({clip.channel_name}): {paced_dur:.1f}s -> ~{running_dur:.1f}s",
                        flush=True,
                    )

            if len(paced_items) < 2:
                raise RuntimeError("Yeterli klip indirilemedi.")

            # Order as Countdown: lowest rank -> #1 (highest views at the end!)
            n_clips = len(paced_items)
            countdown = list(reversed(paced_items))

            edited_segments: list[Path] = []
            segment_details: list[tuple[Clip, float, str]] = []
            teaser_pool: list[tuple[Path, float, object]] = []

            for pos, (clip, paced_path, paced_dur) in enumerate(countdown):
                rank_num = n_clips - pos
                seg_out = tmp / f"edited_{pos}_{rank_num}.mp4"
                print(
                    f"[2/3] #{rank_num} transkript & 9:16 montaj: {clip.channel_name} ({paced_dur:.1f}s)...",
                    flush=True,
                )

                final_analysis = analyze_audio(paced_path)
                framing = (
                    framing_cache.get(paced_path) or detect_framing_plan(paced_path)
                    if seg_cfg.layout == "auto"
                    else None
                )
                cap_res = generate_wspeed_captions(
                    paced_path,
                    tmp / f"cap_{pos}.ass",
                    model_size=whisper_model,
                    language=language or (clip.language if clip.language else None),
                    rank_label="",
                    video_duration=paced_dur,
                    skip_dialogue=False,
                    target_language="en",
                    dual_sub=True,
                )
                pill_png = render_rank_pill_png(
                    rank_num,
                    clip.channel_name,
                    0,
                    tmp / f"pill_{pos}.png",
                    fallback_handle=_extract_slug_handle(clip),
                    show_views=False,
                )
                rendered = render_wspeed_edit(
                    paced_path,
                    seg_out,
                    final_analysis,
                    ass_path=cap_res.ass_path,
                    framing=framing,
                    config=seg_cfg,
                    overlay_png_path=pill_png,
                    overlay_mode="pill",
                )
                seg_dur = probe_video(rendered).duration
                transcript = cap_res.transcript

                # Optional user-requested narration cue (skipped by default)
                if rank_num == 1 and narration_lang and not intro_audio_path:
                    cue_txt = "Ve haftanın bir numarası!" if narration_lang.startswith("tr") else "And at number one."
                    cue_mp3 = tmp / "cue_1.mp3"
                    try:
                        synthesize_narration(cue_txt, cue_mp3, narration_lang)
                        cued_out = tmp / f"edited_{pos}_cued.mp4"
                        _overlay_voice_at_start(rendered, cue_mp3, cued_out, use_nvenc=cfg.use_nvenc)
                        rendered = cued_out
                    except Exception:
                        pass

                edited_segments.append(rendered)
                segment_details.append((clip, seg_dur, transcript))
                peak_hint = final_analysis.climax_time or (final_analysis.hype_peaks[0] if final_analysis.hype_peaks else paced_dur * 0.5)
                teaser_pool.append((paced_path, peak_hint, framing))

            # Build 3-beat neuro-retention cold-open: instant conflict -> smash cut -> blurred #1 open loop
            print(f"[3/3] 3-adimli neuro-hook, xfade gecisler ve {n_clips} klip birlestiriliyor...", flush=True)
            cat_tokens = [c.strip().lower() for c in category.split(",") if c.strip()]
            if cat_tokens == ["grand theft auto vi"]:
                cat_short = "GTA 6"
            elif any("grand theft auto" in c for c in cat_tokens):
                cat_short = "GTA"
            else:
                cat_short = category.split(",")[0].strip().upper()[:14]

            is_tr_hook = (narration_lang or language or "").lower().startswith("tr")
            if is_tr_hook:
                hook_badge = f"EN İYİ {n_clips} {cat_short}"
                hook_title = "1 NUMARADA\nNE OLDU?!"
                hook_sub = "SONUNA KADAR İZLE"
                lock_title = "1 NUMARADA AÇILIR"
                lock_sub = "SONA KADAR BEKLE"
            else:
                hook_badge = f"TOP {n_clips} {cat_short}"
                hook_title = "WHAT DID #1\nJUST DO?!"
                hook_sub = "WAIT TILL THE END"
                lock_title = "UNLOCKS AT #1"
                lock_sub = "WAIT FOR THE ENDING"

            intro_vo: Path | None = None
            if intro_audio_path and Path(intro_audio_path).exists():
                intro_vo = Path(intro_audio_path)
            elif narration_lang:
                intro_mp3 = tmp / "intro_vo.mp3"
                if narration_lang.lower().startswith("tr"):
                    intro_txt = f"{cat_short} dünyasında yayıncıları çıldırtan en iyi {n_clips} an!"
                else:
                    intro_txt = f"Streamers lost their minds over these {cat_short} moments."
                try:
                    intro_vo = synthesize_narration(intro_txt, intro_mp3, narration_lang)
                except Exception:
                    intro_vo = None

            if len(teaser_pool) >= 3:
                split_openers = [
                    cand for cand in teaser_pool[:-1]
                    if getattr(cand[2], "mode", None) == "split_cam"
                ]
                opener_pool = split_openers if len(split_openers) >= 2 else teaser_pool[:-1]
                scored_openers: list[tuple[float, tuple[Path, float, object]]] = []
                for cand in opener_pool:
                    bt, sc = _pick_vivid_teaser_start(cand[0], cand[1], 1.05)
                    scored_openers.append((sc, (cand[0], bt + 0.45, cand[2])))
                scored_openers.sort(key=lambda item: item[0], reverse=True)
                best_b1 = scored_openers[0][1]
                best_b2 = scored_openers[1][1] if len(scored_openers) > 1 else teaser_pool[0]
                teaser_shots = [best_b1, best_b2, teaser_pool[-1]]
            else:
                teaser_shots = list(teaser_pool)

            teaser_path = tmp / "teaser.mp4"
            teaser_dur = _build_teaser_segment(
                teaser_shots,
                teaser_path,
                hook_badge=hook_badge,
                hook_title=hook_title,
                hook_sub=hook_sub,
                lock_title=lock_title,
                lock_sub=lock_sub,
                narration_audio=intro_vo,
                config=seg_cfg,
                use_nvenc=cfg.use_nvenc,
            )

            all_parts = [teaser_path, *edited_segments]
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_video = self.output_dir / f"compilation_{stamp}_{n_clips}clips.mp4"
            _, eff_fade = _concat_segments(
                all_parts,
                out_video,
                fps=cfg.target_fps,
                show_gta_corner=("gta" in cat_short.lower()),
                use_nvenc=cfg.use_nvenc,
            )

        final_dur = probe_video(out_video).duration
        used_clips = [c for (c, _, _) in segment_details]

        # Build clean, compliant metadata with accurate transition-adjusted chapters & creator credits
        is_tr = (narration_lang or language or "").lower().startswith("tr")
        cat_label = cat_short
        if is_tr:
            title = f"En Çok İzlenen {n_clips} {cat_label} Anı (#1 Efsane)"
        else:
            title = f"Top {n_clips} Most Watched {cat_label} Moments (#1 is Wild)"

        chapters = ["00:00 Giriş" if is_tr else "00:00 Intro"]
        cursor = max(teaser_dur - eff_fade, 0.0)
        credits = []
        for idx, (clip, seg_dur, _) in enumerate(segment_details):
            rank_num = n_clips - idx
            chapters.append(f"{_format_mmss(cursor)} #{rank_num} - {clip.channel_name}")
            credits.append(f"#{rank_num} {clip.channel_name} ({clip.platform.upper()}): {clip.url}")
            cursor += max(seg_dur - eff_fade, 0.2)

        tags = ["#gta6", "#gtavi", "#gaming", "#shorts", "#clips"] if "vi" in category.lower() else ["#gaming", "#shorts", "#clips", "#twitch", "#kick"]
        if is_tr and "#kesfet" not in tags:
            tags.append("#kesfet")

        description = (
            f"{title}\n\n"
            + ("Bölümler:\n" if is_tr else "Chapters:\n")
            + "\n".join(chapters)
            + "\n\n"
            + ("Kaynak Klipler / Credits:\n" if is_tr else "Credits:\n")
            + "\n".join(credits)
            + "\n\n"
            + " ".join(tags)
        )

        monetization_checks = {
            "over_60_seconds_tiktok_rewards": final_dur > 60.5,
            "multi_clip_compilation_3_plus": len(used_clips) >= 3,
            "has_voiceover_commentary": bool(intro_vo is not None),
            "no_synthetic_ai_tts": bool(intro_vo is None or (intro_audio_path and Path(intro_audio_path).exists())),
            "vertical_1080x1920": True,
            "creator_credits_included": True,
        }

        meta_dict = {
            "viral_title": title,
            "hook_banner": "",
            "description": description,
            "hashtags": tags,
            "youtube_shorts_title": f"{title} #shorts"[:99],
            "tiktok_caption": f"{title}\n{' '.join(tags)}",
            "instagram_caption": f"{title}\n\n{' '.join(tags)}",
            "source_url": used_clips[-1].url,
            "streamer": ", ".join(c.channel_name for c in used_clips),
            "transcript": " | ".join(t for (_, _, t) in segment_details if t),
            "duration_seconds": round(final_dur, 2),
            "monetization_checks": monetization_checks,
            "credits": credits,
        }

        meta_json = out_video.with_suffix(".json")
        meta_txt = out_video.with_suffix(".txt")
        meta_json.write_text(json.dumps(meta_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        meta_txt.write_text(
            f"=== TITLE ===\n{title}\n\n"
            f"=== YOUTUBE SHORTS TITLE ===\n{meta_dict['youtube_shorts_title']}\n\n"
            f"=== DESCRIPTION (CREDITS + CHAPTERS) ===\n{description}\n",
            encoding="utf-8",
        )

        # Enrich SEO metadata uniquely across existing compilations and update upload_queue.json
        sync_upload_queue(ready_dir=self.output_dir, category=category)
        enriched = json.loads(meta_json.read_text(encoding="utf-8"))
        title = enriched.get("viral_title", title)
        description = enriched.get("description", description)
        tags = enriched.get("hashtags", tags)

        # Track in history so Web UI displays it in Hazır Videolar and skips re-compiling same clips
        for c in used_clips:
            self.history.mark(
                "compiled",
                f"{c.platform}:{c.clip_id}",
                "done",
                title=c.title,
                channel_name=c.channel_name,
                url=c.url,
                output_path=str(out_video.resolve()),
                metadata_path=str(meta_json.resolve()),
            )
        self.history.mark(
            "compilation",
            out_video.stem,
            "done",
            title=title,
            channel_name=", ".join(c.channel_name for c in used_clips),
            url=used_clips[-1].url,
            output_path=str(out_video.resolve()),
            metadata_path=str(meta_json.resolve()),
            extra={"duration_seconds": round(final_dur, 2), "monetization_checks": monetization_checks},
        )

        return CompilationResult(
            output_path=out_video,
            metadata_path=meta_json,
            duration_seconds=final_dur,
            clips_used=used_clips,
            title=title,
            description=description,
            hashtags=tags,
            monetization_checks=monetization_checks,
        )
