from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from clip_finder.models import Clip

Period = Literal["day", "week", "month", "all"]


class BaseClipProvider(ABC):
    """Abstract base class for streaming platform clip providers."""

    name: str = "base"

    @abstractmethod
    def fetch_popular_clips(
        self,
        category: str,
        period: Period = "week",
        limit: int = 20,
        language: str | None = None,
    ) -> list[Clip]:
        """Fetch popular clips for a given game/category and time period."""
        raise NotImplementedError
