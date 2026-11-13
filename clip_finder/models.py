from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass
class Clip:
    """Normalized representation of a popular clip across streaming platforms."""

    platform: str
    clip_id: str
    title: str
    views: int
    duration_seconds: float
    url: str
    thumbnail_url: str
    channel_name: str
    channel_url: str
    category: str
    created_at: str
    language: str = ""
    creator_name: str = ""
    media_url: str = ""
    virality_score: float = 0.0

    def compute_virality_score(self, now: datetime | None = None) -> float:
        """Compute views per hour since creation to surface fast-rising clips."""
        if now is None:
            now = datetime.now(timezone.utc)
        try:
            iso = self.created_at.replace("Z", "+00:00")
            created = datetime.fromisoformat(iso)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            hours_alive = max((now - created).total_seconds() / 3600.0, 0.25)
            self.virality_score = round(self.views / hours_alive, 2)
        except ValueError:
            self.virality_score = float(self.views)
        return self.virality_score

    def to_dict(self) -> dict:
        return asdict(self)
