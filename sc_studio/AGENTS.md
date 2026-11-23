# AGENTS.md

Bu depo **SC Studio 2.0** (eski adı SoundCloud Studio) — Python/PyInstaller uygulamasının Rust portu.
Ayrıntılı devir teslim dosyası: **[`HANDOVER.md`](HANDOVER.md)** (önce onu oku).

## Komutlar

```bash
cargo build --release    # → target/release/soundcloud-studio.exe
cargo test               # 16 test, hepsi geçmeli
cargo check              # hızlı tip kontrolü
```

Çalıştırma / hata ayıklama:

```bash
dist\SoundCloudStudio.exe --server-only   # pencere yok, sadece HTTP
tail -1 "%APPDATA%\SoundCloudStudio\studio.log"   # → http://127.0.0.1:PORT
```

## Mutlak kurallar

1. **`dist/` çalışırken `cargo build` yapılamaz** — exe kilitli. Önce kapat.
2. **Hiçbir şey exe'nin yanına yazılmaz** — tüm durum `%APPDATA%\SoundCloudStudio`.
3. **Puanlama ağırlıkları ve başlık regex sırası değiştirilmez** — orijinal
   Python davranışının birebir portu (`score.rs`, `titles.rs`).
4. **İki webview aynı `wry::WebContext`'i paylaşmalı** — yoksa exe yanında
   `*.WebView2` klasörü açılır.
5. **Kullanıcının müzik klasöründe izinsiz silme/taşıma yapılmaz.**
6. `assets/artwork_pool` (208 gerçek SoundCloud kapağı) **telif riski** —
   ticari sürümden çıkarılmalı, yerine prosedürel üreteç gelmeli.

## Sık düşülen tuzaklar

- `tao`: `CloseRequested`'ı sen işlemezsen pencere kapanmaz.
- `ControlFlow::Wait` periyodik işi durdurur → `WaitUntil(now + 600ms)`.
- `wry 0.53`: `with_data_directory` yok, `WebContext::new(Some(dir))` var.
- `reqwest 0.13`: `.query()` / `.form()` için feature açık olmalı.
- Dinamik MSVC CRT kullanma: `.cargo/config.toml`'da `+crt-static` şart.
- `audio/mpegurl` MP3 **değil** (abr_sq HLS listesi). MP3 testi: `sc::is_mp3_mime`.
- ID3 yalnızca `.mp3`'e yazılır; FLAC/WAV/M4A'ya yazmak dosyayı bozar.
- Canlı test için `APPDATA`'yı geçici klasöre yönlendir; gerçek veriye dokunma.
- WebView2 çerezi: alan çerezi (`.soundcloud.com`, alt alan adlarına da gider) yazmak için
  `Cookie::domain("..soundcloud.com")` ver (cookie kütüphanesi baştaki TEK noktayı atar);
  noktasız alan yalnızca ana makine çerezi olur. `delete_cookie` iki biçimi ayrı sayar →
  `session::delete_cookie_all_variants`. `clear_all_browsing_data` asenkron → hemen ardından
  çerez yazmadan önce `session::wipe_session_blocking` kullan.
- Hesap geçişi çerez anlık görüntüsüyle yapılır (`accounts.json`, DPAPI); token yalnızca yedek
  (web tokenı ~1 saatlik olabilir). Çerez hattını gerçek WebView2'de doğrula:
  `cargo run --example cookie_probe -- <geçici klasör>` (hata varsa çıkış kodu 1).
- `UiEvent::AddAccount` oturumu kaydedip temizler; giriş penceresi kapatılırsa önceki hesap geri yüklenir.
- Tarama: SoundCloud'da son 14 günde 100K+ dinlenmeli parça neredeyse hiç yok; eskiden liste en az
  dinlenenlerle doluyordu. `expand_search` (varsayılan açık) aralık dışından, türe uygun
  (`scan::is_relevant`) ve çok dinlenmiş parçalarla tamamlar; sıralama `scan::rank/tier_of`
  (testli). Kaynaklar: `filter.genre_or_tag` aramaları ve `/tracks/{id}/related`. Aralık dışı
  parçalarda alaka süzgeci şart: yalnızca dinlenme, dizi müziği/pop gibi alakasızları da geçirir.

## Yığın

Rust 1.99 (MSVC, statik CRT) · axum 0.8 · tokio · wry 0.53 + tao 0.34 ·
reqwest 0.13 · image 0.25 · rust-embed 8 · sha2

Arayüz: `assets/index.html` (tek dosya, saf JS/CSS, Türkçe).
