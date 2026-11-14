//! Masaüstü penceresi (tao + wry → WebView2) ve uygulama içi tarayıcı.

use std::sync::Arc;
use std::time::{Duration, Instant};
use tao::dpi::{PhysicalSize, Size};
use tao::event::{Event, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoopBuilder, EventLoopWindowTarget};
use tao::window::{Window, WindowBuilder};
use wry::{WebView, WebViewBuilder};

/// Arayüz thread'ine gönderilen olaylar (HTTP katmanından tetiklenir).
#[derive(Debug, Clone)]
pub enum UiEvent {
    /// Tarayıcı penceresini aç / öne getir. Adres verilirse oraya git
    /// ("Keşfet" adressiz, "SoundCloud ile giriş yap" giriş sayfasıyla).
    OpenBrowser(Option<String>),
    /// Tarayıcıda giriş yapılan hesap alındı; pencere giriş için açıldıysa kapat.
    LoginDetected,
    /// Ana pencereyi öne getir (ör. varsayılan tarayıcıda giriş bitince).
    FocusMain,
}

/// SoundCloud giriş sayfası.
pub const SIGNIN_URL: &str = "https://soundcloud.com/signin";

/// soundcloud.com sayfalarına enjekte edilen betik: giriş yapılmışsa hesabın
/// kimliğini, adını ve avatarını uygulamaya bildirir. Belirteç uygulamaya
/// gönderilmez; yalnızca sayfanın içinde /me isteği için kullanılır.
const LOGIN_PROBE_JS: &str = r#"
(function () {
  if (location.hostname !== "soundcloud.com" || !window.ipc) return;
  var sent = false;
  function report(me) {
    if (sent || !me || !me.id || !me.username) return;
    sent = true;
    window.ipc.postMessage(JSON.stringify({
      type: "sc_user",
      id: String(me.id),
      username: me.username || "",
      avatar_url: me.avatar_url || "",
      permalink_url: me.permalink_url || ""
    }));
  }
  function check() {
    if (sent) return;
    try {
      var h = window.__sc_hydration;
      if (Array.isArray(h)) {
        for (var i = 0; i < h.length; i++) {
          if (h[i] && h[i].hydratable === "meUser" && h[i].data) { report(h[i].data); return; }
        }
      }
      var m = document.cookie.match(/(?:^|;\s*)oauth_token=([^;]+)/);
      if (!m) return;
      fetch("https://api-v2.soundcloud.com/me", {
        headers: { Authorization: "OAuth " + decodeURIComponent(m[1]) }
      }).then(function (r) { return r.ok ? r.json() : null; })
        .then(report).catch(function () {});
    } catch (e) {}
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", check);
  else check();
  setInterval(check, 2500);
})();
"#;

/// Tarayıcıdan gelen hesap bildirimini işler.
fn handle_ipc(state: &crate::state::AppState, page: &str, body: &str) {
    use std::sync::atomic::Ordering;

    // Yalnızca soundcloud.com'dan gelen ve giriş beklenirken gelen bildirim.
    let from_sc = page.starts_with("https://soundcloud.com/") || page == "https://soundcloud.com";
    if !from_sc || !state.login_pending.load(Ordering::SeqCst) {
        return;
    }
    let Ok(v) = serde_json::from_str::<serde_json::Value>(body) else {
        return;
    };
    if v.get("type").and_then(|t| t.as_str()) != Some("sc_user") {
        return;
    }
    let s = |k: &str| v.get(k).and_then(|x| x.as_str()).unwrap_or("").to_string();
    let (id, username) = (s("id"), s("username"));
    if id.is_empty() || username.is_empty() {
        return;
    }

    let auth = crate::auth::AuthState {
        user_id: id,
        username,
        avatar_url: s("avatar_url"),
        permalink_url: s("permalink_url"),
        web_session: true,
        ..Default::default()
    };
    let _ = crate::auth::save(&auth);
    *state.auth.blocking_write() = auth;
    state.login_pending.store(false, Ordering::SeqCst);

    if let Ok(slot) = state.ui_tx.lock() {
        if let Some(proxy) = slot.as_ref() {
            let _ = proxy.send_event(UiEvent::LoginDetected);
        }
    }
}

pub fn run(port: u16, state: Arc<crate::state::AppState>) -> ! {
    let event_loop = EventLoopBuilder::<UiEvent>::with_user_event().build();

    // HTTP katmanı bu proxy üzerinden pencere açtırabiliyor.
    if let Ok(mut slot) = state.ui_tx.lock() {
        *slot = Some(event_loop.create_proxy());
    }

    // Pencere boyutu ekranın %88'i (fiziksel piksel) — yüksek DPI'da taşmasın.
    let main_size = fit_to_screen(&event_loop, 0.88, (1600, 1000), (1100, 700));

    let main_window = match WindowBuilder::new()
        .with_title("SC Studio")
        .with_inner_size(main_size)
        .with_min_inner_size(Size::Physical(PhysicalSize::new(1000, 620)))
        .build(&event_loop)
    {
        Ok(w) => w,
        Err(e) => {
            crate::winmsg::message_box(
                "SC Studio",
                &format!("Pencere oluşturulamadı:\n{e}"),
                true,
            );
            std::process::exit(1);
        }
    };

    if let Some(icon) = load_icon() {
        main_window.set_window_icon(Some(icon));
    }

    let main_id = main_window.id();
    let url = format!("http://127.0.0.1:{}/", port);

    // WebView2 veri klasörü exe'nin yanında değil %APPDATA%'da olsun.
    let data_dir = crate::paths::data_dir().join("WebView2");
    let _ = crate::paths::ensure_dir(&data_dir);
    let mut web_context = wry::WebContext::new(Some(data_dir));

    let main_webview = WebViewBuilder::new_with_web_context(&mut web_context)
        .with_url(&url)
        .with_devtools(cfg!(debug_assertions))
        .with_background_color((11, 11, 12, 255))
        .build(&main_window);

    if let Err(e) = main_webview {
        crate::winmsg::message_box(
            "SC Studio — WebView2",
            &format!(
                "Arayüz başlatılamadı.\n\n{e}\n\n\
                 Microsoft Edge WebView2 çalışma zamanı eksik olabilir:\n\
                 https://developer.microsoft.com/microsoft-edge/webview2/"
            ),
            true,
        );
        std::process::exit(1);
    }

    let mut browser: Option<(Window, WebView)> = None;
    // Tarayıcı penceresi giriş için mi açıldı? (Giriş bitince kendiliğinden kapanır.)
    let mut opened_for_login = false;

    event_loop.run(move |event, target, control_flow| {
        // web_context bu closure'a ait; iki pencere de aynı profili kullanıyor.
        match event {
            Event::WindowEvent {
                window_id,
                event: WindowEvent::CloseRequested,
                ..
            } => {
                if window_id == main_id {
                    *control_flow = ControlFlow::Exit;
                    return;
                }
                // Tarayıcı penceresi kapatıldı; bekleyen giriş de iptal.
                browser = None;
                opened_for_login = false;
                state
                    .login_pending
                    .store(false, std::sync::atomic::Ordering::SeqCst);
            }

            Event::UserEvent(UiEvent::OpenBrowser(url)) => {
                opened_for_login = url.as_deref() == Some(SIGNIN_URL);
                match browser.as_ref() {
                    Some((win, webview)) => {
                        if let Some(u) = url.as_deref() {
                            let _ = webview.load_url(u);
                        }
                        win.set_minimized(false);
                        win.set_focus();
                    }
                    None => {
                        // Aynı WebContext'i paylaş: aksi halde WebView2 exe'nin
                        // yanında ikinci bir "*.WebView2" klasörü açıyor.
                        let start = url.unwrap_or_else(|| "https://soundcloud.com/discover".into());
                        browser = create_browser_window(target, &mut web_context, &start, Arc::clone(&state));
                    }
                }
            }

            Event::UserEvent(UiEvent::FocusMain) => {
                main_window.set_minimized(false);
                main_window.set_focus();
            }

            Event::UserEvent(UiEvent::LoginDetected) => {
                if opened_for_login {
                    browser = None;
                    opened_for_login = false;
                    main_window.set_focus();
                }
            }

            _ => {}
        }

        // Tarayıcıdaki adresi 600 ms'de bir oku; ana arayüzdeki
        // "Sayfayı aktar" düğmesi bu değeri kullanıyor.
        if let Some((_, webview)) = browser.as_ref() {
            if let Ok(current) = webview.url() {
                if let Ok(mut slot) = state.browser_url.lock() {
                    if *slot != current {
                        *slot = current;
                    }
                }
            }
        }
        *control_flow = ControlFlow::WaitUntil(Instant::now() + Duration::from_millis(600));
    });
}

fn create_browser_window(
    target: &EventLoopWindowTarget<UiEvent>,
    context: &mut wry::WebContext,
    start_url: &str,
    state: Arc<crate::state::AppState>,
) -> Option<(Window, WebView)> {
    let window = WindowBuilder::new()
        .with_title("SoundCloud")
        .with_inner_size(Size::Physical(PhysicalSize::new(1180, 820)))
        .with_min_inner_size(Size::Physical(PhysicalSize::new(860, 560)))
        .build(target)
        .ok()?;

    if let Some(icon) = load_icon() {
        window.set_window_icon(Some(icon));
    }

    let webview = WebViewBuilder::new_with_web_context(context)
        .with_url(start_url)
        .with_initialization_script(LOGIN_PROBE_JS)
        // wry yeni pencere isteklerini varsayılan olarak reddeder; SoundCloud'un
        // Facebook / Google / Apple girişleri açılır pencere kullandığı için
        // "Please enable popup windows" hatası veriyordu. WebView2'nin kendi
        // açılır penceresine izin ver (opener bağı korunur, giriş tamamlanır).
        .with_new_window_req_handler(|url, _features| {
            if url.starts_with("https://") || url == "about:blank" {
                wry::NewWindowResponse::Allow
            } else {
                wry::NewWindowResponse::Deny
            }
        })
        .with_ipc_handler(move |req| {
            let page = req.uri().to_string();
            handle_ipc(&state, &page, req.body());
        })
        .with_devtools(cfg!(debug_assertions))
        .with_background_color((18, 18, 18, 255))
        .build(&window)
        .ok()?;

    Some((window, webview))
}

/// Ekranın oranı kadar, verilen sınırlar içinde kalan pencere boyutu.
fn fit_to_screen(
    target: &EventLoopWindowTarget<UiEvent>,
    ratio: f64,
    max: (u32, u32),
    min: (u32, u32),
) -> Size {
    let screen = target
        .primary_monitor()
        .map(|m| m.size())
        .unwrap_or(PhysicalSize::new(1600, 1000));

    let w = ((screen.width as f64 * ratio) as u32).clamp(min.0, max.0);
    let h = ((screen.height as f64 * ratio) as u32).clamp(min.1, max.1);
    Size::Physical(PhysicalSize::new(w, h))
}

fn load_icon() -> Option<tao::window::Icon> {
    let bytes = crate::assets::asset_bytes("icon.png")?;
    let img = image::load_from_memory(&bytes).ok()?.to_rgba8();
    let (w, h) = img.dimensions();
    tao::window::Icon::from_rgba(img.into_raw(), w, h).ok()
}
