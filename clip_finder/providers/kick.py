from __future__ import annotations

import re

import requests

from clip_finder.models import Clip
from clip_finder.providers.base import BaseClipProvider, Period

_KICK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_KICK_PERIOD_MAP: dict[Period, str] = {
    "day": "day",
    "week": "week",
    "month": "month",
    "all": "all",
}


def _slugify_category(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug


class KickProvider(BaseClipProvider):
    """Fetches popular clips from Kick's category clips API."""

    name = "kick"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def fetch_popular_clips(
        self,
        category: str,
        period: Period = "week",
        limit: int = 20,
        language: str | None = None,
    ) -> list[Clip]:
        slug = _slugify_category(category)
        kick_period = _KICK_PERIOD_MAP.get(period, "week")
        base_url = f"https://kick.com/api/v2/categories/{slug}/clips"

        results: list[Clip] = []
        cursor: str | None = None
        seen_ids: set[str] = set()

        while len(results) < limit:
            params: dict[str, str] = {
                "sort": "view",
                "time": kick_period,
            }
            if cursor:
                params["cursor"] = cursor

            resp = requests.get(
                base_url,
                params=params,
                headers=_KICK_HEADERS,
                timeout=self.timeout,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()

            payload = resp.json()
            clips_data = payload.get("clips") or []
            if not clips_data:
                break

            for item in clips_data:
                clip_id = str(item.get("id") or "")
                if not clip_id or clip_id in seen_ids:
                    continue
                seen_ids.add(clip_id)

                channel = item.get("channel") or {}
                channel_slug = channel.get("slug") or ""
                channel_name = channel.get("username") or channel_slug
                creator = item.get("creator") or {}
                cat = item.get("category") or {}

                web_url = (
                    f"https://kick.com/{channel_slug}/clips/{clip_id}"
                    if channel_slug
                    else f"https://kick.com/clips/{clip_id}"
                )

                clip = Clip(
                    platform="kick",
                    clip_id=clip_id,
                    title=item.get("title") or "",
                    views=int(item.get("views") or 0),
                    duration_seconds=float(item.get("duration") or 0),
                    url=web_url,
                    thumbnail_url=item.get("thumbnail_url") or "",
                    channel_name=channel_name,
                    channel_url=f"https://kick.com/{channel_slug}" if channel_slug else "",
                    category=cat.get("name") or category,
                    created_at=item.get("created_at") or "",
                    language="",
                    creator_name=creator.get("username") or "",
                    media_url=item.get("clip_url") or "",
                )
                clip.compute_virality_score()
                results.append(clip)
                if len(results) >= limit:
                    break

            next_cursor = payload.get("nextCursor")
            if not next_cursor:
                break
            cursor = str(next_cursor)

        return results[:limit]
