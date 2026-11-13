from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

from clip_finder.downloader import ClipDownloader
from clip_finder.editor import EditConfig, auto_edit_wspeed
from clip_finder.engine import ClipFinderEngine, SortBy
from clip_finder.history import ClipHistory
from clip_finder.metadata import ViralMetadata, generate_viral_metadata, save_metadata_bundle
from clip_finder.models import Clip
from clip_finder.providers.base import Period


@dataclass
class FarmedClipResult:
    clip: Clip
    raw_path: Path
    output_path: Path
    metadata_path: Path
    metadata: ViralMetadata
    hype_peaks: list[float]


def _safe_slug(text: str, max_len: int = 36) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (text or "").strip())
    return (cleaned.strip("_") or "clip")[:max_len]


def _pick_music_track(explicit_music: str | Path | None, music_dir: str | Path = "assets/music") -> Path | None:
    if explicit_music:
        p = Path(explicit_music)
        return p if p.exists() else None
    mdir = Path(music_dir)
    if not mdir.exists():
        return None
    tracks = [
        p
        for p in mdir.iterdir()
        if p.is_file() and p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    ]
    return random.choice(tracks) if tracks else None


class ClipFarmerPipeline:
    """End-to-end pipeline: discover -> deduplicate -> download -> W-Speed edit -> metadata."""

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

    def process_clip(
        self,
        clip: Clip,
        *,
        whisper_model: str = "base",
        language: str | None = None,
        edit_config: EditConfig | None = None,
        hook_text: str = "",
        show_badge: bool = False,
        force: bool = False,
    ) -> FarmedClipResult:
        existing = self.history.get(clip.platform, clip.clip_id)
        if not force and existing and existing.get("status") == "done":
            out_p = Path(existing.get("output_path", ""))
            meta_p = Path(existing.get("metadata_path", ""))
            raw_p = Path(existing.get("raw_path", ""))
            if out_p.exists() and meta_p.exists():
                import json

                meta_dict = json.loads(meta_p.read_text(encoding="utf-8"))
                meta = ViralMetadata(**meta_dict)
                return FarmedClipResult(
                    clip=clip,
                    raw_path=raw_p,
                    output_path=out_p,
                    metadata_path=meta_p,
                    metadata=meta,
                    hype_peaks=existing.get("hype_peaks", []),
                )

        self.history.mark(
            clip.platform,
            clip.clip_id,
            "downloading",
            title=clip.title,
            channel_name=clip.channel_name,
            url=clip.url,
        )

        raw_path = self.downloader.download(clip, overwrite=force)

        cfg = edit_config or EditConfig()
        if cfg.music_path is None:
            cfg.music_path = _pick_music_track(None)

        out_name = f"{clip.platform}_{_safe_slug(clip.channel_name, 20)}_{_safe_slug(clip.clip_id, 30)}_wspeed.mp4"
        out_path = self.output_dir / out_name

        badge = f"@{clip.channel_name}" if (show_badge and clip.channel_name) else ""

        self.history.mark(
            clip.platform,
            clip.clip_id,
            "editing",
            raw_path=str(raw_path.resolve()),
        )

        rendered_path, analysis, transcript, detected_lang = auto_edit_wspeed(
            raw_path,
            out_path,
            hook_text=hook_text,
            channel_badge=badge,
            whisper_model=whisper_model,
            language=language or (clip.language if clip.language else None),
            config=cfg,
        )

        final_meta = generate_viral_metadata(
            clip,
            transcript=transcript,
            detected_language=detected_lang or clip.language,
        )
        meta_path = save_metadata_bundle(final_meta, rendered_path)

        self.history.mark(
            clip.platform,
            clip.clip_id,
            "done",
            title=clip.title,
            channel_name=clip.channel_name,
            url=clip.url,
            raw_path=str(raw_path.resolve()),
            output_path=str(rendered_path.resolve()),
            metadata_path=str(meta_path.resolve()),
            extra={"hype_peaks": analysis.hype_peaks},
        )

        return FarmedClipResult(
            clip=clip,
            raw_path=raw_path,
            output_path=rendered_path,
            metadata_path=meta_path,
            metadata=final_meta,
            hype_peaks=analysis.hype_peaks,
        )

    def farm_top_clips(
        self,
        *,
        category: str = "Grand Theft Auto VI",
        platforms: list[str] | None = None,
        period: Period = "week",
        sort_by: SortBy = "views",
        count: int = 3,
        min_views: int = 0,
        max_duration: float | None = 90.0,
        language: str | None = None,
        keywords: list[str] | None = None,
        whisper_model: str = "base",
        edit_config: EditConfig | None = None,
        hook_text: str = "",
        show_badge: bool = False,
        force: bool = False,
    ) -> tuple[list[FarmedClipResult], dict[str, str]]:
        search_res = self.engine.search(
            category=category,
            platforms=platforms,
            period=period,
            limit_per_platform=max(count * 4, 20),
            min_views=min_views,
            max_duration=max_duration,
            language=language,
            keywords=keywords,
            sort_by=sort_by,
        )

        errors = dict(search_res.errors)
        results: list[FarmedClipResult] = []
        attempts = 0
        max_attempts = max(count * 3, 6)

        for clip in search_res.clips:
            if len(results) >= count or attempts >= max_attempts:
                break
            if not force and self.history.is_processed(clip.platform, clip.clip_id):
                continue
            attempts += 1
            try:
                res = self.process_clip(
                    clip,
                    whisper_model=whisper_model,
                    language=language,
                    edit_config=edit_config,
                    hook_text=hook_text,
                    show_badge=show_badge,
                    force=force,
                )
                results.append(res)
            except Exception as exc:  # noqa: BLE001
                errors[f"{clip.platform}:{clip.clip_id}"] = str(exc)
                self.history.mark(
                    clip.platform,
                    clip.clip_id,
                    "error",
                    title=clip.title,
                    channel_name=clip.channel_name,
                    url=clip.url,
                    extra={"error": str(exc)},
                )

        return results, errors
