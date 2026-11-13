from __future__ import annotations

import re
import subprocess
from pathlib import Path

from clip_finder.models import Clip


def _safe_filename(text: str, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip())
    cleaned = cleaned.strip("_") or "clip"
    return cleaned[:max_len]


class ClipDownloader:
    """Downloads clips from Twitch and Kick to MP4 using yt-dlp."""

    def __init__(self, download_dir: str | Path = "downloads/raw") -> None:
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def build_target_path(self, clip: Clip) -> Path:
        safe_chan = _safe_filename(clip.channel_name or "streamer", 24)
        safe_id = _safe_filename(clip.clip_id, 40)
        return self.download_dir / f"{clip.platform}_{safe_chan}_{safe_id}.mp4"

    def download(self, clip: Clip, overwrite: bool = False) -> Path:
        target = self.build_target_path(clip)
        if target.exists() and target.stat().st_size > 0 and not overwrite:
            return target

        # Prefer direct media_url for Kick HLS playlists if web URL is protected, otherwise clip.url
        candidate_urls = [clip.url]
        if clip.media_url and clip.media_url not in candidate_urls:
            if clip.platform == "kick":
                candidate_urls = [clip.media_url, clip.url]
            else:
                candidate_urls.append(clip.media_url)

        last_err = ""
        for src_url in candidate_urls:
            if not src_url:
                continue
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--merge-output-format",
                "mp4",
                "-f",
                "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
                "-o",
                str(target),
                src_url,
            ]
            if overwrite:
                cmd.insert(1, "--force-overwrites")

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if proc.returncode == 0 and target.exists() and target.stat().st_size > 0:
                return target
            last_err = (proc.stderr or proc.stdout or f"yt-dlp exited with {proc.returncode}").strip()

        raise RuntimeError(f"Klip indirilemedi ({clip.url}): {last_err}")
