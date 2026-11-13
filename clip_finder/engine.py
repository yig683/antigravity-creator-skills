from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from clip_finder.models import Clip
from clip_finder.providers import BaseClipProvider, KickProvider, Period, TwitchProvider

SortBy = Literal["views", "virality", "recent"]


@dataclass
class SearchResult:
    """Aggregated clip search result with per-platform error tracking."""

    clips: list[Clip] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


class ClipFinderEngine:
    """Queries multiple streaming providers in parallel, filters, ranks, and exports clips."""

    def __init__(self, providers: dict[str, BaseClipProvider] | None = None) -> None:
        self.providers: dict[str, BaseClipProvider] = providers or {
            "twitch": TwitchProvider(),
            "kick": KickProvider(),
        }

    def search(
        self,
        category: str = "Grand Theft Auto VI",
        platforms: list[str] | None = None,
        period: Period = "week",
        limit_per_platform: int = 25,
        min_views: int = 0,
        min_duration: float = 0.0,
        max_duration: float | None = None,
        language: str | None = None,
        keywords: list[str] | None = None,
        sort_by: SortBy = "views",
        total_limit: int | None = None,
    ) -> SearchResult:
        selected = [p.lower() for p in (platforms or list(self.providers.keys()))]
        active = {name: self.providers[name] for name in selected if name in self.providers}
        categories = [c.strip() for c in category.split(",") if c.strip()] or [category]

        all_clips: list[Clip] = []
        errors: dict[str, str] = {}

        if not active:
            return SearchResult(clips=[], errors={"engine": "No valid platforms selected."})

        with ThreadPoolExecutor(max_workers=max(len(active) * len(categories), 1)) as pool:
            futures = {
                pool.submit(
                    provider.fetch_popular_clips,
                    category=cat,
                    period=period,
                    limit=limit_per_platform,
                    language=language,
                ): f"{name}:{cat}"
                for name, provider in active.items()
                for cat in categories
            }
            for future in as_completed(futures):
                key_name = futures[future]
                try:
                    all_clips.extend(future.result())
                except Exception as exc:  # noqa: BLE001 - isolate provider failures
                    errors[key_name] = str(exc)

        filtered = self._filter_clips(
            all_clips,
            min_views=min_views,
            min_duration=min_duration,
            max_duration=max_duration,
            keywords=keywords,
        )
        ranked = self._sort_clips(filtered, sort_by=sort_by)
        if total_limit is not None and total_limit > 0:
            ranked = ranked[:total_limit]

        return SearchResult(clips=ranked, errors=errors)

    @staticmethod
    def _filter_clips(
        clips: list[Clip],
        min_views: int,
        min_duration: float,
        max_duration: float | None,
        keywords: list[str] | None = None,
    ) -> list[Clip]:
        seen: set[tuple[str, str]] = set()
        kw_lower = [k.strip().lower() for k in (keywords or []) if k.strip()]
        result: list[Clip] = []
        for clip in clips:
            key = (clip.platform, clip.clip_id)
            if key in seen:
                continue
            seen.add(key)
            if clip.views < min_views:
                continue
            if clip.duration_seconds < min_duration:
                continue
            if max_duration is not None and clip.duration_seconds > max_duration:
                continue
            if kw_lower:
                haystack = f"{clip.title} {clip.channel_name}".lower()
                if not any(kw in haystack for kw in kw_lower):
                    continue
            result.append(clip)
        return result

    @staticmethod
    def _sort_clips(clips: list[Clip], sort_by: SortBy) -> list[Clip]:
        if sort_by == "virality":
            return sorted(clips, key=lambda c: (c.virality_score, c.views), reverse=True)
        if sort_by == "recent":
            return sorted(clips, key=lambda c: c.created_at, reverse=True)
        return sorted(clips, key=lambda c: (c.views, c.virality_score), reverse=True)

    @staticmethod
    def export_json(clips: list[Clip], path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "count": len(clips),
            "clips": [c.to_dict() for c in clips],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    @staticmethod
    def export_csv(clips: list[Clip], path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "platform",
            "clip_id",
            "title",
            "views",
            "virality_score",
            "duration_seconds",
            "channel_name",
            "language",
            "created_at",
            "url",
            "media_url",
            "thumbnail_url",
            "category",
            "creator_name",
        ]
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for clip in clips:
                writer.writerow(clip.to_dict())
        return out
