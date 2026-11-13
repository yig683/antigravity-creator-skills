"""CLI orchestrator for Makine Studio 3D blueprint video production."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Support invocation both as `python -m makine_studio.studio.pipeline` and `python -m studio.pipeline`.
_STUDIO_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _STUDIO_DIR.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from studio.compositor import (
    compose_preview_frames,
    compose_video,
    generate_cover_thumbnail,
)
from studio.config import (
    BLENDER_EXE,
    DEFAULT_TTS_PROVIDER,
    DEFAULT_TTS_RATE,
    DEFAULT_TTS_VOICE,
    OUTPUT_DIR,
    PROFILES,
)
from studio.sfx_synth import build_master_audio
from studio.tts_engine import build_narration_timeline


_BLENDER_RUNNER_CODE = '''"""Headless Blender runner launched by studio.pipeline."""
import importlib
import importlib.util
import json
import sys
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
if not argv:
    raise SystemExit("Expected path to blender_job.json after '--'")

job = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
studio_root = str(Path(job["studio_root"]).resolve())
if studio_root not in sys.path:
    sys.path.insert(0, studio_root)

ep_file = job.get("episode_file")
if ep_file:
    spec = importlib.util.spec_from_file_location(f"episodes.{job['episode']}", ep_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load episode file: {ep_file}")
    ep_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ep_mod)
else:
    ep_mod = importlib.import_module(f"episodes.{job['episode']}")
timeline = json.loads(Path(job["timeline_path"]).read_text(encoding="utf-8"))
cfg = job["render_cfg"]

result = ep_mod.build_blender_scene(timeline, cfg)
scene = result["scene"]
camera = result["camera"]
hud = result["hud_tracker"]
hero_frame = int(result.get("hero_frame", max(1, timeline["total_frames"] // 2)))

hud_path = Path(job["hud_tracks_path"])
hud.export(scene, camera, hud_path)

frames_dir = Path(job["frames_dir"])
frames_dir.mkdir(parents=True, exist_ok=True)

preview_frames = sorted(
    {
        *[max(1, min(scene.frame_end, (int(b["frame_start"]) + int(b["frame_end"])) // 2)) for b in timeline["beats"]],
        hero_frame,
    }
)

info_path = Path(job["render_info_path"])
info_path.write_text(
    json.dumps({"hero_frame": hero_frame, "preview_frames": preview_frames}, indent=2),
    encoding="utf-8",
)

scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"

if job["mode"] == "preview":
    for fidx in preview_frames:
        scene.frame_set(fidx)
        scene.render.filepath = str(frames_dir / f"frame_{fidx:04d}.png")
        bpy_ops = __import__("bpy").ops
        bpy_ops.render.render(write_still=True)
else:
    scene.render.filepath = str(frames_dir / "frame_")
    bpy_ops = __import__("bpy").ops
    bpy_ops.render.render(animation=True)
'''


def _resolve_episode_module(episode: str, episode_file: str | None) -> tuple[str, Path | None, Any]:
    """Load an episode either from an explicit Python file path or by module name."""
    if episode_file:
        ep_path = Path(episode_file).resolve()
        if not ep_path.exists():
            raise FileNotFoundError(f"Episode file not found: {ep_path}")
        ep_id = ep_path.stem
        spec = importlib.util.spec_from_file_location(f"episodes.{ep_id}", ep_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to import episode file: {ep_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "EPISODE_ID", ep_id), ep_path, mod

    cwd_cand = Path.cwd() / "episodes" / f"{episode}.py"
    if cwd_cand.exists() and cwd_cand.resolve().parent.parent != _ROOT_DIR.resolve():
        spec = importlib.util.spec_from_file_location(f"episodes.{episode}", cwd_cand.resolve())
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return episode, cwd_cand.resolve(), mod

    return episode, None, importlib.import_module(f"episodes.{episode}")


def _run_blender_job(
    episode: str,
    episode_file: Path | None,
    timeline_path: Path,
    work_dir: Path,
    profile: str,
    profile_cfg: dict[str, Any],
    mode: str,
    samples: int,
) -> dict[str, Any]:
    """Execute Blender headless build + render and return render metadata."""
    if not BLENDER_EXE.exists():
        raise FileNotFoundError(
            f"Blender executable not found at {BLENDER_EXE}. "
            "Install Blender 4.2+/5.x or set MAKINE_BLENDER_EXE."
        )

    frames_dir = work_dir / "frames"
    hud_tracks_path = work_dir / "hud_tracks.json"
    render_info_path = work_dir / "render_info.json"
    runner_script = work_dir / "_blender_runner.py"
    job_path = work_dir / "blender_job.json"

    runner_script.write_text(_BLENDER_RUNNER_CODE, encoding="utf-8")
    job_payload = {
        "studio_root": str(_ROOT_DIR),
        "episode": episode,
        "episode_file": str(episode_file) if episode_file else None,
        "timeline_path": str(timeline_path),
        "hud_tracks_path": str(hud_tracks_path),
        "frames_dir": str(frames_dir),
        "render_info_path": str(render_info_path),
        "mode": mode,
        "render_cfg": {
            "profile": profile,
            "stage_w": int(profile_cfg["stage_w"]),
            "stage_h": int(profile_cfg["stage_h"]),
            "fps": int(profile_cfg["fps"]),
            "samples": int(samples),
        },
    }
    job_path.write_text(json.dumps(job_payload, indent=2), encoding="utf-8")

    cmd = [
        str(BLENDER_EXE),
        "-b",
        "-noaudio",
        "--python",
        str(runner_script),
        "--",
        str(job_path),
    ]
    print(f"[MakineStudio] Launching Blender 5.2 ({mode} mode, {samples} samples)...", flush=True)
    proc = subprocess.run(cmd, check=False, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Blender render failed with exit code {proc.returncode}")

    return json.loads(render_info_path.read_text(encoding="utf-8"))


def _write_episode_metadata(
    ep_mod: Any,
    timeline: dict[str, Any],
    out_dir: Path,
    profile: str,
    video_path: Path | None,
    cover_path: Path | None,
) -> Path:
    """Export YouTube upload metadata, chapters, and specs JSON."""
    meta = dict(getattr(ep_mod, "EPISODE_META", {}))
    meta["episode_id"] = getattr(ep_mod, "EPISODE_ID", "unknown")
    meta["profile"] = profile
    meta["duration_sec"] = timeline["total_duration"]
    meta["fps"] = timeline["fps"]
    meta["total_frames"] = timeline["total_frames"]
    meta["video_file"] = str(video_path) if video_path else None
    meta["cover_file"] = str(cover_path) if cover_path else None
    meta["beats"] = [
        {
            "id": b["id"],
            "start_sec": b["start"],
            "end_sec": b["end"],
            "frames": [b["frame_start"], b["frame_end"]],
            "narration": b["narration"],
        }
        for b in timeline["beats"]
    ]
    meta_path = out_dir / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta_path


def run_pipeline(
    episode: str = "asansor_icat",
    profile: str = "shorts",
    mode: str = "preview",
    voice: str = DEFAULT_TTS_VOICE,
    rate: str = DEFAULT_TTS_RATE,
    tts_provider: str = DEFAULT_TTS_PROVIDER,
    voice_prompt: str | None = None,
    narration_dir: str | None = None,
    episode_file: str | None = None,
    output_dir: str | None = None,
    samples: int | None = None,
    fps: int | None = None,
    skip_tts: bool = False,
    recomposite_only: bool = False,
    upload: bool = False,
    upload_only: bool = False,
    privacy: str = "private",
    publish_at: str | None = None,
    client_secrets: str | None = None,
    upload_thumbnail: bool = False,
    post_comment: bool = False,
) -> dict[str, Any]:
    """Run end-to-end audio synthesis, 3D rendering, compositing, and packaging."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile '{profile}'. Available: {list(PROFILES)}")
    if upload and mode == "preview" and not upload_only:
        raise ValueError(
            "YouTube upload requires '--mode full' (or '--upload-only' on an existing full render)."
        )

    if upload_only:
        ep_id = Path(episode_file).stem if episode_file else episode
        if output_dir:
            base_out = Path(output_dir).resolve()
            candidate = base_out / f"{ep_id}_{profile}"
            out_dir = candidate if candidate.exists() else (
                base_out if (base_out / "metadata.json").exists() else candidate
            )
        else:
            cwd_candidate = Path.cwd() / "output" / f"{ep_id}_{profile}"
            out_dir = cwd_candidate if cwd_candidate.exists() else (OUTPUT_DIR / f"{ep_id}_{profile}")

        print(f"[MakineStudio] Uploading existing render at {out_dir} to YouTube...", flush=True)
        from studio.youtube_uploader import upload_episode_output

        yt_receipt = upload_episode_output(
            out_dir=out_dir,
            privacy=privacy,
            publish_at=publish_at,
            client_secrets_path=Path(client_secrets) if client_secrets else None,
            upload_thumbnail=upload_thumbnail,
            post_comment=post_comment,
        )
        return {
            "mode": "upload-only",
            "out_dir": str(out_dir),
            "youtube": yt_receipt,
        }

    profile_cfg = dict(PROFILES[profile])
    if fps is not None:
        if fps < 12:
            raise ValueError(f"fps must be >= 12, got {fps}")
        profile_cfg["fps"] = int(fps)
    render_samples = int(samples if samples is not None else profile_cfg["eevee_samples"])

    ep_id, ep_file_path, ep_mod = _resolve_episode_module(episode, episode_file)
    ep_meta = getattr(ep_mod, "EPISODE_META", {})
    beats_fn = getattr(ep_mod, "get_beats", None)
    beats = beats_fn(profile) if callable(beats_fn) else getattr(ep_mod, "BEATS")

    base_out = Path(output_dir).resolve() if output_dir else (
        Path.cwd() / "output" if ep_file_path is not None else OUTPUT_DIR
    )
    out_dir = base_out / f"{ep_id}_{profile}"
    work_dir = out_dir / "work"
    frames_dir = work_dir / "frames"
    work_dir.mkdir(parents=True, exist_ok=True)

    timeline_path = work_dir / "timeline.json"
    hud_tracks_path = work_dir / "hud_tracks.json"
    render_info_path = work_dir / "render_info.json"
    master_audio_wav = work_dir / "master_audio.wav"

    # 1 & 2. Narration timeline + master audio mix
    if (skip_tts or recomposite_only) and timeline_path.exists() and master_audio_wav.exists():
        print(f"[MakineStudio] Reusing existing timeline & audio at {work_dir}", flush=True)
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        target_fps = int(profile_cfg["fps"])
        if not recomposite_only and fps is not None and int(timeline.get("fps", target_fps)) != target_fps:
            timeline["fps"] = target_fps
            timeline["total_frames"] = max(2, int(round(float(timeline["total_duration"]) * target_fps)) + 1)
            for idx_b, b in enumerate(timeline.get("beats", [])):
                fs = max(1, int(round(float(b["start"]) * target_fps)) + 1)
                fe = max(fs + 2, int(round(float(b["end"]) * target_fps)))
                if idx_b + 1 == len(timeline["beats"]):
                    fe = timeline["total_frames"]
                b["frame_start"] = fs
                b["frame_end"] = fe
            timeline_path.write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print(f"[MakineStudio] Synthesizing Turkish TTS narration (provider={tts_provider})...", flush=True)
        timeline = build_narration_timeline(
            beats=beats,
            work_dir=work_dir,
            fps=int(profile_cfg["fps"]),
            voice=voice,
            rate=rate,
            provider=tts_provider,
            voice_prompt=Path(voice_prompt) if voice_prompt else None,
            narration_dir=Path(narration_dir) if narration_dir else None,
        )
        print(f"[MakineStudio] Mixing narration + procedural SFX bed...", flush=True)
        master_audio_wav = build_master_audio(timeline, work_dir)

    print(
        f"[MakineStudio] Timeline ready: {timeline['total_duration']:.2f}s "
        f"({timeline['total_frames']} frames @ {timeline['fps']} fps)",
        flush=True,
    )

    # Copy clean subtitles.srt to top-level output dir
    work_srt = work_dir / "subtitles.srt"
    out_srt = out_dir / "subtitles.srt"
    if work_srt.exists():
        shutil.copyfile(work_srt, out_srt)

    # 3. Blender 3D render
    if recomposite_only and render_info_path.exists():
        render_info = json.loads(render_info_path.read_text(encoding="utf-8"))
    else:
        render_info = _run_blender_job(
            episode=ep_id,
            episode_file=ep_file_path,
            timeline_path=timeline_path,
            work_dir=work_dir,
            profile=profile,
            profile_cfg=profile_cfg,
            mode=mode,
            samples=render_samples,
        )

    hero_frame = int(render_info["hero_frame"])
    preview_frames = [int(f) for f in render_info["preview_frames"]]
    header_tag = str(ep_meta.get("header_tag", ""))
    cover_lines = ep_meta.get("cover_lines", [("NASIL İCAT", "white"), ("EDERSİN?", "cyan")])

    # 4. Compositing & packaging
    hero_png = frames_dir / f"frame_{hero_frame:04d}.png"
    if mode == "preview":
        preview_dir = out_dir / "preview"
        previews = compose_preview_frames(
            frames_dir=frames_dir,
            timeline=timeline,
            hud_tracks_path=hud_tracks_path,
            out_dir=preview_dir,
            frame_indices=preview_frames,
            profile=profile,
            header_tag=header_tag,
        )
        cover_path = generate_cover_thumbnail(
            blender_hero_path=hero_png,
            out_path=preview_dir / f"cover_preview_{profile}.png",
            title_lines=cover_lines,
            profile=profile,
            header_tag=header_tag,
        )
        meta_path = _write_episode_metadata(ep_mod, timeline, out_dir, profile, None, cover_path)
        print(f"[MakineStudio] Preview complete -> {preview_dir}", flush=True)
        return {
            "mode": "preview",
            "out_dir": str(out_dir),
            "timeline_sec": timeline["total_duration"],
            "total_frames": timeline["total_frames"],
            "previews": [str(p) for p in previews],
            "cover": str(cover_path),
            "metadata": str(meta_path),
            "subtitles": str(out_srt),
        }

    out_mp4 = out_dir / f"{ep_id}_{profile}.mp4"
    print(f"[MakineStudio] Compositing {timeline['total_frames']} frames -> {out_mp4}...", flush=True)
    compose_video(
        frames_dir=frames_dir,
        timeline=timeline,
        hud_tracks_path=hud_tracks_path,
        master_audio_wav=master_audio_wav,
        out_mp4=out_mp4,
        profile=profile,
        header_tag=header_tag,
    )
    cover_path = generate_cover_thumbnail(
        blender_hero_path=hero_png,
        out_path=out_dir / f"cover_{profile}.png",
        title_lines=cover_lines,
        profile=profile,
        header_tag=header_tag,
    )
    meta_path = _write_episode_metadata(ep_mod, timeline, out_dir, profile, out_mp4, cover_path)
    print(f"[MakineStudio] Full production complete -> {out_mp4}", flush=True)
    result: dict[str, Any] = {
        "mode": "full",
        "out_dir": str(out_dir),
        "timeline_sec": timeline["total_duration"],
        "total_frames": timeline["total_frames"],
        "video": str(out_mp4),
        "cover": str(cover_path),
        "subtitles": str(out_srt),
        "metadata": str(meta_path),
    }
    if upload:
        print(f"[MakineStudio] Uploading {out_mp4.name} to YouTube...", flush=True)
        from studio.youtube_uploader import upload_episode_output

        result["youtube"] = upload_episode_output(
            out_dir=out_dir,
            privacy=privacy,
            publish_at=publish_at,
            client_secrets_path=Path(client_secrets) if client_secrets else None,
            upload_thumbnail=upload_thumbnail,
            post_comment=post_comment,
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Makine Studio 3D Blueprint Video Pipeline")
    parser.add_argument("--episode", default="asansor_icat", help="Module name under episodes/")
    parser.add_argument("--episode-file", default=None, help="Explicit path to a workspace episode .py file")
    parser.add_argument("--output-dir", default=None, help="Root directory for generated episode outputs")
    parser.add_argument("--profile", default="shorts", choices=list(PROFILES.keys()))
    parser.add_argument("--mode", default="preview", choices=["preview", "full"])
    parser.add_argument(
        "--tts-provider",
        default=DEFAULT_TTS_PROVIDER,
        choices=["auto", "chatterbox", "edge", "external"],
        help="Turkish narration backend (auto uses GPU Chatterbox if installed, else Edge-TTS)",
    )
    parser.add_argument("--voice-prompt", default=None, help="Optional reference WAV for Chatterbox voice cloning")
    parser.add_argument("--narration-dir", default=None, help="Directory of beat_00..beat_NN WAVs for external mode")
    parser.add_argument("--voice", default=DEFAULT_TTS_VOICE)
    parser.add_argument("--rate", default=DEFAULT_TTS_RATE)
    parser.add_argument("--samples", type=int, default=None, help="Override Blender EEVEE samples")
    parser.add_argument("--fps", type=int, default=None, help="Override profile frame rate (e.g. 24, 30, 60)")
    parser.add_argument("--skip-tts", action="store_true", help="Reuse cached timeline & master audio")
    parser.add_argument("--recomposite-only", action="store_true", help="Re-composite existing Blender frames")
    parser.add_argument("--upload", action="store_true", help="Upload rendered video to YouTube after --mode full")
    parser.add_argument("--upload-only", action="store_true", help="Upload an existing output directory without rendering")
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private", help="YouTube privacy status")
    parser.add_argument("--publish-at", default=None, help="ISO-8601 UTC publish timestamp (forces privacy=private)")
    parser.add_argument("--client-secrets", default=None, help="Path to Google OAuth client_secret.json")
    parser.add_argument("--upload-thumbnail", action="store_true", help="Upload cover PNG as custom thumbnail")
    parser.add_argument("--post-comment", action="store_true", help="Post metadata pinned_comment as first comment")
    args = parser.parse_args()

    result = run_pipeline(
        episode=args.episode,
        profile=args.profile,
        mode=args.mode,
        voice=args.voice,
        rate=args.rate,
        tts_provider=args.tts_provider,
        voice_prompt=args.voice_prompt,
        narration_dir=args.narration_dir,
        episode_file=args.episode_file,
        output_dir=args.output_dir,
        samples=args.samples,
        fps=args.fps,
        skip_tts=args.skip_tts,
        recomposite_only=args.recomposite_only,
        upload=args.upload,
        upload_only=args.upload_only,
        privacy=args.privacy,
        publish_at=args.publish_at,
        client_secrets=args.client_secrets,
        upload_thumbnail=args.upload_thumbnail,
        post_comment=args.post_comment,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
