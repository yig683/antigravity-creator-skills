//! WebView2 oturum çerezleri: okuma (anlık görüntü), tam silme ve geri yükleme.
//! Yalnızca `wry` ve `cookies` modülüne bağımlıdır (tanı örneği doğrudan dahil eder).

use crate::cookies::{is_soundcloud_domain, CookieRec};
use std::time::{Duration, Instant};
use wry::WebView;

pub fn delete_non_local_cookies(webview: &WebView) {
    let mut to_delete = Vec::new();
    if let Ok(all) = webview.cookies() {
        for c in all {
            let dom = c.domain().unwrap_or("");
            if !dom.contains("127.0.0.1") && !dom.eq_ignore_ascii_case("localhost") {
                to_delete.push(c);
            }
        }
    }
    for origin in [
        "https://soundcloud.com",
        "https://m.soundcloud.com",
        "https://secure.soundcloud.com",
        "https://artists.soundcloud.com",
        "https://api-v2.soundcloud.com",
        "https://accounts.google.com",
        "https://appleid.apple.com",
        "https://www.facebook.com",
    ] {
        if let Ok(list) = webview.cookies_for_url(origin) {
            to_delete.extend(list);
        }
    }
    for c in to_delete {
        delete_cookie_all_variants(webview, &c);
    }
}

/// WebView2, `DeleteCookie` çağrısında alan çerezi (`.alan`) ile ana makine çerezini (`alan`)
/// ayrı sayar ve okunan çerezin baştaki noktası kaybolduğundan alan çerezleri silinmiyordu.
/// İki biçim de denenir (olmayan biçimi silmek zararsızdır).
pub fn delete_cookie_all_variants(webview: &WebView, c: &wry::cookie::Cookie<'static>) {
    let _ = webview.delete_cookie(c);
    if let Some(d) = c.domain() {
        let dotted = wry::cookie::Cookie::build((c.name().to_string(), c.value().to_string()))
            .domain(format!("..{}", d.trim_start_matches('.')))
            .path(c.path().unwrap_or("/").to_string())
            .build();
        let _ = webview.delete_cookie(&dotted);
    }
}

/// Yerel (arayüzün kendi) dışındaki çerez sayısı.
pub fn remote_cookie_count(webview: &WebView) -> usize {
    webview
        .cookies()
        .unwrap_or_default()
        .iter()
        .filter(|c| {
            let dom = c.domain().unwrap_or("");
            !dom.contains("127.0.0.1") && !dom.eq_ignore_ascii_case("localhost")
        })
        .count()
}

/// Çerezleri ve tarama verisini siler; silme tamamlanana kadar (en çok ~2,5 sn) bekler.
/// Hemen ardından çerez yazmak güvenli olur (asenkron silme yeni çerezleri ezmez).
pub fn wipe_session_blocking(webview: &WebView) {
    delete_non_local_cookies(webview);
    let _ = webview.clear_all_browsing_data();
    let started = Instant::now();
    while started.elapsed() < Duration::from_millis(2500) {
        if remote_cookie_count(webview) == 0 {
            return;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

/// WebView2'deki SoundCloud çerezlerini (HttpOnly dahil) okur.
///
/// WebView2 hem alan çerezini (`.soundcloud.com`) hem ana makine çerezini aynı alan adıyla
/// listeler. Ayrım için her (alan, yol) çifti, rastgele bir alt alan adı adresiyle sorgulanır:
/// o adrese giden çerez alan çerezidir.
pub fn snapshot_cookies(webview: &WebView) -> Vec<CookieRec> {
    use std::collections::HashMap;
    let all: Vec<wry::cookie::Cookie<'static>> = webview
        .cookies()
        .unwrap_or_default()
        .into_iter()
        .filter(|c| c.domain().map_or(false, is_soundcloud_domain))
        .collect();

    let mut via_subdomain: HashMap<(String, String), Vec<(String, String)>> = HashMap::new();
    for c in &all {
        let d = c.domain().unwrap_or("").to_string();
        let p = c.path().unwrap_or("/").to_string();
        via_subdomain.entry((d.clone(), p.clone())).or_insert_with(|| {
            let url = format!("https://scs-probe.{}{}", d.trim_start_matches('.'), p);
            webview
                .cookies_for_url(&url)
                .unwrap_or_default()
                .iter()
                .map(|x| (x.name().to_string(), x.value().to_string()))
                .collect()
        });
    }

    all.iter()
        .filter_map(|c| {
            let key = (c.domain()?.to_string(), c.path().unwrap_or("/").to_string());
            let is_domain_cookie = via_subdomain
                .get(&key)
                .map_or(false, |v| v.iter().any(|(n, val)| n == c.name() && val == c.value()));
            CookieRec::from_cookie(c, !is_domain_cookie)
        })
        .collect()
}

pub fn unix_now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// Mevcut çerezleri silip verilenleri yükler (süresi dolanlar atlanır). Yüklenen sayıyı döner.
pub fn restore_cookies(webview: &WebView, recs: &[CookieRec]) -> usize {
    wipe_session_blocking(webview);
    let now = unix_now();
    let mut n = 0;
    for r in recs {
        if r.is_expired(now) {
            continue;
        }
        if webview.set_cookie(&r.to_cookie()).is_ok() {
            n += 1;
        }
    }
    n
}

pub fn set_soundcloud_oauth_cookie(webview: &WebView, token: &str) -> wry::Result<()> {
    // Önceki hesabın alan çerezleri silinmezse, eski `oauth_token` yeni token'ın önüne geçer
    // ve hesap değişmez.
    wipe_session_blocking(webview);
    // İki nokta: WebView2'ye ".soundcloud.com" gider (alan çerezi; bkz. CookieRec::to_cookie).
    let cookie = wry::cookie::Cookie::build(("oauth_token", token.to_string()))
        .domain("..soundcloud.com")
        .path("/")
        .secure(true)
        .http_only(false)
        .same_site(wry::cookie::SameSite::Lax)
        .max_age(wry::cookie::time::Duration::days(30))
        .build();
    webview.set_cookie(&cookie)
}
