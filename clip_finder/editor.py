from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from clip_finder.audio_fx import AudioAnalysis, AudioSegment, analyze_audio, ensure_sfx_pack
from clip_finder.captions import ensure_montserrat_font
from clip_finder.facecam import FramingPlan, detect_framing_plan
from clip_finder.graphics import render_neon_divider_png

LayoutMode = Literal["auto", "center_crop", "split_cam", "blur_stack"]
CamCorner = Literal["top_left", "top_right", "bottom_left", "bottom_right"]


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


@dataclass
class EditConfig:
    layout: LayoutMode = "auto"
    cam_corner: CamCorner = "top_left"
    cut_dead_air: bool = True
    max_duration: float | None = 58.0
    punch_zoom: bool = True
    camera_shake: bool = False
    impact_flash: bool = False
    rgb_split: bool = False
    add_sfx: bool = False
    music_path: Path | None = None
    music_volume: float = 0.12
    use_nvenc: bool = True
    target_fps: int = 60


def _ff_escape_path(path: Path) -> str:
    """Escape a filesystem path for FFmpeg filter arguments on Windows/POSIX."""
    s = str(path.resolve()).replace("\\", "/")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    return s


def probe_video(video_path: str | Path) -> VideoInfo:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)

    v_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v_stream:
        raise RuntimeError(f"Video akışı bulunamadı: {video_path}")

    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    width = int(v_stream.get("width") or 1920)
    height = int(v_stream.get("height") or 1080)

    fps_raw = v_stream.get("avg_frame_rate") or v_stream.get("r_frame_rate") or "30/1"
    if "/" in str(fps_raw):
        num, den = str(fps_raw).split("/", 1)
        fps = float(num) / float(den) if float(den) else 30.0
    else:
        fps = float(fps_raw)
    fps = min(max(fps, 15.0), 120.0)

    duration = float((data.get("format") or {}).get("duration") or v_stream.get("duration") or 0.0)
    return VideoInfo(width=width, height=height, fps=fps, duration=duration, has_audio=has_audio)


def _video_encoder_args(use_nvenc: bool) -> list[str]:
    if use_nvenc:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"]


def _run_ffmpeg(cmd: list[str], fallback_cmd: list[str] | None = None) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if proc.returncode == 0:
        return
    if fallback_cmd is not None:
        fb = subprocess.run(fallback_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if fb.returncode == 0:
            return
        raise RuntimeError(f"FFmpeg hatası:\n{fb.stderr[-1500:]}")
    raise RuntimeError(f"FFmpeg hatası:\n{proc.stderr[-1500:]}")


def jump_cut_dead_air(
    input_path: Path,
    segments: list[AudioSegment],
    out_path: Path,
    info: VideoInfo,
    *,
    start_offset: float = 0.0,
    max_duration: float | None = 58.0,
    use_nvenc: bool = True,
) -> Path:
    """Remove dead-air pauses with clean hard jump cuts anchored at start_offset."""
    win_start = max(0.0, min(start_offset, max(info.duration - 1.5, 0.0)))
    win_end = info.duration

    if not segments:
        if max_duration and (win_end - win_start) > max_duration or win_start > 0.15:
            kept = [AudioSegment(win_start, min(win_end, win_start + (max_duration or win_end)), False)]
        else:
            return input_path
    else:
        # Tighter algorithm pacing: keep active speech/action, cut silent pauses >= 0.24s
        kept = []
        for seg in segments:
            if seg.end <= win_start:
                continue
            if not seg.is_silent or (seg.end - seg.start) < 0.24:
                s = max(win_start, seg.start - 0.05)
                e = min(win_end, seg.end + 0.05)
                if e - s < 0.08:
                    continue
                if kept and s <= kept[-1].end + 0.10:
                    kept[-1].end = max(kept[-1].end, e)
                else:
                    kept.append(AudioSegment(s, e, False))

        total_kept = sum(k.end - k.start for k in kept)
        if not kept or total_kept < min(2.0, (win_end - win_start) * 0.4):
            kept = [AudioSegment(win_start, win_end, False)]

    # Avoid redundant re-encode only if practically the full clip is kept untouched
    total_kept = sum(k.end - k.start for k in kept)
    if (
        win_start <= 0.15
        and len(kept) == 1
        and kept[0].start <= 0.15
        and kept[0].end >= info.duration - 0.15
        and (not max_duration or info.duration <= max_duration)
    ):
        return input_path

    if len(kept) > 18:
        kept = [AudioSegment(win_start, min(win_end, win_start + (max_duration or win_end)), False)]

    parts: list[str] = []
    concat_inputs: list[str] = []
    elapsed = 0.0

    for idx, seg in enumerate(kept):
        if max_duration and elapsed >= max_duration:
            break
        s = seg.start
        e = seg.end
        if max_duration and elapsed + (e - s) > max_duration:
            e = s + (max_duration - elapsed)
        if e - s < 0.12:
            continue
        elapsed += e - s

        v_tag = f"[v{idx}]"
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS{v_tag}")
        concat_inputs.append(v_tag)
        if info.has_audio:
            a_tag = f"[a{idx}]"
            parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS{a_tag}")
            concat_inputs.append(a_tag)

    n_seg = len(concat_inputs) // (2 if info.has_audio else 1)
    if n_seg == 0:
        return input_path

    if info.has_audio:
        filter_str = ";".join(parts) + f";{''.join(concat_inputs)}concat=n={n_seg}:v=1:a=1[vout][aout]"
        maps = ["-map", "[vout]", "-map", "[aout]"]
        a_args = ["-c:a", "aac", "-b:a", "192k"]
    else:
        filter_str = ";".join(parts) + f";{''.join(concat_inputs)}concat=n={n_seg}:v=1:a=0[vout]"
        maps = ["-map", "[vout]"]
        a_args = []

    base_cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(input_path), "-filter_complex", filter_str, *maps]
    cmd = [*base_cmd, *_video_encoder_args(use_nvenc), *a_args, str(out_path)]
    fb = [*base_cmd, *_video_encoder_args(False), *a_args, str(out_path)] if use_nvenc else None
    _run_ffmpeg(cmd, fb)
    return out_path


def _build_wspeed_motion_terms(peaks: list[float], config: EditConfig) -> tuple[str, str, str, str, str]:
    """Build smooth eased punch-zooms, continuous push-in drift, and damped peak impact FX."""
    active_peaks = peaks[:4]

    zoom_terms: list[str] = ["1.02+0.03*min(t/7.0,1)"]
    shake_x_terms = ["0"]
    shake_y_terms = ["0"]
    flash_terms = ["0"]
    rgb_terms: list[str] = []

    if config.punch_zoom:
        zoom_terms.append("0.08*between(t,0.00,0.18)*(1-t/0.18)")
    if config.impact_flash:
        flash_terms.append("0.14*between(t,0.00,0.09)*(1-t/0.09)")

    for p in active_peaks:
        if config.punch_zoom:
            zoom_terms.append(f"0.11*between(t,{p:.2f},{p+0.70:.2f})*exp(-4.8*(t-{p:.2f}))")
        if config.camera_shake:
            shake_x_terms.append(
                f"7*between(t,{p:.2f},{p+0.18:.2f})*(1-(t-{p:.2f})/0.18)*sin(t*85)"
            )
            shake_y_terms.append(
                f"6*between(t,{p:.2f},{p+0.18:.2f})*(1-(t-{p:.2f})/0.18)*cos(t*105)"
            )
        if config.impact_flash:
            flash_terms.append(f"0.12*between(t,{p:.2f},{p+0.08:.2f})*(1-(t-{p:.2f})/0.08)")
        if config.rgb_split:
            rgb_terms.append(f"between(t,{p:.2f},{p+0.12:.2f})")

    zoom_expr = "+".join(zoom_terms)
    shake_x = "+".join(shake_x_terms)
    shake_y = "+".join(shake_y_terms)
    flash_expr = "+".join(flash_terms)
    rgb_enable = "+".join(rgb_terms) if rgb_terms else "0"
    return zoom_expr, shake_x, shake_y, flash_expr, rgb_enable


def _build_zoompan_exprs(
    peaks: list[float],
    duration: float,
    fps: int,
    config: EditConfig,
) -> tuple[str, str, str]:
    """Build subpixel FFmpeg zoompan expressions using `on`/`it` (zero 2px jitter)."""
    total_frames = max(int(round(max(duration, 1.5) * fps)), 60)
    z_terms: list[str] = [f"1.045+0.075*min(on/{total_frames},1)"]
    sx_terms: list[str] = ["0"]
    sy_terms: list[str] = ["0"]

    if config.punch_zoom:
        z_terms.append("0.065*between(it,0.00,0.22)*(1-it/0.22)")

    effective_peaks = list(peaks[:4])
    if duration >= 3.2 and len(effective_peaks) < 2:
        for t_mid in (round(duration * 0.36, 2), round(duration * 0.70, 2)):
            if all(abs(t_mid - ep) > 0.9 for ep in effective_peaks):
                effective_peaks.append(t_mid)

    for p in effective_peaks[:4]:
        if config.punch_zoom:
            z_terms.append(f"0.135*between(it,{p:.2f},{p+0.68:.2f})*exp(-4.6*(it-{p:.2f}))")
        if config.camera_shake:
            sx_terms.append(
                f"9*between(it,{p:.2f},{p+0.20:.2f})*(1-(it-{p:.2f})/0.20)*sin(it*85)"
            )
            sy_terms.append(
                f"8*between(it,{p:.2f},{p+0.20:.2f})*(1-(it-{p:.2f})/0.20)*cos(it*105)"
            )

    z_expr = "+".join(z_terms)
    x_expr = "iw/2-(iw/zoom/2)" + (f"+({'+'.join(sx_terms[1:])})" if len(sx_terms) > 1 else "")
    y_expr = "ih/2-(ih/zoom/2)" + (f"+({'+'.join(sy_terms[1:])})" if len(sy_terms) > 1 else "")
    return z_expr, x_expr, y_expr


def _cam_crop_expr(corner: CamCorner) -> tuple[str, str, str, str]:
    """Return (w, h, x, y) crop expressions for streamer webcam box."""
    w = "iw*0.26"
    h = "ih*0.34"
    if corner == "top_left":
        return w, h, "0", "0"
    if corner == "top_right":
        return w, h, "iw-ow", "0"
    if corner == "bottom_left":
        return w, h, "0", "ih-oh"
    return w, h, "iw-ow", "ih-oh"


def _resolve_layout(
    cfg: EditConfig,
    framing: FramingPlan | None,
) -> tuple[Literal["center_crop", "split_cam", "blur_stack"], tuple[str, str, str, str] | None, float]:
    if cfg.layout == "auto" and framing is not None:
        if framing.mode == "split_cam" and framing.cam_box is not None:
            bx, by, bw, bh = framing.cam_box
            box_expr = (f"iw*{bw:.4f}", f"ih*{bh:.4f}", f"iw*{bx:.4f}", f"ih*{by:.4f}")
            return "split_cam", box_expr, 0.5
        if framing.mode == "face_center":
            return "center_crop", None, framing.face_center_x
        return "center_crop", None, 0.5

    if cfg.layout == "split_cam":
        return "split_cam", _cam_crop_expr(cfg.cam_corner), 0.5
    if cfg.layout == "blur_stack":
        return "blur_stack", None, 0.5
    return "center_crop", None, 0.5


def render_wspeed_edit(
    paced_path: Path,
    output_path: Path,
    analysis: AudioAnalysis,
    *,
    ass_path: Path | None = None,
    framing: FramingPlan | None = None,
    config: EditConfig | None = None,
    overlay_png_path: Path | None = None,
    overlay_mode: Literal["pill", "hook"] = "pill",
) -> Path:
    """Render a clean, full-screen 1080x1920@60fps edit with subpixel zoompan, HUD, and captions."""
    cfg = config or EditConfig()
    info = probe_video(paced_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    _, _, _, flash_expr, rgb_enable = _build_wspeed_motion_terms(analysis.hype_peaks, cfg)
    zp_z, zp_x, zp_y = _build_zoompan_exprs(
        analysis.hype_peaks, info.duration, cfg.target_fps, cfg
    )
    resolved_layout, cam_box_expr, center_x_frac = _resolve_layout(cfg, framing)

    # Track FFmpeg inputs sequentially so stream indices always match
    inputs: list[str] = ["-i", str(paced_path)]
    next_idx = 1

    ov_idx: int | None = None
    if overlay_png_path and Path(overlay_png_path).exists():
        ov_idx = next_idx
        inputs.extend(["-loop", "1", "-t", f"{info.duration + 0.30:.3f}", "-i", str(overlay_png_path)])
        next_idx += 1

    div_idx: int | None = None
    if resolved_layout == "split_cam":
        div_png = render_neon_divider_png(1080, 8, out_path="assets/ui/neon_divider_1080x8.png")
        div_idx = next_idx
        inputs.extend(["-loop", "1", "-t", f"{info.duration + 0.30:.3f}", "-i", str(div_png)])
        next_idx += 1

    # --- Video Filtergraph (Subpixel Zoompan + Vice-City Vibrant Color) ---
    v_filters: list[str] = []
    if resolved_layout == "center_crop":
        v_filters.append(
            f"[0:v]setpts=PTS-STARTPTS,fps={cfg.target_fps},"
            f"scale=1440:2560:force_original_aspect_ratio=increase,"
            f"crop=1440:2560:'(iw-1440)*{center_x_frac:.3f}':'(ih-2560)/2',"
            f"zoompan=z='{zp_z}':x='{zp_x}':y='{zp_y}':d=1:s=1080x1920:fps={cfg.target_fps},"
            f"eq=contrast=1.13:saturation=1.30:brightness='({flash_expr})+0.025':eval=frame,"
            f"unsharp=5:5:0.80:3:3:0.0,vignette=angle=PI/7[vfx]"
        )
    elif resolved_layout == "split_cam":
        assert cam_box_expr is not None
        assert div_idx is not None
        cw, ch, cx, cy = cam_box_expr
        v_filters.append(f"[0:v]setpts=PTS-STARTPTS,fps={cfg.target_fps},split=2[cam_src][game_src]")
        v_filters.append(
            f"[cam_src]crop={cw}:{ch}:{cx}:{cy},"
            f"scale=1080:640:force_original_aspect_ratio=increase,crop=1080:640,"
            f"eq=contrast=1.10:saturation=1.22:brightness=0.022,unsharp=5:5:0.75:3:3:0.0[cam]"
        )
        v_filters.append(
            f"[{div_idx}:v]fps={cfg.target_fps},setsar=1,trim=0:{info.duration:.3f},setpts=PTS-STARTPTS[sep]"
        )
        v_filters.append(
            f"[game_src]scale=1440:1700:force_original_aspect_ratio=increase,crop=1440:1700,"
            f"zoompan=z='{zp_z}':x='{zp_x}':y='{zp_y}':d=1:s=1080x1272:fps={cfg.target_fps},"
            f"eq=contrast=1.13:saturation=1.30:brightness='({flash_expr})+0.025':eval=frame,"
            f"unsharp=5:5:0.80:3:3:0.0,vignette=angle=PI/7[game]"
        )
        v_filters.append("[cam][sep][game]vstack=inputs=3:shortest=1[vfx]")
    else:
        fg_h = int(round(1080 * info.height / max(info.width, 1)))
        fg_h = fg_h - (fg_h % 2)
        fg_h = min(max(fg_h, 400), 1400)
        fg_h_hi = int(round(fg_h * 1440 / 1080))
        fg_h_hi = max(fg_h_hi - (fg_h_hi % 2), 400)
        v_filters.append(f"[0:v]setpts=PTS-STARTPTS,fps={cfg.target_fps},split=2[bg_src][fg_src]")
        v_filters.append(
            "[bg_src]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
            "gblur=sigma=8,scale=1080:1920:flags=bilinear,eq=brightness=-0.16:saturation=1.22[bg]"
        )
        v_filters.append(
            f"[fg_src]scale=1440:{fg_h_hi}:force_original_aspect_ratio=increase,crop=1440:{fg_h_hi},"
            f"zoompan=z='{zp_z}':x='{zp_x}':y='{zp_y}':d=1:s=1080x{fg_h}:fps={cfg.target_fps},"
            f"eq=contrast=1.12:saturation=1.28:brightness='({flash_expr})+0.022':eval=frame[fg]"
        )
        v_filters.append("[bg][fg]overlay=x=0:y=(H-h)/2[vfx]")

    current_v = "[vfx]"
    if cfg.rgb_split and rgb_enable != "0":
        v_filters.append(f"{current_v}rgbashift=rh=7:bh=-7:enable='{rgb_enable}'[vrgb]")
        current_v = "[vrgb]"

    if ass_path and ass_path.exists():
        fonts_dir, _ = ensure_montserrat_font()
        ass_esc = _ff_escape_path(ass_path)
        if fonts_dir:
            fdir_esc = _ff_escape_path(fonts_dir)
            v_filters.append(f"{current_v}ass=filename='{ass_esc}':fontsdir='{fdir_esc}'[vsub]")
        else:
            v_filters.append(f"{current_v}ass=filename='{ass_esc}'[vsub]")
        current_v = "[vsub]"

    if ov_idx is not None:
        if overlay_mode == "hook":
            hook_y = 490 if resolved_layout == "split_cam" else 160
            fade_out = max(info.duration - 0.18, 0.35)
            v_filters.append(
                f"[{ov_idx}:v]format=rgba,fade=t=in:st=0:d=0.10:alpha=1,"
                f"fade=t=out:st={fade_out:.2f}:d=0.16:alpha=1[ov]"
            )
            v_filters.append(
                f"{current_v}[ov]overlay=x='(W-w)/2':"
                f"y='if(lt(t,0.20),{hook_y}+46*pow(1-t/0.20,3),{hook_y})':shortest=1,setsar=1[vout]"
            )
        else:
            pill_y = 574 if resolved_layout == "split_cam" else 40
            v_filters.append(
                f"{current_v}[{ov_idx}:v]overlay="
                f"x='if(lt(t,0.28),-w+(32+w)*(1-pow(1-t/0.28,3)),32)':"
                f"y={pill_y}:shortest=1,setsar=1[vout]"
            )
    else:
        v_filters.append(f"{current_v}setsar=1[vout]")

    # --- Audio & Punchy Cinema SFX/Music Mixing ---
    a_filters: list[str] = []
    mix_labels: list[str] = []

    if info.has_audio:
        a_filters.append(
            "[0:a]acompressor=threshold=-20dB:ratio=1.8:attack=8:release=110,alimiter=limit=0.95[main_a]"
        )
        mix_labels.append("[main_a]")

    if cfg.add_sfx and analysis.hype_peaks:
        sfx = ensure_sfx_pack()
        top_peak = analysis.climax_time if (analysis.climax_time and 0.3 < analysis.climax_time < info.duration - 0.3) else analysis.hype_peaks[0]
        delay_whoosh = max(int((top_peak - 0.16) * 1000), 0)
        inputs.extend(["-i", str(sfx["whoosh"])])
        a_filters.append(f"[{next_idx}:a]adelay={delay_whoosh}:all=1,volume=0.52[wh_{next_idx}]")
        mix_labels.append(f"[wh_{next_idx}]")
        next_idx += 1

        delay_boom = max(int(max(top_peak - 0.04, 0.0) * 1000), 0)
        inputs.extend(["-i", str(sfx["bass_boom"])])
        a_filters.append(f"[{next_idx}:a]adelay={delay_boom}:all=1,volume=0.52[boom_{next_idx}]")
        mix_labels.append(f"[boom_{next_idx}]")
        next_idx += 1

    if cfg.music_path and Path(cfg.music_path).exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(cfg.music_path)])
        a_filters.append(
            f"[{next_idx}:a]atrim=0:{info.duration:.3f},volume={cfg.music_volume:.2f}[bgm]"
        )
        mix_labels.append("[bgm]")
        next_idx += 1

    maps = ["-map", "[vout]"]
    a_enc_args: list[str] = []
    if mix_labels:
        if len(mix_labels) == 1:
            a_filters.append(
                f"{mix_labels[0]}aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-14:TP=-1.0:LRA=11[aout]"
            )
        else:
            a_filters.append(
                f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:normalize=0,"
                f"aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-14:TP=-1.0:LRA=11[aout]"
            )
        maps.extend(["-map", "[aout]"])
        a_enc_args = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        inputs.extend(["-f", "lavfi", "-t", f"{info.duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        a_filters.append(f"[{next_idx}:a]acopy[aout]")
        maps.extend(["-map", "[aout]"])
        a_enc_args = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]

    full_filter = ";".join([*v_filters, *a_filters])
    base_cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", full_filter, *maps]
    cmd = [*base_cmd, *_video_encoder_args(cfg.use_nvenc), *a_enc_args, "-movflags", "+faststart", str(out_path)]
    fb = (
        [*base_cmd, *_video_encoder_args(False), *a_enc_args, "-movflags", "+faststart", str(out_path)]
        if cfg.use_nvenc
        else None
    )
    _run_ffmpeg(cmd, fb)
    return out_path


def auto_edit_wspeed(
    input_video: str | Path,
    output_video: str | Path,
    *,
    hook_text: str = "",
    channel_badge: str = "",
    rank_label: str = "",
    whisper_model: str = "base",
    language: str | None = None,
    config: EditConfig | None = None,
) -> tuple[Path, AudioAnalysis, str, str]:
    """Complete retention-focused editing pipeline for a single raw clip."""
    from clip_finder.captions import generate_wspeed_captions

    cfg = config or EditConfig()
    src = Path(input_video)
    out = Path(output_video)
    info = probe_video(src)

    with tempfile.TemporaryDirectory(prefix="wspeed_") as tmp_dir:
        tmp = Path(tmp_dir)
        initial_analysis = analyze_audio(src)

        if cfg.cut_dead_air:
            paced = jump_cut_dead_air(
                src,
                initial_analysis.segments,
                tmp / "paced.mp4",
                info,
                max_duration=cfg.max_duration,
                use_nvenc=cfg.use_nvenc,
            )
        else:
            paced = src

        paced_info = probe_video(paced)
        final_analysis = analyze_audio(paced)
        framing = detect_framing_plan(paced) if cfg.layout == "auto" else None

        cap_res = generate_wspeed_captions(
            paced,
            tmp / "captions.ass",
            model_size=whisper_model,
            language=language,
            hook_text=hook_text,
            channel_badge=channel_badge,
            rank_label=rank_label,
            video_duration=paced_info.duration,
        )

        render_wspeed_edit(
            paced,
            out,
            final_analysis,
            ass_path=cap_res.ass_path,
            framing=framing,
            config=cfg,
        )

    return out, final_analysis, cap_res.transcript, cap_res.language
