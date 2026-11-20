//! Çoklu hesap: token ile bağlanan hesapları saklar ve aralarında geçişi sağlar.
//!
//! Token'lar `%APPDATA%\SoundCloudStudio\accounts.json` içinde Windows DPAPI ile
//! (yalnızca bu Windows kullanıcısı çözebilir) şifrelenmiş olarak tutulur.

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
}

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

/// Hesabı ekler veya günceller (token yenilenir).
pub fn upsert(entry: AccountEntry, token: &str) {
    let Some(enc) = protect(token.as_bytes()) else { return };
    let mut list = load();
    let mut entry = entry;
    entry.token_enc = hex(&enc);
    if let Some(slot) = list.iter_mut().find(|a| a.user_id == entry.user_id) {
        *slot = entry;
    } else {
        list.push(entry);
    }
    store(&list);
}

pub fn remove(user_id: &str) {
    let mut list = load();
    list.retain(|a| a.user_id != user_id);
    store(&list);
}

pub fn token_for(user_id: &str) -> Option<String> {
    let list = load();
    let acc = list.iter().find(|a| a.user_id == user_id)?;
    let bytes = unhex(&acc.token_enc)?;
    String::from_utf8(unprotect(&bytes)?).ok()
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
// Windows dışında token saklanmaz.
#[cfg(not(windows))]
fn protect(_: &[u8]) -> Option<Vec<u8>> {
    None
}
#[cfg(not(windows))]
fn unprotect(_: &[u8]) -> Option<Vec<u8>> {
    None
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;

    #[test]
    fn dpapi_roundtrip() {
        let enc = protect(b"2-123456-abcdef").unwrap();
        assert_ne!(enc, b"2-123456-abcdef");
        assert_eq!(unprotect(&enc).unwrap(), b"2-123456-abcdef");
    }

    #[test]
    fn hex_roundtrip() {
        let b = vec![0u8, 15, 255, 128];
        assert_eq!(unhex(&hex(&b)).unwrap(), b);
        assert!(unhex("abc").is_none());
    }
}
