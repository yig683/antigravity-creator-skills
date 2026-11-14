//! SC Studio — Rust sürümü.
//!
//! Mimarî: arka planda yerel bir HTTP sunucusu (axum) çalışır, ön yüz bu
//! sunucudan beslenir ve WebView2 penceresinde gösterilir. Orijinal
//! Python/pywebview/Flask yapısıyla aynı fikir, fakat tek bir statik binary.
//!
//! Release derlemesi `windows` alt sistemini kullanır: çift tıklanınca
//! konsol penceresi açılmaz. Bu yüzden başlatma hataları MessageBox ile
//! gösterilir (bkz. `winmsg`).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod api;
mod artwork;
mod auth;
mod assets;
mod config;
mod download;
mod id3;
mod jobobj;
mod paths;
mod rng;
mod sc;
mod scan;
mod score;
mod state;
mod titles;
mod ui;
mod winmsg;

use std::sync::Arc;

fn main() {
    // Kapanınca ffmpeg gibi alt süreçler de ölsün.
    jobobj::kill_children_on_exit();

    if let Err(e) = paths::bootstrap() {
        winmsg::message_box(
            "SC Studio",
            &format!(
                "Veri klasörü oluşturulamadı:\n{}\n\n{}",
                paths::data_dir().display(),
                e
            ),
            true,
        );
        std::process::exit(1);
    }

    // Konsol olmadığı için log'ları dosyaya yaz. Veri klasörü yukarıda
    // oluşturuldu; ilk açılışta da log yazılabilsin diye sıra önemli.
    let log_target = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(paths::data_dir().join("studio.log"))
        .ok();

    let server_only = std::env::args().any(|a| a == "--server-only");

    // Tek örnek: uygulama zaten açıksa onu öne getir ve çık. İki örnek aynı
    // ayar dosyasına yazıp birbirinin durumunu ezerdi.
    if !server_only && !winmsg::acquire_single_instance() {
        winmsg::focus_existing_window("SC Studio");
        std::process::exit(0);
    }

    if !winmsg::webview2_available() {
        winmsg::message_box(
            "SC Studio — WebView2 gerekli",
            "Bu bilgisayarda Microsoft Edge WebView2 çalışma zamanı bulunamadı.\n\n\
             Windows 10 ve 11'de genellikle kurulu gelir. Kurmak için:\n\
             https://developer.microsoft.com/microsoft-edge/webview2/\n\n\
             (\"Evergreen Standalone Installer\" bağlantısını indirin.)",
            true,
        );
        std::process::exit(1);
    }

    let cfg = config::load();
    // Önceki oturumdan kalan yarım indirme dosyalarını temizle.
    let _ = download::cleanup_stale_parts(&cfg.target_dir());

    let state = match state::AppState::new(cfg) {
        Ok(s) => Arc::new(s),
        Err(e) => {
            winmsg::message_box(
                "SC Studio",
                &format!("Uygulama başlatılamadı:\n{e}"),
                true,
            );
            std::process::exit(1);
        }
    };

    let port = match start_server(Arc::clone(&state)) {
        Ok(p) => p,
        Err(e) => {
            winmsg::message_box(
                "SC Studio",
                &format!("Yerel sunucu başlatılamadı:\n{e}"),
                true,
            );
            std::process::exit(1);
        }
    };

    if let Some(mut f) = log_target {
        use std::io::Write;
        let _ = writeln!(f, "SC Studio başladı — http://127.0.0.1:{port}");
    }

    // Hata ayıklama / otomasyon için: pencere açmadan sadece sunucuyu çalıştır.
    if server_only {
        loop {
            std::thread::sleep(std::time::Duration::from_secs(3600));
        }
    }

    // WebView ana thread'de çalışmak zorunda; olay döngüsü hiç dönmez.
    ui::run(port, Arc::clone(&state));
}

/// Arka plan thread'inde tokio çalışma zamanını ve HTTP sunucusunu başlatır.
/// Dinleyici burada (senkron olarak) bağlandığı için port hazır olduğunda
/// döner; WebView açıldığında sunucu çoktan bağlantı kabul ediyor olur.
fn start_server(state: Arc<state::AppState>) -> std::io::Result<u16> {
    let (tx, rx) = std::sync::mpsc::channel::<std::io::Result<u16>>();

    std::thread::Builder::new()
        .name("scs-http".into())
        .spawn(move || {
            let runtime = match tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .build()
            {
                Ok(rt) => rt,
                Err(e) => {
                    let _ = tx.send(Err(e));
                    return;
                }
            };

            runtime.block_on(async move {
                let listener = match tokio::net::TcpListener::bind(("127.0.0.1", 0)).await {
                    Ok(l) => l,
                    Err(e) => {
                        let _ = tx.send(Err(e));
                        return;
                    }
                };
                let port = match listener.local_addr() {
                    Ok(addr) => addr.port(),
                    Err(e) => {
                        let _ = tx.send(Err(e));
                        return;
                    }
                };
                *state.port.write().await = port;
                let _ = tx.send(Ok(port));

                let router = api::router(Arc::clone(&state));
                if let Err(e) = axum::serve(listener, router).await {
                    eprintln!("Sunucu hatası: {e}");
                }
            });
        })?;

    rx.recv()
        .unwrap_or_else(|_| Err(std::io::Error::other("sunucu thread'i kapandı")))
}
