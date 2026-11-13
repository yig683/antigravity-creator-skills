from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from clip_finder.models import Clip


@dataclass
class ViralMetadata:
    viral_title: str
    hook_banner: str
    description: str
    hashtags: list[str]
    youtube_shorts_title: str
    tiktok_caption: str
    instagram_caption: str
    source_url: str
    streamer: str
    transcript: str

    def to_dict(self) -> dict:
        return asdict(self)


def _category_hashtags(category: str) -> list[str]:
    low = category.lower()
    if "vi" in low or "gta 6" in low or "gta6" in low:
        return ["#gta6", "#gtavi"]
    if "gta" in low or "grand theft auto" in low:
        return ["#gtav", "#gtarp"]
    slug = re.sub(r"[^a-z0-9]+", "", low)
    return [f"#{slug}"] if slug else ["#gaming"]


def generate_viral_metadata(
    clip: Clip,
    transcript: str = "",
    detected_language: str = "",
) -> ViralMetadata:
    """Create clean, natural titles and concise hashtags without AI spam."""
    lang = detected_language or clip.language or "en"
    is_tr = lang.lower().startswith("tr")
    streamer = clip.channel_name or "Streamer"
    clean_title = re.sub(r"\s+", " ", (clip.title or "").strip())

    if clean_title and len(clean_title) >= 3:
        viral_title = f"{streamer}: {clean_title}"
    else:
        viral_title = f"{streamer} - {clip.category}"

    cat_tags = _category_hashtags(clip.category)
    streamer_tag = "#" + re.sub(r"[^a-zA-Z0-9]+", "", streamer.lower())
    base_tags = ["#shorts", "#clips", f"#{clip.platform.lower()}"]
    if is_tr:
        base_tags.append("#kesfet")

    hashtags: list[str] = []
    for tag in cat_tags + ([streamer_tag] if len(streamer_tag) > 2 else []) + base_tags:
        if tag not in hashtags:
            hashtags.append(tag)
    hashtags = hashtags[:6]

    tag_str = " ".join(hashtags)
    yt_title = f"{viral_title} #shorts"[:99]
    tiktok_cap = f"{viral_title}\n{tag_str}"
    ig_cap = f"{viral_title}\n\n{tag_str}"
    description = (
        f"{viral_title}\n"
        f"Kaynak: {clip.url}\n\n"
        f"{tag_str}"
    )

    return ViralMetadata(
        viral_title=viral_title,
        hook_banner="",
        description=description,
        hashtags=hashtags,
        youtube_shorts_title=yt_title,
        tiktok_caption=tiktok_cap,
        instagram_caption=ig_cap,
        source_url=clip.url,
        streamer=streamer,
        transcript=transcript,
    )


def save_metadata_bundle(meta: ViralMetadata, base_output_path: Path) -> Path:
    """Save JSON and human-readable TXT social copy alongside the rendered MP4."""
    json_path = base_output_path.with_suffix(".json")
    txt_path = base_output_path.with_suffix(".txt")

    json_path.write_text(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    txt_content = (
        f"=== YOUTUBE SHORTS TITLE ===\n{meta.youtube_shorts_title}\n\n"
        f"=== TIKTOK CAPTION ===\n{meta.tiktok_caption}\n\n"
        f"=== INSTAGRAM REELS CAPTION ===\n{meta.instagram_caption}\n\n"
        f"=== TRANSKRİPT ===\n{meta.transcript or '(Konuşma algılanmadı)'}\n"
    )
    txt_path.write_text(txt_content, encoding="utf-8")
    return json_path
