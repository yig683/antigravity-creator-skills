# Antigravity Creator Skills & Shorts Automation Suite

Blender EEVEE tabanlı 3D *"Nasıl İcat Edersin?"* Shorts üretim stüdyosu (`makine-studio`), dikey video tutma/kalite denetçisi (`viral-shorts-architect`), sıfır görsel turlu Chrome CDP YouTube Studio yükleyicisi (`youtube-studio-uploader`), hızlandırılmış Windows masaüstü kontrol MCP eklentisi (`computer-use`), Twitch/Kick `9:16` klip derleyicisi (`clip_finder`) ve SoundCloud viral edit küratör / 320 kbps MP3 masaüstü uygulaması (`sc_studio`).

Tüm sistem tek repoda toplanmıştır; ancak aşağıdaki tablodan **istediğiniz skilli veya eklentiyi tek tek (standalone `.zip` veya tek klasör olarak)** indirebilirsiniz.

---

## Ayrı Ayrı İndir & Kur (Standalone Packages)

| Skill / Eklenti | Açıklama | Tek Tıkla `.zip` İndir | Klasörü Gör | Kurulum |
| :--- | :--- | :---: | :---: | :--- |
| **Makine Studio (`makine-studio`)** | 3D Blender EEVEE + Edge-TTS/Chatterbox + Whisper hizalamalı 2D blueprint HUD Shorts stüdyosu | [makine-studio-plugin.zip](https://github.com/yig683/antigravity-creator-skills/raw/main/packages/makine-studio-plugin.zip) | [`plugins/makine-studio/`](plugins/makine-studio/README.md) | Zipten çıkar → `install.bat` |
| **Fast Computer Use (`computer-use`)** | `batch(fast=true, ui_after=true)`, `paste_text`, `file_dialog` ve COM UIA `ScrollItemPattern` auto-scroll destekli hızlı Windows MCP | [computer-use-plugin.zip](https://github.com/yig683/antigravity-creator-skills/raw/main/packages/computer-use-plugin.zip) | [`plugins/computer-use/`](plugins/computer-use/README.md) | Zipten çıkar → `install.bat` |
| **YouTube Studio Uploader (`youtube-studio-uploader`)** | Chrome CDP Code Mode (`DOM.setFileInputFiles`, ~15–30 sn/video) + `chrome-devtools` MCP + Turbo `batch` yükleyici | [youtube-studio-uploader-skill.zip](https://github.com/yig683/antigravity-creator-skills/raw/main/packages/youtube-studio-uploader-skill.zip) | [`.agents/skills/youtube-studio-uploader/`](.agents/skills/youtube-studio-uploader/SKILL.md) | Projedeki `.agents/skills/` altına aç |
| **Viral Shorts Architect (`viral-shorts-architect`)** | İlk 2 sn şok/tehlike kancası, `1080×1920` güvenli bölge, `-14 LUFS` ses ve görsel QA (`qa_check.py`) | [viral-shorts-architect-skill.zip](https://github.com/yig683/antigravity-creator-skills/raw/main/packages/viral-shorts-architect-skill.zip) | [`.agents/skills/viral-shorts-architect/`](.agents/skills/viral-shorts-architect/SKILL.md) | Projedeki `.agents/skills/` altına aç |
| **SC Studio 2.0 (`sc_studio`)** | SoundCloud viral edit küratörü + 320 kbps MP3 indirici + akıllı başlık & 800×800 kapak gömen Rust + WebView2 masaüstü uygulaması | [sc-studio-win64.zip](https://github.com/yig683/antigravity-creator-skills/raw/main/packages/sc-studio-win64.zip) | [`sc_studio/`](sc_studio/README.md) | Zipten çıkar → `SoundCloudStudio.exe` (`ffmpeg.exe` gerekli) |

### Sadece Tek Bir Klasörü Git ile İndirmek (Sparse Checkout)

```powershell
git clone --filter=blob:none --sparse https://github.com/yig683/antigravity-creator-skills.git
cd antigravity-creator-skills
# Örnek: yalnızca youtube-studio-uploader, makine-studio veya sc_studio çekmek için:
git sparse-checkout set .agents/skills/youtube-studio-uploader
# veya:
git sparse-checkout set plugins/makine-studio
# veya:
git sparse-checkout set sc_studio
```

---

## Tarayıcı Hızlandırma Notu (`chrome-devtools-mcp --autoConnect`)

`youtube-studio-uploader` ve tarayıcı otomasyonlarında piksel tıklaması yerine mevcut Chrome oturumunuzu (`127.0.0.1:9222`) kullanmak için:

1. Chrome'da `chrome://inspect/#remote-debugging` açıp uzaktan hata ayıklamaya izin verin.
2. `~/.gemini/config/mcp_config.json` içine telemetrisiz `chrome-devtools-mcp` yapılandırmasını ekleyin:
   ```json
   {
     "mcpServers": {
       "chrome-devtools": {
         "command": "npx.cmd",
         "args": [
           "-y",
           "chrome-devtools-mcp@latest",
           "--autoConnect",
           "--no-usage-statistics",
           "--no-performance-crux"
         ],
         "env": {
           "CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS": "1",
           "CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS": "1"
         }
       }
     }
   }
   ```

---

## Çalışma Alanı Araçları (`clip_finder`, `makine_studio` & `sc_studio`)

### 1) Makine Studio (3D Blueprint Shorts)
```powershell
cd .\makine_studio
python -m studio.pipeline --episode asansor_icat --profile shorts --mode preview
python -m studio.pipeline --episode asansor_icat --profile shorts --mode full --skip-tts
```

### 2) GTA 6 Clip Farmer (Twitch & Kick → 9:16 + 62+ sn Derleme)
- **Web Paneli:** `python main.py --web` (`http://127.0.0.1:5000`)
- **62+ sn Derleme CLI:**
  ```powershell
  python main.py --compile --game "Grand Theft Auto VI" --period all --min-views 10000 --narration tr
  ```
- **Tekli Klipler:**
  ```powershell
  python main.py --farm --game "Grand Theft Auto VI" --farm-count 3 --min-views 5000
  ```
- **Yükleme Kuyruğu & Hızlı CDP Yükleme:**
  ```powershell
  python main.py --prepare-uploads
  node .agents/skills/youtube-studio-uploader/scripts/cdp_studio_upload.mjs --queue output/ready/upload_queue.json
  ```

### 3) SC Studio 2.0 (`sc_studio/`)
SoundCloud'daki viral edit parçalarını (hardtekk / slowed+reverb / phonk / montagem) puanlayan, 320 kbps MP3 olarak indirip akıllı başlık + ID3 ve 800×800 kapak gömen Rust + WebView2 masaüstü uygulaması ([`sc_studio/README.md`](sc_studio/README.md)).
```powershell
cd .\sc_studio
cargo test
cargo build --release
```
