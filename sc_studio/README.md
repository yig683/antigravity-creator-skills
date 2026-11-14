# SC Studio 2.0 (Rust)

> Eski adı "SoundCloud Studio". Görünen ad değişti; veri klasörü (`%APPDATA%\SoundCloudStudio`) mevcut kullanıcıların verisi kaybolmasın diye aynı kaldı.

SoundCloud'daki viral edit parçalarını (hardtekk / slowed + reverb / phonk /
montagem) bulup puanlayan, seçtiklerinizi **320 kbps MP3** olarak indiren,
başlıklarını TikTok/Reels estetiğine göre yeniden yazan ve her parçaya
**tekrarsız, 800×800 gerçek kapak** atayan masaüstü uygulaması.

Bu depo, PyInstaller ile paketlenmiş Python sürümünün (v1.1) **Rust'a portudur**.
Arayüz aynı görsel dili korur; arka uç sıfırdan, tek bir statik binary olacak
şekilde yazıldı.

---

## Neden port edildi

Orijinal sürüm çalışıyordu ama bakımı zordu:

| Sorun | Rust sürümünde |
|---|---|
| Tek bir sabit `client_id` — SoundCloud değiştirince uygulama tamamen ölüyordu | Anahtar soundcloud.com'un JS paketlerinden otomatik çıkarılıyor, 401/403'te kendini yeniliyor |
| `config.json` exe'nin yanına yazılıyordu (Program Files'ta çalışmaz) | Tüm durum `%APPDATA%\SoundCloudStudio` altında |
| Arayüzdeki filtreler her açılışta sıfırlanıyordu | Tüm seçimler kalıcı |
| İndirme motoru `yt-dlp` (Python) — SoundCloud şifreli HLS'e geçince kırıldı | Saf Rust akış çözümleme + ffmpeg; progressive ve normal HLS destekli |
| 208 görsel + Python + ffmpeg = 250 MB klasör | Tek exe (~35 MB) + ffmpeg |
| Ses oynatıcıda ileri sarma yok (Flask `send_file` kopyası yoktu) | `Range` destekli dosya sunumu |
| Hatalar sessizce yutuluyordu | Durum çubuğu + toast bildirimleri, hata mesajları görünür |
| Kapaklar `resize((800,800))` ile **geriliyordu** | `resize_to_fill` ile kırpılıyor (oran bozulmuyor) |
| Dosya adı çakışmalarında kapak adı kayıyordu | Kapak her zaman gerçek dosya adına bağlı |
| Sunucuya path traversal koruması yoktu | Tüm dosya yolları kök klasöre sabitlendi |

---

## İlk açılış

1. **Tanıtım animasyonu** — koyu karo yerine oturur, ses dalgası soldan sağa
   tek çizgiyle çizilir, altta "SC Studio" belirir (≈1.5 s, tıklayınca atlanır).
2. **Giriş ekranı** — "SoundCloud ile giriş yap" veya "Misafir olarak devam et".
   Bu ekran yalnızca ilk açılışta görünür; seçim `config.json`'a yazılır.

### SoundCloud ile giriş (opsiyonel)

Giriş yapmak zorunlu değil; yapıldığında **"Beğenilerim"** kaynağı açılır ve
hesap üst çubukta görünür.

Kurulum (tek seferlik, geliştirici tarafı):

1. https://soundcloud.com/you/apps → "Register a new application"
2. **Redirect URI** alanına birebir şunu yazın:
   `http://127.0.0.1:47821/oauth/callback`
3. Aldığınız `client_id` / `client_secret` değerlerini uygulamada
   *Giriş ekranı → Gelişmiş* bölümüne (veya `config.json`'a) girin.

Akış: OAuth 2.1 + PKCE (S256). Uygulama sistem tarayıcısını açar, yerel
`127.0.0.1:47821` dinleyicisi kodu yakalar, token `%APPDATA%\SoundCloudStudio\auth.json`
içine yazılır. Erişim token'ı ~1 saat geçerlidir ve sessizce yenilenir
(refresh token tek kullanımlık). Tarayıcı geri dönmezse yönlendirme adresi
elle yapıştırılabilir.

## Özellikler

- **AI Küratör taraması** — 4 hazır havuz (hardtekk, phonk, slowed+reverb,
  karışık) + 11 referans kanal + özel link/terim. Taramalar paralel çalışır.
- **Çok boyutlu puanlama** — viral anahtar kelimeler, süre, dinlenme, beğeni,
  beğeni oranı, repost ve "referans kanal" bonusu. Ağırlıklar orijinalle birebir.
- **Tekrarsız keşif** — görülen parçalar hatırlanır; havuz tükenirse en iyi
  sonuçlarla doldurulur ve durum çubuğu bunu açıkça söyler.
- **Akıllı başlık** — `y2mate.com - X (320kbps) [slowed]` → `X (Slowed + Reverb)`.
  6 stil + 13 varyasyonluk rastgele havuz.
- **Gerçek kapaklar** — 208 görsellik gömülü havuzdan tekrarsız seçim,
  800×800 JPEG (q92), hem ID3 `APIC` olarak gömülür hem `.jpg` olarak yanına yazılır.
- **Kütüphane yönetimi** — çal, yeniden adlandır/yeniden kapakla, sil,
  kapakları dışa aktar, klasör değiştir.
- **Uygulama içi tarayıcı** — "Keşfet" ayrı bir pencerede soundcloud.com açar;
  "Sayfayı aktar" o an açık olan parça/albüm sayfasını doğrudan taramaya verir.
- **Beğenilerim** — giriş yapıldıysa kendi beğendiğin parçalar kaynak olur.
- **320 kbps MP3** — ffmpeg + libmp3lame; kaynak HLS ne olursa olsun sabit bit hızı.

---

## Mimari

```
┌──────────────────────────────────────────────┐
│  WebView2 penceresi (tao + wry)              │
│  assets/index.html  — tek dosya, saf JS/CSS  │
└───────────────┬──────────────────────────────┘
                │ fetch() → 127.0.0.1:<rastgele port>
┌───────────────▼──────────────────────────────┐
│  axum HTTP sunucusu (arka plan thread'i)     │
│  ├── api.rs      rotalar, Range'li dosya sunumu
│  ├── scan.rs     küratör taraması + sıralama
│  ├── score.rs    puanlama motoru
│  ├── sc.rs       SoundCloud API + client_id yenileme
│  ├── download.rs ffmpeg hattı, ilerleme takibi
│  ├── titles.rs   akıllı başlık üretimi
│  ├── artwork.rs  kapak havuzu + 800×800 JPEG
│  ├── id3.rs      ID3v2.3 yazıcı (TIT2/TPE1/TALB/TCON/APIC)
│  └── state.rs    paylaşılan durum (tokio RwLock)
└──────────────────────────────────────────────┘
```

Sunucu `127.0.0.1:0`'a bağlanır (rastgele boş port), yani başka bir uygulamayla
çakışmaz ve dışarıdan erişilemez.

### Dosya konumları

| Ne | Nerede |
|---|---|
| Ayarlar | `%APPDATA%\SoundCloudStudio\config.json` |
| Görülen parçalar | `%APPDATA%\SoundCloudStudio\seen_tracks.json` |
| Şarkı meta verisi | `%APPDATA%\SoundCloudStudio\track_metadata.json` |
| Kapak önbelleği | `%APPDATA%\SoundCloudStudio\covers\` |
| Kullanıcı kapakları | `%APPDATA%\SoundCloudStudio\artwork_pool\` (buraya kendi görsellerinizi atabilirsiniz) |
| İndirilen şarkılar | `%USERPROFILE%\Music\SoundCloud_Dinleme_Arsivi` (değiştirilebilir) |

---

## Derleme

Gereksinimler: **Rust 1.80+** ve Windows'ta WebView2 (Windows 10/11'de kurulu gelir).

```bash
cargo build --release
```

Çıktı: `target/release/soundcloud-studio.exe`

Çalıştırmak için exe'nin yanında `ffmpeg.exe` bulunmalıdır (PATH'te de olur):

```
SoundCloudStudio/
├── SoundCloudStudio.exe
├── ffmpeg.exe
└── Beni Oku.txt
```

### Başka bir bilgisayara göndermek

Uygulama **kurulum gerektirmez** ama tek başına exe de yetmez. Gerekenler:

| Gereksinim | Durum |
|---|---|
| Visual C++ Redistributable | **Gerekmez** — C runtime exe'ye statik gömülü (`+crt-static`) |
| .NET / Python / Java | Gerekmez |
| Microsoft Edge WebView2 | Windows 10 ve 11'de kurulu gelir; yoksa uygulama açılışta uyarı verip indirme bağlantısını gösterir |
| `ffmpeg.exe` | **Zorunlu** (ses dönüştürme için), exe'nin yanında olmalı |
| İnternet | Tarama ve indirme için gerekli |

Yani doğru yöntem: **`dist/` klasörünü ZIP'leyip göndermek.**
Hazır paket: `SoundCloudStudio-2.0-win64.zip` (~113 MB; içinde exe + ffmpeg + kısa kullanım notu).

ZIP'i alan kişi:
1. Klasöre çıkarır (sağ tık → Tümünü ayıkla).
2. `SoundCloudStudio.exe`'ye çift tıklar.
3. Windows "Bilinmeyen yayıncı" / SmartScreen uyarısı gösterirse
   **Daha fazla bilgi → Yine de çalıştır** der (imzasız, kendi derlemeniz olduğu için).

Sadece 34 MB'lık exe'yi göndermek isterseniz, karşı taraf
[ffmpeg](https://www.gyan.dev/ffmpeg/builds/) indirip exe'nin yanına koymalıdır —
uygulama eksikse bunu net bir hata mesajıyla söyler.

### Dağıtım paketi

```bash
cargo build --release
mkdir -p dist
cp target/release/soundcloud-studio.exe dist/SoundCloudStudio.exe
cp /yol/ffmpeg.exe dist/
cp docs/"Beni Oku.txt" dist/
```

### Testler

```bash
cargo test
```

Puanlama, başlık temizleme ve ID3 yazıcı için birim testleri vardır.

### Pencere olmadan çalıştırma

```bash
soundcloud-studio.exe --server-only
```

Sadece HTTP sunucusunu açar (hata ayıklama / otomasyon için).

---

## Bilinen sınırlar

- **DRM'li parçalar**: SoundCloud parçaların bir kısmını `cbc-encrypted-hls` /
  `ctr-encrypted-hls` ile sunuyor (anketlerde ~%5). Bunlar indirilemez ve
  arayüz bunu açıkça bildirir. `yt-dlp` de bu parçaları atlar.
- **ffmpeg zorunlu**: dönüştürme için harici `ffmpeg.exe` gerekir.
  Uygulama bulamazsa net bir hata verir.
- **İmzasız exe**: kod imzası yok; Windows SmartScreen ilk çalıştırmada uyarabilir.
- Yalnızca Windows 10/11 (x64) hedeflenmiştir (WebView2 + `explorer` entegrasyonu).

---

## Lisans / sorumluluk

Bu araç yalnızca kişisel arşivleme içindir. İndirdiğiniz içeriğin lisansına ve
SoundCloud Kullanım Şartları'na uymak kullanıcının sorumluluğundadır.
