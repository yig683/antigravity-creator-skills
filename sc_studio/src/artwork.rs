//! Kapak görseli havuzu ve 800x800 JPEG üretimi.
//!
//! Orijinal uygulama 200+ gerçek SoundCloud kapağını `artwork_pool` içinde
//! taşıyor ve her indirmede tekrarsız olarak birini atıyordu. Aynı davranış
//! korunuyor; ek olarak kullanıcı kendi görsellerini
//! `%APPDATA%\SoundCloudStudio\artwork_pool` klasörüne atabiliyor.

use crate::assets::Assets;
use crate::rng::Rng;
use anyhow::{anyhow, Result};
use image::{ImageEncoder, RgbImage};
use std::collections::HashSet;
use std::path::{Path, PathBuf};

pub struct ArtworkPool {
    embedded: Vec<String>,
    user: Vec<PathBuf>,
    used: HashSet<String>,
}

impl ArtworkPool {
    pub fn load() -> Self {
        let embedded: Vec<String> = Assets::iter()
            .filter(|p| p.starts_with("artwork_pool/"))
            .filter(|p| {
                let lower = p.to_lowercase();
                lower.ends_with(".jpg") || lower.ends_with(".jpeg") || lower.ends_with(".png")
                    || lower.ends_with(".webp")
            })
            .map(|p| p.to_string())
            .collect();

        let user = list_user_artwork();
        let used = load_history();

        Self {
            embedded,
            user,
            used,
        }
    }

    pub fn count(&self) -> usize {
        self.embedded.len() + self.user.len()
    }

    fn key_embedded(name: &str) -> String {
        format!("embedded:{}", name)
    }

    fn key_user(path: &Path) -> String {
        format!(
            "user:{}",
            path.file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default()
        )
    }

    /// Tekrarsız seçim: havuzdaki tüm görseller tükenmeden hiçbiri tekrar
    /// seçilmez. Tükenince geçmiş sıfırlanır.
    pub fn pick_bytes(&mut self, rng: &mut Rng) -> Result<Vec<u8>> {
        for _ in 0..2 {
            let mut candidates: Vec<(String, Option<PathBuf>)> = Vec::new();
            for name in &self.embedded {
                if !self.used.contains(&Self::key_embedded(name)) {
                    candidates.push((name.clone(), None));
                }
            }
            for path in &self.user {
                if !self.used.contains(&Self::key_user(path)) {
                    candidates.push((String::new(), Some(path.clone())));
                }
            }

            if candidates.is_empty() {
                self.used.clear();
                continue;
            }

            let idx = rng.below(candidates.len());
            let (name, file) = candidates.swap_remove(idx);
            let key = match &file {
                Some(p) => Self::key_user(p),
                None => Self::key_embedded(&name),
            };
            self.used.insert(key);

            let bytes = match file {
                Some(p) => std::fs::read(&p)?,
                None => Assets::get(&name)
                    .ok_or_else(|| anyhow!("gömülü görsel okunamadı: {}", name))?
                    .data
                    .to_vec(),
            };
            return Ok(bytes);
        }
        Err(anyhow!("kapak havuzu boş"))
    }

    pub fn save_history(&self) {
        let list: Vec<&String> = self.used.iter().collect();
        let _ = crate::config::save_atomic(&crate::paths::artwork_history_file(), &list);
    }
}

fn list_user_artwork() -> Vec<PathBuf> {
    let dir = crate::paths::user_artwork_dir();
    let Ok(entries) = std::fs::read_dir(&dir) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let ext = path
            .extension()
            .map(|e| e.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        if matches!(ext.as_str(), "jpg" | "jpeg" | "png" | "webp") {
            out.push(path);
        }
    }
    out.sort();
    out
}

fn load_history() -> HashSet<String> {
    let path = crate::paths::artwork_history_file();
    let Ok(text) = std::fs::read_to_string(path) else {
        return HashSet::new();
    };
    serde_json::from_str::<Vec<String>>(&text)
        .map(|v| v.into_iter().collect())
        .unwrap_or_default()
}

/// Havuzdan rastgele bir görsel seçip 800x800 JPEG olarak yazar.
pub fn make_cover(pool: &mut ArtworkPool, rng: &mut Rng, out_path: &Path) -> Result<()> {
    if let Some(parent) = out_path.parent() {
        crate::paths::ensure_dir(parent)?;
    }

    let bytes = pool.pick_bytes(rng)?;
    // Tekrarsız seçim geçmişi her kapaktan sonra diske yazılmalı, yoksa
    // uygulama her açılışta aynı görselleri yeniden kullanmaya başlar.
    pool.save_history();
    let img = image::load_from_memory(&bytes);

    let rgb: RgbImage = match img {
        Ok(img) => img
            .resize_to_fill(800, 800, image::imageops::FilterType::Lanczos3)
            .to_rgb8(),
        Err(_) => RgbImage::from_pixel(800, 800, image::Rgb([12, 12, 16])),
    };

    write_jpeg(&rgb, out_path, 92)
}

fn write_jpeg(img: &RgbImage, out_path: &Path, quality: u8) -> Result<()> {
    let file = std::fs::File::create(out_path)?;
    let mut writer = std::io::BufWriter::new(file);
    image::codecs::jpeg::JpegEncoder::new_with_quality(&mut writer, quality)
        .write_image(img.as_raw(), img.width(), img.height(), image::ExtendedColorType::Rgb8)?;
    Ok(())
}
