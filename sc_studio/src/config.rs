//! Kalıcı ayarlar.
//!
//! Orijinal uygulama arayüzdeki filtreleri hiç kaydetmiyordu; her açılışta
//! varsayılana dönüyordu. Burada tüm seçimler diske yazılıyor.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const DEFAULT_CHANNELS: &[&str] = &[
    "https://soundcloud.com/bora-868621288/tracks",
    "https://soundcloud.com/me0o0/tracks",
    "https://soundcloud.com/kewzy-613918745/tracks",
    "https://soundcloud.com/d3n_z/tracks",
    "https://soundcloud.com/arda-dogan-995997823/tracks",
    "https://soundcloud.com/userkyuv/tracks",
    "https://soundcloud.com/reverox/tracks",
    "https://soundcloud.com/jigsawdaemon/tracks",
    "https://soundcloud.com/phonkinh0/tracks",
    "https://soundcloud.com/arda-do-an-439781546/tracks",
    "https://soundcloud.com/big-chunk-193729735/tracks",
];

/// Derleme zamanında verilen SoundCloud uygulama kimliği (bkz. `oauth_client_id`).
const BUILTIN_CLIENT_ID: Option<&str> = option_env!("SCS_SC_CLIENT_ID");
const BUILTIN_CLIENT_SECRET: Option<&str> = option_env!("SCS_SC_CLIENT_SECRET");

pub const NAMING_STYLES: &[&str] = &[
    "smart_random",
    "slowed",
    "hardtekk",
    "super_slowed",
    "phonk",
    "pitched",
];

pub const SOURCE_TYPES: &[&str] = &[
    "my_likes",
    "curated_creators",
    "hardtekk",
    "phonk",
    "slowed_reverb",
    "all_viral",
    "custom_url",
];

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    pub channels: Vec<String>,
    pub naming_style: String,
    pub naming_prefix: String,
    /// Şarkıların kaydedileceği klasör. Boşsa `Müzik/SoundCloud_Dinleme_Arsivi`.
    pub uploader_source_dir: String,
    pub min_score: i32,
    pub min_views: i64,
    pub max_days: f64,
    pub track_count: usize,
    pub source_type: String,
    pub custom_input: String,
    /// SoundCloud API anahtarı. Boşsa ilk istekte otomatik alınır.
    pub client_id: String,

    /// İlk kurulum (tanıtım + giriş) tamamlandı mı?
    pub onboarded: bool,

    /// "SoundCloud ile giriş" uygulama kimliği (soundcloud.com/you/apps).
    pub sc_client_id: String,
    pub sc_client_secret: String,
    /// Kayıtlı yönlendirme adresiyle BİREBİR aynı olmalı.
    pub sc_redirect_uri: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            channels: DEFAULT_CHANNELS.iter().map(|s| s.to_string()).collect(),
            naming_style: "smart_random".into(),
            naming_prefix: String::new(),
            uploader_source_dir: String::new(),
            min_score: 65,
            min_views: 10_000,
            max_days: 7.0,
            track_count: 5,
            source_type: "curated_creators".into(),
            custom_input: String::new(),
            client_id: String::new(),
            onboarded: false,
            sc_client_id: String::new(),
            sc_client_secret: String::new(),
            sc_redirect_uri: "http://127.0.0.1:47821/oauth/callback".into(),
        }
    }
}

impl Config {
    pub fn sanitized(mut self) -> Self {
        if self.channels.is_empty() {
            self.channels = DEFAULT_CHANNELS.iter().map(|s| s.to_string()).collect();
        }
        if !NAMING_STYLES.contains(&self.naming_style.as_str()) {
            self.naming_style = "smart_random".into();
        }
        if !SOURCE_TYPES.contains(&self.source_type.as_str()) {
            self.source_type = "curated_creators".into();
        }
        self.track_count = self.track_count.clamp(1, 50);
        self.min_score = self.min_score.clamp(0, 100);
        self.min_views = self.min_views.max(0);
        if !self.max_days.is_finite() || self.max_days < 0.0 {
            self.max_days = 0.0;
        }
        self
    }

    /// Giriş akışı için gereken alanlar dolu mu?
    pub fn oauth_configured(&self) -> bool {
        !self.oauth_client_id().is_empty()
            && !self.oauth_client_secret().is_empty()
            && !self.sc_redirect_uri.trim().is_empty()
    }

    /// Kullanıcının ayarlara girdiği kimlik; yoksa derlemeye gömülü olan.
    ///
    /// Ürün sahibi SoundCloud uygulamasını bir kez kaydeder ve derlerken
    /// `SCS_SC_CLIENT_ID` / `SCS_SC_CLIENT_SECRET` ortam değişkenlerini verir;
    /// böylece son kullanıcı hiçbir şey girmeden "SoundCloud ile giriş yap"
    /// varsayılan tarayıcıda açılır. Gömülü değerler config.json'a yazılmaz.
    pub fn oauth_client_id(&self) -> &str {
        let own = self.sc_client_id.trim();
        if own.is_empty() {
            BUILTIN_CLIENT_ID.unwrap_or("").trim()
        } else {
            own
        }
    }

    pub fn oauth_client_secret(&self) -> &str {
        let own = self.sc_client_secret.trim();
        if own.is_empty() {
            BUILTIN_CLIENT_SECRET.unwrap_or("").trim()
        } else {
            own
        }
    }

    /// Derlemeye gömülü SoundCloud uygulama kimliği var mı?
    pub fn oauth_builtin() -> bool {
        BUILTIN_CLIENT_ID.map_or(false, |s| !s.trim().is_empty())
            && BUILTIN_CLIENT_SECRET.map_or(false, |s| !s.trim().is_empty())
    }

    /// Yönlendirme adresinin portu (loopback akışı için).
    pub fn redirect_port(&self) -> Option<u16> {
        let raw = self.sc_redirect_uri.trim();
        let rest = raw.strip_prefix("http://")?;
        let authority = rest.split('/').next()?;
        let port = authority.rsplit_once(':')?.1;
        port.parse::<u16>().ok()
    }

    /// Şarkıların gerçekten yazılacağı klasör.
    pub fn target_dir(&self) -> PathBuf {
        let raw = self.uploader_source_dir.trim();
        if raw.is_empty() {
            return crate::paths::default_music_dir();
        }
        let p = PathBuf::from(raw);
        if p.is_dir() {
            p
        } else {
            crate::paths::default_music_dir()
        }
    }
}

pub fn load() -> Config {
    let path = crate::paths::config_file();
    match std::fs::read_to_string(&path) {
        Ok(text) => serde_json::from_str::<Config>(&text)
            .map(|c| c.sanitized())
            .unwrap_or_default(),
        Err(_) => Config::default(),
    }
}

/// Atomik yazma: yarım kalmış dosya ayarları bozmasın.
pub fn save_atomic<T: Serialize>(path: &Path, value: &T) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        crate::paths::ensure_dir(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let data = serde_json::to_vec_pretty(value)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
    std::fs::write(&tmp, data)?;
    std::fs::rename(&tmp, path)
}

pub fn save(cfg: &Config) -> std::io::Result<()> {
    save_atomic(&crate::paths::config_file(), cfg)
}
