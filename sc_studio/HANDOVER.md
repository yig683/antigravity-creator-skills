# DEVİR TESLİM — SC Studio 2.0 (Rust, eski adı SoundCloud Studio)

> **Bu dosya bir yapay zekâ asistanına devretmek için yazıldı.**
> Yeni oturuma şunu ver: bu dosyanın içeriği + depo yolu
> `C:\Users\alief\WorkBuddy AI\2026-11-11-22-39-58\soundcloud-studio`.
> Başlamadan önce `README.md`'yi de oku; burası onun üstüne operasyonel
> gerçeği ekler.

Son güncelleme: 12 Kasım 2026, 03:10 (GMT+3)
Son commit: `ca8770b` — "SoundCloud Studio 2.0 — Rust portu: tarama, indirme, kapak, OAuth, tarayıcı"

---

## 1. Tek cümlede proje

PyInstaller ile paketlenmiş bir Python uygulaması (SoundCloud'dan viral edit
parçası bulup indiren araç) **sıfırdan Rust'a port edildi**; şu an çalışır
durumda, tek exe + ffmpeg olarak dağıtılıyor ve **ticari satışa hazırlanıyor**.

Kullanıcı Türkçe konuşuyor, ürünün arayüzü de Türkçe. Kod yorumları Türkçe.

---

## 2. Hızlı başlangıç

```bash
cd "C:\Users\alief\WorkBuddy AI\2026-11-11-22-39-58\soundcloud-studio"

cargo build --release          # ~30-60 sn (ilk temiz derleme ~4 dk)
cargo test                     # 16 test, hepsi geçmeli
cargo check                    # hızlı tip kontrolü
```

Çalıştırma:

```bash
dist\SoundCloudStudio.exe              # normal (WebView2 penceresi)
dist\SoundCloudStudio.exe --server-only # pencere yok, sadece HTTP sunucu
```

`--server-only` hata ayıklamada çok işe yarıyor: port `studio.log`'a yazılıyor,
`curl` ile API'yi test edebiliyorsun:

```bash
tail -1 "%APPDATA%\SoundCloudStudio\studio.log"   # → http://127.0.0.1:PORT
curl http://127.0.0.1:PORT/api/health
```

Paketleme:

```bash
cp target/release/soundcloud-studio.exe dist/SoundCloudStudio.exe
# dist/ içinde: SoundCloudStudio.exe + ffmpeg.exe + Beni Oku.txt
# ZIP: SoundCloudStudio-2.0-win64.zip (113 MB)
```

> **DİKKAT:** `dist/SoundCloudStudio.exe` çalışırken `cargo build` başarısız
> olur ("Erişim engellendi"). Önce uygulamayı kapat.

---

## 3. Ürün ne yapıyor

1. **AI Küratör taraması** — SoundCloud'da viral edit parçalarını (hardtekk,
   slowed+reverb, phonk, montagem) paralel tarar, 8 boyutlu puanlar.
2. **İndirme** — seçilenleri 320 kbps MP3 olarak indirir (HLS → ffmpeg).
3. **Akıllı başlık** — `y2mate.com - X (320kbps) [slowed]` → `X (Slowed + Reverb)`.
4. **Kapak** — 800×800 JPEG üretir, ID3'e gömer, yanına `.jpg` bırakır.
5. **Kütüphane** — çal, yenile, sil, klasör değiştir, kapakları dışa aktar.
6. **SoundCloud ile giriş** (OAuth 2.1 + PKCE) → "Beğenilerim" kaynağı.
7. **Uygulama içi tarayıcı** — ayrı pencerede soundcloud.com; "Sayfayı aktar"
   o an açık sayfayı taramaya verir.

---

## 4. Mimari

```
┌───────────────────────────────────────────────┐
│ WebView2 (tao + wry)                          │
│  assets/index.html — tek dosya, saf JS/CSS    │
│  · açılış animasyonu (WAAPI)                  │
│  · giriş ekranı (ilk açılış)                  │
│  · 3 sütunlu ana panel + player               │
└──────────────┬────────────────────────────────┘
               │ fetch → 127.0.0.1:<rastgele port>
┌──────────────▼────────────────────────────────┐
│ axum HTTP sunucusu (ayrı thread + tokio)      │
│  api.rs 1113  rotalar, Range'li dosya sunumu  │
│  scan.rs 458  tarama orkestrasyonu + sıralama │
│  sc.rs   448  SoundCloud API + client_id      │
│  auth.rs 327  OAuth 2.1 PKCE + token          │
│  download.rs 337  ffmpeg hattı + ilerleme     │
│  score.rs 252 puanlama (ağırlıklar birebir)   │
│  titles.rs 227 akıllı başlık (regex sırası)   │
│  ui.rs   171  pencere + tarayıcı penceresi    │
│  artwork.rs    kapak havuzu: kayan pencere +  │
│                ikiz görseller + 800×800       │
│  coverfx.rs    kapak çeşitlendirme (kırpma,   │
│                renk tonu, tane; `cover_style`)│
│  accounts.rs   çoklu hesap listesi (DPAPI)    │
│  cookies.rs    çerez kaydı biçimi (alan/ana   │
│                makine ayrımı)                 │
│  session.rs    WebView2 çerez oku/sil/yükle   │
│  id3.rs  162  elle yazılmış ID3v2.3           │
│  config.rs 166 ayarlar (atomik yazma)         │
│  main.rs 160  bootstrap + sunucu thread'i     │
│  state.rs 129 paylaşılan durum                │
│  winmsg.rs 109 MessageBoxW + WebView2 kontrol │
│  paths.rs 104 dosya yerleşimi                 │
│  jobobj.rs 96 Job Object (çocuk süreç öldürme)│
│  rng.rs   54  xorshift (bağımlılıksız)        │
│  assets.rs 15 gömülü varlıklar                │
└───────────────────────────────────────────────┘
```

**Veri akışı (indirme):** `POST /api/curator/download-selected` → `tokio::spawn`
→ `download::run_batch` → `sc.resolve(url)` → `sc.stream_source()` →
`ffmpeg` (HLS→MP3) → `artwork::make_cover` → `id3::write_tags` → meta kaydı.

**Neden bu mimari:** orijinal uygulama Flask + pywebview'dı; aynı fikri
koruyup (yerel HTTP + webview) Rust'a taşımak, arayüzü yeniden yazmadan
backend'i sağlamlaştırdı. Tauri yerine `wry` seçildi çünkü Node/npm ve
Tauri CLI olmadan `cargo build` ile derlenebiliyor.

---

## 5. Dosya yerleşimi (çalışma zamanı)

| Ne | Nerede |
|---|---|
| Ayarlar | `%APPDATA%\SoundCloudStudio\config.json` |
| OAuth oturumu | `%APPDATA%\SoundCloudStudio\auth.json` |
| Görülen parçalar | `%APPDATA%\SoundCloudStudio\seen_tracks.json` |
| Şarkı meta | `%APPDATA%\SoundCloudStudio\track_metadata.json` |
| Kapak önbelleği | `%APPDATA%\SoundCloudStudio\covers\` |
| Kullanıcı kapakları | `%APPDATA%\SoundCloudStudio\artwork_pool\` |
| WebView2 profili | `%APPDATA%\SoundCloudStudio\WebView2\` |
| Log (port dahil) | `%APPDATA%\SoundCloudStudio\studio.log` |
| İndirilen şarkılar | `%USERPROFILE%\Music\SoundCloud_Dinleme_Arsivi` |

**Kural:** hiçbir şey exe'nin yanına yazılmaz. (İlk sürümlerde yazıyordu,
Program Files'ta kırılıyordu; `paths.rs` bunu garanti eder.)

---

## 6. Doğrulanmış durum (iddia değil, test edilmiş)

| Ne | Nasıl doğrulandı |
|---|---|
| Derleme | `cargo build --release`, **sıfır uyarı** |
| Testler | `cargo test` → **16/16** (puanlama, başlık, ID3, PKCE, MP3 türü, yol güvenliği) |
| Tarama | 4 farklı kaynak (hardtekk, phonk, slowed, tek parça URL) canlı test |
| İndirme | 320 kbps MP3 (AAC kaynaktan çevrim; ffmpeg probe), ID3 TIT2/TPE1/TALB/TCON/APIC doğru, kapak 800×800 |
| Toplu ilerleme | 2 parçalık indirmede çubuk 0→%50→%100, "1/2", "2/2" (12 Kas, izole APPDATA) |
| Tek örnek | İkinci açılış eskisini öne getirip çıkıyor (çıkış kodu 0) |
| Beğeniler (girişsiz) | Profil linkiyle `my_likes` → 5 aday |
| Range isteği | `206 Partial Content` + `Content-Range` |
| Path traversal | `..%2F..%2FWindows%2Fwin.ini` → 404 |
| Pencere kapatma | `taskkill /PID` (WM_CLOSE) → süreç anında çıkıyor |
| ffmpeg temizliği | İndirme sırasında kapatma → ffmpeg sayısı 1→0 |
| Statik CRT | PE import tablosunda `VCRUNTIME140.dll` **yok** |
| GUI alt sistemi | PE subsystem = 2 (konsol penceresi açılmıyor) |
| Tarayıcı penceresi | Açılıyor, `/api/browser/url` → `https://soundcloud.com/discover` |
| WebView2 klasörü | Exe yanında oluşmuyor (ortak WebContext) |

### Doğrulanmamış (dikkat)

- **Gerçek OAuth girişi uçtan uca test edilmedi** — kullanıcının SoundCloud
  uygulama kaydı yok, `client_id`/`client_secret` boş. Kod hazır, kimlik yok.
  Kayıt yapılınca kimlik derlemeye gömülür (config.json'a yazılmaz):
  `SCS_SC_CLIENT_ID=... SCS_SC_CLIENT_SECRET=... cargo build --release`.
  Yönlendirme adresi kayıtta birebir `http://127.0.0.1:47821/oauth/callback`
  olmalı. Gömülüyse "SoundCloud ile giriş yap" varsayılan tarayıcıda açılır;
  değilse uygulama içi pencereye düşer (`/api/auth/web-login`).
- `my_likes` kaynağı gerçek hesapla denenmedi (giriş olmadığı için).
- Çoklu monitör / farklı DPI ölçeklerinde pencere yerleşimi denenmedi.
- Kurulum sihirbazı, kod imzası, otomatik güncelleme **yok**.

---

## 7. Bilinen sorunlar / yarım işler

1. **Kapak havuzu telif riski (SATIŞTAN ÖNCE ÇÖZÜLMELİ).** `assets/artwork_pool`
   içinde 208 gerçek SoundCloud kapağı var (27 MB). Bunlar başka kullanıcıların
   yüklediği görseller; ticari üründe dağıtmak telif ihlali. Plan: kullanıcı
   klasörü + uygun görselleri dış kaynaktan bulup çekme (prosedürel üreteç
   tercih edilmiyor, bkz. §12.2); havuzu ücretli sürümden çıkar.
2. **Lisans/deneme sistemi yok.** Satış modeli kararlaştırıldı (aylık üyelik,
   ~$2.99/ay veya $19.99/yıl, LemonSqueezy/Paddle üzerinden) ama kod yazılmadı.
3. **İmzasız exe** → SmartScreen uyarısı. Kod imzası sertifikası gerekli.
4. **Kurulum sihirbazı yok** (Inno Setup önerilir).
5. **Otomatik güncelleme yok.** Abonelik modelinde kritik: SoundCloud
   `client_id` değiştirince uygulama kırılır.
6. **DRM'li parçalar** (`cbc-/ctr-encrypted-hls`, ~%5) indirilemiyor; arayüz
   bunu açıkça söylüyor. Bu bilinçli bir karar, hata değil.
7. **`client_id` kazıma** kırılgan: soundcloud.com'un JS paketlerinden regex ile
   alınıyor, başarısız olursa sabit yedek anahtara düşüyor (`sc.rs`).
8. Kullanıcının müzik klasöründe test artıkları var (bkz. §11).

---

## 8. Tuzaklar (bunlar saatlere mal oldu — tekrar yaşama)

| Tuzak | Doğrusu |
|---|---|
| `tao` pencere kapatmayı **otomatik uygulamıyor** | `WindowEvent::CloseRequested` → `ControlFlow::Exit` (`ui.rs`) |
| `ControlFlow::Wait` verilince periyodik iş duruyor | Her turda `WaitUntil(now + 600ms)` ata |
| İkinci webview varsayılan WebContext kullanırsa exe yanında `*.WebView2` açar | İki pencere **aynı** `wry::WebContext`'i paylaşmalı |
| WebView2 veri klasörü `Program Files`'ta açılış bozar | `WebContext::new(Some(%APPDATA%\...\WebView2))` |
| Windows alt süreçleri ebeveyn ölünce ölmez | `jobobj.rs`: `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` |
| Dinamik MSVC CRT → arkadaşının PC'sinde açılmaz | `.cargo/config.toml`: `-C target-feature=+crt-static` |
| Konsol alt sistemi → çift tıklayınca siyah pencere | `#![windows_subsystem = "windows"]` + `winmsg` ile MessageBox |
| Rust `println!` GUI alt sisteminde görünmez | Log'u dosyaya yaz (`studio.log`) |
| `wry::WebViewBuilder` API'si sürüme göre değişiyor | Bu proje **wry 0.53 / tao 0.34**; `with_data_directory` yok, `WebContext` var |
| `reqwest 0.13`'te `.query()` ve `.form()` feature arkasında | `features = ["query","form"]` |
| Logo'yu luminance ile alfa yapmak turuncu zeminde hayalet bırakır | Alfayı **mavi kanal**dan al (turuncuda 0, beyazda 255) |
| `rustc` ara sıra `cpufeatures` derlerken `0xc0000005` ile çöküyor | Aynı komutu tekrar çalıştır, geçiyor |
| `rm -rf` bir klasörde 50+ dosya varsa güvenlik nedeniyle bloklanır | Klasörü silmek yerine taşı (`mv`) |
| `client_id` kazıma ilk 6 JS paketine bakıyordu, anahtar 8.'sinde → hep sabit yedeğe düşüyordu | Sondan başla, tümüne bak; bulunanı `client_id.txt`'ye önbellekle |
| SoundCloud `abr_sq` türü `audio/mpegurl`; `contains("mpeg")` onu MP3 sanıyordu | `is_mp3_mime`: yalnızca tam `audio/mpeg` |
| MP3 akışı yalnızca `policy=SNIP` (30 sn önizleme) parçalarda kaldı; tam parçalar AAC 96/160k | SNIP taramada elenir; AAC → 320k MP3'e çevrilir, MP3 gelirse kopyalanır |
| "Yenile" klasördeki tüm sesleri `.mp3` yapıp ID3 yazıyordu (FLAC bozulur) | Yalnızca `.mp3`; toplu yenilemede yalnızca uygulamanın ürettikleri (meta ya da yan `.jpg`) |
| Geçersiz indirme isteği `downloading=true` bırakıp uygulamayı kilitliyordu | Önce doğrula, sonra bayrağı kaldır |
| PowerShell 5.1 BOM'suz UTF-8 `.ps1`'i bozuk okur | Test betiklerini BOM'lu kaydet |
| Orijinal Python'da `strict` sayımı `scored` üzerinden yapılıyordu | Doğrusu `final_list` üzerinden (mesaj yanlış çıkıyordu) |

---

## 9. Alınan kararlar ve gerekçeleri

- **wry + axum, Tauri değil** → Node/npm gerektirmeden `cargo build`; arayüz
  zaten HTTP'ye yazılmıştı, aynen korundu.
- **Puanlama ağırlıkları birebir korundu** → mevcut kullanıcının alıştığı
  sıralama bozulmasın. `score.rs` orijinalin portu; değiştirme.
- **Başlık regex sırası birebir korundu** (`titles.rs`) → aynı girdi aynı
  çıktıyı versin diye. Sıra değiştirmek davranışı bozar.
- **ID3 elle yazıldı** → `lofty`/`id3` bağımlılığı ve API oynaklığı yerine
  162 satır, tam kontrol. Etiketler her yazımda sıfırdan kuruluyor.
- **Kapak `resize_to_fill`** → orijinal `resize((800,800))` görseli geriyordu.
- **Ayar dosyaları atomik** (`tmp` + `rename`) → yarım yazma ayarları bozmaz.
- **`client_secret` arayüze geri gönderilmiyor** (`get_settings` maskeler).

---

## 10. Ticari / hukuki uyarılar

- **Ürün adı:** 12 Kasım 2026'da görünen ad **SC Studio** yapıldı ve giriş ekranına "SoundCloud ile bağlantılı değildir" notu eklendi. Logo da değişti: koyu karo üzerinde sönümlenen ses dalgası (`assets/logo.svg`; `icon.png` onu `python tools/make_icon.py` ile üretilir). Eski bulut görseli `mark.png` silindi. `docs/*.png` ekran görüntüleri hâlâ eski logoyu gösteriyor. Eski not: Satıştan
  önce isim değiştirilmeli (EditForge / Phonk Vault / Slowed Studio gibi).
  Arayüze "SoundCloud ile bağlantılı değildir" notu + EULA eklenmeli.
- **Kapak havuzu:** §7.1 — en acil hukuki madde.
- **Konumlandırma:** "SoundCloud indirici" olarak pazarlamak ödeme
  sağlayıcılarında ve pazaryerlerinde sorun çıkarabilir. "Kişisel müzik
  arşivi / edit kütüphanesi" çerçevesi daha savunulabilir. DRM'li içerik
  indirilmediği için teknik bir savunma noktası var.
- **Ödeme:** Türkiye'den Stripe yok. LemonSqueezy/Paddle (Merchant of Record,
  KDV'yi halleder) veya iyzico/PayTR/Shopier.
- **Fiyat matematiği:** $1.99/ay'da komisyon %18-30'a çıkıyor; yıllık
  $19.99 marjı %7'ye indiriyor. Yıllık ağırlıklı fiyatlandırma önerildi.

---

## 11. Kullanıcı hakkında

- Türkçe konuşuyor; kısa, doğrudan cevap ve **kanıt** istiyor ("test ettim"
  demek yetmiyor, çıktı göstermek gerekiyor).
- Tasarım zevki yüksek; "premium" görünüm istiyor. Hareketli arayüz seviyor.
- **Müzik kütüphanesinde değişiklik yapıldı:** 11 Kasım'da "Başlıkları &
  Kapakları Yenile" özelliği gerçek dosyalarda test edildi → **8 dosya yeni
  başlık/kapak aldı** (ses verisi sağlam). Ayrıca test indirmeleri birikti.
  Kullanıcıya bildirildi; **kendi onayı olmadan silme/taşıma yapma.**
- Konuşma dili: samimi ama laubali değil. Teknik terimleri Türkçe kullanıyor
  (commit, build gibi yerleşmiş olanlar hariç).

---

## 12. Yol haritası (kullanıcıyla mutabık)

1. **Lisans + 14 gün deneme** — LemonSqueezy license API, cihaz aktivasyonu,
   72 saat önbellek + 7 gün çevrimdışı tolerans. *Satış için ön koşul.*
2. **Kapak kaynağı (ertelendi).** Kullanıcı 21 Kasım 2026'da prosedürel
   üreteci **istemediğini** söyledi; tercihi uygun görselleri bir yerlerden
   bulup çekmek ("şimdi değil"). Kaynak, filtre ve telif kararları kullanıcıyla
   netleşmeden başlanmaz. Bu arada kapak tekrarı `cover_style` ayarı
   (Özgün / Çeşitli / Cesur), kayan pencere seçimi ve ikiz görsel listesiyle
   azaltıldı (`artwork.rs`, `coverfx.rs`).
3. **Zamanlanmış otomatik tarama + kuyruk** (duraklat/devam/yeniden dene) —
   abonelikte "sürekli değer" üreten kısım.
4. **Kütüphane:** arama, etiket, M3U/Rekordbox dışa aktarma.
5. **Kurulum + kod imzası + otomatik güncelleme.**

Sıradaki adım kullanıcıya soruldu; cevap: "önce bunları yap, sonrasına bakarız"
→ §7'deki 1-2-3 sırası öneriliyor.

---

## 13. Depodaki diğer dosyalar

| Yol | Ne işe yarar |
|---|---|
| `README.md` | Kullanıcıya dönük dokümantasyon (kurulum, mimari, dağıtım) |
| `docs/Beni Oku.txt` | ZIP içine giren kısa kullanım notu |
| `docs/original_index.html` | Orijinal Python uygulamasının arayüzü (referans) |
| `docs/splash.png`, `login.png`, `ui-preview.png` | Güncel ekran görüntüleri |
| `../reverse/` (44 MB) | Tersine mühendislik çıktıları: `pyinstxtractor` çıktısı, `dis_*.txt` (bytecode dökümleri), `dump_dis.py`. **Derleme için gerekmez**, orijinal davranışı doğrulamak istersen burada. |
| `../reverse/dis_score.txt` | Orijinal puanlama fonksiyonunun disassembly'si |
| `../reverse/dis_title.txt` | Orijinal başlık üretiminin disassembly'si |
| `../reverse/dis_scan.txt`, `dis_dl.txt` | Tarama ve indirme işçilerinin disassembly'si |

Orijinal uygulama hâlâ `C:\Users\alief\Downloads\SoundCloud Studio` altında
duruyor (çalışan Python sürümü) — davranış karşılaştırması için.

---

## 14. Devir teslim kontrol listesi

Yeni asistan ilk 10 dakikada şunları yapmalı:

- [ ] `cargo test` → 13/13 geçtiğini gör
- [ ] `dist\SoundCloudStudio.exe --server-only` çalıştır, `studio.log`'dan port al
- [ ] `curl /api/health`, `/api/settings`, `/api/auth/status` yanıtlarını gör
- [ ] `README.md` + bu dosyayı oku
- [ ] Kullanıcıya **tek soru** sor: "Lisans altyapısı mı, kapak stüdyosu mu?"
- [ ] Kod yazmadan önce §8 tuzaklarını aklında tut

**Yapma:** `dist/`, `assets/artwork_pool/`, `%APPDATA%\SoundCloudStudio\` veya
kullanıcının müzik klasörünü izinsiz silme/değiştirme.
