//! SoundCloud API istemcisi.
//!
//! Orijinal uygulama tek bir sabit `client_id` kullanıyordu; SoundCloud onu
//! döndürdüğünde uygulama tamamen ölüyordu. Burada anahtar, soundcloud.com
//! üzerindeki JS paketlerinden otomatik çıkarılıp önbelleğe alınıyor ve
//! 401/403 alındığında kendiliğinden yenileniyor.

use anyhow::{anyhow, Result};
use regex::Regex;
use serde::Deserialize;
use serde_json::Value;
use std::sync::OnceLock;
use std::time::Duration;
use tokio::sync::RwLock;

const API: &str = "https://api-v2.soundcloud.com";
const UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
                  (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

/// Bilinen son çalışan anahtar – otomatik çıkarma başarısız olursa yedek.
const FALLBACK_CLIENT_ID: &str = "QhVEWrrJKvW4uSU5u5EoI0FTXYUGzy5k";

#[derive(Debug, Clone)]
pub struct Transcoding {
    pub url: String,
    pub preset: String,
    pub protocol: String,
    pub mime: String,
    pub snipped: bool,
}

#[derive(Debug, Clone)]
pub struct Track {
    pub id: String,
    pub title: String,
    pub uploader: String,
    pub permalink_url: String,
    pub duration_secs: f64,
    pub views: i64,
    pub likes: i64,
    pub reposts: i64,
    pub artwork_url: Option<String>,
    pub created_at: Option<String>,
    pub description: String,
    pub streamable: bool,
    pub blocked: bool,
    pub transcodings: Vec<Transcoding>,
    /// Akış adresini çözerken SoundCloud web istemcisinin gönderdiği belirteç.
    pub track_authorization: String,
}

impl Track {
    pub fn from_json(v: &Value) -> Option<Track> {
        let id = v.get("id").map(json_id)?;
        let duration_ms = v.get("duration").and_then(Value::as_f64).unwrap_or(0.0);
        let uploader = v
            .get("user")
            .and_then(|u| u.get("username"))
            .and_then(Value::as_str)
            .unwrap_or("SoundCloud Artist")
            .to_string();
        let artwork = v
            .get("artwork_url")
            .and_then(Value::as_str)
            .map(|s| s.replace("-large.", "-t500x500."));

        let transcodings = v
            .get("media")
            .and_then(|m| m.get("transcodings"))
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .filter_map(|t| {
                        Some(Transcoding {
                            url: t.get("url")?.as_str()?.to_string(),
                            preset: t
                                .get("preset")
                                .and_then(Value::as_str)
                                .unwrap_or_default()
                                .to_string(),
                            protocol: t
                                .get("format")
                                .and_then(|f| f.get("protocol"))
                                .and_then(Value::as_str)
                                .unwrap_or("http")
                                .to_string(),
                            mime: t
                                .get("format")
                                .and_then(|f| f.get("mime_type"))
                                .and_then(Value::as_str)
                                .unwrap_or_default()
                                .to_string(),
                            snipped: t.get("snipped").and_then(Value::as_bool).unwrap_or(false),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();

        Some(Track {
            id,
            title: v
                .get("title")
                .and_then(Value::as_str)
                .unwrap_or("Bilinmeyen Parça")
                .to_string(),
            uploader,
            permalink_url: v
                .get("permalink_url")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            duration_secs: duration_ms / 1000.0,
            views: v.get("playback_count").and_then(Value::as_i64).unwrap_or(0),
            likes: v
                .get("likes_count")
                .and_then(Value::as_i64)
                .or_else(|| v.get("favoritings_count").and_then(Value::as_i64))
                .unwrap_or(0),
            reposts: v
                .get("reposts_count")
                .and_then(Value::as_i64)
                .unwrap_or(0),
            artwork_url: artwork,
            created_at: v
                .get("created_at")
                .and_then(Value::as_str)
                .map(str::to_string),
            description: v
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            streamable: v.get("streamable").and_then(Value::as_bool).unwrap_or(true),
            // SNIP: yalnızca 30 sn önizleme (Go+ parçası); tam hali indirilemez.
            blocked: matches!(v.get("policy").and_then(Value::as_str), Some("BLOCK") | Some("SNIP")),
            transcodings,
            track_authorization: v
                .get("track_authorization")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
        })
    }
}

fn json_id(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        _ => String::new(),
    }
}

/// İndirilebilir bir akış kaynağı (doğrudan dosya ya da HLS listesi;
/// ffmpeg ikisini de doğrudan okur).
#[derive(Debug, Clone)]
pub struct StreamSource {
    pub url: String,
    /// Kaynak zaten MP3 mü? Öyleyse yeniden kodlamadan kopyalanır
    /// (kalite kaybı yok, daha hızlı).
    pub mp3: bool,
}

pub struct ScClient {
    http: reqwest::Client,
    client_id: RwLock<String>,
}

#[derive(Deserialize)]
struct StreamInfo {
    url: String,
}

impl ScClient {
    pub fn new(hint: &str) -> Result<Self> {
        let http = reqwest::Client::builder()
            .user_agent(UA)
            .timeout(Duration::from_secs(25))
            .connect_timeout(Duration::from_secs(10))
            .build()?;
        // Önceki oturumda kazınan anahtarı kullan; her açılışta
        // soundcloud.com'u yeniden taramaya gerek yok. Geçersizse ilk 401'de
        // kendiliğinden yenilenir.
        let mut initial = hint.trim().to_string();
        if initial.is_empty() {
            initial = std::fs::read_to_string(crate::paths::client_id_cache_file())
                .map(|s| s.trim().to_string())
                .unwrap_or_default();
        }
        Ok(Self {
            http,
            client_id: RwLock::new(initial),
        })
    }

    pub async fn client_id(&self) -> String {
        let guard = self.client_id.read().await.clone();
        if guard.is_empty() {
            drop(guard);
            self.refresh_client_id().await
        } else {
            guard
        }
    }

    /// soundcloud.com'un JS paketlerinden güncel `client_id`'yi çıkarır.
    pub async fn refresh_client_id(&self) -> String {
        match self.scrape_client_id().await {
            Ok(id) => {
                *self.client_id.write().await = id.clone();
                let _ = std::fs::write(crate::paths::client_id_cache_file(), &id);
                id
            }
            Err(_) => {
                *self.client_id.write().await = FALLBACK_CLIENT_ID.to_string();
                FALLBACK_CLIENT_ID.to_string()
            }
        }
    }

    async fn scrape_client_id(&self) -> Result<String> {
        let html = self
            .http
            .get("https://soundcloud.com/discover")
            .send()
            .await?
            .text()
            .await?;

        static ASSET: OnceLock<Regex> = OnceLock::new();
        static CID: OnceLock<Regex> = OnceLock::new();
        let asset_re =
            ASSET.get_or_init(|| Regex::new(r#"src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)""#).unwrap());
        let cid_re = CID.get_or_init(|| {
            Regex::new(r#"client_id["']?\s*[:=]\s*["']([0-9a-zA-Z]{32})["']"#).unwrap()
        });

        // HTML'in kendisinde gömülü olabilir.
        if let Some(c) = cid_re.captures(&html) {
            return Ok(c[1].to_string());
        }

        let assets: Vec<String> = asset_re
            .captures_iter(&html)
            .map(|c| c[1].to_string())
            .collect();

        // Anahtar son paketlerde duruyor (Kasım 2026: 8 paketin 8.'si). Eski
        // kod yalnızca ilk 6'ya bakıyordu, bu yüzden kazıma hiç başarılı
        // olmuyor, hep sabit yedeğe düşüyordu. Sondan başla; tek bir paketin
        // ağ hatası aramayı bitirmesin, sıradakine geçilsin.
        for url in assets.iter().rev().take(12) {
            let Ok(resp) = self.http.get(url).send().await else {
                continue;
            };
            if let Ok(text) = resp.text().await {
                if let Some(c) = cid_re.captures(&text) {
                    return Ok(c[1].to_string());
                }
            }
        }
        Err(anyhow!("client_id bulunamadı"))
    }

    async fn get(&self, url: &str, params: &[(&str, String)]) -> Result<Value> {
        for attempt in 0..2 {
            let cid = self.client_id().await;
            let mut query: Vec<(&str, String)> = params.to_vec();
            query.push(("client_id", cid));

            let resp = self.http.get(url).query(&query).send().await?;
            let status = resp.status();

            if status == reqwest::StatusCode::UNAUTHORIZED
                || status == reqwest::StatusCode::FORBIDDEN
            {
                if attempt == 0 {
                    self.refresh_client_id().await;
                    continue;
                }
                return Err(anyhow!("SoundCloud yetkilendirme hatası ({})", status));
            }
            if status == reqwest::StatusCode::NOT_FOUND {
                return Err(anyhow!("Bulunamadı: {}", url));
            }
            if !status.is_success() {
                return Err(anyhow!("SoundCloud hatası: HTTP {}", status));
            }
            return Ok(resp.json::<Value>().await?);
        }
        Err(anyhow!("SoundCloud isteği başarısız"))
    }

    /// Bir kullanıcı/parça/playlist URL'sini API nesnesine çevirir.
    pub async fn resolve(&self, url: &str) -> Result<Value> {
        self.get(&format!("{}/resolve", API), &[("url", url.to_string())])
            .await
    }

    pub async fn user_tracks(&self, user_id: &str, limit: usize, offset: usize) -> Result<Vec<Track>> {
        let v = self
            .get(
                &format!("{}/users/{}/tracks", API, user_id),
                &[
                    ("limit", limit.to_string()),
                    ("offset", offset.to_string()),
                    ("linked_partitioning", "1".to_string()),
                ],
            )
            .await?;
        Ok(collection(&v))
    }

    pub async fn search(
        &self,
        query: &str,
        created_filter: Option<&str>,
        offset: usize,
    ) -> Result<Vec<Track>> {
        let mut params = vec![
            ("q", query.to_string()),
            ("limit", "50".to_string()),
            ("offset", offset.to_string()),
        ];
        if let Some(f) = created_filter {
            params.push(("filter.created_at", f.to_string()));
        }
        let v = self.get(&format!("{}/search/tracks", API), &params).await?;
        Ok(collection(&v))
    }

    /// Verilen URL bir parça, kullanıcı ya da playlist olabilir; hepsini
    /// parça listesine çevirir. (Orijinal sürüm yalnızca kullanıcı linklerini
    /// destekliyordu, tek parça linki verince sessizce boş dönüyordu.)
    pub async fn tracks_from_url(&self, url: &str) -> Result<Vec<Track>> {
        let trimmed = url.trim().split(['?', '#']).next().unwrap_or("");
        let mut base = trimmed.trim_end_matches('/').to_string();
        // ".../likes" linki kullanıcının parçalarını değil beğenilerini ister.
        if let Some(profile) = base.strip_suffix("/likes") {
            let v = self.resolve(profile).await?;
            let id = v.get("id").map(json_id).unwrap_or_default();
            if id.is_empty() {
                return Err(anyhow!("Profil çözümlenemedi: {}", url));
            }
            return self.user_likes(&id, 50).await;
        }
        for suffix in ["/tracks", "/albums", "/sets", "/reposts"] {
            if let Some(stripped) = base.strip_suffix(suffix) {
                base = stripped.to_string();
                break;
            }
        }

        let v = self.resolve(&base).await?;
        let kind = v.get("kind").and_then(Value::as_str).unwrap_or("");

        match kind {
            "track" => Ok(Track::from_json(&v).into_iter().collect()),
            "playlist" | "system-playlists" => {
                let id = v.get("id").map(json_id).unwrap_or_default();
                let list = self
                    .get(
                        &format!("{}/playlists/{}/tracks", API, id),
                        &[
                            ("limit", "50".to_string()),
                            ("offset", "0".to_string()),
                            ("linked_partitioning", "1".to_string()),
                        ],
                    )
                    .await?;
                Ok(collection(&list))
            }
            _ => {
                let id = v.get("id").map(json_id).unwrap_or_default();
                if id.is_empty() {
                    return Err(anyhow!("Kaynak çözümlenemedi: {}", url));
                }
                self.user_tracks(&id, 50, 0).await
            }
        }
    }

    /// Kullanıcının beğendiği parçalar (giriş yapılmışsa).
    pub async fn user_likes(&self, user_id: &str, limit: usize) -> Result<Vec<Track>> {
        let v = self
            .get(
                &format!("{}/users/{}/likes", API, user_id),
                &[
                    ("limit", limit.to_string()),
                    ("offset", "0".to_string()),
                    ("linked_partitioning", "1".to_string()),
                ],
            )
            .await?;

        let mut out = Vec::new();
        if let Some(arr) = v.get("collection").and_then(Value::as_array) {
            for item in arr {
                // Beğeni kaydı { track: {...} } şeklinde gelir.
                let raw = item.get("track").unwrap_or(item);
                if let Some(t) = Track::from_json(raw) {
                    out.push(t);
                }
            }
        }
        Ok(out)
    }

    /// Parçanın indirilebilir akış adresini döndürür.
    pub async fn stream_source(&self, track: &Track) -> Result<StreamSource, String> {
        if track.transcodings.is_empty() {
            return Err("Bu parça için akış bilgisi yok".into());
        }

        // 1) Şifresiz progressive akış varsa en iyisi odur.
        if let Some(t) = track
            .transcodings
            .iter()
            .find(|t| t.protocol == "progressive" && !t.snipped)
        {
            let url = self.resolve_transcoding(&t.url, &track.track_authorization).await?;
            return Ok(StreamSource {
                url,
                mp3: is_mp3_mime(&t.mime),
            });
        }

        // 2) Şifresiz HLS.
        let mut hls: Vec<&Transcoding> = track
            .transcodings
            .iter()
            .filter(|t| t.protocol == "hls" && !t.snipped)
            .collect();
        // Sıra: gerçek MP3 (kopyalanır, kayıpsız) → aac_160k → aac_96k →
        // abr_sq. Dikkat: abr_sq'nin türü "audio/mpegurl" (uyarlanabilir HLS
        // listesi), MP3 değil; "mpeg" içerdiği için eski kod onu MP3 sanıp
        // başa koyuyordu.
        hls.sort_by_key(|t| {
            if is_mp3_mime(&t.mime) {
                0
            } else if t.preset.contains("160") {
                1
            } else if t.mime.contains("mpegurl") || t.preset.contains("abr") {
                3
            } else {
                2
            }
        });
        for t in hls {
            if let Ok(url) = self.resolve_transcoding(&t.url, &track.track_authorization).await {
                return Ok(StreamSource {
                    url,
                    mp3: is_mp3_mime(&t.mime),
                });
            }
        }

        if track
            .transcodings
            .iter()
            .any(|t| t.protocol.contains("encrypted"))
        {
            return Err("Bu parça korumalı (DRM) akışla sunuluyor, indirilemez".into());
        }
        if track.transcodings.iter().all(|t| t.snipped) {
            return Err("Bu parça yalnızca 30 sn önizleme olarak sunuluyor (SoundCloud Go+), tam hali indirilemez".into());
        }
        Err("Uygun akış bulunamadı".into())
    }

    /// Dinleme önizlemesi için akış çözer: `(url, is_progressive, is_mp3)`.
    /// Öncelik: şifresiz progressive (anında çalar) → HLS (ffmpeg ile geçici önbellek).
    pub async fn preview_source(&self, track: &Track) -> Result<(String, bool, bool), String> {
        if let Some(t) = track
            .transcodings
            .iter()
            .find(|t| t.protocol == "progressive" && !t.protocol.contains("encrypted"))
        {
            if let Ok(url) = self.resolve_transcoding(&t.url, &track.track_authorization).await {
                return Ok((url, true, is_mp3_mime(&t.mime)));
            }
        }
        if let Ok(src) = self.stream_source(track).await {
            return Ok((src.url, false, src.mp3));
        }
        if let Some(t) = track
            .transcodings
            .iter()
            .find(|t| t.protocol == "hls" && !t.protocol.contains("encrypted"))
        {
            if let Ok(url) = self.resolve_transcoding(&t.url, &track.track_authorization).await {
                return Ok((url, false, is_mp3_mime(&t.mime)));
            }
        }
        Err("Bu parça önizlenemedi".into())
    }

    /// Önizleme için verilen ses URL'sini (gerekirse Range başlığı ile) okur.
    pub async fn fetch_audio_response(&self, url: &str, range: Option<&str>) -> Result<reqwest::Response, String> {
        let mut req = self.http.get(url);
        if let Some(r) = range {
            req = req.header(reqwest::header::RANGE, r);
        }
        let resp = req.send().await.map_err(|e| e.to_string())?;
        if !resp.status().is_success() && resp.status() != reqwest::StatusCode::PARTIAL_CONTENT {
            return Err(format!("Ses akışı hatası: HTTP {}", resp.status()));
        }
        Ok(resp)
    }

    async fn resolve_transcoding(&self, transcoding_url: &str, track_auth: &str) -> Result<String, String> {
        let cid = self.client_id().await;
        let sep = if transcoding_url.contains('?') { '&' } else { '?' };
        let mut url = format!("{}{}client_id={}", transcoding_url, sep, cid);
        if !track_auth.is_empty() {
            url.push_str("&track_authorization=");
            url.push_str(&urlencoding::encode(track_auth));
        }
        let resp = self
            .http
            .get(&url)
            .send()
            .await
            .map_err(|e| e.to_string())?;
        if !resp.status().is_success() {
            return Err(format!("akış bilgisi alınamadı: HTTP {}", resp.status()));
        }
        let info: StreamInfo = resp.json().await.map_err(|e| e.to_string())?;
        Ok(info.url)
    }
}

/// Akış gerçekten MP3 ses mi? ("audio/mpeg" evet, "audio/mpegurl" hayır —
/// o bir HLS oynatma listesi türü.)
fn is_mp3_mime(mime: &str) -> bool {
    let base = mime.split(';').next().unwrap_or("").trim();
    base.eq_ignore_ascii_case("audio/mpeg")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mpegurl_is_not_mp3() {
        assert!(is_mp3_mime("audio/mpeg"));
        assert!(is_mp3_mime("audio/mpeg; codecs=\"mp3\""));
        assert!(!is_mp3_mime("audio/mpegurl"));
        assert!(!is_mp3_mime("audio/mp4; codecs=\"mp4a.40.2\""));
        assert!(!is_mp3_mime(""));
    }
}

fn collection(v: &Value) -> Vec<Track> {
    v.get("collection")
        .and_then(Value::as_array)
        .map(|arr| arr.iter().filter_map(Track::from_json).collect())
        .unwrap_or_default()
}
