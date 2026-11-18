//! İndirme hattı: akış çözümleme → ffmpeg ile 320k MP3 → kapak → ID3.

use crate::id3::{self, Tags};
use crate::sc::{StreamSource, Track};
use crate::state::{save_meta, AppState, TrackMeta};
use crate::titles::generate_smart_title;
use anyhow::{anyhow, Context, Result};
use serde::Deserialize;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, BufReader};

#[derive(Debug, Clone, Deserialize)]
pub struct DownloadItem {
    pub url: String,
    #[serde(default)]
    pub title: String,
    /// Arayüzden gelen kapak adresi; şu an kullanılmıyor ama protokolün
    /// parçası olduğu için alan korunuyor.
    #[serde(default)]
    #[allow(dead_code)]
    pub thumbnail: String,
}

const UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)";

/// Windows'ta dosya adında yasak olan karakterleri temizler.
pub fn sanitize_filename(name: &str) -> String {
    let cleaned: String = name
        .chars()
        .filter(|c| !matches!(c, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*' | '\0'))
        .collect();
    let cleaned = cleaned.trim().trim_end_matches('.').trim().to_string();
    // Uzun başlıklar yol sınırını aşmasın.
    let limited: String = cleaned.chars().take(120).collect();
    if limited.is_empty() {
        "Track".to_string()
    } else {
        limited
    }
}

pub fn fnv_hex(input: &str) -> String {
    let mut hash: u64 = 0xcbf29ce484222325;
    for b in input.as_bytes() {
        hash ^= *b as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{:012x}", hash & 0xffff_ffff_ffff)
}

pub fn cover_filename(track_filename: &str) -> String {
    format!("cover_{}.jpg", fnv_hex(track_filename))
}

/// Yarıda kalmış indirmelerin geçici dosyalarını siler.
///
/// Uygulama indirme sırasında kapatılırsa `.scs_<pid>.part.mp3` kalabilir;
/// bir sonraki açılışta temizleniyor.
pub fn cleanup_stale_parts(dir: &Path) -> usize {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return 0;
    };
    let mut removed = 0;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with(".scs_") && name.ends_with(".part.mp3") {
            if std::fs::remove_file(entry.path()).is_ok() {
                removed += 1;
            }
        }
    }
    removed
}

fn unique_mp3_path(dir: &Path, base: &str) -> PathBuf {
    let mut candidate = dir.join(format!("{}.mp3", base));
    let mut n = 1;
    while candidate.exists() {
        n += 1;
        candidate = dir.join(format!("{} {}.mp3", base, n));
    }
    candidate
}

/// Akışı MP3 olarak kaydeder.
///
/// Kaynak zaten MP3 ise ses verisi **olduğu gibi kopyalanır**: yeniden
/// kodlamak kalite eklemez, yalnızca dosyayı büyütür ve kayıp ekler. AAC
/// kaynaklar MP3'e çevrilir; ikinci bir kayıplı kodlamada en az kaybı
/// yüksek bit hızı verdiği için 320 kbps kullanılır.
///
/// Not (Kasım 2026): SoundCloud tam parçaları artık yalnızca AAC (96/160k)
/// veriyor; MP3 akışı sadece 30 sn önizlemelerde kaldı. Kopyalama yolu
/// SoundCloud MP3'ü geri getirirse diye duruyor.
async fn ffmpeg_to_mp3(
    state: &Arc<AppState>,
    source: &StreamSource,
    out: &Path,
    duration_secs: f64,
    index: usize,
    total: usize,
) -> Result<()> {
    if source.mp3 {
        match run_ffmpeg(state, &source.url, out, duration_secs, index, total, true).await {
            Ok(()) => return Ok(()),
            // Kopyalama nadiren başarısız olur (bozuk bölüm vb.); o zaman
            // yeniden kodlamaya düş.
            Err(_) => {
                let _ = std::fs::remove_file(out);
            }
        }
    }
    run_ffmpeg(state, &source.url, out, duration_secs, index, total, false).await
}

async fn run_ffmpeg(
    state: &Arc<AppState>,
    url: &str,
    out: &Path,
    duration_secs: f64,
    index: usize,
    total: usize,
    copy: bool,
) -> Result<()> {
    let ffmpeg = crate::paths::ffmpeg_path();
    if !ffmpeg.is_file() {
        return Err(anyhow!(
            "ffmpeg.exe bulunamadı. Uygulamanın yanına koyun veya PATH'e ekleyin. \
             İndirme adresi: https://www.gyan.dev/ffmpeg/builds/ (release-essentials)"
        ));
    }

    let codec: &[&str] = if copy {
        &["-c:a", "copy"]
    } else {
        &["-c:a", "libmp3lame", "-b:a", "320k"]
    };

    let mut cmd = tokio::process::Command::new(&ffmpeg);
    cmd.arg("-y")
        .arg("-hide_banner")
        .arg("-loglevel")
        .arg("error")
        .arg("-nostats")
        .arg("-progress")
        .arg("pipe:1")
        .arg("-user_agent")
        .arg(UA)
        .arg("-i")
        .arg(url)
        .arg("-vn")
        .args(codec)
        .arg("-map_metadata")
        .arg("-1")
        .arg("-id3v2_version")
        .arg("0")
        .arg("-write_id3v1")
        .arg("0")
        .arg("-f")
        .arg("mp3")
        .arg(out)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .stdin(std::process::Stdio::null());

    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn().context("ffmpeg başlatılamadı")?;

    let stderr_task = child.stderr.take().map(|stderr| {
        tokio::spawn(async move {
            use tokio::io::AsyncReadExt;
            let mut buf = Vec::new();
            let mut r = stderr;
            let _ = r.read_to_end(&mut buf).await;
            buf
        })
    });

    if let Some(stdout) = child.stdout.take() {
        let state = Arc::clone(state);
        tokio::spawn(async move {
            let mut lines = BufReader::new(stdout).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                if let Some(rest) = line.strip_prefix("out_time_us=") {
                    if let (Ok(us), true) = (rest.trim().parse::<f64>(), duration_secs > 0.0) {
                        let ratio = (us / 1_000_000.0 / duration_secs).clamp(0.0, 1.0);
                        // Toplu indirmede çubuk tüm listenin ilerlemesini göstersin.
                        let overall = ((index.saturating_sub(1)) as f64 + ratio) / total.max(1) as f64;
                        state.curator.write().await.progress = overall as f32;
                    }
                }
            }
        });
    }

    let mut cancel_poll = tokio::time::interval(std::time::Duration::from_millis(120));
    let status = loop {
        if state.cancel_download.load(std::sync::atomic::Ordering::SeqCst) {
            let _ = child.start_kill();
            let _ = child.wait().await;
            return Err(anyhow!("İndirme durduruldu"));
        }
        tokio::select! {
            res = child.wait() => break res?,
            _ = cancel_poll.tick() => {}
        }
    };

    let stderr_bytes = match stderr_task {
        Some(t) => t.await.unwrap_or_default(),
        None => Vec::new(),
    };
    if !status.success() {
        let err = String::from_utf8_lossy(&stderr_bytes);
        let msg = err.lines().last().unwrap_or("bilinmeyen ffmpeg hatası");
        return Err(anyhow!("dönüştürme başarısız: {}", msg.trim()));
    }
    if !out.is_file() || std::fs::metadata(out)?.len() < 1024 {
        return Err(anyhow!("çıktı dosyası oluşmadı"));
    }
    Ok(())
}

/// Tek bir parçayı indirir, başlık + kapak + etiket uygular.
pub async fn download_one(state: &Arc<AppState>, item: &DownloadItem, index: usize, total: usize) -> Result<PathBuf> {
    use std::sync::atomic::Ordering;

    if state.cancel_download.load(Ordering::SeqCst) {
        return Err(anyhow!("İndirme durduruldu"));
    }

    let cfg = state.cfg.read().await.clone();
    let target_dir = cfg.target_dir();
    crate::paths::ensure_dir(&target_dir)?;

    {
        let mut c = state.curator.write().await;
        c.current = if item.title.is_empty() { item.url.clone() } else { item.title.clone() };
        c.current_url = item.url.clone();
        c.stage = "Çözümleniyor".into();
        c.batch_index = index;
        c.batch_total = total;
        c.log = format!(
            "[{}/{}] Parça bilgisi alınıyor: {}",
            index,
            total,
            if item.title.is_empty() { &item.url } else { &item.title }
        );
    }

    // 1) Parça meta verisi
    let value = state.sc.resolve(&item.url).await?;
    let track: Track = Track::from_json(&value).ok_or_else(|| anyhow!("parça çözümlenemedi"))?;

    if state.cancel_download.load(Ordering::SeqCst) {
        return Err(anyhow!("İndirme durduruldu"));
    }

    // 2) Akış adresi
    let source = state
        .sc
        .stream_source(&track)
        .await
        .map_err(|e| anyhow!(e))?;

    // 3) Başlık
    let raw_title = if !track.title.is_empty() {
        track.title.clone()
    } else if !item.title.is_empty() {
        item.title.clone()
    } else {
        format!("Track_{}", index)
    };

    let base_name = {
        let mut rng = state.rng.lock().unwrap();
        let generated = generate_smart_title(&raw_title, &cfg.naming_style, &cfg.naming_prefix, &mut rng);
        sanitize_filename(&generated)
    };

    let final_path = unique_mp3_path(&target_dir, &base_name);
    let final_name = final_path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| format!("{}.mp3", base_name));

    // 4) İndirme + dönüştürme (geçici dosyaya)
    let tmp = target_dir.join(format!(".scs_{}.part.mp3", std::process::id()));
    let _ = std::fs::remove_file(&tmp);

    {
        let mut c = state.curator.write().await;
        c.log = format!(
            "[{}/{}] {}: {}",
            index,
            total,
            if source.mp3 { "İndiriliyor" } else { "320 kbps MP3'e çevriliyor" },
            final_name
        );
        c.progress = (index.saturating_sub(1)) as f32 / total.max(1) as f32;
        c.current = final_name.clone();
        c.current_url = item.url.clone();
        c.stage = if source.mp3 { "MP3 İndiriliyor".into() } else { "320k MP3".into() };
        c.batch_index = index;
        c.batch_total = total;
    }

    let result = ffmpeg_to_mp3(state, &source, &tmp, track.duration_secs, index, total).await;
    if let Err(e) = result {
        let _ = std::fs::remove_file(&tmp);
        return Err(e);
    }

    std::fs::rename(&tmp, &final_path)?;

    // 5) Kapak
    {
        let mut c = state.curator.write().await;
        c.stage = "Kapak".into();
    }
    let cover_name = cover_filename(&final_name);
    let cover_path = crate::paths::covers_dir().join(&cover_name);

    let pool_state = Arc::clone(state);
    let cover_target = cover_path.clone();
    let cover_ok = tokio::task::spawn_blocking(move || {
        let mut pool = pool_state.art.lock().unwrap();
        let mut rng = pool_state.rng.lock().unwrap();
        crate::artwork::make_cover(&mut pool, &mut rng, &cover_target)
    })
    .await
    .unwrap_or_else(|e| Err(anyhow!("kapak görevi çöktü: {}", e)));

    let mut cover_bytes: Option<Vec<u8>> = None;
    if cover_ok.is_ok() {
        // Şarkının yanına da bir kopya bırak (orijinal davranış).
        let final_stem = Path::new(&final_name)
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| base_name.clone());
        let sidecar = target_dir.join(format!("{}.jpg", final_stem));
        let _ = std::fs::copy(&cover_path, &sidecar);
        cover_bytes = std::fs::read(&cover_path).ok();
    }

    // 6) ID3 etiketleri
    {
        let mut c = state.curator.write().await;
        c.stage = "ID3".into();
    }
    let title_for_tag = base_name.clone();
    let artist = if track.uploader.is_empty() {
        "SoundCloud".to_string()
    } else {
        track.uploader.clone()
    };
    let tag_path = final_path.clone();
    let tag_title = title_for_tag.clone();
    let tag_artist = artist.clone();
    tokio::task::spawn_blocking(move || {
        id3::write_tags(
            &tag_path,
            &Tags {
                title: &tag_title,
                artist: &tag_artist,
                album: "SC Studio",
                genre: "Phonk / Edit",
                cover: cover_bytes.as_deref(),
            },
        )
    })
    .await??;

    // 7) Meta kaydı
    {
        let mut meta = state.meta.write().await;
        meta.insert(
            final_name.clone(),
            TrackMeta {
                title: base_name.clone(),
                cover: if cover_ok.is_ok() { cover_name } else { String::new() },
            },
        );
        save_meta(&meta);
    }

    state.curator.write().await.progress = index as f32 / total.max(1) as f32;
    Ok(final_path)
}

/// Seçilen parçaları sırayla indirir.
pub async fn run_batch(state: Arc<AppState>, items: Vec<DownloadItem>) {
    use std::sync::atomic::Ordering;

    state.cancel_download.store(false, Ordering::SeqCst);
    {
        let mut c = state.curator.write().await;
        c.downloading = true;
        c.error = None;
        c.progress = 0.0;
        c.stage = "Hazırlanıyor".into();
        c.current.clear();
        c.current_url.clear();
        c.completed_urls.clear();
        c.failed_urls.clear();
        c.batch_index = 0;
        c.batch_total = items.len();
    }

    let total = items.len();
    let mut ok = 0usize;
    let mut failed = 0usize;
    let mut cancelled = false;
    let mut last_error: Option<String> = None;

    for (i, item) in items.iter().enumerate() {
        if state.cancel_download.load(Ordering::SeqCst) {
            cancelled = true;
            break;
        }
        match download_one(&state, item, i + 1, total).await {
            Ok(_) => {
                ok += 1;
                state.curator.write().await.completed_urls.push(item.url.clone());
            }
            Err(e) => {
                if state.cancel_download.load(Ordering::SeqCst) {
                    cancelled = true;
                    break;
                }
                failed += 1;
                last_error = Some(e.to_string());
                state.curator.write().await.failed_urls.push(item.url.clone());
            }
        }
    }

    let mut c = state.curator.write().await;
    c.downloading = false;
    c.current.clear();
    c.current_url.clear();
    c.stage.clear();
    c.batch_index = 0;
    c.batch_total = 0;
    if cancelled {
        c.progress = 0.0;
        c.log = format!("İndirme durduruldu ({} parça tamamlandı).", ok);
        c.error = None;
    } else if failed == 0 {
        c.progress = 1.0;
        c.log = format!("✓ İndirme tamamlandı! {} şarkı yeni başlık ve kapakla hazırlandı.", ok);
        c.error = None;
    } else {
        c.progress = 1.0;
        c.log = format!("İndirme bitti: {} şarkı hazır, {} şarkı indirilemedi.", ok, failed);
        c.error = last_error;
    }
}
