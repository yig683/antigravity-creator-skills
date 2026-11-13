# Makine Studio

Otomatik 3D blueprint mühendislik ve *"Nasıl İcat Edersin?"* video üretim hattı (Blender 5.2 EEVEE + Edge-TTS Türkçe + NumPy/Pillow 2D HUD Compositor + FFmpeg).

## Yapı

```text
makine_studio/
├── CONTENT_PLAN.md              # Tek kanallı hızlı gelir stratejisi & 16 viral bölüm fikri
├── README.md
├── studio/
│   ├── config.py                # Çözünürlük profilleri (shorts / landscape), renk paleti, fontlar
│   ├── tts_engine.py            # WordBoundary destekli Türkçe Edge-TTS & .srt zaman çizelgesi
│   ├── sfx_synth.py             # Prosedürel ses efektleri (clank, ding, alert) + ambient miks
│   ├── blender_scene_api.py     # Blender 5.2 materyal, MannequinRig, CameraRig, HUDTracker
│   ├── compositor.py            # Blueprint arka plan, tüy geçişi, HUD okları/etiketleri, başlık & altyazı
│   └── pipeline.py              # Uçtan uca CLI üretim boru hattı
└── episodes/
    ├── asansor_icat.py          # Pilot bölüm: "Asansörü Nasıl İcat Edersin?"
    └── template_episode.py      # Yeni bölümler için kopyalanabilir şablon
```

## Hızlı Kullanım

1. **Hızlı önizleme (her sahneden 1 kare + kapak görseli, ~10 saniye):**

```powershell
cd .\makine_studio
python -m studio.pipeline --episode asansor_icat --profile shorts --mode preview
```

2. **Tam render (1080x1920 MP4, kapak görseli, SRT, YouTube metadata):**

```powershell
cd .\makine_studio
python -m studio.pipeline --episode asansor_icat --profile shorts --mode full
```

3. **Sadece 2D kaplama / altyazı / başlık güncellemesi (3D render'ı tekrar çalıştırmadan):**

```powershell
python -m studio.pipeline --episode asansor_icat --profile shorts --mode full --recomposite-only
```

4. **Yatay uzun video profili (1920x1080 Companion Long-Form):**

```powershell
python -m studio.pipeline --episode asansor_icat --profile landscape --mode preview
```
