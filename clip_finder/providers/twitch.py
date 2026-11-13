from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

from clip_finder.models import Clip
from clip_finder.providers.base import BaseClipProvider, Period

_TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
_TWITCH_PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
_TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_TWITCH_HELIX_URL = "https://api.twitch.tv/helix"

_GQL_PERIOD_MAP: dict[Period, str] = {
    "day": "LAST_DAY",
    "week": "LAST_WEEK",
    "month": "LAST_MONTH",
    "all": "ALL_TIME",
}

_HELIX_PERIOD_DAYS: dict[Period, int | None] = {
    "day": 1,
    "week": 7,
    "month": 30,
    "all": None,
}


class TwitchProvider(BaseClipProvider):
    """Fetches popular clips from Twitch via Helix API (if configured) or GQL."""

    name = "twitch"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: int = 15,
    ) -> None:
        self.client_id = client_id or os.getenv("TWITCH_CLIENT_ID", "").strip()
        self.client_secret = client_secret or os.getenv("TWITCH_CLIENT_SECRET", "").strip()
        self.timeout = timeout
        self._app_token: str | None = None

    def fetch_popular_clips(
        self,
        category: str,
        period: Period = "week",
        limit: int = 20,
        language: str | None = None,
    ) -> list[Clip]:
        if self.client_id and self.client_secret:
            return self._fetch_via_helix(category, period, limit, language)
        return self._fetch_via_gql(category, period, limit, language)

    def _get_helix_token(self) -> str:
        if self._app_token:
            return self._app_token
        resp = requests.post(
            _TWITCH_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        self._app_token = resp.json()["access_token"]
        return self._app_token

    def _fetch_via_helix(
        self,
        category: str,
        period: Period,
        limit: int,
        language: str | None,
    ) -> list[Clip]:
        token = self._get_helix_token()
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
        }

        game_resp = requests.get(
            f"{_TWITCH_HELIX_URL}/games",
            params={"name": category},
            headers=headers,
            timeout=self.timeout,
        )
        game_resp.raise_for_status()
        games = game_resp.json().get("data", [])
        if not games:
            return []
        game_id = games[0]["id"]
        game_name = games[0]["name"]

        params: dict[str, str | int] = {
            "game_id": game_id,
            "first": min(max(limit, 1), 100),
        }
        days = _HELIX_PERIOD_DAYS.get(period)
        if days is not None:
            now = datetime.now(timezone.utc)
            params["started_at"] = (now - timedelta(days=days)).isoformat()
            params["ended_at"] = now.isoformat()

        clips_resp = requests.get(
            f"{_TWITCH_HELIX_URL}/clips",
            params=params,
            headers=headers,
            timeout=self.timeout,
        )
        clips_resp.raise_for_status()

        results: list[Clip] = []
        for item in clips_resp.json().get("data", []):
            clip_lang = (item.get("language") or "").lower()
            if language and clip_lang != language.lower():
                continue
            broadcaster_name = item.get("broadcaster_name") or ""
            clip = Clip(
                platform="twitch",
                clip_id=item["id"],
                title=item.get("title") or "",
                views=int(item.get("view_count") or 0),
                duration_seconds=float(item.get("duration") or 0),
                url=item.get("url") or "",
                thumbnail_url=item.get("thumbnail_url") or "",
                channel_name=broadcaster_name,
                channel_url=f"https://www.twitch.tv/{broadcaster_name.lower()}" if broadcaster_name else "",
                category=game_name,
                created_at=item.get("created_at") or "",
                language=clip_lang,
                creator_name=item.get("creator_name") or "",
            )
            clip.compute_virality_score()
            results.append(clip)

        return results[:limit]

    def _fetch_via_gql(
        self,
        category: str,
        period: Period,
        limit: int,
        language: str | None,
    ) -> list[Clip]:
        gql_period = _GQL_PERIOD_MAP.get(period, "LAST_WEEK")
        # Fetch a slightly larger batch when language filtering is active.
        fetch_count = min(max(limit * 3 if language else limit, 1), 100)

        query = """
        query($gameName: String!, $first: Int!, $period: ClipsPeriod!) {
          game(name: $gameName) {
            id
            name
            clips(first: $first, criteria: { period: $period }) {
              edges {
                node {
                  id
                  slug
                  title
                  viewCount
                  durationSeconds
                  url
                  thumbnailURL
                  language
                  createdAt
                  broadcaster {
                    login
                    displayName
                  }
                  curator {
                    displayName
                  }
                }
              }
            }
          }
        }
        """

        resp = requests.post(
            _TWITCH_GQL_URL,
            json={
                "query": query,
                "variables": {
                    "gameName": category,
                    "first": fetch_count,
                    "period": gql_period,
                },
            },
            headers={"Client-ID": _TWITCH_PUBLIC_CLIENT_ID},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        game = (payload.get("data") or {}).get("game")
        if not game:
            return []

        game_name = game.get("name") or category
        edges = (game.get("clips") or {}).get("edges") or []

        results: list[Clip] = []
        for edge in edges:
            node = edge.get("node") or {}
            clip_lang = (node.get("language") or "").lower()
            if language and clip_lang != language.lower():
                continue

            broadcaster = node.get("broadcaster") or {}
            login = broadcaster.get("login") or ""
            display_name = broadcaster.get("displayName") or login
            curator = node.get("curator") or {}

            clip = Clip(
                platform="twitch",
                clip_id=node.get("slug") or node.get("id") or "",
                title=node.get("title") or "",
                views=int(node.get("viewCount") or 0),
                duration_seconds=float(node.get("durationSeconds") or 0),
                url=node.get("url") or "",
                thumbnail_url=node.get("thumbnailURL") or "",
                channel_name=display_name,
                channel_url=f"https://www.twitch.tv/{login}" if login else "",
                category=game_name,
                created_at=node.get("createdAt") or "",
                language=clip_lang,
                creator_name=curator.get("displayName") or "",
            )
            clip.compute_virality_score()
            results.append(clip)
            if len(results) >= limit:
                break

        return results
