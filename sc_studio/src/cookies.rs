//! Tarayıcı çerez kaydı: WebView2'den okunan çerezlerin saklama biçimi ve geri dönüşümü.
//! Başka uygulama modüllerine bağımlı değildir (tanı örneği bu dosyayı doğrudan dahil eder).

use serde::{Deserialize, Serialize};
use wry::cookie::{Cookie, SameSite};

/// Tek bir tarayıcı çerezi (WebView2'den okunur / geri yüklenir).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CookieRec {
    pub name: String,
    pub value: String,
    pub domain: String,
    pub path: String,
    pub secure: bool,
    pub http_only: bool,
    /// 0 = Lax, 1 = Strict, 2 = None
    pub same_site: u8,
    /// Unix saniye; `None` = oturum çerezi.
    pub expires: Option<i64>,
    /// `true`: yalnızca bu ana makineye giden çerez; `false`: alt alan adlarına da giden alan çerezi.
    /// (WebView2 her ikisini de aynı alan adıyla listeler; ayrım alt alan sorgusuyla yapılır.)
    #[serde(default)]
    pub host_only: bool,
}

/// soundcloud.com ve alt alan adları (secure., artists., api-v2. ...).
pub fn is_soundcloud_domain(domain: &str) -> bool {
    let d = domain.trim_start_matches('.').to_ascii_lowercase();
    d == "soundcloud.com" || d.ends_with(".soundcloud.com")
}

impl CookieRec {
    pub fn from_cookie(c: &Cookie<'_>, host_only: bool) -> Option<Self> {
        // Alan adı her zaman baştaki noktasız saklanır; alan/ana makine ayrımı `host_only` ile taşınır.
        let domain = c.domain()?.trim_start_matches('.').to_string();
        Some(Self {
            name: c.name().to_string(),
            value: c.value().to_string(),
            domain,
            path: c.path().unwrap_or("/").to_string(),
            secure: c.secure().unwrap_or(false),
            http_only: c.http_only().unwrap_or(false),
            same_site: match c.same_site() {
                Some(SameSite::Strict) => 1,
                Some(SameSite::None) => 2,
                _ => 0,
            },
            expires: c.expires_datetime().map(|d| d.unix_timestamp()),
            host_only,
        })
    }

    pub fn to_cookie(&self) -> Cookie<'static> {
        // `cookie` kütüphanesi baştaki TEK noktayı okurken atar; WebView2'ye ".alan" gitsin
        // (alt alan adlarına da giden alan çerezi) diye iki nokta yazılır. Noktasız alan
        // WebView2'de yalnızca ana makine çerezi olur.
        let domain = if self.host_only {
            self.domain.clone()
        } else {
            format!("..{}", self.domain.trim_start_matches('.'))
        };
        let mut b = Cookie::build((self.name.clone(), self.value.clone()))
            .domain(domain)
            .path(self.path.clone())
            .secure(self.secure)
            .http_only(self.http_only)
            .same_site(match self.same_site {
                1 => SameSite::Strict,
                2 => SameSite::None,
                _ => SameSite::Lax,
            });
        if let Some(ts) = self.expires {
            if let Ok(dt) = wry::cookie::time::OffsetDateTime::from_unix_timestamp(ts) {
                b = b.expires(dt);
            }
        }
        b.build()
    }

    pub fn is_expired(&self, now_unix: i64) -> bool {
        matches!(self.expires, Some(t) if t <= now_unix)
    }
}

/// Çerez listesinde giriş yapılmış bir hesabı gösteren `oauth_token` var mı?
pub fn has_login_cookie(recs: &[CookieRec]) -> bool {
    recs.iter().any(|r| r.name == "oauth_token" && !r.value.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn domain_cookies_reach_webview2_with_a_leading_dot_and_host_cookies_without() {
        // WebView2'ye giden alan = Cookie::domain() çıktısı (wry bunu CreateCookie'ye verir).
        let mut r = rec("refresh", "tok", "soundcloud.com", Some(1_900_000_000));
        r.host_only = false;
        assert_eq!(r.to_cookie().domain(), Some(".soundcloud.com"), "alan çerezi: baştaki nokta korunmalı");
        r.domain = ".soundcloud.com".into(); // zaten noktalıysa tekrarlanmamalı
        assert_eq!(r.to_cookie().domain(), Some(".soundcloud.com"));
        r.host_only = true;
        r.domain = "secure.soundcloud.com".into();
        assert_eq!(r.to_cookie().domain(), Some("secure.soundcloud.com"), "ana makine çerezi: noktasız");
    }

    #[test]
    fn cookie_conversion_roundtrip_keeps_every_attribute() {
        let r = rec("refresh", "tok", "soundcloud.com", Some(1_900_000_000));
        let c = r.to_cookie();
        assert_eq!(c.name(), "refresh");
        assert_eq!(c.http_only(), Some(true));
        assert_eq!(c.secure(), Some(true));
        assert_eq!(c.same_site(), Some(SameSite::Strict));
        // Okurken noktayı atan accessor yüzünden geri dönüşüm alan adını noktasız verir; host_only ayrı taşınır.
        assert_eq!(CookieRec::from_cookie(&c, false).unwrap(), r);
        let mut h = r.clone();
        h.host_only = true;
        assert_eq!(CookieRec::from_cookie(&h.to_cookie(), true).unwrap(), h);

        // oturum çerezi: süre yok
        let s = rec("s", "v", "soundcloud.com", None);
        assert_eq!(CookieRec::from_cookie(&s.to_cookie(), false).unwrap().expires, None);

        // alan adı yoksa kaydedilemez
        let no_domain = Cookie::build(("a", "b")).build();
        assert!(CookieRec::from_cookie(&no_domain, false).is_none());

        // SameSite eşlemesi
        for (n, ss) in [(0u8, SameSite::Lax), (1, SameSite::Strict), (2, SameSite::None)] {
            let mut x = rec("a", "b", "soundcloud.com", None);
            x.same_site = n;
            assert_eq!(x.to_cookie().same_site(), Some(ss));
        }
    }

    #[test]
    fn soundcloud_domain_filter_and_expiry() {
        assert!(is_soundcloud_domain(".soundcloud.com"));
        assert!(is_soundcloud_domain("soundcloud.com"));
        assert!(is_soundcloud_domain("artists.soundcloud.com"));
        assert!(is_soundcloud_domain(".Secure.SoundCloud.com"));
        assert!(!is_soundcloud_domain("notsoundcloud.com"));
        assert!(!is_soundcloud_domain(".google.com"));
        assert!(!is_soundcloud_domain("127.0.0.1"));
        assert!(is_soundcloud_domain("api-v2.soundcloud.com") && !is_soundcloud_domain("soundcloud.com.evil.io"));

        assert!(rec("a", "b", "soundcloud.com", Some(100)).is_expired(200));
        assert!(!rec("a", "b", "soundcloud.com", Some(300)).is_expired(200));
        assert!(!rec("a", "b", "soundcloud.com", None).is_expired(200));
    }

    #[test]
    fn login_cookie_detection() {
        assert!(!has_login_cookie(&[]));
        assert!(!has_login_cookie(&[rec("sid", "x", "soundcloud.com", None)]));
        assert!(!has_login_cookie(&[rec("oauth_token", "", "soundcloud.com", None)]));
        assert!(has_login_cookie(&[rec("oauth_token", "2-1", "soundcloud.com", None)]));
    }
}
