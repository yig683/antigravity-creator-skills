//! Tanı aracı: hesap oturumu kaydetme / silme / geri yükleme işlevlerini GERÇEK WebView2 ile dener.
//! Uygulamadaki `session.rs` ve `cookies.rs` doğrudan dahil edilir (kopya değil).
//!
//!   cargo run --example cookie_probe -- <geçici veri klasörü>
//!
//! Gerçek giriş yapılmaz; sahte çerezlerle iki hesap simüle edilir. Hata varsa çıkış kodu 1.

#[path = "../src/cookies.rs"]
mod cookies;
#[path = "../src/session.rs"]
mod session;

use cookies::{has_login_cookie, CookieRec};
use std::time::Instant;
use tao::event_loop::EventLoop;
use tao::window::WindowBuilder;
use wry::cookie::{time::Duration, Cookie, SameSite};
use wry::{WebContext, WebView, WebViewBuilder};

struct Report {
    failed: u32,
}

impl Report {
    fn check(&mut self, ok: bool, what: &str) {
        println!("  [{}] {}", if ok { "OK " } else { "HATA" }, what);
        if !ok {
            self.failed += 1;
        }
    }
}

fn mk(name: &str, value: &str, domain: &str, http_only: bool, ss: SameSite) -> Cookie<'static> {
    Cookie::build((name.to_string(), value.to_string()))
        .domain(domain.to_string())
        .path("/")
        .secure(true)
        .http_only(http_only)
        .same_site(ss)
        .max_age(Duration::days(30))
        .build()
}

/// Hesap A/B için sahte oturum: alan çerezi, ana makine çerezleri, HttpOnly, alt alan adı çerezi.
fn put_account(wv: &WebView, tag: &str) {
    // ".." -> WebView2'ye ".alan" gider (alt alan adlarına da giden alan çerezi)
    wv.set_cookie(&mk("oauth_token", &format!("tok-{tag}"), "..soundcloud.com", false, SameSite::Lax)).unwrap();
    wv.set_cookie(&mk("sc_host", &format!("host-{tag}"), "soundcloud.com", false, SameSite::Lax)).unwrap();
    wv.set_cookie(&mk("sess", &format!("sess-{tag}"), "secure.soundcloud.com", true, SameSite::Strict)).unwrap();
    wv.set_cookie(&mk("artists_sid", &format!("art-{tag}"), "..artists.soundcloud.com", true, SameSite::None)).unwrap();
    // SoundCloud dışı (Google): silinmeli ama anlık görüntüye girmemeli
    wv.set_cookie(&mk("g_cookie", &format!("g-{tag}"), "..google.com", true, SameSite::None)).unwrap();
}

fn names_for(wv: &WebView, url: &str) -> Vec<String> {
    let mut v: Vec<String> = wv
        .cookies_for_url(url)
        .unwrap()
        .iter()
        .map(|c| format!("{}={}", c.name(), c.value()))
        .collect();
    v.sort();
    v
}

fn find<'a>(recs: &'a [CookieRec], name: &str) -> Option<&'a CookieRec> {
    recs.iter().find(|r| r.name == name)
}

fn main() {
    let dir = std::env::args().nth(1).expect("veri klasörü ver");
    let event_loop = EventLoop::new();
    let window = WindowBuilder::new().with_visible(false).build(&event_loop).unwrap();
    let mut ctx = WebContext::new(Some(dir.into()));
    let wv = WebViewBuilder::new_with_web_context(&mut ctx)
        .with_url("about:blank")
        .build(&window)
        .expect("webview");
    let mut r = Report { failed: 0 };

    println!("1) Hesap A'nın oturumu yazılır, anlık görüntü alınır");
    session::wipe_session_blocking(&wv);
    r.check(session::snapshot_cookies(&wv).is_empty(), "başlangıçta SoundCloud çerezi yok");
    put_account(&wv, "A");
    let snap_a = session::snapshot_cookies(&wv);
    r.check(snap_a.len() == 4, &format!("4 SoundCloud çerezi kaydedildi (Google hariç): {}", snap_a.len()));
    r.check(has_login_cookie(&snap_a), "oauth_token (giriş çerezi) algılandı");
    r.check(find(&snap_a, "oauth_token").map_or(false, |c| !c.host_only), "oauth_token = ALAN çerezi");
    r.check(find(&snap_a, "artists_sid").map_or(false, |c| !c.host_only), "artists_sid = ALAN çerezi");
    r.check(find(&snap_a, "sc_host").map_or(false, |c| c.host_only), "sc_host = ana makine çerezi");
    r.check(find(&snap_a, "sess").map_or(false, |c| c.host_only), "sess = ana makine çerezi");
    r.check(
        find(&snap_a, "sess").map_or(false, |c| c.http_only && c.secure && c.same_site == 1),
        "sess: HttpOnly + Secure + SameSite=Strict korundu",
    );
    r.check(find(&snap_a, "oauth_token").and_then(|c| c.expires).is_some(), "oauth_token süresi okundu");

    println!("2) Hesap B'ye geçiş: tam silme + B çerezleri");
    let t = Instant::now();
    session::wipe_session_blocking(&wv);
    println!("     (silme {} ms sürdü)", t.elapsed().as_millis());
    r.check(wv.cookies().unwrap().is_empty(), "A'nın alan çerezleri dahil HİÇBİR çerez kalmadı (Google dahil)");
    put_account(&wv, "B");
    let snap_b = session::snapshot_cookies(&wv);
    r.check(find(&snap_b, "oauth_token").map_or(false, |c| c.value == "tok-B"), "B'nin oauth_token'ı yazıldı");
    r.check(
        wv.cookies().unwrap().iter().filter(|c| c.name() == "oauth_token").count() == 1,
        "tek bir oauth_token var (eski hesabın çerezi önüne geçmiyor)",
    );

    println!("3) A'ya dön: anlık görüntüyü geri yükle");
    let n = session::restore_cookies(&wv, &snap_a);
    r.check(n == 4, &format!("4 çerez geri yüklendi: {n}"));
    let all = wv.cookies().unwrap();
    r.check(all.len() == 4, &format!("yalnızca A'nın 4 çerezi var: {}", all.len()));
    r.check(!all.iter().any(|c| c.value().contains("-B") || c.name() == "g_cookie"), "B'den ve Google'dan iz yok");
    let on_secure = names_for(&wv, "https://secure.soundcloud.com");
    r.check(on_secure.contains(&"oauth_token=tok-A".to_string()), "alan çerezi oauth_token secure.* adresine gidiyor");
    r.check(on_secure.contains(&"sess=sess-A".to_string()), "sess (ana makine) secure.* adresine gidiyor");
    let on_artists = names_for(&wv, "https://artists.soundcloud.com");
    r.check(on_artists.contains(&"oauth_token=tok-A".to_string()), "alan çerezi oauth_token artists.* adresine gidiyor");
    r.check(on_artists.contains(&"artists_sid=art-A".to_string()), "artists_sid alan çerezi artists.* adresine gidiyor");
    let on_main = names_for(&wv, "https://soundcloud.com");
    r.check(on_main.contains(&"sc_host=host-A".to_string()), "sc_host ana sayfaya gidiyor");
    r.check(!on_secure.contains(&"sc_host=host-A".to_string()), "sc_host (ana makine) alt alan adlarına SIZMIYOR");
    let snap_a2 = session::snapshot_cookies(&wv);
    let mut a1 = snap_a.clone();
    let mut a2 = snap_a2.clone();
    a1.sort_by(|x, y| x.name.cmp(&y.name));
    a2.sort_by(|x, y| x.name.cmp(&y.name));
    r.check(a1 == a2, "geri yüklenen oturum, kaydedilenle BİREBİR aynı (tüm özellikler)");

    println!("4) Token ile giriş: eski alan çerezi ezilmeli, yeni token alt alan adlarına da gitmeli");
    session::set_soundcloud_oauth_cookie(&wv, "tok-C").unwrap();
    let toks: Vec<String> = wv
        .cookies()
        .unwrap()
        .iter()
        .filter(|c| c.name() == "oauth_token")
        .map(|c| c.value().to_string())
        .collect();
    r.check(toks == vec!["tok-C".to_string()], &format!("yalnızca yeni token var: {toks:?}"));
    r.check(
        names_for(&wv, "https://artists.soundcloud.com").contains(&"oauth_token=tok-C".to_string()),
        "token çerezi artists.soundcloud.com adresine de gidiyor",
    );
    r.check(
        !wv.cookies().unwrap().iter().any(|c| c.name() == "sess" || c.name() == "artists_sid"),
        "önceki hesabın diğer çerezleri temizlendi",
    );

    println!("5) Süresi dolmuş çerez geri yüklenmez");
    let mut old = snap_a.clone();
    for c in old.iter_mut() {
        c.expires = Some(1_000_000_000); // 2001
    }
    let n = session::restore_cookies(&wv, &old);
    r.check(n == 0 && wv.cookies().unwrap().is_empty(), "süresi dolanlar atlandı, eski oturum da silindi");

    session::wipe_session_blocking(&wv);
    println!("\n{}", if r.failed == 0 { "TÜM KONTROLLER GEÇTİ" } else { "BAŞARISIZ KONTROL VAR" });
    std::process::exit(if r.failed == 0 { 0 } else { 1 });
}
