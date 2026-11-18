//! Paylaşılan uygulama durumu.

use crate::artwork::ArtworkPool;
use crate::auth::{AuthState, PendingAuth};
use crate::config::Config;
use crate::rng::Rng;
use crate::sc::ScClient;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use tokio::sync::RwLock;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TrackMeta {
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub cover: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Candidate {
    pub id: String,
    pub title: String,
    pub uploader: String,
    pub url: String,
    pub thumbnail: String,
    pub duration_str: String,
    pub date_str: String,
    pub days_ago: f64,
    pub views: i64,
    pub likes: i64,
    pub score: i32,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Default)]
pub struct CuratorStatus {
    pub scanning: bool,
    pub downloading: bool,
    pub log: String,
    pub candidates: Vec<Candidate>,
    pub seen_count: usize,
    /// 0..1 arası ilerleme (indirme sırasında).
    pub progress: f32,
    /// Şu anda işlenen parçanın adı.
    pub current: String,
    /// Şu anda indirilen adayın SoundCloud URL'si (aday kartı vurgusu için).
    pub current_url: String,
    /// Aktif indirme / tarama aşaması ("Çözümleniyor", "320k MP3", "Kapak", "ID3" vb.).
    pub stage: String,
    /// Mevcut / son toplu indirmede başarıyla inen URL'ler.
    pub completed_urls: Vec<String>,
    /// Mevcut / son toplu indirmede başarısız olan URL'ler.
    pub failed_urls: Vec<String>,
    /// Toplu indirmede kaçıncı parça / toplam (indirme yoksa 0).
    pub batch_index: usize,
    pub batch_total: usize,
    /// Son hata (arayüzde kırmızı uyarı olarak gösterilir).
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Default)]
pub struct UploadStatus {
    pub active: bool,
    pub filename: String,
    pub stage: String,
    pub ok: bool,
    pub error: Option<String>,
}

pub struct AppState {
    pub cfg: RwLock<Config>,
    /// "SoundCloud ile giriş" oturumu.
    pub auth: RwLock<AuthState>,
    /// Devam eden OAuth akışları (state → PKCE verifier).
    pub pending_auth: PendingAuth,
    /// "SoundCloud ile giriş yap"a basıldı, tarayıcıdan hesap bekleniyor.
    /// Yalnızca bu açıkken tarayıcının bildirdiği hesap kabul edilir; böylece
    /// çıkış yaptıktan sonra "Keşfet" penceresi oturumu kendiliğinden geri açmaz.
    pub login_pending: std::sync::atomic::AtomicBool,
    /// Uygulama içi tarayıcı penceresi şu anda açık mı?
    pub browser_open: std::sync::atomic::AtomicBool,
    /// Aktif tarama veya indirmeyi kullanıcı isteğiyle durdurma bayrakları.
    pub cancel_scan: std::sync::atomic::AtomicBool,
    pub cancel_download: std::sync::atomic::AtomicBool,
    /// Ana pencerenin yerel Win32 HWND tutamacı (klasör iletişim kutusu sahipliği için).
    pub main_hwnd: std::sync::atomic::AtomicIsize,
    /// Uygulama içi tarayıcıda en son görülen adres.
    pub browser_url: Mutex<String>,
    /// SoundCloud dahili yükleme durumu.
    pub upload_status: RwLock<UploadStatus>,
    /// Arayüz thread'ine olay göndermek için (tarayıcı penceresi vb.).
    pub ui_tx: Mutex<Option<tao::event_loop::EventLoopProxy<crate::ui::UiEvent>>>,
    pub seen: RwLock<HashSet<String>>,
    pub meta: RwLock<HashMap<String, TrackMeta>>,
    pub curator: RwLock<CuratorStatus>,
    pub sc: ScClient,
    pub art: Mutex<ArtworkPool>,
    pub rng: Mutex<Rng>,
    pub port: RwLock<u16>,
}

impl AppState {
    pub fn new(cfg: Config) -> anyhow::Result<Self> {
        let sc = ScClient::new(&cfg.client_id)?;

        // ffmpeg yoksa kullanıcı bunu ilk indirmeye kadar değil, hemen görsün.
        let initial_log = if crate::paths::ffmpeg_path().is_file() {
            "AI Küratör hazır.".to_string()
        } else {
            "AI Küratör hazır — ancak ffmpeg.exe bulunamadı, indirme çalışmaz."
                .to_string()
        };

        Ok(Self {
            cfg: RwLock::new(cfg),
            auth: RwLock::new(crate::auth::load()),
            pending_auth: PendingAuth::default(),
            login_pending: std::sync::atomic::AtomicBool::new(false),
            browser_open: std::sync::atomic::AtomicBool::new(false),
            cancel_scan: std::sync::atomic::AtomicBool::new(false),
            cancel_download: std::sync::atomic::AtomicBool::new(false),
            main_hwnd: std::sync::atomic::AtomicIsize::new(0),
            browser_url: Mutex::new(String::new()),
            upload_status: RwLock::new(UploadStatus::default()),
            ui_tx: Mutex::new(None),
            seen: RwLock::new(load_seen()),
            meta: RwLock::new(load_meta()),
            curator: RwLock::new(CuratorStatus {
                log: initial_log,
                ..Default::default()
            }),
            sc,
            art: Mutex::new(ArtworkPool::load()),
            rng: Mutex::new(Rng::new()),
            port: RwLock::new(0),
        })
    }

    pub async fn set_log(&self, msg: impl Into<String>) {
        self.curator.write().await.log = msg.into();
    }
}

pub fn load_seen() -> HashSet<String> {
    std::fs::read_to_string(crate::paths::seen_file())
        .ok()
        .and_then(|t| serde_json::from_str::<Vec<String>>(&t).ok())
        .map(|v| v.into_iter().collect())
        .unwrap_or_default()
}

pub fn save_seen(seen: &HashSet<String>) {
    let list: Vec<&String> = seen.iter().collect();
    let _ = crate::config::save_atomic(&crate::paths::seen_file(), &list);
}

pub fn load_meta() -> HashMap<String, TrackMeta> {
    std::fs::read_to_string(crate::paths::meta_file())
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default()
}

pub fn save_meta(meta: &HashMap<String, TrackMeta>) {
    let _ = crate::config::save_atomic(&crate::paths::meta_file(), meta);
}
