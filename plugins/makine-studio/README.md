# Makine Studio — Antigravity Skill & Plugin Paketi (v2.0)

3D blueprint mühendislik ve *"Nasıl İcat Edersin?"* konseptinde dikey YouTube Shorts / Reels / TikTok veya 16:9 yatay açıklayıcı videolar üreten uçtan uca Antigravity eklentisi.

## Paket İçeriği

- `plugin.json`, `rules/AGENTS.md`, `skills/makine-studio/SKILL.md`: Antigravity ajanının sıfırdan 3D bölüm yazma, önizleme alma, görsel/işitsel hata ayıklama ve tam video render alma talimatları.
- `engine/studio/`: Blender 5.2 / 4.2+ EEVEE 3D API'si (`30/60 fps` desteği), NumPy/Pillow 2D Blueprint HUD Compositor, ses mikseri (FFmpeg 2-pass `-14 LUFS` broadcast loudness + soft `alimiter` ve 0 ms'e kırpılmış gerçek CC0/PD foley WAV bankası), çoklu TTS motoru (`Chatterbox GPU` / `Edge-TTS` / `External`) + `faster-whisper` hizalama.
- `engine/episodes/`: Hazır 10 katlı pilot bölüm (`asansor_icat.py` — `shorts` şok kancalı ~52 sn veya `tiktok` çift güvenlik+kuyu tamponlu ~62 sn) ve yeni bölümler için şablon (`template_episode.py`).
- `engine/assets/`: Paket içi `Montserrat-Black.ttf` yazı tipi ve 0 ms kırpılmış gerçek foley + HUD SFX sesleri (`step`, `clank`, `ding`, `cable_snap`, `alert`, `motor`, `bass_boom`, `pop`, `riser`, `whoosh`).

## Gereksinimler

1. **Blender 4.2+ veya 5.x** (`C:\Program Files\Blender Foundation\Blender ...\` veya `PATH` üzerinde `blender`; farklı konumdaysa `MAKINE_BLENDER_EXE` ortam değişkeni ayarlanabilir)
2. **FFmpeg / FFprobe** (`winget install Gyan.FFmpeg`)
3. **Python 3.10+**
4. *(İsteğe bağlı — doğal insan sesine yakın yerel GPU Türkçe TTS için)* **NVIDIA CUDA GPU** (`install.ps1 -WithGpuTts`)

## 1 Dakikada Kurulum (Windows)

Zip arşivini çıkartıp klasör içinde **`install.bat`** dosyasına çift tıklayabilir veya PowerShell ile çalıştırabilirsiniz:

```powershell
# Standart kurulum (Edge-TTS Türkçe ile anında kullanıma hazır + Global Antigravity Plugin):
powershell -ExecutionPolicy Bypass -File .\install.ps1

# VEYA NVIDIA GPU varsa yerel Chatterbox Multilingual Türkçe TTS ile kurulum (~2.5 GB model):
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WithGpuTts
```

> Sadece tek bir proje klasörüne kurmak isterseniz: `powershell -ExecutionPolicy Bypass -File .\install.ps1 -WorkspacePath "C:\Projem"`

Alternatif olarak hiç script çalıştırmadan klasörün tamamını projenizin `.agents/plugins/makine-studio/` veya `%USERPROFILE%\.gemini\config\plugins\makine-studio\` altına kopyalayabilirsiniz.

## Antigravity İçinde Kullanım

Eklenti aktifken kendi çalışma klasörünüzde ajana doğrudan şu komutlardan birini yazmanız yeterli:

- *"Denizaltı nasıl dalıp çıkar 3D blueprint Shorts videosu üret."*
- *"Paraşütün nasıl çalıştığını 'Nasıl İcat Edersin?' formatında 3D video yap."*
- *"Asansör pilot bölümünün önizlemesini oluştur."*

Ajan yeni bölümü kendi çalışma klasörünüzdeki `episodes/` içine yazar, önce `--mode preview` ile tüm sahneleri ve sesi doğrular, ardından final 1080×1920 MP4 + kapak + `.srt` + `metadata.json` çıktısını `output/` klasörüne üretir.

## Doğrudan Komut Satırından Test (Örnek Pilot Bölüm)

```powershell
$env:PYTHONPATH = "$env:USERPROFILE\.gemini\config\plugins\makine-studio\engine"
python -m studio.pipeline --episode asansor_icat --output-dir .\output --profile shorts --mode preview
python -m studio.pipeline --episode asansor_icat --output-dir .\output --profile shorts --mode full --skip-tts
```

## Doğrudan YouTube Yükleme Bağlantısı (Opsiyonel)

Render bitince videoyu, Türkçe `.srt` altyazıyı ve başlık/açıklama/etiketleri doğrudan YouTube'a yüklemek için:

1. Google Cloud Console'da **YouTube Data API v3**'ü etkinleştirin ve **OAuth client ID → Desktop app** oluşturup JSON dosyasını indirin.
2. İndirdiğiniz dosyayı güvenli kullanıcı klasörüne (proje veya eklenti klasörünün *dışına*) şu isimle kaydedin:
   `%USERPROFILE%\.gemini\config\makine_studio\youtube_client_secret.json`
3. Tek seferlik Google hesabı yetkilendirmesi yapın:
   ```powershell
   $env:PYTHONPATH = "$env:USERPROFILE\.gemini\config\plugins\makine-studio\engine"
   python -m studio.youtube_uploader --auth-only
   ```
4. Hazır bir çıktıyı doğrudan yükleyin (varsayılan `--privacy private` güvenli taslaktır):
   ```powershell
   python -m studio.pipeline --episode asansor_icat --output-dir .\output --profile shorts --upload-only --privacy private
   ```
   > Veya tam render + yüklemeyi tek komutta birleştirmek için `--mode full --skip-tts --upload` kullanabilirsiniz. İsteğe bağlı `--publish-at`, `--upload-thumbnail` ve `--post-comment` bayrakları da desteklenir.
