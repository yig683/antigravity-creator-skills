"""YouTube Data API v3 OAuth 2.0 uploader for Makine Studio episodes."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ROOT_DIR

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
UPLOAD_ONLY_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

USER_CONFIG_DIR = Path.home() / ".gemini" / "config" / "makine_studio"
DEFAULT_CLIENT_SECRETS_FILE = USER_CONFIG_DIR / "youtube_client_secret.json"
DEFAULT_TOKEN_FILE = USER_CONFIG_DIR / "youtube_token.json"

# Category 28 = Science & Technology (best fit for mechanical/engineering explainers)
DEFAULT_CATEGORY_ID = "28"


def _resolve_client_secrets(explicit_path: Path | None = None) -> Path:
    """Locate Google Cloud OAuth Desktop client_secret.json across standard paths."""
    if explicit_path is not None:
        resolved = explicit_path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"OAuth client secrets file not found: {resolved}")
        return resolved

    env_path = os.environ.get("MAKINE_YT_CLIENT_SECRETS")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.exists():
            return p

    candidates = [
        DEFAULT_CLIENT_SECRETS_FILE,
        Path.cwd() / "youtube_client_secret.json",
        Path.cwd() / "client_secret.json",
        ROOT_DIR / "youtube_client_secret.json",
        ROOT_DIR / "client_secret.json",
    ]
    for glob_base in (USER_CONFIG_DIR, Path.cwd(), ROOT_DIR):
        if glob_base.is_dir():
            candidates.extend(sorted(glob_base.glob("client_secret*.json")))

    for cand in candidates:
        if cand.exists():
            return cand.resolve()

    raise FileNotFoundError(
        "Google Cloud OAuth 'client_secret.json' bulunamadı.\n"
        f"Beklenen varsayılan konum: {DEFAULT_CLIENT_SECRETS_FILE}\n"
        "Kurulum adımları:\n"
        "  1. https://console.cloud.google.com/ -> Proje oluşturup 'YouTube Data API v3' etkinleştirin.\n"
        "  2. Google Auth Platform / OAuth consent screen'i 'External' seçip kendi Google hesabınızı 'Test users' ekleyin.\n"
        "  3. Credentials -> Create Credentials -> OAuth client ID -> Application type: Desktop app.\n"
        f"  4. İndirdiğiniz JSON dosyasını şu yola kaydedin: {DEFAULT_CLIENT_SECRETS_FILE}\n"
        "  5. Ardından `python -m studio.youtube_uploader --auth-only` ile tek sefer giriş yapın."
    )


def _resolve_token_path(explicit_token: Path | None = None) -> Path:
    if explicit_token is not None:
        return explicit_token.expanduser().resolve()
    env_tok = os.environ.get("MAKINE_YT_TOKEN_FILE")
    if env_tok:
        return Path(env_tok).expanduser().resolve()
    return DEFAULT_TOKEN_FILE


def authenticate_youtube(
    client_secrets_path: Path | None = None,
    token_path: Path | None = None,
    scopes: list[str] | None = None,
) -> Any:
    """Authenticate via cached OAuth token or interactive local browser flow and return API client."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "YouTube yükleme paketleri eksik. Kurmak için:\n"
            "  python -m pip install google-api-python-client google-auth-oauthlib"
        ) from exc

    active_scopes = list(scopes or YOUTUBE_SCOPES)
    tok_file = _resolve_token_path(token_path)
    creds = None

    if tok_file.exists():
        creds = Credentials.from_authorized_user_file(str(tok_file), active_scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            secrets_file = _resolve_client_secrets(client_secrets_path)
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), active_scopes)
            print("[YouTube] Tarayıcıda Google OAuth giriş penceresi açılıyor...", flush=True)
            creds = flow.run_local_server(port=0, open_browser=True)

        tok_file.parent.mkdir(parents=True, exist_ok=True)
        tok_file.write_text(creds.to_json(), encoding="utf-8")
        print(f"[YouTube] OAuth token kaydedildi -> {tok_file}", flush=True)

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _fit_tags_budget(tags: list[str], max_chars: int = 450) -> list[str]:
    """Fit tag strings within YouTube's 500-char combined metadata budget."""
    selected: list[str] = []
    seen_lower: set[str] = set()
    used = 0
    for raw in tags:
        tag = str(raw).strip().replace("<", "").replace(">", "")
        if not tag or tag.lower() in seen_lower:
            continue
        # YouTube counts quotes around multi-word tags + comma separators
        cost = len(tag) + (2 if " " in tag else 0) + (1 if selected else 0)
        if used + cost > max_chars:
            continue
        selected.append(tag)
        seen_lower.add(tag.lower())
        used += cost
    return selected


def _build_video_body(
    meta: dict[str, Any],
    privacy: str = "private",
    publish_at: str | None = None,
    category_id: str = DEFAULT_CATEGORY_ID,
    language: str = "tr",
) -> dict[str, Any]:
    """Construct validated YouTube videos.insert payload from episode metadata.json."""
    title = str(meta.get("title") or meta.get("episode_id") or "Makine Studio").strip()
    if len(title) > 100:
        title = title[:97].rstrip() + "..."

    desc = str(meta.get("description") or "").strip()
    is_shorts = str(meta.get("profile", "")).lower() == "shorts"
    if is_shorts and "#shorts" not in desc.lower():
        desc = (desc + "\n\n#shorts").strip()

    raw_tags = [str(t) for t in meta.get("tags", [])]
    if is_shorts and not any(t.strip().lower() == "shorts" for t in raw_tags):
        raw_tags.append("shorts")
    tags = _fit_tags_budget(raw_tags)

    # YouTube requires privacyStatus='private' whenever scheduled publishAt is supplied
    effective_privacy = "private" if publish_at else privacy
    status: dict[str, Any] = {
        "privacyStatus": effective_privacy,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status["publishAt"] = publish_at

    return {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags,
            "categoryId": str(category_id),
            "defaultLanguage": language,
            "defaultAudioLanguage": language,
        },
        "status": status,
    }


def _find_output_artifact(out_dir: Path, meta_key: str, patterns: tuple[str, ...]) -> Path | None:
    meta_path = out_dir / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        val = meta.get(meta_key)
        if val:
            cand = Path(val)
            if cand.exists():
                return cand
    for pat in patterns:
        matches = sorted(out_dir.glob(pat))
        if matches:
            return matches[0]
    return None


def upload_episode_output(
    out_dir: Path,
    privacy: str = "private",
    publish_at: str | None = None,
    client_secrets_path: Path | None = None,
    token_path: Path | None = None,
    upload_captions: bool = True,
    upload_thumbnail: bool = False,
    post_comment: bool = False,
    category_id: str = DEFAULT_CATEGORY_ID,
) -> dict[str, Any]:
    """Upload a rendered episode directory (MP4 + metadata + SRT + optional cover/comment)."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    out_dir = Path(out_dir).resolve()
    meta_path = out_dir / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json not found in {out_dir}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    video_path = _find_output_artifact(out_dir, "video_file", ("*.mp4",))
    if video_path is None or not video_path.exists():
        raise FileNotFoundError(
            f"Final MP4 not found in {out_dir}. Run --mode full first before uploading."
        )

    cover_path = _find_output_artifact(out_dir, "cover_file", ("cover_*.png", "cover*.png", "*.jpg"))
    srt_path = out_dir / "subtitles.srt"

    youtube = authenticate_youtube(client_secrets_path=client_secrets_path, token_path=token_path)
    body = _build_video_body(meta, privacy=privacy, publish_at=publish_at, category_id=category_id)

    print(f"[YouTube] Yükleniyor ({body['status']['privacyStatus']}): {video_path.name}", flush=True)
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response: dict[str, Any] | None = None
    last_pct = -1
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            if pct >= last_pct + 20:
                print(f"[YouTube] Yükleme ilerlemesi: %{pct}", flush=True)
                last_pct = pct

    video_id = str(response["id"])
    profile = str(meta.get("profile", "shorts"))
    watch_url = f"https://youtube.com/shorts/{video_id}" if profile == "shorts" else f"https://www.youtube.com/watch?v={video_id}"
    studio_url = f"https://studio.youtube.com/video/{video_id}/edit"
    print(f"[YouTube] Video yüklendi -> {studio_url}", flush=True)

    captions_status = "skipped"
    if upload_captions and srt_path.exists():
        try:
            cap_media = MediaFileUpload(str(srt_path), mimetype="application/octet-stream")
            youtube.captions().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "language": "tr",
                        "name": "Türkçe",
                        "isDraft": False,
                    }
                },
                media_body=cap_media,
            ).execute()
            captions_status = "uploaded"
            print("[YouTube] Türkçe altyazı (.srt) eklendi.", flush=True)
        except HttpError as err:
            captions_status = f"failed: {err.resp.status}"
            print(f"[YouTube] Uyarı: Altyazı yüklenemedi ({err.resp.status}). Video yüklemesi başarılı.", flush=True)

    thumb_status = "skipped"
    if upload_thumbnail and cover_path is not None and cover_path.exists():
        try:
            mime = "image/png" if cover_path.suffix.lower() == ".png" else "image/jpeg"
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(cover_path), mimetype=mime),
            ).execute()
            thumb_status = "uploaded"
            print("[YouTube] Özel kapak görseli (thumbnail) ayarlandı.", flush=True)
        except HttpError as err:
            thumb_status = f"failed: {err.resp.status}"
            print(
                f"[YouTube] Not: Özel kapak ayarlanamadı ({err.resp.status} — Shorts'ta mobil seçimi veya telefonla doğrulanmış kanal gerekebilir).",
                flush=True,
            )

    comment_status = "skipped"
    pinned_text = str(meta.get("pinned_comment") or "").strip()
    if post_comment and pinned_text:
        try:
            youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {"snippet": {"textOriginal": pinned_text}},
                    }
                },
            ).execute()
            comment_status = "posted_unpinned"
            print("[YouTube] İlk yorum eklendi (YouTube Studio'dan sabitleyebilirsiniz).", flush=True)
        except HttpError as err:
            comment_status = f"failed: {err.resp.status}"
            print(f"[YouTube] Uyarı: İlk yorum eklenemedi ({err.resp.status}).", flush=True)

    receipt = {
        "video_id": video_id,
        "watch_url": watch_url,
        "studio_url": studio_url,
        "privacy_status": response.get("status", {}).get("privacyStatus", body["status"]["privacyStatus"]),
        "captions": captions_status,
        "thumbnail": thumb_status,
        "comment": comment_status,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "youtube_upload.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload Makine Studio episode to YouTube via Data API v3")
    parser.add_argument("--output-dir", default=None, help="Rendered episode directory containing MP4 and metadata.json")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    parser.add_argument("--publish-at", default=None, help="Optional UTC ISO-8601 schedule time (e.g. 2026-11-15T15:00:00Z)")
    parser.add_argument("--client-secrets", default=None, help="Path to Google Cloud OAuth client_secret.json")
    parser.add_argument("--token-file", default=None, help="Path to cached OAuth refresh token JSON")
    parser.add_argument("--no-captions", action="store_true", help="Skip uploading subtitles.srt")
    parser.add_argument("--upload-thumbnail", action="store_true", help="Attempt setting cover PNG as custom thumbnail")
    parser.add_argument("--post-comment", action="store_true", help="Post pinned_comment from metadata.json")
    parser.add_argument("--auth-only", action="store_true", help="Only run OAuth login and cache refresh token")
    args = parser.parse_args()

    secrets_path = Path(args.client_secrets) if args.client_secrets else None
    token_path = Path(args.token_file) if args.token_file else None

    if args.auth_only:
        yt = authenticate_youtube(client_secrets_path=secrets_path, token_path=token_path)
        ch = yt.channels().list(part="snippet", mine=True).execute()
        items = ch.get("items", [])
        title = items[0]["snippet"]["title"] if items else "(kanal bilgisi bulunamadı)"
        print(json.dumps({"authenticated": True, "channel": title}, indent=2, ensure_ascii=False))
        return

    if not args.output_dir:
        raise SystemExit("--output-dir veya --auth-only gerekli.")

    receipt = upload_episode_output(
        out_dir=Path(args.output_dir),
        privacy=args.privacy,
        publish_at=args.publish_at,
        client_secrets_path=secrets_path,
        token_path=token_path,
        upload_captions=not args.no_captions,
        upload_thumbnail=args.upload_thumbnail,
        post_comment=args.post_comment,
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
