//! Kapak görseli havuzu ve 800x800 JPEG üretimi.
//!
//! Orijinal uygulama 200+ gerçek SoundCloud kapağını `artwork_pool` içinde
//! taşıyor ve her indirmede tekrarsız olarak birini atıyordu. Aynı davranış
//! korunuyor; ek olarak kullanıcı kendi görsellerini
//! `%APPDATA%\SoundCloudStudio\artwork_pool` klasörüne atabiliyor.
//!
//! Tekrarı azaltmak için üç katman var:
//!   1. **Kayan pencere:** bir görsel, havuzun neredeyse tamamı dönmeden
//!      yeniden seçilmez (eskiden havuz bitince geçmiş tek seferde sıfırlanıyordu).
//!   2. **İkizler:** havuzdaki neredeyse aynı görseller (aynı kapağın farklı
//!      parçalardaki kopyaları) birlikte "kullanıldı" sayılır.
//!   3. **Çeşitlendirme:** her kapağa kırpma/renk/tane uygulanır (`coverfx`).

use crate::assets::Assets;
use crate::coverfx;
pub use crate::coverfx::CoverStyle;
use crate::rng::Rng;
use anyhow::{anyhow, Result};
use image::{ImageEncoder, RgbImage};
use std::collections::{HashMap, HashSet, VecDeque};
use std::path::{Path, PathBuf};

/// Havuzun bu kadarı "yakın geçmiş" dışında bırakılır: bir görsel en az
/// `havuz - WINDOW_MARGIN` kapak boyunca tekrar seçilmez.
const WINDOW_MARGIN: usize = 12;

/// Birbirine çok benzeyen görsel grupları (bir tanesi kullanılınca diğerleri de "kullanıldı" sayılır).
const TWIN_GROUPS: &[&[&str]] = &[
    &["x_2231011673.jpg", "x_2235959549.jpg"],
    &["x_2255105588.jpg", "x_2255107877.jpg", "x_2255114600.jpg"],
    &["x_2315843783.jpg", "x_2315844392.jpg"],
    &["x_2324824280.jpg", "x_2324879822.jpg", "x_2324899823.jpg"],
    &["x_2378737517.jpg", "x_2378737775.jpg"],
    &["x_2420090214.jpg", "x_2420090994.jpg"],
    &["x_2421873525.jpg", "x_2426433918.jpg"],
];

pub struct ArtworkPool {
    embedded: Vec<String>,
    user: Vec<PathBuf>,
    /// Son seçilenler (eskiden yeniye): tekrarı önleyen kayan pencere.
    recent: VecDeque<String>,
    /// Anahtar → aynı görselin ikizleri (kendisi hariç).
    twins: HashMap<String, Vec<String>>,
}

enum Choice {
    Embedded(String),
    User(PathBuf),
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

        Self::from_parts(embedded, list_user_artwork(), load_history())
    }

    fn from_parts(embedded: Vec<String>, user: Vec<PathBuf>, recent: VecDeque<String>) -> Self {
        let mut twins: HashMap<String, Vec<String>> = HashMap::new();
        for group in TWIN_GROUPS {
            let keys: Vec<String> = group
                .iter()
                .map(|f| Self::key_embedded(&format!("artwork_pool/{}", f)))
                .collect();
            for k in &keys {
                twins.insert(k.clone(), keys.iter().filter(|o| *o != k).cloned().collect());
            }
        }
        Self { embedded, user, recent, twins }
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

    fn push_recent(&mut self, key: &str) {
        self.recent.retain(|k| k != key);
        self.recent.push_back(key.to_string());
    }

    /// Kayan pencereye göre bir sonraki görseli seçer ve kullanıldı olarak işaretler.
    fn choose(&mut self, rng: &mut Rng) -> Option<(String, Choice)> {
        let total = self.count();
        if total == 0 {
            return None;
        }
        let window = total.saturating_sub(WINDOW_MARGIN).max(1);

        for _ in 0..2 {
            while self.recent.len() > window {
                self.recent.pop_front();
            }
            let used: HashSet<&str> = self.recent.iter().map(|s| s.as_str()).collect();
            let mut candidates: Vec<(String, Choice)> = Vec::new();
            for name in &self.embedded {
                let key = Self::key_embedded(name);
                if !used.contains(key.as_str()) {
                    candidates.push((key, Choice::Embedded(name.clone())));
                }
            }
            for path in &self.user {
                let key = Self::key_user(path);
                if !used.contains(key.as_str()) {
                    candidates.push((key, Choice::User(path.clone())));
                }
            }

            if candidates.is_empty() {
                self.recent.clear();
                continue;
            }

            let idx = rng.below(candidates.len());
            let (key, choice) = candidates.swap_remove(idx);
            let twins = self.twins.get(&key).cloned().unwrap_or_default();
            self.push_recent(&key);
            for t in twins {
                self.push_recent(&t);
            }
            return Some((key, choice));
        }
        None
    }

    /// Tekrarsız seçim: bir görsel, havuz dönmeden yeniden seçilmez.
    pub fn pick_bytes(&mut self, rng: &mut Rng) -> Result<Vec<u8>> {
        let (_, choice) = self.choose(rng).ok_or_else(|| anyhow!("kapak havuzu boş"))?;
        match choice {
            Choice::User(p) => Ok(std::fs::read(&p)?),
            Choice::Embedded(name) => Ok(Assets::get(&name)
                .ok_or_else(|| anyhow!("gömülü görsel okunamadı: {}", name))?
                .data
                .to_vec()),
        }
    }

    pub fn save_history(&self) {
        let list: Vec<&String> = self.recent.iter().collect();
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

fn load_history() -> VecDeque<String> {
    let path = crate::paths::artwork_history_file();
    let Ok(text) = std::fs::read_to_string(path) else {
        return VecDeque::new();
    };
    let list: Vec<String> = serde_json::from_str(&text).unwrap_or_default();
    let mut seen = HashSet::new();
    list.into_iter().filter(|k| seen.insert(k.clone())).collect()
}

/// Havuzdan bir görsel seçip, `style`a göre çeşitlendirerek 800x800 JPEG olarak yazar.
pub fn make_cover(pool: &mut ArtworkPool, rng: &mut Rng, out_path: &Path, style: CoverStyle) -> Result<()> {
    make_cover_inner(pool, rng, out_path, style, true)
}

fn make_cover_inner(
    pool: &mut ArtworkPool,
    rng: &mut Rng,
    out_path: &Path,
    style: CoverStyle,
    persist_history: bool,
) -> Result<()> {
    if let Some(parent) = out_path.parent() {
        crate::paths::ensure_dir(parent)?;
    }

    let bytes = pool.pick_bytes(rng)?;
    // Seçim geçmişi her kapaktan sonra diske yazılmalı, yoksa uygulama her
    // açılışta aynı görselleri yeniden kullanmaya başlar.
    if persist_history {
        pool.save_history();
    }

    let rgb: RgbImage = match image::load_from_memory(&bytes) {
        Ok(img) => coverfx::render(&img, style, rng),
        Err(_) => RgbImage::from_pixel(coverfx::SIZE, coverfx::SIZE, image::Rgb([12, 12, 16])),
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

#[cfg(test)]
mod tests {
    use super::*;

    fn pool_of(names: &[&str]) -> ArtworkPool {
        let embedded = names.iter().map(|n| format!("artwork_pool/{}", n)).collect();
        ArtworkPool::from_parts(embedded, Vec::new(), VecDeque::new())
    }

    fn key_of(c: &Choice) -> String {
        match c {
            Choice::Embedded(n) => n.clone(),
            Choice::User(p) => p.display().to_string(),
        }
    }

    #[test]
    fn no_repeat_within_window() {
        let names: Vec<String> = (0..60).map(|i| format!("img_{i}.jpg")).collect();
        let refs: Vec<&str> = names.iter().map(|s| s.as_str()).collect();
        let mut pool = pool_of(&refs);
        let mut rng = Rng::from_seed(42);
        let window = 60 - WINDOW_MARGIN;
        let mut picks: Vec<String> = Vec::new();
        for _ in 0..400 {
            let (_, c) = pool.choose(&mut rng).unwrap();
            picks.push(key_of(&c));
        }
        // Aynı görsel, pencere boyunca asla tekrar etmemeli.
        for i in 0..picks.len() {
            for j in (i + 1)..(i + window).min(picks.len()) {
                assert_ne!(picks[i], picks[j], "tekrar: {} ve {}. seçim", i, j);
            }
        }
        // Havuzun tamamı dönüyor (hepsi en az bir kez seçildi).
        let distinct: HashSet<&String> = picks.iter().collect();
        assert_eq!(distinct.len(), 60);
    }

    #[test]
    fn twins_are_never_picked_close_together() {
        let mut names: Vec<String> = (0..40).map(|i| format!("img_{i}.jpg")).collect();
        names.push("x_2255105588.jpg".into());
        names.push("x_2255107877.jpg".into());
        names.push("x_2255114600.jpg".into());
        let refs: Vec<&str> = names.iter().map(|s| s.as_str()).collect();
        let mut pool = pool_of(&refs);
        let mut rng = Rng::from_seed(5);
        let twin_names = ["x_2255105588.jpg", "x_2255107877.jpg", "x_2255114600.jpg"];
        let mut last_twin_pick: Option<usize> = None;
        for i in 0..300 {
            let (_, c) = pool.choose(&mut rng).unwrap();
            let k = key_of(&c);
            if twin_names.iter().any(|t| k.ends_with(t)) {
                if let Some(prev) = last_twin_pick {
                    // Üç ikizden herhangi biri, arka arkaya ikizlerden biri sayılacak
                    // kadar yakın aralıkta seçilmemeli (pencerenin yarısından fazla ara).
                    assert!(i - prev > 20, "ikizler çok yakın seçildi: {} -> {}", prev, i);
                }
                last_twin_pick = Some(i);
            }
        }
        assert!(last_twin_pick.is_some());
    }

    #[test]
    fn tiny_and_empty_pools_do_not_panic() {
        let mut rng = Rng::from_seed(1);
        let mut empty = pool_of(&[]);
        assert!(empty.choose(&mut rng).is_none());
        let mut one = pool_of(&["a.jpg"]);
        for _ in 0..5 {
            assert!(one.choose(&mut rng).is_some());
        }
        let mut few = pool_of(&["a.jpg", "b.jpg", "c.jpg"]);
        for _ in 0..20 {
            assert!(few.choose(&mut rng).is_some());
        }
    }

    #[test]
    fn history_order_is_kept_and_deduplicated() {
        let mut pool = pool_of(&["a.jpg", "b.jpg", "c.jpg"]);
        pool.push_recent("k1");
        pool.push_recent("k2");
        pool.push_recent("k1");
        let order: Vec<&str> = pool.recent.iter().map(|s| s.as_str()).collect();
        assert_eq!(order, vec!["k2", "k1"]);
    }

    /// Görsel inceleme için örnek kapaklar üretir (normal test çalıştırmasında atlanır):
    /// `SCS_SAMPLE_DIR=... cargo test --release render_samples -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn render_samples() {
        let Ok(dir) = std::env::var("SCS_SAMPLE_DIR") else { return };
        std::fs::create_dir_all(&dir).unwrap();
        let mut names: Vec<String> = Assets::iter()
            .filter(|p| p.starts_with("artwork_pool/"))
            .map(|p| p.to_string())
            .collect();
        names.sort();
        let mut rng = Rng::from_seed(2026);
        let started = std::time::Instant::now();
        let mut renders = 0;
        for (n, idx) in [0usize, 27, 55, 83, 111, 139, 167, 195].iter().enumerate() {
            let bytes = Assets::get(&names[*idx]).unwrap().data.to_vec();
            let img = image::load_from_memory(&bytes).unwrap();
            for (label, style, count) in [
                ("a_orig", CoverStyle::Original, 1),
                ("b_var", CoverStyle::Varied, 5),
                ("c_bold", CoverStyle::Bold, 3),
            ] {
                for k in 0..count {
                    let out = coverfx::render(&img, style, &mut rng);
                    renders += 1;
                    write_jpeg(&out, &Path::new(&dir).join(format!("s{n}_{label}{k}.jpg")), 88).unwrap();
                }
            }
        }
        println!("{} kapak, kapak başına ~{} ms", renders, started.elapsed().as_millis() / renders);
    }

    #[test]
    fn make_cover_writes_distinct_800px_jpegs() {
        let dir = std::env::temp_dir().join(format!("scs_cover_test_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        for style in [CoverStyle::Original, CoverStyle::Varied, CoverStyle::Bold] {
            let mut pool = pool_of(&["x_2231011673.jpg", "x_2255105588.jpg", "x_2315843783.jpg", "x_2378737517.jpg"]);
            let mut rng = Rng::from_seed(77);
            let a = dir.join(format!("a_{style:?}.jpg"));
            let b = dir.join(format!("b_{style:?}.jpg"));
            make_cover_inner(&mut pool, &mut rng, &a, style, false).unwrap();
            make_cover_inner(&mut pool, &mut rng, &b, style, false).unwrap();
            let ia = image::open(&a).unwrap();
            assert_eq!((ia.width(), ia.height()), (coverfx::SIZE, coverfx::SIZE));
            assert_ne!(std::fs::read(&a).unwrap(), std::fs::read(&b).unwrap(), "{style:?}: iki kapak aynı");
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn bundled_twin_files_exist_in_assets() {
        // Sabit listedeki dosya adları gerçek havuzla eşleşmeli (yazım hatasını yakalar).
        for group in TWIN_GROUPS {
            for f in *group {
                assert!(
                    Assets::get(&format!("artwork_pool/{}", f)).is_some(),
                    "havuzda yok: {f}"
                );
            }
        }
    }
}
