from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_READY_DIR = Path("output") / "ready"
QUEUE_FILENAME = "upload_queue.json"

_CREATOR_DISPLAY_ALIASES: dict[str, str] = {
    "kaicenat": "Kai Cenat",
    "ishowspeed": "IShowSpeed",
    "typicalgamer": "Typical Gamer",
    "hasanabi": "HasanAbi",
    "xqc": "xQc",
    "jynxzi": "Jynxzi",
    "moistcr1tikal": "MoistCr1TiKaL",
    "timthetatman": "TimTheTatman",
    "missmikkaa": "MissMikkaa",
    "zackrawrr": "Asmongold",
    "skillz0r1337": "SKILLZ0R",
}


def fit_tags_budget(tags: list[str], max_chars: int = 450) -> list[str]:
    """Fit YouTube tags within the 500-character combined metadata budget."""
    selected: list[str] = []
    seen_lower: set[str] = set()
    used = 0
    for raw in tags:
        clean = re.sub(r"[<>]", "", str(raw)).strip()
        if not clean or clean.lower() in seen_lower:
            continue
        cost = len(clean) + (2 if " " in clean else 0) + (1 if selected else 0)
        if used + cost > max_chars:
            continue
        selected.append(clean)
        seen_lower.add(clean.lower())
        used += cost
    return selected


def _parse_streamers(meta: dict[str, Any]) -> list[str]:
    """Return ordered list of creator handles (#N -> #1) from metadata."""
    raw = str(meta.get("streamer") or "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if parts:
        return parts
    found: list[str] = []
    for credit in meta.get("credits", []):
        m = re.match(r"^#\d+\s+([^\s(]+)", str(credit).strip())
        if m:
            found.append(m.group(1))
    return found


def _display_creator(handle: str) -> str:
    low = handle.strip().lstrip("@").lower()
    return _CREATOR_DISPLAY_ALIASES.get(low, handle.strip())


def _infer_clip_count(meta: dict[str, Any], default: int = 11) -> int:
    credits = meta.get("credits")
    if isinstance(credits, list) and credits:
        return len(credits)
    streamers = _parse_streamers(meta)
    return len(streamers) if streamers else default


def _split_description_sections(description: str) -> tuple[str, str]:
    """Extract Chapters..Credits core body from an existing compilation description."""
    lines = description.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith(("Chapters:", "Bölümler:")):
            core_lines = lines[idx:]
            # Strip trailing standalone hashtag line so upgraded hashtags can replace it cleanly
            while core_lines and (
                not core_lines[-1].strip() or all(tok.startswith("#") for tok in core_lines[-1].split())
            ):
                core_lines.pop()
            return "\n".join(core_lines).strip(), ""
    return "", description.strip()


def build_unique_title(
    meta: dict[str, Any],
    existing_titles: set[str] | None = None,
    category: str = "Grand Theft Auto VI",
) -> str:
    """Create a distinct high-CTR YouTube Shorts title (<= 100 chars) avoiding duplicates."""
    used_lower = {t.strip().lower() for t in (existing_titles or set()) if t.strip()}
    streamers = _parse_streamers(meta)
    n_clips = _infer_clip_count(meta)

    top1 = _display_creator(streamers[-1]) if streamers else "Streamers"
    top2 = _display_creator(streamers[-2]) if len(streamers) >= 2 else "xQc"
    top3 = _display_creator(streamers[-3]) if len(streamers) >= 3 else "Rubius"
    cat_short = "GTA 6" if ("vi" in category.lower() or "gta 6" in category.lower() or "gta6" in category.lower()) else category

    transcript = str(meta.get("transcript") or "").lower()
    if "goosebumps" in transcript or "if you're on stream" in transcript:
        # Highlight features dual-sub international + KaiCenat / IShowSpeed police chase hook
        candidates = [
            f"{top1}, {top2} & More Lose It Over {cat_short} (#1 Wild) #shorts",
            f"Insane {cat_short} Streamer Reactions (#1 {top1} & {top2}) #shorts",
            f"Top {n_clips} {cat_short} Moments That Broke the Internet (#1 {top1}) #shorts",
            f"{top1} & {top2} React to Unreal {cat_short} Gameplay! #shorts",
        ]
    else:
        candidates = [
            f"Streamers Went Crazy Reacting to {cat_short} (#1 {top1}) #shorts",
            f"{top1}, {top2} & {top3} React to {cat_short}! (#{n_clips} Countdown) #shorts",
            f"Top {n_clips} Unforgettable {cat_short} Streamer Clips (#1 {top1}) #shorts",
            f"When Streamers Saw {cat_short} for the First Time (#1 {top1}) #shorts",
        ]

    for cand in candidates:
        trimmed = cand if len(cand) <= 99 else (cand[:91].rstrip() + " #shorts")
        if trimmed.lower() not in used_lower:
            return trimmed

    base = candidates[0]
    for suffix_idx in range(2, 50):
        suffix = f" [Pt {suffix_idx}] #shorts"
        head = base.replace(" #shorts", "")[: 99 - len(suffix)].rstrip()
        attempt = f"{head}{suffix}"
        if attempt.lower() not in used_lower:
            return attempt
    return base[:99]


def build_seo_tags(
    meta: dict[str, Any],
    category: str = "Grand Theft Auto VI",
    max_chars: int = 450,
) -> list[str]:
    """Generate prioritized YouTube tags strictly under YouTube's character limit."""
    streamers = list(reversed(_parse_streamers(meta)))
    is_gta6 = "vi" in category.lower() or "gta 6" in category.lower() or "gta6" in category.lower()

    raw: list[str] = []
    if is_gta6:
        raw.extend(
            [
                "gta 6",
                "grand theft auto 6",
                "gta vi",
                "gta 6 shorts",
                "gta 6 gameplay",
                "gta 6 streamer reactions",
                "vice city",
                "leonida",
                "gta 6 clips",
                "rockstar games",
            ]
        )
    else:
        raw.extend([category.lower(), f"{category.lower()} clips", f"{category.lower()} shorts"])

    for handle in streamers[:6]:
        display = _display_creator(handle).lower()
        raw.append(f"{display} gta 6" if is_gta6 else display)
        raw.append(display)

    raw.extend(["twitch clips", "gaming shorts", "viral gaming", "shorts"])
    return fit_tags_budget(raw, max_chars=max_chars)


def build_hashtags(meta: dict[str, Any], category: str = "Grand Theft Auto VI") -> list[str]:
    """Return balanced, clean hashtags for description footer."""
    is_gta6 = "vi" in category.lower() or "gta 6" in category.lower() or "gta6" in category.lower()
    tags = ["#gta6", "#gtavi", "#grandtheftauto6", "#leonida", "#vicecity", "#gaming", "#shorts"] if is_gta6 else ["#gaming", "#shorts", "#clips"]
    return tags


def build_pinned_comment(meta: dict[str, Any]) -> str:
    """Create an engaging Viewer CTA pinned comment tailored to top streamer."""
    streamers = _parse_streamers(meta)
    top1 = _display_creator(streamers[-1]) if streamers else "#1"
    top2 = _display_creator(streamers[-2]) if len(streamers) >= 2 else "the others"
    return (
        f"Who had the best reaction — {top1} at #1 or {top2}? "
        f"Drop your favorite timestamp below! 👇🔥"
    )


def build_rich_description(
    meta: dict[str, Any],
    clean_title: str,
    hashtags: list[str],
) -> str:
    """Build YouTube Shorts description with curiosity opener, chapters, credits, and tags."""
    streamers = list(reversed(_parse_streamers(meta)))
    featured = ", ".join(_display_creator(s) for s in streamers[:5])
    opener = (
        f"{clean_title}\n\n"
        f"Watch {len(_parse_streamers(meta)) or 11} viral streamer reactions to Grand Theft Auto VI "
        f"featuring {featured} and more!"
    )

    core_chapters, fallback = _split_description_sections(str(meta.get("description") or ""))
    body_block = core_chapters or fallback
    tag_line = " ".join(hashtags)
    full_desc = f"{opener}\n\n{body_block}\n\n{tag_line}".strip()
    if len(full_desc) > 4900:
        full_desc = full_desc[:4897].rstrip() + "..."
    return full_desc


def _write_readable_txt(meta: dict[str, Any], txt_path: Path) -> None:
    """Write copy-paste / Studio automation ready TXT summary beside video."""
    tags_csv = meta.get("youtube_tags_csv") or ", ".join(meta.get("tags", []))
    studio = meta.get("youtube_studio", {})
    content = (
        f"=== TITLE (WITHOUT #shorts) ===\n{meta.get('viral_title', '')}\n\n"
        f"=== YOUTUBE SHORTS TITLE ===\n{meta.get('youtube_shorts_title', '')}\n\n"
        f"=== DESCRIPTION (CREDITS + CHAPTERS) ===\n{meta.get('description', '')}\n\n"
        f"=== YOUTUBE TAGS (CSV) ===\n{tags_csv}\n\n"
        f"=== PINNED COMMENT ===\n{meta.get('pinned_comment', '')}\n\n"
        f"=== YOUTUBE STUDIO SETTINGS ===\n"
        f"Category      : {studio.get('category', 'Oyun')} (ID: {studio.get('category_id', '20')})\n"
        f"Game Title    : {studio.get('game_title', 'Grand Theft Auto VI')}\n"
        f"Language      : {studio.get('video_language', 'İngilizce')}\n"
        f"Made for Kids : {studio.get('made_for_kids', False)}\n"
        f"Altered AI    : {studio.get('altered_content', False)}\n"
    )
    txt_path.write_text(content, encoding="utf-8")


def enrich_compilation_package(
    json_path: Path,
    existing_titles: set[str] | None = None,
    category: str = "Grand Theft Auto VI",
    save: bool = True,
) -> dict[str, Any]:
    """Upgrade a compilation metadata JSON + TXT with full SEO fields for YouTube Studio."""
    meta = json.loads(json_path.read_text(encoding="utf-8"))

    shorts_title = build_unique_title(meta, existing_titles=existing_titles, category=category)
    clean_title = re.sub(r"\s*#shorts\b", "", shorts_title, flags=re.IGNORECASE).strip()
    hashtags = build_hashtags(meta, category=category)
    tags = build_seo_tags(meta, category=category)
    description = build_rich_description(meta, clean_title=clean_title, hashtags=hashtags)
    pinned_comment = build_pinned_comment(meta)

    meta["viral_title"] = clean_title
    meta["youtube_shorts_title"] = shorts_title
    meta["description"] = description
    meta["hashtags"] = hashtags
    meta["tags"] = tags
    meta["youtube_tags_csv"] = ", ".join(tags)
    meta["pinned_comment"] = pinned_comment
    meta["tiktok_caption"] = f"{clean_title}\n{' '.join(hashtags)}"
    meta["instagram_caption"] = f"{clean_title}\n\n{' '.join(hashtags)}"
    meta["youtube_studio"] = {
        "category": "Oyun",
        "category_en": "Gaming",
        "category_id": "20",
        "game_title": category,
        "video_language": "İngilizce",
        "video_language_code": "en",
        "made_for_kids": False,
        "altered_content": False,
    }

    if save:
        json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_readable_txt(meta, json_path.with_suffix(".txt"))

    return meta


def sync_upload_queue(
    ready_dir: Path = DEFAULT_READY_DIR,
    channel_name: str = "LEONIDA TOP",
    channel_handle: str = "@LeonidaTop",
    category: str = "Grand Theft Auto VI",
    schedule_hours_gap: int = 24,
) -> dict[str, Any]:
    """Scan output/ready MP4 files, enrich SEO metadata, and build upload_queue.json."""
    ready_dir = Path(ready_dir)
    ready_dir.mkdir(parents=True, exist_ok=True)
    queue_path = ready_dir / QUEUE_FILENAME

    existing_by_stem: dict[str, dict[str, Any]] = {}
    if queue_path.exists():
        try:
            old = json.loads(queue_path.read_text(encoding="utf-8"))
            for item in old.get("items", []):
                if item.get("stem"):
                    existing_by_stem[item["stem"]] = item
        except Exception:
            pass

    # Order newest compiled MP4 first so latest quality iteration goes public first
    mp4_files = sorted(
        ready_dir.glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    seen_titles: set[str] = set()
    queue_items: list[dict[str, Any]] = []
    next_slot_index = 0

    for mp4 in mp4_files:
        stem = mp4.stem
        json_path = mp4.with_suffix(".json")
        if not json_path.exists():
            continue

        prev = existing_by_stem.get(stem, {})
        meta = enrich_compilation_package(json_path, existing_titles=seen_titles, category=category, save=True)
        seen_titles.add(meta["youtube_shorts_title"])

        status = prev.get("status") or "pending"
        if status in {"published", "scheduled"} and prev.get("visibility"):
            rec_visibility = prev["visibility"]
            rec_schedule = prev.get("publish_at_local", "")
        else:
            if next_slot_index == 0:
                rec_visibility = "public"
                rec_schedule = ""
            else:
                target_dt = (datetime.now(timezone.utc) + timedelta(hours=3) + timedelta(days=next_slot_index)).replace(
                    hour=20, minute=0, second=0, microsecond=0
                )
                rec_visibility = "scheduled"
                rec_schedule = target_dt.strftime("%Y-%m-%d %H:%M")
            next_slot_index += 1

        queue_items.append(
            {
                "stem": stem,
                "video_path": str(mp4.resolve()),
                "json_path": str(json_path.resolve()),
                "txt_path": str(mp4.with_suffix(".txt").resolve()),
                "duration_seconds": meta.get("duration_seconds"),
                "title": meta["youtube_shorts_title"],
                "description": meta["description"],
                "tags": meta["tags"],
                "tags_csv": meta["youtube_tags_csv"],
                "pinned_comment": meta["pinned_comment"],
                "studio_settings": meta["youtube_studio"],
                "recommended_visibility": rec_visibility,
                "publish_at_local": rec_schedule,
                "status": status,
                "visibility": prev.get("visibility", ""),
                "video_url": prev.get("video_url", ""),
                "studio_url": prev.get("studio_url", ""),
                "updated_at": prev.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            }
        )

    payload = {
        "channel_name": channel_name,
        "channel_handle": channel_handle,
        "studio_url": "https://studio.youtube.com",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_ready": len(queue_items),
        "pending_count": sum(1 for it in queue_items if it["status"] == "pending"),
        "items": queue_items,
    }
    queue_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def mark_upload_result(
    stem: str,
    status: str,
    ready_dir: Path = DEFAULT_READY_DIR,
    video_url: str = "",
    studio_url: str = "",
    visibility: str = "",
) -> dict[str, Any]:
    """Update upload status for a queue item after YouTube Studio publish/schedule."""
    queue_path = Path(ready_dir) / QUEUE_FILENAME
    if not queue_path.exists():
        raise FileNotFoundError(f"Upload queue not found: {queue_path}")

    data = json.loads(queue_path.read_text(encoding="utf-8"))
    matched = False
    for item in data.get("items", []):
        if item.get("stem") == stem:
            item["status"] = status
            if visibility:
                item["visibility"] = visibility
            if video_url:
                item["video_url"] = video_url
            if studio_url:
                item["studio_url"] = studio_url
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            matched = True
            break

    if not matched:
        raise KeyError(f"Queue item not found for stem: {stem}")

    data["pending_count"] = sum(1 for it in data.get("items", []) if it.get("status") == "pending")
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    queue_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
