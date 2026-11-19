//! HTTP API katmanı (axum).
//!
//! Yollar orijinal Flask uygulamasıyla birebir aynı tutuldu; böylece arayüz
//! tarafında uyumluluk sorunu çıkmıyor.

use crate::assets::Assets;
use crate::config::{self, Config};
use crate::download::{self, DownloadItem};
use crate::scan;
use crate::state::{save_meta, AppState, TrackMeta};
use axum::body::Body;
use axum::extract::{Path as AxPath, Query, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::sync::Arc;

type Shared = Arc<AppState>;

pub fn router(state: Shared) -> Router {
    Router::new()
        .route("/", get(index))
        .route("/static/{*path}", get(static_file))
        .route("/covers/{*path}", get(cover_file))
        .route("/downloads/{*path}", get(audio_file))
        .route("/api/health", get(health))
        .route("/api/app/info", get(app_info))
        .route("/api/app/confirm-exit", post(confirm_exit))
        .route("/api/open-folder", post(open_folder))
        .route("/api/folder/browse", post(browse_folder))
        .route("/api/folder/reveal", post(reveal_file))
        .route("/api/settings", get(get_settings).post(set_settings))
        .route("/api/auth/status", get(auth_status))
        .route("/api/auth/start", post(auth_start))
        .route("/api/auth/manual", post(auth_manual))
        .route("/api/auth/logout", post(auth_logout))
        .route("/api/auth/web-login", post(auth_web_login))
        .route("/api/auth/token-login", post(auth_token_login))
        .route("/api/onboarding/complete", post(onboarding_complete))
        .route("/api/browser/open", post(browser_open))
        .route("/api/browser/url", get(browser_url))
        .route("/api/soundcloud/nav", post(sc_nav))
        .route("/api/soundcloud/monetize-sweep", post(sc_monetize_sweep))
        .route("/api/archive/upload", post(archive_upload))
        .route("/api/upload/status", get(upload_status))
        .route("/api/upload/cancel", post(cancel_upload))
        .route("/api/curator/reset-memory", post(reset_memory))
        .route("/api/curator/clear", post(clear_candidates))
        .route("/api/curator/scan", post(start_scan))
        .route("/api/curator/cancel", post(cancel_curator))
        .route("/api/curator/preview", get(curator_preview))
        .route("/api/curator/download-selected", post(download_selected))
        .route("/api/trends/status", get(trends_status))
        .route("/api/archive/cover/{name}", get(archive_cover))
        .route("/api/archive/delete", post(delete_archive))
        .route("/api/archive/clear", post(clear_archive))
        .route("/api/my-tracks", get(my_tracks))
        .route("/api/my-tracks/regenerate", post(regenerate))
        .route("/api/my-tracks/set-folder", post(set_folder))
        .route("/api/my-tracks/export-paired", post(export_paired))
        .fallback(not_found)
        .with_state(state)
}

// ---------------------------------------------------------------- yardımcılar

fn html_response(status: StatusCode, body: String) -> Response {
    (
        status,
        [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
        body,
    )
        .into_response()
}

fn json_error(status: StatusCode, message: impl Into<String>) -> Response {
    (status, Json(json!({ "success": false, "error": message.into() }))).into_response()
}

/// Verilen yolun `root` altında kaldığını doğrular (path traversal koruması).
fn safe_join(root: &Path, rel: &str) -> Option<PathBuf> {
    let rel = rel.trim_start_matches(['/', '\\']);
    if rel.split(['/', '\\']).any(|part| part == "..") {
        return None;
    }
    let candidate = root.join(rel);
    let canon_root = root.canonicalize().ok()?;
    let canon = candidate.canonicalize().ok()?;
    if canon.starts_with(&canon_root) {
        Some(canon)
    } else {
        None
    }
}

fn guess_mime(path: &Path) -> &'static str {
    match path
        .extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .unwrap_or_default()
        .as_str()
    {
        "mp3" => "audio/mpeg",
        "wav" => "audio/wav",
        "flac" => "audio/flac",
        "m4a" => "audio/mp4",
        "jpg" | "jpeg" => "image/jpeg",
        "png" => "image/png",
        "webp" => "image/webp",
        "html" => "text/html; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "js" => "application/javascript; charset=utf-8",
        _ => "application/octet-stream",
    }
}

/// `Range` başlığını destekleyen dosya sunucu.
/// (Flask'ın `send_file` davranışı; ses oynatıcıda ileri sarma için şart.)
fn serve_file(path: &Path, headers: &HeaderMap, download_name: Option<&str>) -> Response {
    let Ok(meta) = std::fs::metadata(path) else {
        return (StatusCode::NOT_FOUND, "Dosya bulunamadı").into_response();
    };
    if !meta.is_file() {
        return (StatusCode::NOT_FOUND, "Dosya bulunamadı").into_response();
    }
    let total = meta.len();
    let mime = guess_mime(path);

    let range = headers
        .get(header::RANGE)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("bytes="))
        .and_then(|v| v.split(',').next())
        .and_then(|spec| {
            let (start, end) = spec.split_once('-')?;
            let start: u64 = if start.trim().is_empty() {
                // "bytes=-500" → son 500 bayt
                let suffix: u64 = end.trim().parse().ok()?;
                return Some((total.saturating_sub(suffix), total.saturating_sub(1)));
            } else {
                start.trim().parse().ok()?
            };
            let end: u64 = if end.trim().is_empty() {
                total.saturating_sub(1)
            } else {
                end.trim().parse().ok()?
            };
            Some((start.min(total.saturating_sub(1)), end.min(total.saturating_sub(1))))
        });

    let mut builder = Response::builder()
        .header(header::ACCEPT_RANGES, "bytes")
        .header(header::CONTENT_TYPE, mime);

    if let Some(name) = download_name {
        builder = builder.header(
            header::CONTENT_DISPOSITION,
            format!("inline; filename=\"{}\"", name.replace('"', "")),
        );
    }

    match range {
        Some((start, end)) if start <= end => {
            use std::io::{Read, Seek, SeekFrom};
            let Ok(mut file) = std::fs::File::open(path) else {
                return (StatusCode::INTERNAL_SERVER_ERROR, "Okunamadı").into_response();
            };
            if file.seek(SeekFrom::Start(start)).is_err() {
                return (StatusCode::INTERNAL_SERVER_ERROR, "Okunamadı").into_response();
            }
            let len = end - start + 1;
            let mut buf = vec![0u8; len as usize];
            let mut read = 0usize;
            while read < buf.len() {
                match file.read(&mut buf[read..]) {
                    Ok(0) => break,
                    Ok(n) => read += n,
                    Err(_) => break,
                }
            }
            buf.truncate(read);
            builder
                .status(StatusCode::PARTIAL_CONTENT)
                .header(header::CONTENT_RANGE, format!("bytes {}-{}/{}", start, end, total))
                .header(header::CONTENT_LENGTH, buf.len())
                .body(Body::from(buf))
                .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
        }
        _ => match std::fs::read(path) {
            Ok(bytes) => builder
                .status(StatusCode::OK)
                .header(header::CONTENT_LENGTH, bytes.len())
                .body(Body::from(bytes))
                .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response()),
            Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "Okunamadı").into_response(),
        },
    }
}

// ------------------------------------------------------------------ statik

async fn index() -> Response {
    match crate::assets::asset_text("index.html") {
        Some(html) => html_response(StatusCode::OK, html),
        None => html_response(StatusCode::INTERNAL_SERVER_ERROR, "index.html yok".into()),
    }
}

async fn static_file(AxPath(path): AxPath<String>) -> Response {
    match Assets::get(&path) {
        Some(f) => {
            let mime = f.metadata.mimetype().to_string();
            ([(header::CONTENT_TYPE, mime)], f.data.to_vec()).into_response()
        }
        None => (StatusCode::NOT_FOUND, "bulunamadı").into_response(),
    }
}

async fn cover_file(State(state): State<Shared>, AxPath(path): AxPath<String>) -> Response {
    let _ = &state;
    match safe_join(&crate::paths::covers_dir(), &path) {
        Some(p) => serve_file(&p, &HeaderMap::new(), None),
        None => (StatusCode::NOT_FOUND, "bulunamadı").into_response(),
    }
}

async fn audio_file(State(state): State<Shared>, AxPath(path): AxPath<String>, headers: HeaderMap) -> Response {
    let dir = state.cfg.read().await.target_dir();
    match safe_join(&dir, &path) {
        Some(p) => serve_file(&p, &headers, p.file_name().and_then(|n| n.to_str())),
        None => (StatusCode::NOT_FOUND, "bulunamadı").into_response(),
    }
}

async fn health() -> Json<Value> {
    Json(json!({ "ok": true, "app": "SC Studio", "version": env!("CARGO_PKG_VERSION") }))
}

// ------------------------------------------------------------------ eylemler

#[derive(Deserialize)]
struct FolderReq {
    #[serde(default)]
    folder: String,
}

async fn open_folder(State(state): State<Shared>, body: Option<Json<FolderReq>>) -> Response {
    let requested = body.map(|b| b.0.folder).unwrap_or_default();
    let path = if requested.trim().is_empty() {
        state.cfg.read().await.target_dir()
    } else {
        PathBuf::from(requested)
    };
    if !path.exists() {
        return json_error(StatusCode::NOT_FOUND, "Klasör bulunamadı");
    }
    let _ = std::process::Command::new("explorer").arg(&path).spawn();
    Json(json!({ "success": true, "folder": path.display().to_string() })).into_response()
}

#[derive(Deserialize)]
struct RevealReq {
    filename: String,
}

async fn reveal_file(State(state): State<Shared>, Json(req): Json<RevealReq>) -> Response {
    let dir = state.cfg.read().await.target_dir();
    let Some(path) = safe_join(&dir, req.filename.trim()) else {
        return json_error(StatusCode::BAD_REQUEST, "Geçersiz dosya adı");
    };
    if !path.is_file() {
        return json_error(StatusCode::NOT_FOUND, "Dosya bulunamadı");
    }
    #[cfg(windows)]
    {
        let arg = format!("/select,{}", path.display());
        let _ = std::process::Command::new("explorer").arg(arg).spawn();
    }
    #[cfg(not(windows))]
    {
        let _ = std::process::Command::new("xdg-open").arg(&dir).spawn();
    }
    Json(json!({ "success": true })).into_response()
}

async fn browse_folder(State(state): State<Shared>) -> Response {
    use std::sync::atomic::Ordering;

    let current = state.cfg.read().await.target_dir();
    let hwnd = state.main_hwnd.load(Ordering::Relaxed);
    let picked = tokio::task::spawn_blocking(move || {
        crate::winmsg::pick_folder_dialog(hwnd, "Şarkı Arşiv Klasörünü Seçin", Some(&current))
    })
    .await
    .ok()
    .flatten();

    let Some(selected) = picked else {
        return Json(json!({ "success": true, "cancelled": true })).into_response();
    };
    let resolved = PathBuf::from(selected.trim());
    if let Err(e) = crate::paths::ensure_dir(&resolved) {
        return json_error(StatusCode::BAD_REQUEST, format!("Klasör kullanılamadı: {}", e));
    }

    let preset = {
        let mut cfg = state.cfg.write().await;
        cfg.uploader_source_dir = resolved.display().to_string();
        let snapshot = cfg.clone();
        drop(cfg);
        let _ = config::save(&snapshot);
        snapshot.active_folder_preset()
    };

    Json(json!({
        "success": true,
        "cancelled": false,
        "folder": resolved.display().to_string(),
        "preset": preset,
    }))
    .into_response()
}

async fn app_info(State(state): State<Shared>) -> Json<Value> {
    let cfg = state.cfg.read().await.clone();
    let ff = crate::paths::ffmpeg_path();
    let art_count = state.art.lock().map(|p| p.count()).unwrap_or(0);
    let seen_count = state.seen.read().await.len();
    let meta_count = state.meta.read().await.len();
    let cur = state.curator.read().await.clone();

    Json(json!({
        "version": env!("CARGO_PKG_VERSION"),
        "ffmpeg_ok": ff.is_file(),
        "ffmpeg_path": ff.display().to_string(),
        "data_dir": crate::paths::data_dir().display().to_string(),
        "covers_dir": crate::paths::covers_dir().display().to_string(),
        "target_dir": cfg.target_dir().display().to_string(),
        "target_preset": cfg.active_folder_preset(),
        "artwork_count": art_count,
        "seen_count": seen_count,
        "meta_count": meta_count,
        "scanning": cur.scanning,
        "downloading": cur.downloading,
    }))
}

async fn confirm_exit(State(state): State<Shared>) -> Response {
    use std::sync::atomic::Ordering;
    state.cancel_scan.store(true, Ordering::SeqCst);
    state.cancel_download.store(true, Ordering::SeqCst);
    let _ = crate::download::cleanup_stale_parts(&state.cfg.read().await.target_dir());
    crate::paths::cleanup_preview_cache();
    send_ui(&state, crate::ui::UiEvent::ForceExit)
}

async fn get_settings(State(state): State<Shared>) -> Json<Value> {
    let cfg = state.cfg.read().await.clone();
    let covers = crate::paths::covers_dir();
    let art_count = state.art.lock().map(|p| p.count()).unwrap_or(0);
    // client_secret arayüze geri gönderilmez; sadece dolu olup olmadığı.
    let mut safe = cfg.clone();
    safe.sc_client_secret = if cfg.sc_client_secret.is_empty() { String::new() } else { "••••••••".into() };
    safe.client_id = String::new();

    Json(json!({
        "config": safe,
        "oauth_configured": cfg.oauth_configured(),
        "ffmpeg_ok": crate::paths::ffmpeg_path().is_file(),
        "target_dir": cfg.target_dir().display().to_string(),
        "target_preset": cfg.active_folder_preset(),
        "covers_dir": covers.display().to_string(),
        "artwork_count": art_count,
        "naming_styles": config::NAMING_STYLES,
        "source_types": config::SOURCE_TYPES,
    }))
}

async fn set_settings(State(state): State<Shared>, Json(patch): Json<Value>) -> Response {
    let mut cfg = state.cfg.read().await.clone();
    merge_config(&mut cfg, &patch);
    let cfg = cfg.sanitized();
    if let Err(e) = config::save(&cfg) {
        return json_error(StatusCode::INTERNAL_SERVER_ERROR, format!("Ayarlar yazılamadı: {}", e));
    }
    *state.cfg.write().await = cfg.clone();
    Json(json!({ "success": true, "config": cfg })).into_response()
}

fn merge_config(cfg: &mut Config, patch: &Value) {
    let Some(obj) = patch.as_object() else { return };
    if let Some(v) = obj.get("channels").and_then(Value::as_array) {
        let list: Vec<String> = v
            .iter()
            .filter_map(Value::as_str)
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();
        if !list.is_empty() {
            cfg.channels = list;
        }
    }
    if let Some(v) = obj.get("naming_style").and_then(Value::as_str) {
        cfg.naming_style = v.to_string();
    }
    if let Some(v) = obj.get("naming_prefix").and_then(Value::as_str) {
        cfg.naming_prefix = v.to_string();
    }
    if let Some(v) = obj.get("uploader_source_dir").and_then(Value::as_str) {
        cfg.uploader_source_dir = v.to_string();
    }
    if let Some(v) = obj.get("min_score").and_then(Value::as_i64) {
        cfg.min_score = v as i32;
    }
    if let Some(v) = obj.get("min_views").and_then(Value::as_i64) {
        cfg.min_views = v;
    }
    if let Some(v) = obj.get("max_days").and_then(Value::as_f64) {
        cfg.max_days = v;
    }
    if let Some(v) = obj.get("track_count").and_then(Value::as_i64) {
        cfg.track_count = v.max(1) as usize;
    }
    if let Some(v) = obj.get("source_type").and_then(Value::as_str) {
        cfg.source_type = v.to_string();
    }
    if let Some(v) = obj.get("custom_input").and_then(Value::as_str) {
        cfg.custom_input = v.to_string();
    }
    if let Some(v) = obj.get("onboarded").and_then(Value::as_bool) {
        cfg.onboarded = v;
    }
    if let Some(v) = obj.get("sc_client_id").and_then(Value::as_str) {
        cfg.sc_client_id = v.trim().to_string();
    }
    if let Some(v) = obj.get("sc_client_secret").and_then(Value::as_str) {
        cfg.sc_client_secret = v.trim().to_string();
    }
    if let Some(v) = obj.get("sc_redirect_uri").and_then(Value::as_str) {
        let v = v.trim();
        if !v.is_empty() {
            cfg.sc_redirect_uri = v.to_string();
        }
    }
    if let Some(v) = obj.get("player_volume").and_then(Value::as_f64) {
        cfg.player_volume = v;
    }
    if let Some(v) = obj.get("player_muted").and_then(Value::as_bool) {
        cfg.player_muted = v;
    }
    if let Some(v) = obj.get("playback_rate").and_then(Value::as_f64) {
        cfg.playback_rate = v;
    }
    if let Some(v) = obj.get("library_sort").and_then(Value::as_str) {
        cfg.library_sort = v.to_string();
    }
    if let Some(v) = obj.get("cand_sort").and_then(Value::as_str) {
        cfg.cand_sort = v.to_string();
    }
}

async fn reset_memory(State(state): State<Shared>) -> Response {
    let mut seen = state.seen.write().await;
    let count = seen.len();
    seen.clear();
    crate::state::save_seen(&seen);
    drop(seen);

    let mut c = state.curator.write().await;
    c.seen_count = 0;
    c.log = "Tarama geçmişi sıfırlandı! Artık tüm şarkılar baştan taranabilir.".into();
    Json(json!({ "success": true, "seen_count": count })).into_response()
}

fn clear_curator_candidates(c: &mut crate::state::CuratorStatus) -> usize {
    let cleared = c.candidates.len();
    c.candidates.clear();
    c.completed_urls.clear();
    c.failed_urls.clear();
    c.error = None;
    c.progress = 0.0;
    c.current.clear();
    c.current_url.clear();
    c.stage.clear();
    c.batch_index = 0;
    c.batch_total = 0;
    c.log = "Bulunan parçalar sıfırlandı.".into();
    cleared
}

async fn clear_candidates(State(state): State<Shared>) -> Response {
    let mut c = state.curator.write().await;
    if c.scanning || c.downloading {
        return json_error(
            StatusCode::CONFLICT,
            "Aktif tarama veya indirme sürerken liste sıfırlanamaz.",
        );
    }
    let cleared = clear_curator_candidates(&mut c);
    Json(json!({ "success": true, "cleared": cleared })).into_response()
}

#[derive(Deserialize)]
struct ScanReq {
    #[serde(default = "default_source")]
    source: String,
    #[serde(default)]
    custom_input: String,
    #[serde(default = "default_min_score")]
    min_score: i32,
    #[serde(default = "default_count")]
    count: usize,
    #[serde(default = "default_days")]
    max_days: f64,
    #[serde(default)]
    min_views: i64,
    #[serde(default)]
    naming_style: Option<String>,
}

fn default_source() -> String {
    "curated_creators".into()
}
fn default_min_score() -> i32 {
    65
}
fn default_count() -> usize {
    5
}
fn default_days() -> f64 {
    7.0
}

async fn start_scan(State(state): State<Shared>, Json(req): Json<ScanReq>) -> Response {
    {
        let mut c = state.curator.write().await;
        if c.scanning || c.downloading {
            return json_error(StatusCode::CONFLICT, "Şu anda devam eden bir işlem var.");
        }
        c.scanning = true;
        c.error = None;
    }

    // Seçimleri sınır kontrolünden geçirip kalıcı hale getir; tarama da
    // aynı temizlenmiş değerlerle çalışsın.
    let cfg_now = {
        let mut cfg = state.cfg.read().await.clone();
        cfg.source_type = req.source.clone();
        cfg.custom_input = req.custom_input.clone();
        cfg.min_score = req.min_score;
        cfg.track_count = req.count;
        cfg.max_days = req.max_days;
        cfg.min_views = req.min_views;
        if let Some(style) = &req.naming_style {
            cfg.naming_style = style.clone();
        }
        let cfg = cfg.sanitized();
        *state.cfg.write().await = cfg.clone();
        let _ = config::save(&cfg);
        cfg
    };

    let view_label = if cfg_now.min_views > 0 {
        format!("{}K+ dinlenmeli", cfg_now.min_views / 1000)
    } else {
        String::new()
    };
    state
        .set_log(format!(
            "AI Küratör {} popüler şarkıları arıyor ({} adet)...",
            view_label, cfg_now.track_count
        ))
        .await;

    let state_clone = Arc::clone(&state);
    tokio::spawn(async move {
        if let Err(e) = scan::run_scan(
            Arc::clone(&state_clone),
            cfg_now.source_type,
            cfg_now.custom_input,
            cfg_now.min_score,
            cfg_now.track_count,
            cfg_now.max_days,
            cfg_now.min_views,
        )
        .await
        {
            let mut c = state_clone.curator.write().await;
            c.scanning = false;
            c.log = format!("Tarama hatası: {}", e);
            c.error = Some(e.to_string());
        }
    });

    Json(json!({ "success": true })).into_response()
}

async fn cancel_curator(State(state): State<Shared>) -> Response {
    use std::sync::atomic::Ordering;

    state.cancel_scan.store(true, Ordering::SeqCst);
    state.cancel_download.store(true, Ordering::SeqCst);
    {
        let mut c = state.curator.write().await;
        if c.scanning || c.downloading {
            c.log = "İşlem durduruluyor...".into();
        }
    }
    Json(json!({ "success": true })).into_response()
}

#[derive(Deserialize)]
struct PreviewQuery {
    url: String,
}

fn preview_cache_path(url: &str) -> PathBuf {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for b in url.as_bytes() {
        hash ^= *b as u64;
        hash = hash.wrapping_mul(0x0100_0000_01b3);
    }
    crate::paths::preview_cache_dir().join(format!("p_{:016x}.mp3", hash))
}

async fn curator_preview(
    State(state): State<Shared>,
    Query(q): Query<PreviewQuery>,
    headers: HeaderMap,
) -> Response {
    let url = q.url.trim();
    if !(url.starts_with("https://soundcloud.com/") || url.starts_with("https://on.soundcloud.com/")) {
        return json_error(StatusCode::BAD_REQUEST, "Geçersiz SoundCloud bağlantısı.");
    }

    let cache_dir = crate::paths::preview_cache_dir();
    let _ = crate::paths::ensure_dir(&cache_dir);
    let cache_path = preview_cache_path(url);

    if cache_path.is_file() {
        return serve_file(&cache_path, &headers, None);
    }

    let value = match state.sc.resolve(url).await {
        Ok(v) => v,
        Err(e) => return json_error(StatusCode::BAD_GATEWAY, format!("Parça çözümlenemedi: {}", e)),
    };
    let Some(track) = crate::sc::Track::from_json(&value) else {
        return json_error(StatusCode::BAD_GATEWAY, "Parça bilgisi okunamadı.");
    };
    let (stream_url, is_prog, is_mp3) = match state.sc.preview_source(&track).await {
        Ok(s) => s,
        Err(e) => return json_error(StatusCode::UNPROCESSABLE_ENTITY, e),
    };

    let tmp_path = cache_path.with_extension(format!("{}.tmp", std::process::id()));
    let _ = std::fs::remove_file(&tmp_path);

    if is_prog && is_mp3 {
        match state.sc.fetch_audio_response(&stream_url, None).await {
            Ok(resp) => {
                if let Ok(bytes) = resp.bytes().await {
                    if !bytes.is_empty() && std::fs::write(&tmp_path, &bytes).is_ok() {
                        let _ = std::fs::rename(&tmp_path, &cache_path);
                        if cache_path.is_file() {
                            return serve_file(&cache_path, &headers, None);
                        }
                    }
                }
            }
            Err(e) => return json_error(StatusCode::BAD_GATEWAY, e),
        }
    }

    let ffmpeg = crate::paths::ffmpeg_path();
    if !ffmpeg.is_file() {
        return json_error(
            StatusCode::PRECONDITION_FAILED,
            "Bu parçanın önizlemesi HLS akışı kullanıyor; çalmak için ffmpeg.exe gerekli.",
        );
    }

    let mut cmd = tokio::process::Command::new(&ffmpeg);
    cmd.args(["-y", "-hide_banner", "-loglevel", "error", "-t", "45", "-i"])
        .arg(&stream_url)
        .args(["-vn", "-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3"])
        .arg(&tmp_path)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .stdin(std::process::Stdio::null())
        .kill_on_drop(true);
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000);

    let out = match cmd.output().await {
        Ok(o) => o,
        Err(e) => return json_error(StatusCode::INTERNAL_SERVER_ERROR, format!("Önizleme başlatılamadı: {}", e)),
    };
    if !out.status.success() || !tmp_path.is_file() {
        let _ = std::fs::remove_file(&tmp_path);
        return json_error(StatusCode::BAD_GATEWAY, "Parça akışı çözülemedi.");
    }
    if std::fs::rename(&tmp_path, &cache_path).is_err() {
        let _ = std::fs::remove_file(&tmp_path);
        return json_error(StatusCode::INTERNAL_SERVER_ERROR, "Önizleme önbelleğe alınamadı.");
    }

    serve_file(&cache_path, &headers, None)
}

#[derive(Deserialize)]
struct DownloadReq {
    #[serde(default)]
    items: Vec<DownloadItem>,
    #[serde(default)]
    urls: Vec<String>,
}

async fn download_selected(State(state): State<Shared>, Json(req): Json<DownloadReq>) -> Response {
    // Önce isteği doğrula: geçersiz istek "indiriliyor" bayrağını açık
    // bırakmasın (yoksa uygulama yeniden başlatılana kadar kilitlenir).
    let mut items = req.items;
    for url in req.urls {
        items.push(DownloadItem {
            url,
            title: String::new(),
            thumbnail: String::new(),
        });
    }
    items.retain(|i| !i.url.trim().is_empty());

    if items.is_empty() {
        return json_error(StatusCode::BAD_REQUEST, "İndirilecek şarkı seçilmedi.");
    }

    {
        let mut c = state.curator.write().await;
        if c.downloading {
            return json_error(StatusCode::CONFLICT, "Zaten indirme yapılıyor.");
        }
        // Bayrağı burada (senkron) kaldırıyoruz; aksi halde hızlı iki tıklama
        // iki paralel indirme başlatabilir.
        c.downloading = true;
        c.error = None;
    }

    let state_clone = Arc::clone(&state);
    tokio::spawn(async move {
        download::run_batch(state_clone, items).await;
    });

    Json(json!({ "success": true })).into_response()
}

fn is_temp_part_name(name: &str) -> bool {
    name.starts_with(".scs_") && name.ends_with(".part.mp3")
}

async fn trends_status(State(state): State<Shared>) -> Json<Value> {
    let status = state.curator.read().await.clone();
    let cfg = state.cfg.read().await.clone();
    let dir = cfg.target_dir();

    let mut files: Vec<Value> = Vec::new();
    if let Ok(entries) = std::fs::read_dir(&dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map(|e| e.eq_ignore_ascii_case("mp3")).unwrap_or(false) {
                let name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
                if is_temp_part_name(&name) {
                    continue;
                }
                let size = entry.metadata().map(|m| m.len()).unwrap_or(0);
                files.push(json!({
                    "name": name,
                    "size": size,
                    "cover_url": format!("/api/archive/cover/{}", urlencoding::encode(&name)),
                }));
            }
        }
    }
    files.sort_by(|a, b| {
        a["name"].as_str().unwrap_or("").cmp(b["name"].as_str().unwrap_or(""))
    });

    Json(json!({
        "state": status,
        "files": files,
        "folder": dir.display().to_string(),
    }))
}

async fn archive_cover(State(state): State<Shared>, AxPath(name): AxPath<String>) -> Response {
    let covers = crate::paths::covers_dir();

    // 1) Doğrudan kapak dosyası adı verilmiş olabilir.
    if let Some(p) = safe_join(&covers, &name) {
        if p.is_file() {
            return serve_file(&p, &HeaderMap::new(), None);
        }
    }

    // 2) Şarkı adı verilmişse meta kaydına bak.
    let meta = state.meta.read().await;
    if let Some(entry) = meta.get(&name) {
        if !entry.cover.is_empty() {
            if let Some(p) = safe_join(&covers, &entry.cover) {
                if p.is_file() {
                    return serve_file(&p, &HeaderMap::new(), None);
                }
            }
        }
    }
    drop(meta);

    // 3) Şarkının yanındaki .jpg kopyası.
    let dir = state.cfg.read().await.target_dir();
    let stem = Path::new(&name)
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default();
    for ext in ["jpg", "jpeg", "png"] {
        if let Some(p) = safe_join(&dir, &format!("{}.{}", stem, ext)) {
            if p.is_file() {
                return serve_file(&p, &HeaderMap::new(), None);
            }
        }
    }

    // 4) Varsayılan ikon.
    match Assets::get("icon.png") {
        Some(f) => ([(header::CONTENT_TYPE, "image/png")], f.data.to_vec()).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

#[derive(Deserialize)]
struct DeleteReq {
    filename: String,
}

async fn delete_archive(State(state): State<Shared>, Json(req): Json<DeleteReq>) -> Response {
    let dir = state.cfg.read().await.target_dir();
    let Some(path) = safe_join(&dir, &req.filename) else {
        return json_error(StatusCode::BAD_REQUEST, "Geçersiz dosya adı");
    };

    let stem = path
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default();

    let mut removed = Vec::new();
    if std::fs::remove_file(&path).is_ok() {
        removed.push(path.display().to_string());
    }
    for ext in ["jpg", "jpeg", "png"] {
        let sidecar = dir.join(format!("{}.{}", stem, ext));
        if sidecar.is_file() && std::fs::remove_file(&sidecar).is_ok() {
            removed.push(sidecar.display().to_string());
        }
    }

    {
        let mut meta = state.meta.write().await;
        if let Some(entry) = meta.remove(&req.filename) {
            if !entry.cover.is_empty() {
                let cover = crate::paths::covers_dir().join(&entry.cover);
                let _ = std::fs::remove_file(cover);
            }
        }
        save_meta(&meta);
    }

    Json(json!({ "success": true, "removed": removed })).into_response()
}

fn clear_archive_dir(
    dir: &Path,
    covers_dir: &Path,
    meta: &mut std::collections::HashMap<String, TrackMeta>,
) -> usize {
    let mut removed_tracks = 0usize;
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            if path
                .file_name()
                .and_then(|s| s.to_str())
                .map(is_temp_part_name)
                .unwrap_or(false)
            {
                continue;
            }
            let ext = path
                .extension()
                .and_then(|s| s.to_str())
                .map(|s| s.to_ascii_lowercase())
                .unwrap_or_default();
            if AUDIO_EXTS.contains(&ext.as_str()) {
                let stem = path
                    .file_stem()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_default();
                if std::fs::remove_file(&path).is_ok() {
                    removed_tracks += 1;
                }
                for img_ext in ["jpg", "jpeg", "png"] {
                    let sidecar = dir.join(format!("{stem}.{img_ext}"));
                    if sidecar.is_file() {
                        let _ = std::fs::remove_file(&sidecar);
                    }
                }
            }
        }
    }
    let _ = crate::download::cleanup_stale_parts(dir);
    for entry in meta.values() {
        if !entry.cover.is_empty() {
            let cov = covers_dir.join(&entry.cover);
            if cov.is_file() {
                let _ = std::fs::remove_file(cov);
            }
        }
    }
    meta.clear();
    removed_tracks
}

async fn clear_archive(State(state): State<Shared>) -> Response {
    if state.curator.read().await.downloading || state.upload_status.read().await.active {
        return json_error(
            StatusCode::CONFLICT,
            "Aktif indirme veya yükleme sürerken arşiv temizlenemez.",
        );
    }
    let dir = state.cfg.read().await.target_dir();
    let covers_dir = crate::paths::covers_dir();
    let removed = {
        let mut meta = state.meta.write().await;
        let count = clear_archive_dir(&dir, &covers_dir, &mut meta);
        save_meta(&meta);
        count
    };
    crate::paths::cleanup_preview_cache();
    Json(json!({ "success": true, "removed": removed })).into_response()
}

// -------------------------------------------------------------- kütüphane

const AUDIO_EXTS: &[&str] = &["mp3", "wav", "flac", "m4a"];

/// ID3 etiketi yalnızca MP3'e güvenle yazılabilir; FLAC/WAV/M4A'ya yazmak
/// dosyayı bozar.
fn is_mp3(path: &Path) -> bool {
    path.extension()
        .map(|e| e.eq_ignore_ascii_case("mp3"))
        .unwrap_or(false)
}

fn human_size(bytes: u64) -> String {
    format!("{:.1} MB", bytes as f64 / 1_048_576.0)
}

async fn my_tracks(State(state): State<Shared>) -> Json<Value> {
    let cfg = state.cfg.read().await.clone();
    let dir = cfg.target_dir();
    let meta = state.meta.read().await.clone();

    let mut tracks: Vec<Value> = Vec::new();
    if let Ok(entries) = std::fs::read_dir(&dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            let ext = path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            if !path.is_file() || !AUDIO_EXTS.contains(&ext.as_str()) {
                continue;
            }
            let name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
            if is_temp_part_name(&name) {
                continue;
            }
            let fmeta = entry.metadata().ok();
            let size = fmeta.as_ref().map(|m| m.len()).unwrap_or(0);
            let modified = fmeta
                .and_then(|m| m.modified().ok())
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or(0);
            let stem = path
                .file_stem()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_default();
            let smart_title = meta
                .get(&name)
                .map(|m| m.title.clone())
                .filter(|t| !t.is_empty())
                .unwrap_or_else(|| stem.clone());

            tracks.push(json!({
                "name": name,
                "smart_title": smart_title,
                "cover_url": format!("/api/archive/cover/{}", urlencoding::encode(&name)),
                "size": human_size(size),
                "bytes": size,
                "ext": ext.to_uppercase(),
                "modified": modified,
                "editable": ext == "mp3",
            }));
        }
    }
    // En yeni dosya en üstte.
    tracks.sort_by(|a, b| {
        b["modified"]
            .as_u64()
            .unwrap_or(0)
            .cmp(&a["modified"].as_u64().unwrap_or(0))
            .then_with(|| a["name"].as_str().unwrap_or("").cmp(b["name"].as_str().unwrap_or("")))
    });

    Json(json!({
        "tracks": tracks,
        "source_dir": dir.display().to_string(),
        "covers_dir": crate::paths::covers_dir().display().to_string(),
    }))
}

#[derive(Deserialize)]
struct RegenerateReq {
    #[serde(default)]
    filename: String,
    #[serde(default)]
    custom_title: String,
    #[serde(default)]
    style: Option<String>,
    #[serde(default)]
    prefix: Option<String>,
}

async fn regenerate(State(state): State<Shared>, Json(req): Json<RegenerateReq>) -> Response {
    let mut cfg = state.cfg.read().await.clone();
    if let Some(style) = req.style.clone() {
        if config::NAMING_STYLES.contains(&style.as_str()) {
            cfg.naming_style = style;
        }
    }
    if let Some(prefix) = req.prefix.clone() {
        cfg.naming_prefix = prefix;
    }

    let dir = cfg.target_dir();
    let targets: Vec<String> = if req.filename.trim().is_empty() {
        // Toplu yenileme yalnızca uygulamanın ürettiği MP3'lere dokunur:
        // meta kaydı olan ya da yanında aynı adlı kapak bulunan dosyalar.
        // Kullanıcının kendi müziği (ör. İndirilenler klasörü) etkilenmez.
        let meta = state.meta.read().await;
        let mut all = Vec::new();
        if let Ok(entries) = std::fs::read_dir(&dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if !path.is_file() || !is_mp3(&path) {
                    continue;
                }
                let name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
                if is_temp_part_name(&name) {
                    continue;
                }
                if meta.contains_key(&name) || path.with_extension("jpg").is_file() {
                    all.push(name);
                }
            }
        }
        all
    } else {
        if !is_mp3(Path::new(&req.filename)) {
            return json_error(
                StatusCode::BAD_REQUEST,
                "Yalnızca MP3 dosyalarının başlığı ve kapağı yenilenebilir.",
            );
        }
        vec![req.filename.clone()]
    };

    if targets.is_empty() {
        return json_error(StatusCode::NOT_FOUND, "Yenilenecek şarkı bulunamadı.");
    }

    let mut updated = 0usize;
    let mut errors: Vec<String> = Vec::new();

    for filename in &targets {
        match regenerate_one(&state, &cfg, filename, &req.custom_title).await {
            Ok(()) => updated += 1,
            Err(e) => errors.push(format!("{}: {}", filename, e)),
        }
    }

    Json(json!({
        "success": errors.is_empty(),
        "updated": updated,
        "errors": errors,
    }))
    .into_response()
}

async fn regenerate_one(
    state: &Shared,
    cfg: &Config,
    filename: &str,
    custom_title: &str,
) -> anyhow::Result<()> {
    let dir = cfg.target_dir();
    let Some(old_path) = safe_join(&dir, filename) else {
        anyhow::bail!("dosya yok");
    };
    if !old_path.is_file() || !is_mp3(&old_path) {
        anyhow::bail!("yalnızca MP3 dosyaları yenilenebilir");
    }
    let old_cover = state
        .meta
        .read()
        .await
        .get(filename)
        .map(|m| m.cover.clone())
        .unwrap_or_default();

    let stem = old_path
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| filename.to_string());

    // Yeni başlık: kullanıcı verdiyse o, yoksa akıllı üretim.
    let new_title = if custom_title.trim().is_empty() {
        let mut rng = state.rng.lock().unwrap();
        crate::titles::generate_smart_title(&stem, &cfg.naming_style, &cfg.naming_prefix, &mut rng)
    } else {
        custom_title.trim().to_string()
    };
    let new_title = download::sanitize_filename(&new_title);

    // Aynı isimde başka dosya varsa sonuna sayı ekle.
    let mut new_path = dir.join(format!("{}.mp3", new_title));
    let mut n = 1;
    while new_path.exists() && new_path != old_path {
        n += 1;
        new_path = dir.join(format!("{} {}.mp3", new_title, n));
    }

    let new_filename = new_path
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| format!("{}.mp3", new_title));

    if new_path != old_path {
        std::fs::rename(&old_path, &new_path)?;
        // Eski adla kalan yan kapak dosyaları yetim kalmasın.
        for ext in ["jpg", "jpeg", "png"] {
            let _ = std::fs::remove_file(dir.join(format!("{}.{}", stem, ext)));
        }
    }

    let new_stem = new_path
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| new_title.clone());

    // Yeni kapak üret.
    let cover_name = download::cover_filename(&new_filename);
    let cover_path = crate::paths::covers_dir().join(&cover_name);

    let pool_state = Arc::clone(state);
    let cover_target = cover_path.clone();
    let cover_res = tokio::task::spawn_blocking(move || {
        let mut pool = pool_state.art.lock().unwrap();
        let mut rng = pool_state.rng.lock().unwrap();
        crate::artwork::make_cover(&mut pool, &mut rng, &cover_target)
    })
    .await
    .unwrap_or_else(|e| Err(anyhow::anyhow!("kapak görevi çöktü: {}", e)));

    let mut cover_bytes = None;
    if cover_res.is_ok() {
        // Yan kopya, dosyanın gerçek adıyla eşleşmeli ("Başlık 2.mp3" → "Başlık 2.jpg").
        let _ = std::fs::copy(&cover_path, dir.join(format!("{}.jpg", new_stem)));
        cover_bytes = std::fs::read(&cover_path).ok();
        // Önbellekteki eski kapak artık kullanılmıyor.
        if !old_cover.is_empty() && old_cover != cover_name {
            let _ = std::fs::remove_file(crate::paths::covers_dir().join(&old_cover));
        }
    }

    // Etiketleri güncelle.
    let tag_path = new_path.clone();
    let tag_title = new_title.clone();
    tokio::task::spawn_blocking(move || {
        crate::id3::write_tags(
            &tag_path,
            &crate::id3::Tags {
                title: &tag_title,
                artist: "SoundCloud",
                album: "SC Studio",
                genre: "Phonk / Edit",
                cover: cover_bytes.as_deref(),
            },
        )
    })
    .await??;

    // Meta güncelle.
    {
        let mut meta = state.meta.write().await;
        if new_filename != filename {
            meta.remove(filename);
        }
        meta.insert(
            new_filename,
            TrackMeta {
                title: new_title.clone(),
                cover: if cover_res.is_ok() { cover_name } else { String::new() },
            },
        );
        save_meta(&meta);
    }

    Ok(())
}

#[derive(Deserialize)]
struct FolderSetReq {
    folder: String,
}

async fn set_folder(State(state): State<Shared>, Json(req): Json<FolderSetReq>) -> Response {
    let raw = req.folder.trim().to_string();
    let resolved = match raw.as_str() {
        "music" | "" => crate::paths::default_music_dir(),
        "downloads" => crate::paths::downloads_preset_dir(),
        "studio" => crate::paths::studio_preset_dir(),
        other => PathBuf::from(other),
    };

    if let Err(e) = crate::paths::ensure_dir(&resolved) {
        return json_error(
            StatusCode::BAD_REQUEST,
            format!("Klasör oluşturulamadı: {}", e),
        );
    }

    let preset = {
        let mut cfg = state.cfg.write().await;
        cfg.uploader_source_dir = resolved.display().to_string();
        let snapshot = cfg.clone();
        drop(cfg);
        let _ = config::save(&snapshot);
        snapshot.active_folder_preset()
    };

    Json(json!({
        "success": true,
        "folder": resolved.display().to_string(),
        "preset": preset,
    }))
    .into_response()
}

async fn export_paired(State(state): State<Shared>) -> Response {
    let dir = state.cfg.read().await.target_dir();
    let meta = state.meta.read().await.clone();
    let covers = crate::paths::covers_dir();

    let mut count = 0usize;
    for (name, entry) in meta.iter() {
        if entry.cover.is_empty() {
            continue;
        }
        let src = covers.join(&entry.cover);
        if !src.is_file() {
            continue;
        }
        let stem = Path::new(name)
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        let dst = dir.join(format!("{}.jpg", stem));
        if std::fs::copy(&src, &dst).is_ok() {
            count += 1;
        }
    }

    Json(json!({ "success": true, "count": count })).into_response()
}

async fn not_found() -> Response {
    (StatusCode::NOT_FOUND, "Bulunamadı").into_response()
}

// ============================================================ giriş / OAuth

async fn auth_status(State(state): State<Shared>) -> Json<Value> {
    let cfg = state.cfg.read().await.clone();
    let mut auth = state.auth.read().await.clone();

    // Süresi dolmak üzereyse sessizce yenile (refresh token tek kullanımlık).
    if auth.is_signed_in() {
        if let Ok(true) = crate::auth::refresh_if_needed(&cfg, &mut auth).await {
            *state.auth.write().await = auth.clone();
        }
    }
    Json(json!({
        "configured": cfg.oauth_configured(),
        "signed_in": auth.is_signed_in(),
        "username": auth.username,
        "user_id": auth.user_id,
        "avatar_url": auth.avatar_url,
        "permalink_url": auth.permalink_url,
        "onboarded": cfg.onboarded,
        "redirect_uri": cfg.sc_redirect_uri,
        "has_client_id": !cfg.oauth_client_id().is_empty(),
        "builtin": crate::config::Config::oauth_builtin(),
        "has_client_secret": !cfg.oauth_client_secret().is_empty(),
        "has_oauth_token": !auth.access_token.is_empty(),
    }))
}

async fn auth_start(State(state): State<Shared>) -> Response {
    let cfg = state.cfg.read().await.clone();
    if !cfg.oauth_configured() {
        return json_error(
            StatusCode::BAD_REQUEST,
            "SoundCloud uygulama bilgileri eksik. Ayarlar → SoundCloud Girişi bölümüne client_id ve client_secret girin.",
        );
    }
    let Some(port) = cfg.redirect_port() else {
        return json_error(
            StatusCode::BAD_REQUEST,
            "Yönlendirme adresi http://127.0.0.1:PORT/... biçiminde olmalı.",
        );
    };

    let verifier = crate::auth::random_token(48);
    let state_token = crate::auth::random_token(18);
    state.pending_auth.insert(&state_token, &verifier);
    let url = crate::auth::authorize_url(&cfg, &state_token, &verifier);

    let st = Arc::clone(&state);
    tokio::spawn(async move { listen_for_callback(st, port).await });
    open_in_browser(&url);

    Json(json!({ "success": true, "url": url })).into_response()
}

#[derive(Deserialize)]
struct ManualAuthReq {
    url: String,
}

async fn auth_manual(State(state): State<Shared>, Json(req): Json<ManualAuthReq>) -> Response {
    let (code, st) = match crate::auth::parse_redirect(req.url.trim()) {
        Ok(v) => v,
        Err(e) => return json_error(StatusCode::BAD_REQUEST, e.to_string()),
    };
    let Some(verifier) = state.pending_auth.take(&st) else {
        return json_error(
            StatusCode::BAD_REQUEST,
            "Bu giriş isteği bulunamadı veya süresi doldu. Yeniden 'SoundCloud ile giriş yap' deneyin.",
        );
    };
    let cfg = state.cfg.read().await.clone();
    match crate::auth::complete_login(&cfg, &code, &verifier).await {
        Ok(a) => {
            let name = a.username.clone();
            *state.auth.write().await = a;
            Json(json!({ "success": true, "username": name })).into_response()
        }
        Err(e) => json_error(StatusCode::BAD_REQUEST, e.to_string()),
    }
}

async fn auth_logout(State(state): State<Shared>) -> Response {
    let _ = crate::auth::clear();
    state
        .login_pending
        .store(false, std::sync::atomic::Ordering::SeqCst);
    *state.auth.write().await = Default::default();
    let _ = send_ui(&state, crate::ui::UiEvent::ScClearSession);
    Json(json!({ "success": true })).into_response()
}

#[derive(Deserialize)]
struct TokenLoginReq {
    token: String,
}

fn normalize_oauth_cookie_token(raw: &str) -> String {
    let mut s = raw.trim().trim_matches('"').trim_matches('\'').trim();
    if let Some(rest) = s.strip_prefix("oauth_token=") {
        s = rest.trim();
    }
    if let Some(rest) = s.strip_prefix("OAuth ").or_else(|| s.strip_prefix("oauth ")) {
        s = rest.trim();
    }
    if let Some((head, _)) = s.split_once(';') {
        s = head.trim();
    }
    s.to_string()
}

async fn auth_token_login(State(state): State<Shared>, Json(req): Json<TokenLoginReq>) -> Response {
    let token = normalize_oauth_cookie_token(&req.token);
    if token.len() < 12 {
        return json_error(StatusCode::BAD_REQUEST, "Geçerli bir SoundCloud oauth_token girin.");
    }
    let client = match reqwest::Client::builder()
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36")
        .build()
    {
        Ok(c) => c,
        Err(e) => return json_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
    };
    let resp = match client
        .get("https://api-v2.soundcloud.com/me")
        .header(reqwest::header::AUTHORIZATION, format!("OAuth {token}"))
        .send()
        .await
    {
        Ok(r) => r,
        Err(e) => return json_error(StatusCode::BAD_GATEWAY, format!("SoundCloud bağlantı hatası: {e}")),
    };
    if !resp.status().is_success() {
        return json_error(StatusCode::UNAUTHORIZED, "Token geçersiz veya süresi dolmuş.");
    }
    let Ok(me) = resp.json::<Value>().await else {
        return json_error(StatusCode::BAD_GATEWAY, "SoundCloud profil yanıtı okunamadı.");
    };
    let id = me
        .get("id")
        .and_then(|v| v.as_u64().map(|n| n.to_string()).or_else(|| v.as_str().map(str::to_string)))
        .unwrap_or_default();
    let username = me
        .get("username")
        .and_then(|v| v.as_str())
        .or_else(|| me.get("full_name").and_then(|v| v.as_str()))
        .unwrap_or("")
        .trim()
        .to_string();
    if id.is_empty() || username.is_empty() {
        return json_error(StatusCode::BAD_GATEWAY, "SoundCloud kullanıcı adı alınamadı.");
    }

    let auth = crate::auth::AuthState {
        user_id: id,
        username: username.clone(),
        avatar_url: me.get("avatar_url").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        permalink_url: me.get("permalink_url").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        web_session: true,
        ..Default::default()
    };
    let _ = crate::auth::save(&auth);
    *state.auth.write().await = auth;
    state
        .login_pending
        .store(false, std::sync::atomic::Ordering::SeqCst);
    let _ = send_ui(&state, crate::ui::UiEvent::ScSetOauthCookie(token));

    Json(json!({ "success": true, "username": username })).into_response()
}

fn open_in_browser(url: &str) {
    #[cfg(windows)]
    {
        let _ = std::process::Command::new("cmd")
            .args(["/C", "start", "", url])
            .spawn();
    }
    #[cfg(not(windows))]
    {
        let _ = std::process::Command::new("xdg-open").arg(url).spawn();
    }
}

/// Tarayıcının geri dönüşünü yakalayan tek kullanımlık HTTP dinleyicisi.
async fn listen_for_callback(state: Shared, port: u16) {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let listener = match tokio::net::TcpListener::bind(("127.0.0.1", port)).await {
        Ok(l) => l,
        Err(_) => {
            // Port meşgul: kullanıcı yine de adresi elle yapıştırabilir.
            return;
        }
    };

    let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(300);
    loop {
        let Ok(Ok((mut sock, _))) = tokio::time::timeout_at(deadline, listener.accept()).await else {
            return;
        };
        let mut buf = vec![0u8; 8192];
        let n = match sock.read(&mut buf).await {
            Ok(n) => n,
            Err(_) => continue,
        };
        let req = String::from_utf8_lossy(&buf[..n]).to_string();
        let path = req
            .lines()
            .next()
            .and_then(|l| l.split_whitespace().nth(1))
            .unwrap_or("");

        if !path.contains("code=") && !path.contains("error=") {
            let _ = sock.write_all(b"HTTP/1.1 404 Not Found\r\ncontent-length: 0\r\n\r\n").await;
            continue;
        }

        let target = format!("http://127.0.0.1:{}{}", port, path);
        let (title, body, ok) = match crate::auth::parse_redirect(&target) {
            Ok((code, st)) => {
                let cfg = state.cfg.read().await.clone();
                match state.pending_auth.take(&st) {
                    Some(verifier) => match crate::auth::complete_login(&cfg, &code, &verifier).await {
                        Ok(a) => {
                            let name = a.username.clone();
                            *state.auth.write().await = a;
                            // Kullanıcı tarayıcıdan uygulamaya geri dönsün.
                            let _ = send_ui(&state, crate::ui::UiEvent::FocusMain);
                            (
                                "Giriş başarılı",
                                format!("<b>{}</b> olarak giriş yapıldı.", name),
                                true,
                            )
                        }
                        Err(e) => ("Giriş başarısız", e.to_string(), false),
                    },
                    None => (
                        "Oturum bulunamadı",
                        "Bu giriş isteği zaman aşımına uğramış. Uygulamadan yeniden deneyin.".into(),
                        false,
                    ),
                }
            }
            Err(e) => ("Geçersiz yanıt", e.to_string(), false),
        };

        let html = callback_page(title, &body, ok);
        let resp = format!(
            "HTTP/1.1 200 OK\r\ncontent-type: text/html; charset=utf-8\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
            html.len(),
            html
        );
        let _ = sock.write_all(resp.as_bytes()).await;
        let _ = sock.flush().await;
        return;
    }
}

fn callback_page(title: &str, body: &str, ok: bool) -> String {
    let accent = if ok { "#22c55e" } else { "#ef4444" };
    format!(
        r#"<!doctype html><html lang="tr"><head><meta charset="utf-8"><title>{title}</title>
<style>
html,body{{height:100%;margin:0}}
body{{background:#0f0f0f;color:#fff;font:15px/1.6 -apple-system,"Segoe UI",Roboto,sans-serif;
display:grid;place-items:center}}
.card{{max-width:420px;padding:38px 34px;border:1px solid #262626;border-radius:16px;
background:#161616;text-align:center}}
.mark{{width:52px;height:52px;border-radius:14px;margin:0 auto 18px;display:grid;place-items:center;
background:{accent}1f;color:{accent};font-size:26px}}
h1{{font-size:17px;margin:0 0 8px;font-weight:700}}
p{{margin:0;color:#9a9a9a;font-size:13.5px}}
small{{display:block;margin-top:20px;color:#5f5f5f;font-size:12px}}
</style></head><body><div class="card">
<div class="mark">{icon}</div>
<h1>{title}</h1><p>{body}</p>
<small>Bu sekmeyi kapatıp uygulamaya dönebilirsiniz.</small>
</div></body></html>"#,
        icon = if ok { "✓" } else { "!" },
    )
}

// ============================================================ ilk kurulum

async fn onboarding_complete(State(state): State<Shared>) -> Response {
    let mut cfg = state.cfg.write().await;
    cfg.onboarded = true;
    let snapshot = cfg.clone();
    drop(cfg);
    if let Err(e) = config::save(&snapshot) {
        return json_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string());
    }
    Json(json!({ "success": true })).into_response()
}

// ============================================================ tarayıcı

async fn browser_open(State(state): State<Shared>) -> Response {
    send_ui(&state, crate::ui::UiEvent::OpenBrowser(None))
}

/// "SoundCloud ile giriş yap": uygulama kaydı (client_id/secret) yoksa
/// giriş, uygulama içi tarayıcıda doğrudan soundcloud.com üzerinden yapılır.
async fn auth_web_login(State(state): State<Shared>) -> Response {
    state
        .login_pending
        .store(true, std::sync::atomic::Ordering::SeqCst);
    send_ui(
        &state,
        crate::ui::UiEvent::OpenBrowser(Some(crate::ui::SIGNIN_URL.to_string())),
    )
}

fn send_ui(state: &Shared, event: crate::ui::UiEvent) -> Response {
    let tx = state.ui_tx.lock().ok().and_then(|g| g.clone());
    match tx {
        Some(proxy) => match proxy.send_event(event) {
            Ok(_) => Json(json!({ "success": true })).into_response(),
            Err(_) => json_error(StatusCode::INTERNAL_SERVER_ERROR, "Arayüz kapalı."),
        },
        None => json_error(StatusCode::INTERNAL_SERVER_ERROR, "Arayüz hazır değil."),
    }
}

async fn browser_url(State(state): State<Shared>) -> Json<Value> {
    let url = state.browser_url.lock().map(|u| u.clone()).unwrap_or_default();
    let open = state.browser_open.load(std::sync::atomic::Ordering::Relaxed);
    Json(json!({ "url": url, "open": open }))
}

#[derive(Deserialize)]
struct ScNavReq {
    target: String,
}

async fn sc_nav(State(state): State<Shared>, Json(req): Json<ScNavReq>) -> Response {
    let target = req.target.trim().to_string();
    let valid = matches!(target.as_str(), "back" | "forward" | "reload")
        || target.starts_with("https://soundcloud.com")
        || target.starts_with("https://artists.soundcloud.com");
    if !valid {
        return json_error(StatusCode::BAD_REQUEST, "Geçersiz SoundCloud adresi.");
    }
    send_ui(&state, crate::ui::UiEvent::ScNavigate(target))
}

fn default_true() -> bool {
    true
}

#[derive(Deserialize)]
struct MonetizeSweepReq {
    #[serde(default = "default_true")]
    resubmit_rejected: bool,
    #[serde(default = "default_true")]
    submit_unsubmitted: bool,
}

async fn sc_monetize_sweep(
    State(state): State<Shared>,
    body: Option<Json<MonetizeSweepReq>>,
) -> Response {
    if state.upload_status.read().await.active {
        return json_error(StatusCode::CONFLICT, "Şu anda başka bir yükleme veya monetize işlemi sürüyor.");
    }
    let req = body.map(|b| b.0).unwrap_or(MonetizeSweepReq {
        resubmit_rejected: true,
        submit_unsubmitted: true,
    });
    let artist_hint = state.auth.read().await.username.clone();
    {
        let mut st = state.upload_status.write().await;
        st.active = true;
        st.ok = false;
        st.error = None;
        st.filename = "Monetize".into();
        st.stage = "Monetize kontrol ediliyor (yeni + reddedilenler)...".into();
    }
    let job = crate::ui::MonetizeJob {
        target_title: None,
        resubmit_rejected: req.resubmit_rejected,
        submit_unsubmitted: req.submit_unsubmitted,
        artist_hint,
        intro_note: String::new(),
    };
    let resp = send_ui(&state, crate::ui::UiEvent::ScStartMonetize(job));
    if !resp.status().is_success() {
        let mut st = state.upload_status.write().await;
        st.active = false;
        st.stage.clear();
        st.error = Some("Dahili SoundCloud penceresi hazır değil.".into());
    }
    resp
}

async fn upload_status(State(state): State<Shared>) -> Json<Value> {
    let st = state.upload_status.read().await.clone();
    Json(json!(st))
}

async fn cancel_upload(State(state): State<Shared>) -> Response {
    {
        let mut st = state.upload_status.write().await;
        st.active = false;
        st.ok = false;
        st.error = None;
        st.stage = "Yükleme durduruldu.".into();
    }
    let _ = send_ui(&state, crate::ui::UiEvent::ScCancelUpload);
    Json(json!({ "success": true })).into_response()
}

#[derive(Deserialize)]
struct UploadTrackReq {
    filename: String,
    #[serde(default)]
    title: String,
    #[serde(default)]
    sharing: String,
    #[serde(default)]
    mode: String,
    #[serde(default)]
    skip_monetize: bool,
}

async fn archive_upload(State(state): State<Shared>, Json(req): Json<UploadTrackReq>) -> Response {
    if state.upload_status.read().await.active {
        return json_error(StatusCode::CONFLICT, "Şu anda başka bir yükleme devam ediyor.");
    }
    let cfg = state.cfg.read().await.clone();
    let dir = cfg.target_dir();
    let Some(path) = safe_join(&dir, req.filename.trim()) else {
        return json_error(StatusCode::BAD_REQUEST, "Geçersiz dosya adı.");
    };
    if !path.is_file() {
        return json_error(StatusCode::NOT_FOUND, "Ses dosyası bulunamadı.");
    }

    let meta_entry = state.meta.read().await.get(&req.filename).cloned();
    let stem = path
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default();
    let title = if req.title.trim().is_empty() {
        meta_entry
            .as_ref()
            .map(|m| m.title.clone())
            .filter(|t| !t.is_empty())
            .unwrap_or_else(|| stem.clone())
    } else {
        req.title.trim().to_string()
    };

    // Kapak dosyasını bul: meta.cover → ses yanındaki kapak.
    let mut cover_path: Option<PathBuf> = None;
    if let Some(m) = meta_entry.as_ref() {
        if !m.cover.is_empty() {
            let p = crate::paths::covers_dir().join(&m.cover);
            if p.is_file() {
                cover_path = Some(p);
            }
        }
    }
    if cover_path.is_none() {
        for ext in ["jpg", "jpeg", "png"] {
            let cand = dir.join(format!("{}.{}", stem, ext));
            if cand.is_file() {
                cover_path = Some(cand);
                break;
            }
        }
    }

    let audio_bytes = match tokio::task::spawn_blocking({
        let p = path.clone();
        move || std::fs::read(&p)
    })
    .await
    {
        Ok(Ok(b)) if !b.is_empty() => b,
        _ => return json_error(StatusCode::INTERNAL_SERVER_ERROR, "Ses dosyası okunamadı."),
    };

    let cover_bytes = match cover_path {
        Some(cp) => tokio::task::spawn_blocking(move || std::fs::read(&cp))
            .await
            .ok()
            .and_then(|r| r.ok()),
        None => None,
    };

    // Resmi OAuth access_token varsa doğrudan API ile yükle.
    let mode = if req.mode.trim().is_empty() { "auto" } else { req.mode.trim() };
    let sharing = if req.sharing == "private" { "private" } else { "public" };
    let auth = state.auth.read().await.clone();
    if (mode == "api" || mode == "auto") && !auth.access_token.is_empty() {
        {
            let mut st = state.upload_status.write().await;
            st.active = true;
            st.ok = false;
            st.error = None;
            st.filename = req.filename.clone();
            st.stage = "SoundCloud API'ye yükleniyor...".into();
        }
        let (boundary, body) = build_track_multipart(
            &title,
            sharing,
            &req.filename,
            &audio_bytes,
            cover_bytes.as_deref(),
        );
        let client = reqwest::Client::new();
        let res = client
            .post("https://api.soundcloud.com/tracks")
            .header("Authorization", format!("OAuth {}", auth.access_token))
            .header(
                "Content-Type",
                format!("multipart/form-data; boundary={}", boundary),
            )
            .body(body)
            .send()
            .await;

        let mut st = state.upload_status.write().await;
        st.active = false;
        match res {
            Ok(resp) if resp.status().is_success() => {
                let v: Value = resp.json().await.unwrap_or_default();
                let link = v.get("permalink_url").and_then(Value::as_str).unwrap_or("");
                st.ok = true;
                st.stage = if link.is_empty() {
                    "✓ SoundCloud'a yüklendi!".into()
                } else {
                    format!("✓ Yüklendi: {}", link)
                };
                return Json(json!({ "success": true, "mode": "api", "permalink_url": link })).into_response();
            }
            Ok(resp) => {
                let code = resp.status();
                let err_txt = resp.text().await.unwrap_or_default();
                let msg = format!("SoundCloud API hatası ({}): {}", code, err_txt.chars().take(180).collect::<String>());
                st.ok = false;
                st.error = Some(msg.clone());
                st.stage.clear();
                return json_error(StatusCode::BAD_GATEWAY, msg);
            }
            Err(e) => {
                let msg = format!("Ağ hatası: {}", e);
                st.ok = false;
                st.error = Some(msg.clone());
                st.stage.clear();
                return json_error(StatusCode::BAD_GATEWAY, msg);
            }
        }
    }

    // Varsayılan yol: dahili SoundCloud WebView2 sekmesine dosya + başlık + kapak enjekte et.
    let audio_b64 = tokio::task::spawn_blocking(move || encode_b64(&audio_bytes))
        .await
        .unwrap_or_default();
    let cover_b64 = match cover_bytes {
        Some(cb) => tokio::task::spawn_blocking(move || encode_b64(&cb)).await.ok(),
        None => None,
    };

    {
        let mut st = state.upload_status.write().await;
        st.active = true;
        st.ok = false;
        st.error = None;
        st.filename = req.filename.clone();
        st.stage = "SoundCloud yükleme sayfası hazırlanıyor...".into();
    }

    let job = crate::ui::UploadJob {
        filename: req.filename,
        title,
        audio_b64,
        cover_b64,
        auto_submit: true,
        sharing: sharing.to_string(),
        skip_monetize: req.skip_monetize,
    };
    let resp = send_ui(&state, crate::ui::UiEvent::ScInjectUpload(job));
    if !resp.status().is_success() {
        let mut st = state.upload_status.write().await;
        st.active = false;
        st.stage.clear();
        st.error = Some("Dahili SoundCloud penceresi hazır değil.".into());
    }
    resp
}

fn encode_b64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0];
        let b1 = *chunk.get(1).unwrap_or(&0);
        let b2 = *chunk.get(2).unwrap_or(&0);
        let n = ((b0 as u32) << 16) | ((b1 as u32) << 8) | b2 as u32;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if chunk.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    out
}

fn build_track_multipart(
    title: &str,
    sharing: &str,
    filename: &str,
    audio: &[u8],
    cover: Option<&[u8]>,
) -> (String, Vec<u8>) {
    let boundary = format!("----SCStudioUpload{}", std::process::id());
    let mut body = Vec::with_capacity(audio.len() + cover.map(|c| c.len()).unwrap_or(0) + 1024);

    let push_text = |buf: &mut Vec<u8>, name: &str, val: &str| {
        buf.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n"
            )
            .as_bytes(),
        );
    };

    push_text(&mut body, "track[title]", title);
    push_text(&mut body, "track[sharing]", sharing);
    push_text(&mut body, "track[genre]", "Phonk");

    let safe_fn = filename.replace('"', "");
    body.extend_from_slice(
        format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"track[asset_data]\"; filename=\"{safe_fn}\"\r\nContent-Type: audio/mpeg\r\n\r\n"
        )
        .as_bytes(),
    );
    body.extend_from_slice(audio);
    body.extend_from_slice(b"\r\n");

    if let Some(cov) = cover {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"track[artwork_data]\"; filename=\"cover.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n"
            )
            .as_bytes(),
        );
        body.extend_from_slice(cov);
        body.extend_from_slice(b"\r\n");
    }

    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());
    (boundary, body)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_mp3_is_editable() {
        assert!(is_mp3(Path::new("Parca.mp3")));
        assert!(is_mp3(Path::new("PARCA.MP3")));
        for name in ["kayit.flac", "kayit.wav", "kayit.m4a", "kayit", "mp3"] {
            assert!(!is_mp3(Path::new(name)), "{name}");
        }
    }

    #[test]
    fn safe_join_blocks_traversal() {
        let root = std::env::temp_dir();
        assert!(safe_join(&root, "../x.mp3").is_none());
        assert!(safe_join(&root, r"..\x.mp3").is_none());
    }

    #[test]
    fn preview_cache_path_is_deterministic_mp3() {
        let a = preview_cache_path("https://soundcloud.com/a/b");
        let b = preview_cache_path("https://soundcloud.com/a/b");
        let c = preview_cache_path("https://soundcloud.com/a/c");
        assert_eq!(a, b);
        assert_ne!(a, c);
        assert_eq!(a.extension().and_then(|s| s.to_str()), Some("mp3"));
    }

    #[test]
    fn temp_part_filter_excludes_only_scs_part_files() {
        assert!(is_temp_part_name(".scs_9921.part.mp3"));
        assert!(!is_temp_part_name("track.mp3"));
        assert!(!is_temp_part_name("part.mp3"));
    }

    #[test]
    fn base64_matches_rfc4648_vectors() {
        assert_eq!(encode_b64(b""), "");
        assert_eq!(encode_b64(b"f"), "Zg==");
        assert_eq!(encode_b64(b"fo"), "Zm8=");
        assert_eq!(encode_b64(b"foo"), "Zm9v");
        assert_eq!(encode_b64(b"Man"), "TWFu");
    }

    #[test]
    fn multipart_contains_title_audio_and_cover() {
        let (boundary, body) = build_track_multipart("Test Track", "public", "test.mp3", b"MP3DATA", Some(b"JPG"));
        let txt = String::from_utf8_lossy(&body);
        assert!(txt.contains("track[title]"));
        assert!(txt.contains("Test Track"));
        assert!(txt.contains("track[asset_data]"));
        assert!(txt.contains("track[artwork_data]"));
        assert!(txt.ends_with(&format!("--{boundary}--\r\n")));
    }

    #[test]
    fn monetize_sweep_defaults_to_both_true() {
        let req: MonetizeSweepReq = serde_json::from_str("{}").unwrap();
        assert!(req.resubmit_rejected);
        assert!(req.submit_unsubmitted);
    }

    #[test]
    fn clear_curator_candidates_empties_state() {
        let mut st = crate::state::CuratorStatus {
            candidates: vec![crate::state::Candidate {
                id: "1".into(),
                title: "Test".into(),
                uploader: "ZYRO".into(),
                url: "https://soundcloud.com/zyro/test".into(),
                thumbnail: String::new(),
                duration_str: "1:30".into(),
                date_str: "1d".into(),
                days_ago: 1.0,
                views: 100,
                likes: 10,
                score: 90,
                reasons: vec![],
            }],
            completed_urls: vec!["https://soundcloud.com/zyro/test".into()],
            failed_urls: vec!["https://soundcloud.com/zyro/fail".into()],
            progress: 0.5,
            error: Some("err".into()),
            ..Default::default()
        };
        let cleared = clear_curator_candidates(&mut st);
        assert_eq!(cleared, 1);
        assert!(st.candidates.is_empty());
        assert!(st.completed_urls.is_empty());
        assert!(st.failed_urls.is_empty());
        assert!(st.error.is_none());
        assert_eq!(st.progress, 0.0);
    }

    #[test]
    fn clear_archive_dir_deletes_audio_sidecars_and_meta() {
        let base = std::env::temp_dir().join(format!("scs_clear_test_{}", std::process::id()));
        let covers = base.join("covers");
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(&covers).unwrap();

        std::fs::write(base.join("track1.mp3"), b"mp3").unwrap();
        std::fs::write(base.join("track1.jpg"), b"jpg").unwrap();
        std::fs::write(base.join(".scs_1.part.mp3"), b"part").unwrap();
        std::fs::write(base.join("keep_notes.txt"), b"txt").unwrap();
        std::fs::write(covers.join("cov1.jpg"), b"cov").unwrap();

        let mut meta = std::collections::HashMap::new();
        meta.insert(
            "track1.mp3".to_string(),
            TrackMeta {
                title: "Track 1".into(),
                cover: "cov1.jpg".into(),
            },
        );

        let removed = clear_archive_dir(&base, &covers, &mut meta);
        assert_eq!(removed, 1);
        assert!(meta.is_empty());
        assert!(!base.join("track1.mp3").exists());
        assert!(!base.join("track1.jpg").exists());
        assert!(!base.join(".scs_1.part.mp3").exists());
        assert!(!covers.join("cov1.jpg").exists());
        assert!(base.join("keep_notes.txt").exists());
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn normalize_oauth_cookie_token_strips_prefixes() {
        assert_eq!(normalize_oauth_cookie_token("2-123456-7890-abcdef"), "2-123456-7890-abcdef");
        assert_eq!(normalize_oauth_cookie_token("  \"oauth_token=2-123456-7890-abcdef; path=/\"  "), "2-123456-7890-abcdef");
        assert_eq!(normalize_oauth_cookie_token("OAuth 2-123456-7890-abcdef"), "2-123456-7890-abcdef");
    }

    #[test]
    fn upload_track_req_defaults_skip_monetize_false() {
        let req: UploadTrackReq = serde_json::from_str(r#"{"filename":"x.mp3"}"#).unwrap();
        assert!(!req.skip_monetize);
        let bulk: UploadTrackReq = serde_json::from_str(r#"{"filename":"x.mp3","skip_monetize":true}"#).unwrap();
        assert!(bulk.skip_monetize);
    }
}
