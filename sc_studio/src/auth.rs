//! "SoundCloud ile giriş" — OAuth 2.1 + PKCE.
//!
//! SoundCloud tüm istemcileri "confidential" saydığı için `client_secret`
//! zorunlu; PKCE de şart. Kullanıcı kendi uygulamasını
//! https://soundcloud.com/you/apps adresinden kaydedip client_id/secret ve
//! yönlendirme adresini ayarlara girer.
//!
//! Yönlendirme iki şekilde yakalanabiliyor:
//!   1. Loopback HTTP (`http://127.0.0.1:47821/oauth/callback`) — varsayılan.
//!   2. Elle yapıştırma — tarayıcı geri dönmezse adres çubuğundaki URL.

use crate::config::Config;
use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

const AUTHORIZE_URL: &str = "https://secure.soundcloud.com/authorize";
const TOKEN_URL: &str = "https://secure.soundcloud.com/oauth/token";
const API_BASE: &str = "https://api.soundcloud.com";

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AuthState {
    #[serde(default)]
    pub access_token: String,
    #[serde(default)]
    pub refresh_token: String,
    /// Unix saniye.
    #[serde(default)]
    pub expires_at: i64,
    #[serde(default)]
    pub user_id: String,
    #[serde(default)]
    pub username: String,
    #[serde(default)]
    pub avatar_url: String,
    #[serde(default)]
    pub permalink_url: String,
    /// Uygulama içi tarayıcıda soundcloud.com'a giriş yapılarak bağlandı.
    /// Bu yolda belirteç saklanmaz; yalnızca hesap kimliği ve adı tutulur
    /// (beğeniler herkese açık API'den okunur).
    #[serde(default)]
    pub web_session: bool,
}

impl AuthState {
    pub fn is_signed_in(&self) -> bool {
        (!self.access_token.is_empty() || self.web_session) && !self.username.is_empty()
    }
}

#[derive(Debug, Deserialize)]
struct TokenResponse {
    access_token: String,
    #[serde(default)]
    refresh_token: String,
    #[serde(default)]
    expires_in: i64,
}

struct Pending {
    verifier: String,
    created: Instant,
}

#[derive(Default)]
pub struct PendingAuth(Mutex<HashMap<String, Pending>>);

impl PendingAuth {
    pub fn insert(&self, state: &str, verifier: &str) {
        let mut map = self.0.lock().unwrap();
        // 10 dakikadan eski kayıtları temizle.
        map.retain(|_, p| p.created.elapsed() < Duration::from_secs(600));
        map.insert(
            state.to_string(),
            Pending {
                verifier: verifier.to_string(),
                created: Instant::now(),
            },
        );
    }

    pub fn take(&self, state: &str) -> Option<String> {
        self.0
            .lock()
            .unwrap()
            .remove(state)
            .map(|p| p.verifier)
    }
}

fn b64url(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut out = String::with_capacity((data.len() * 4) / 3 + 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0];
        let b1 = *chunk.get(1).unwrap_or(&0);
        let b2 = *chunk.get(2).unwrap_or(&0);
        let n = ((b0 as u32) << 16) | ((b1 as u32) << 8) | b2 as u32;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        if chunk.len() > 1 {
            out.push(T[(n >> 6) as usize & 63] as char);
        }
        if chunk.len() > 2 {
            out.push(T[n as usize & 63] as char);
        }
    }
    out
}

pub fn random_token(len: usize) -> String {
    let mut rng = crate::rng::Rng::new();
    let mut bytes = Vec::with_capacity(len);
    while bytes.len() < len {
        bytes.extend_from_slice(&rng.next_u64().to_le_bytes());
    }
    bytes.truncate(len);
    b64url(&bytes)
}

pub fn pkce_challenge(verifier: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(verifier.as_bytes());
    b64url(&hasher.finalize())
}

/// Tarayıcıda açılacak yetkilendirme adresi.
pub fn authorize_url(cfg: &Config, state: &str, verifier: &str) -> String {
    format!(
        "{}?client_id={}&redirect_uri={}&response_type=code&code_challenge={}&code_challenge_method=S256&state={}",
        AUTHORIZE_URL,
        urlencoding::encode(cfg.oauth_client_id()),
        urlencoding::encode(cfg.sc_redirect_uri.trim()),
        pkce_challenge(verifier),
        urlencoding::encode(state),
    )
}

/// Yönlendirme adresinden `code` ve `state` çıkarır.
pub fn parse_redirect(raw: &str) -> Result<(String, String)> {
    let query = raw
        .split_once('?')
        .map(|(_, q)| q)
        .ok_or_else(|| anyhow!("Adreste '?' bulunamadı — tam yönlendirme adresini yapıştırın."))?;
    let mut code = None;
    let mut state = None;
    let mut error = None;
    for pair in query.split('&') {
        let (k, v) = match pair.split_once('=') {
            Some(kv) => kv,
            None => continue,
        };
        let v = urlencoding::decode(v)
            .map(|c| c.to_string())
            .unwrap_or_else(|_| v.to_string());
        match k {
            "code" => code = Some(v),
            "state" => state = Some(v),
            "error" => error = Some(v),
            "error_description" => error = Some(v),
            _ => {}
        }
    }
    if let Some(e) = error {
        return Err(anyhow!("SoundCloud yetkilendirmeyi reddetti: {}", e));
    }
    match (code, state) {
        (Some(c), Some(s)) => Ok((c, s)),
        _ => Err(anyhow!("Yönlendirme adresinde code/state yok.")),
    }
}

fn http_client() -> Result<reqwest::Client> {
    Ok(reqwest::Client::builder()
        .user_agent("SCStudio/2.0")
        .timeout(Duration::from_secs(30))
        .build()?)
}

async fn exchange_code(cfg: &Config, code: &str, verifier: &str) -> Result<TokenResponse> {
    let form = [
        ("grant_type", "authorization_code"),
        ("client_id", cfg.oauth_client_id()),
        ("client_secret", cfg.oauth_client_secret()),
        ("redirect_uri", cfg.sc_redirect_uri.trim()),
        ("code_verifier", verifier),
        ("code", code),
    ];
    let resp = http_client()?
        .post(TOKEN_URL)
        .form(&form)
        .send()
        .await
        .context("token isteği gönderilemedi")?;

    let status = resp.status();
    let body = resp.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(anyhow!("SoundCloud token hatası ({}): {}", status, body));
    }
    serde_json::from_str::<TokenResponse>(&body)
        .map_err(|e| anyhow!("token yanıtı okunamadı: {} — {}", e, body))
}

/// Kod alışverişi + kullanıcı bilgisini çekip kaydeder.
pub async fn complete_login(cfg: &Config, code: &str, verifier: &str) -> Result<AuthState> {
    let token = exchange_code(cfg, code, verifier).await?;
    let mut auth = AuthState {
        access_token: token.access_token,
        refresh_token: token.refresh_token,
        expires_at: chrono::Utc::now().timestamp() + token.expires_in.max(60),
        ..Default::default()
    };

    if let Ok(me) = fetch_me(&auth.access_token).await {
        auth.user_id = me.0;
        auth.username = me.1;
        auth.avatar_url = me.2;
        auth.permalink_url = me.3;
    } else {
        auth.username = "SoundCloud kullanıcısı".into();
    }

    save(&auth)?;
    Ok(auth)
}

/// `Authorization: OAuth <token>` ile /me.
async fn fetch_me(token: &str) -> Result<(String, String, String, String)> {
    let resp = http_client()?
        .get(format!("{}/me", API_BASE))
        .header(reqwest::header::AUTHORIZATION, format!("OAuth {}", token))
        .send()
        .await?;
    if !resp.status().is_success() {
        return Err(anyhow!("/me hatası: HTTP {}", resp.status()));
    }
    let v: serde_json::Value = resp.json().await?;
    let id = match v.get("id") {
        Some(serde_json::Value::Number(n)) => n.to_string(),
        Some(serde_json::Value::String(s)) => s.clone(),
        _ => String::new(),
    };
    Ok((
        id,
        v.get("username").and_then(|x| x.as_str()).unwrap_or("SoundCloud").to_string(),
        v.get("avatar_url").and_then(|x| x.as_str()).unwrap_or("").to_string(),
        v.get("permalink_url").and_then(|x| x.as_str()).unwrap_or("").to_string(),
    ))
}

/// Süresi dolmuşsa refresh token ile yeniler (refresh token tek kullanımlık).
pub async fn refresh_if_needed(cfg: &Config, auth: &mut AuthState) -> Result<bool> {
    if auth.refresh_token.is_empty() {
        return Ok(false);
    }
    // 2 dakikalık emniyet payı.
    if chrono::Utc::now().timestamp() < auth.expires_at - 120 {
        return Ok(false);
    }

    let form = [
        ("grant_type", "refresh_token"),
        ("client_id", cfg.oauth_client_id()),
        ("client_secret", cfg.oauth_client_secret()),
        ("refresh_token", auth.refresh_token.as_str()),
    ];
    let resp = http_client()?.post(TOKEN_URL).form(&form).send().await?;
    if !resp.status().is_success() {
        return Err(anyhow!("token yenilenemedi: HTTP {}", resp.status()));
    }
    let token: TokenResponse = resp.json().await?;
    auth.access_token = token.access_token;
    if !token.refresh_token.is_empty() {
        auth.refresh_token = token.refresh_token;
    }
    auth.expires_at = chrono::Utc::now().timestamp() + token.expires_in.max(60);
    save(auth)?;
    Ok(true)
}

pub fn load() -> AuthState {
    std::fs::read_to_string(crate::paths::auth_file())
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default()
}

pub fn save(auth: &AuthState) -> Result<()> {
    crate::config::save_atomic(&crate::paths::auth_file(), auth)?;
    Ok(())
}

pub fn clear() -> Result<()> {
    let path = crate::paths::auth_file();
    if path.exists() {
        std::fs::remove_file(path)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pkce_matches_rfc7636_example() {
        // RFC 7636 Appendix B.
        let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        assert_eq!(
            pkce_challenge(verifier),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
    }

    #[test]
    fn parses_redirect_url() {
        let (code, state) =
            parse_redirect("http://127.0.0.1:47821/oauth/callback?code=abc123&state=xyz").unwrap();
        assert_eq!(code, "abc123");
        assert_eq!(state, "xyz");
    }

    #[test]
    fn reports_denied_authorization() {
        let err = parse_redirect("http://127.0.0.1:1/cb?error=access_denied").unwrap_err();
        assert!(err.to_string().contains("reddetti"));
    }
}
