//! Çoklu hesap: hesapları saklar ve aralarında geçişi sağlar.
//!
//! Her hesap için iki şey saklanabilir (ikisi de Windows DPAPI ile şifrelenir,
//! yalnızca bu Windows kullanıcısı çözebilir):
//!   * `token_enc`   — Chrome'dan yapıştırılan `oauth_token` (kısa ömürlü olabilir),
//!   * `cookies_enc` — hesaptan ayrılırken alınan tam SoundCloud oturum çerezleri
//!     (yenileme çerezleri dahil; geçişte aynen geri yüklenir, süre sorunu olmaz).
//!
//! Dosya: `%APPDATA%\SoundCloudStudio\accounts.json`.

use crate::auth::AuthState;
use crate::cookies::CookieRec;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AccountEntry {
    pub user_id: String,
    pub username: String,
    #[serde(default)]
    pub avatar_url: String,
    #[serde(default)]
    pub permalink_url: String,
    /// DPAPI ile şifrelenmiş token (hex).
    #[serde(default)]
    pub token_enc: String,
    /// DPAPI ile şifrelenmiş oturum çerezleri (JSON, hex).
    #[serde(default)]
    pub cookies_enc: String,
}

/// Hesabı tanımlayan, sır içermeyen alanlar.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Identity {
    pub user_id: String,
    pub username: String,
    pub avatar_url: String,
    pub permalink_url: String,
}

impl From<&AuthState> for Identity {
    fn from(a: &AuthState) -> Self {
        Self {
            user_id: a.user_id.clone(),
            username: a.username.clone(),
            avatar_url: a.avatar_url.clone(),
            permalink_url: a.permalink_url.clone(),
        }
    }
}

impl From<&AccountEntry> for Identity {
    fn from(a: &AccountEntry) -> Self {
        Self {
            user_id: a.user_id.clone(),
            username: a.username.clone(),
            avatar_url: a.avatar_url.clone(),
            permalink_url: a.permalink_url.clone(),
        }
    }
}

impl Identity {
    pub fn is_valid(&self) -> bool {
        !self.user_id.is_empty() && !self.username.is_empty()
    }

    /// Bu kimlikle (belirteçsiz, çerez tabanlı) oturum durumu.
    pub fn to_auth(&self) -> AuthState {
        AuthState {
            user_id: self.user_id.clone(),
            username: self.username.clone(),
            avatar_url: self.avatar_url.clone(),
            permalink_url: self.permalink_url.clone(),
            web_session: true,
            ..Default::default()
        }
    }
}

// ------------------------------------------------------------------ dosya

fn file() -> std::path::PathBuf {
    crate::paths::data_dir().join("accounts.json")
}

pub fn load() -> Vec<AccountEntry> {
    std::fs::read_to_string(file())
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default()
}

fn store(list: &[AccountEntry]) {
    let _ = crate::config::save_atomic(&file(), &list.to_vec());
}

pub fn get(user_id: &str) -> Option<AccountEntry> {
    load().into_iter().find(|a| a.user_id == user_id)
}

/// Kimliği ekler/günceller; verilen token ve çerezleri (varsa) şifreleyip yazar.
/// Verilmeyen alanlar mevcut kayıtta korunur.
pub fn upsert_session(id: &Identity, token: Option<&str>, cookies: Option<&[CookieRec]>) {
    if !id.is_valid() {
        return;
    }
    let token_enc = token.and_then(|t| protect(t.as_bytes())).map(|b| hex(&b));
    let cookies_enc = cookies.and_then(encode_cookies);
    let mut list = load();
    merge_entry(&mut list, id, token_enc, cookies_enc);
    store(&list);
}

/// Saf birleştirme mantığı (dosya erişimi yok; test edilebilir).
fn merge_entry(list: &mut Vec<AccountEntry>, id: &Identity, token_enc: Option<String>, cookies_enc: Option<String>) {
    let keep = |new: Option<String>, old: &str| match new {
        Some(n) if !n.is_empty() => n,
        _ => old.to_string(),
    };
    if let Some(slot) = list.iter_mut().find(|a| a.user_id == id.user_id) {
        slot.username = id.username.clone();
        if !id.avatar_url.is_empty() {
            slot.avatar_url = id.avatar_url.clone();
        }
        if !id.permalink_url.is_empty() {
            slot.permalink_url = id.permalink_url.clone();
        }
        slot.token_enc = keep(token_enc, &slot.token_enc);
        slot.cookies_enc = keep(cookies_enc, &slot.cookies_enc);
    } else {
        list.push(AccountEntry {
            user_id: id.user_id.clone(),
            username: id.username.clone(),
            avatar_url: id.avatar_url.clone(),
            permalink_url: id.permalink_url.clone(),
            token_enc: token_enc.unwrap_or_default(),
            cookies_enc: cookies_enc.unwrap_or_default(),
        });
    }
}

pub fn remove(user_id: &str) {
    let mut list = load();
    list.retain(|a| a.user_id != user_id);
    store(&list);
}

pub fn token_for(user_id: &str) -> Option<String> {
    let acc = get(user_id)?;
    let bytes = unhex(&acc.token_enc)?;
    String::from_utf8(unprotect(&bytes)?).ok()
}

pub fn load_cookies(user_id: &str) -> Option<Vec<CookieRec>> {
    let acc = get(user_id)?;
    decode_cookies(&acc.cookies_enc)
}

pub fn has_cookies(user_id: &str) -> bool {
    get(user_id).map_or(false, |a| !a.cookies_enc.is_empty())
}

fn encode_cookies(recs: &[CookieRec]) -> Option<String> {
    if recs.is_empty() {
        return None;
    }
    let json = serde_json::to_vec(recs).ok()?;
    Some(hex(&protect(&json)?))
}

fn decode_cookies(enc: &str) -> Option<Vec<CookieRec>> {
    if enc.is_empty() {
        return None;
    }
    let json = unprotect(&unhex(enc)?)?;
    serde_json::from_slice(&json).ok()
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn unhex(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 {
        return None;
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok())
        .collect()
}

#[cfg(windows)]
mod dpapi {
    use std::ffi::c_void;

    #[repr(C)]
    struct DataBlob {
        cb_data: u32,
        pb_data: *mut u8,
    }

    #[link(name = "crypt32")]
    extern "system" {
        fn CryptProtectData(
            data_in: *const DataBlob,
            descr: *const u16,
            entropy: *const DataBlob,
            reserved: *mut c_void,
            prompt: *mut c_void,
            flags: u32,
            data_out: *mut DataBlob,
        ) -> i32;
        fn CryptUnprotectData(
            data_in: *const DataBlob,
            descr: *mut *mut u16,
            entropy: *const DataBlob,
            reserved: *mut c_void,
            prompt: *mut c_void,
            flags: u32,
            data_out: *mut DataBlob,
        ) -> i32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn LocalFree(p: *mut c_void) -> *mut c_void;
    }

    pub fn protect(data: &[u8]) -> Option<Vec<u8>> {
        let input = DataBlob { cb_data: data.len() as u32, pb_data: data.as_ptr() as *mut u8 };
        let mut out = DataBlob { cb_data: 0, pb_data: std::ptr::null_mut() };
        unsafe {
            let ok = CryptProtectData(
                &input,
                std::ptr::null(),
                std::ptr::null(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                0,
                &mut out,
            );
            if ok == 0 || out.pb_data.is_null() {
                return None;
            }
            let v = std::slice::from_raw_parts(out.pb_data, out.cb_data as usize).to_vec();
            LocalFree(out.pb_data as *mut c_void);
            Some(v)
        }
    }

    pub fn unprotect(data: &[u8]) -> Option<Vec<u8>> {
        let input = DataBlob { cb_data: data.len() as u32, pb_data: data.as_ptr() as *mut u8 };
        let mut out = DataBlob { cb_data: 0, pb_data: std::ptr::null_mut() };
        unsafe {
            let ok = CryptUnprotectData(
                &input,
                std::ptr::null_mut(),
                std::ptr::null(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                0,
                &mut out,
            );
            if ok == 0 || out.pb_data.is_null() {
                return None;
            }
            let v = std::slice::from_raw_parts(out.pb_data, out.cb_data as usize).to_vec();
            LocalFree(out.pb_data as *mut c_void);
            Some(v)
        }
    }
}

#[cfg(windows)]
fn protect(d: &[u8]) -> Option<Vec<u8>> {
    dpapi::protect(d)
}
#[cfg(windows)]
fn unprotect(d: &[u8]) -> Option<Vec<u8>> {
    dpapi::unprotect(d)
}
// Windows dışında hiçbir şey saklanmaz.
#[cfg(not(windows))]
fn protect(_: &[u8]) -> Option<Vec<u8>> {
    None
}
#[cfg(not(windows))]
fn unprotect(_: &[u8]) -> Option<Vec<u8>> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn id(n: &str) -> Identity {
        Identity {
            user_id: format!("id-{n}"),
            username: n.to_string(),
            avatar_url: String::new(),
            permalink_url: String::new(),
        }
    }

    fn rec(name: &str, value: &str, domain: &str, exp: Option<i64>) -> CookieRec {
        CookieRec {
            name: name.into(),
            value: value.into(),
            domain: domain.into(),
            path: "/".into(),
            secure: true,
            http_only: true,
            same_site: 1,
            expires: exp,
            host_only: false,
        }
    }

    #[test]
    fn hex_roundtrip() {
        let b = vec![0u8, 15, 255, 128];
        assert_eq!(unhex(&hex(&b)).unwrap(), b);
        assert!(unhex("abc").is_none());
    }

    #[cfg(windows)]
    #[test]
    fn dpapi_roundtrip() {
        let enc = protect(b"2-123456-abcdef").unwrap();
        assert_ne!(enc, b"2-123456-abcdef");
        assert_eq!(unprotect(&enc).unwrap(), b"2-123456-abcdef");
    }

    #[cfg(windows)]
    #[test]
    fn cookies_encrypt_and_decrypt_roundtrip() {
        let recs = vec![
            rec("oauth_token", "2-1-2-abc", ".soundcloud.com", Some(2_000_000_000)),
            rec("sid", "xyz", "secure.soundcloud.com", None),
        ];
        let enc = encode_cookies(&recs).unwrap();
        assert!(!enc.contains("oauth_token"), "düz metin sızmamalı");
        assert_eq!(decode_cookies(&enc).unwrap(), recs);
        assert!(decode_cookies("").is_none());
        assert!(decode_cookies("zz").is_none());
        assert!(encode_cookies(&[]).is_none());
    }

    #[test]
    fn merge_keeps_token_when_only_cookies_arrive_and_vice_versa() {
        let mut list: Vec<AccountEntry> = Vec::new();
        // 1) yalnızca token ile eklenir
        merge_entry(&mut list, &id("a"), Some("T1".into()), None);
        assert_eq!(list.len(), 1);
        assert_eq!((list[0].token_enc.as_str(), list[0].cookies_enc.as_str()), ("T1", ""));
        // 2) sonradan çerez gelir: token silinmez
        merge_entry(&mut list, &id("a"), None, Some("C1".into()));
        assert_eq!((list[0].token_enc.as_str(), list[0].cookies_enc.as_str()), ("T1", "C1"));
        // 3) yeni token gelir: çerez silinmez
        merge_entry(&mut list, &id("a"), Some("T2".into()), None);
        assert_eq!((list[0].token_enc.as_str(), list[0].cookies_enc.as_str()), ("T2", "C1"));
        // 4) boş değer mevcut kaydı ezmez
        merge_entry(&mut list, &id("a"), Some(String::new()), Some(String::new()));
        assert_eq!((list[0].token_enc.as_str(), list[0].cookies_enc.as_str()), ("T2", "C1"));
        // 5) başka hesap ayrı kayıt olur
        merge_entry(&mut list, &id("b"), None, None);
        assert_eq!(list.len(), 2);
    }

    #[test]
    fn merge_updates_identity_without_losing_known_fields() {
        let mut list = Vec::new();
        let mut a = id("a");
        a.avatar_url = "https://x/av.jpg".into();
        merge_entry(&mut list, &a, None, None);
        let mut renamed = id("a");
        renamed.username = "a-yeni".into();
        merge_entry(&mut list, &renamed, None, None);
        assert_eq!(list[0].username, "a-yeni");
        assert_eq!(list[0].avatar_url, "https://x/av.jpg", "boş avatar mevcut olanı silmemeli");
    }

    #[test]
    fn identity_validity_and_auth() {
        assert!(id("a").is_valid());
        assert!(!Identity::default().is_valid());
        let a = id("a").to_auth();
        assert!(a.web_session && a.access_token.is_empty() && a.is_signed_in());
    }
}
