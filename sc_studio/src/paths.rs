//! Dosya sistemi yerleşimi.
//!
//! Orijinal uygulama `config.json`, `seen_tracks.json` gibi dosyaları exe'nin
//! yanına yazıyordu; bu, uygulama `Program Files` gibi korumalı bir klasöre
//! kurulduğunda tamamen bozuluyordu. Burada tüm durum `%APPDATA%` altında,
//! üretilen müzik ise kullanıcının `Müzik` klasöründe tutuluyor.

use std::path::{Path, PathBuf};

pub const APP_DIR_NAME: &str = "SoundCloudStudio";
pub const MUSIC_DIR_NAME: &str = "SoundCloud_Dinleme_Arsivi";

fn home() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

pub fn exe_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .unwrap_or_else(|| PathBuf::from("."))
}

/// Uygulama durumu (ayarlar, geçmiş, kapak önbelleği).
pub fn data_dir() -> PathBuf {
    let base = std::env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join("AppData").join("Roaming"));
    base.join(APP_DIR_NAME)
}

pub fn ensure_dir(p: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(p)
}

pub fn default_music_dir() -> PathBuf {
    home().join("Music").join(MUSIC_DIR_NAME)
}

pub fn downloads_preset_dir() -> PathBuf {
    home().join("Downloads").join("my_tracks")
}

pub fn studio_preset_dir() -> PathBuf {
    data_dir().join("my_tracks")
}

pub fn covers_dir() -> PathBuf {
    data_dir().join("covers")
}

pub fn preview_cache_dir() -> PathBuf {
    data_dir().join("preview_cache")
}

pub fn cleanup_preview_cache() {
    let dir = preview_cache_dir();
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_file() {
                let _ = std::fs::remove_file(p);
            }
        }
    }
}

/// Kullanıcının kendi eklediği kapak görselleri.
pub fn user_artwork_dir() -> PathBuf {
    data_dir().join("artwork_pool")
}

pub fn config_file() -> PathBuf {
    data_dir().join("config.json")
}

pub fn seen_file() -> PathBuf {
    data_dir().join("seen_tracks.json")
}

pub fn meta_file() -> PathBuf {
    data_dir().join("track_metadata.json")
}

pub fn auth_file() -> PathBuf {
    data_dir().join("auth.json")
}

/// Son çalışan SoundCloud `client_id` önbelleği.
pub fn client_id_cache_file() -> PathBuf {
    data_dir().join("client_id.txt")
}

pub fn artwork_history_file() -> PathBuf {
    data_dir().join("artwork_history.json")
}

/// ffmpeg'i şu sırayla arar: exe yanı → PATH → yaygın kurulum yerleri.
pub fn ffmpeg_path() -> PathBuf {
    let local = exe_dir().join(if cfg!(windows) { "ffmpeg.exe" } else { "ffmpeg" });
    if local.is_file() {
        return local;
    }
    if let Some(paths) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&paths) {
            let cand = dir.join(if cfg!(windows) { "ffmpeg.exe" } else { "ffmpeg" });
            if cand.is_file() {
                return cand;
            }
        }
    }
    for guess in [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ] {
        let p = PathBuf::from(guess);
        if p.is_file() {
            return p;
        }
    }
    local
}

/// Başlangıçta gerekli klasörleri hazırla.
pub fn bootstrap() -> std::io::Result<()> {
    for dir in [data_dir(), covers_dir(), user_artwork_dir()] {
        ensure_dir(&dir)?;
    }
    Ok(())
}
