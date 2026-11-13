from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ClipHistory:
    """Persistent JSON tracker preventing duplicate downloads or edits of the same clip."""

    def __init__(self, db_path: str | Path = "data/history.json") -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.db_path.exists():
            return {}
        try:
            raw = json.loads(self.db_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _save(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.db_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.db_path)

    @staticmethod
    def make_key(platform: str, clip_id: str) -> str:
        return f"{platform.lower()}:{clip_id}"

    def is_processed(self, platform: str, clip_id: str) -> bool:
        with self._lock:
            entry = self._data.get(self.make_key(platform, clip_id))
            if not entry:
                return False
            output_file = entry.get("output_path")
            return bool(entry.get("status") == "done" and output_file and Path(output_file).exists())

    def get(self, platform: str, clip_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._data.get(self.make_key(platform, clip_id))

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._data.values())
        return sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)

    def mark(
        self,
        platform: str,
        clip_id: str,
        status: str,
        *,
        title: str = "",
        channel_name: str = "",
        url: str = "",
        raw_path: str = "",
        output_path: str = "",
        metadata_path: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        key = self.make_key(platform, clip_id)
        with self._lock:
            prev = self._data.get(key, {})
            entry = {
                **prev,
                "key": key,
                "platform": platform.lower(),
                "clip_id": clip_id,
                "status": status,
                "title": title or prev.get("title", ""),
                "channel_name": channel_name or prev.get("channel_name", ""),
                "url": url or prev.get("url", ""),
                "raw_path": raw_path or prev.get("raw_path", ""),
                "output_path": output_path or prev.get("output_path", ""),
                "metadata_path": metadata_path or prev.get("metadata_path", ""),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if extra:
                entry.update(extra)
            self._data[key] = entry
            self._save()
