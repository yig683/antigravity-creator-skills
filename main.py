from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clip_finder.compiler import CompilationPipeline
from clip_finder.editor import EditConfig, auto_edit_wspeed
from clip_finder.engine import ClipFinderEngine
from clip_finder.pipeline import ClipFarmerPipeline
from clip_finder.uploader import DEFAULT_READY_DIR, mark_upload_result, sync_upload_queue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Twitch & Kick popüler klip bulucu ve tam ekran 9:16 Shorts/Reels/TikTok edit sistemi."
    )
    parser.add_argument(
        "--game",
        "-g",
        default="Grand Theft Auto VI",
        help="Oyun / kategori adı (virgülle çoklu destekler, varsayılan: 'Grand Theft Auto VI')",
    )
    parser.add_argument(
        "--platform",
        "-p",
        default="twitch,kick",
        help="Virgülle ayrılmış platformlar: twitch,kick (varsayılan: twitch,kick)",
    )
    parser.add_argument(
        "--period",
        choices=["day", "week", "month", "all"],
        default="week",
        help="Zaman aralığı (varsayılan: week)",
    )
    parser.add_argument(
        "--sort",
        choices=["views", "virality", "recent"],
        default="views",
        help="Sıralama: views (en çok izlenen), virality (izlenme/saat), recent (varsayılan: views)",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=15,
        help="Platform başına çekilecek maksimum klip sayısı (varsayılan: 15)",
    )
    parser.add_argument(
        "--min-views",
        type=int,
        default=0,
        help="Minimum izlenme filtresi (örn: 5000)",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=None,
        help="Maksimum klip süresi (saniye) — Shorts/Reels için örn. 60",
    )
    parser.add_argument(
        "--language",
        "-l",
        default=None,
        help="Dil filtresi (Twitch için, örn: tr, en)",
    )
    parser.add_argument(
        "--keyword",
        "-k",
        default=None,
        help="Başlık/yayıncı içinde kelime filtresi (virgülle, örn: 'gta 6,gta vi')",
    )
    parser.add_argument(
        "--export",
        default=None,
        help="Arama sonuçlarını kaydet (.json veya .csv)",
    )

    # --- Farm & Auto-Edit Arguments ---
    parser.add_argument(
        "--farm",
        action="store_true",
        help="En popüler klipleri indir ve otomatik tam ekran 9:16 + jump cut + altyazı ile hazırla",
    )
    parser.add_argument(
        "--farm-count",
        type=int,
        default=3,
        help="Tek seferde otomatik düzenlenecek yeni klip sayısı (varsayılan: 3)",
    )
    parser.add_argument(
        "--edit-local",
        default=None,
        help="Yerel bir MP4 dosyasına doğrudan 9:16 edit uygula",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="--edit-local için çıktı video yolu",
    )
    parser.add_argument(
        "--hook",
        default="",
        help="İsteğe bağlı üst hook yazısı (varsayılan: kapalı)",
    )
    parser.add_argument(
        "--badge",
        action="store_true",
        help="Yayıncı @kullanıcıadı rozetini ekrana ekle (varsayılan: kapalı)",
    )
    parser.add_argument(
        "--layout",
        choices=["auto", "center_crop", "split_cam", "blur_stack"],
        default="auto",
        help="9:16 ekran düzeni: auto (webcam algılar / tam ekran), center_crop, split_cam, blur_stack",
    )
    parser.add_argument(
        "--cam-corner",
        choices=["top_left", "top_right", "bottom_left", "bottom_right"],
        default="top_left",
        help="split_cam düzeni için yayıncı kamera köşesi (varsayılan: top_left)",
    )
    parser.add_argument(
        "--whisper-model",
        choices=["tiny", "base", "small", "medium"],
        default="base",
        help="Otomatik altyazı Whisper modeli (varsayılan: base)",
    )
    parser.add_argument(
        "--music",
        default=None,
        help="Arka plan müzik dosyası (.mp3/.wav) — verilmezse assets/music içinden alınır",
    )
    parser.add_argument(
        "--no-cut-dead-air",
        action="store_true",
        help="Sessiz boşlukları jump-cut ile kesmeyi kapat",
    )
    parser.add_argument(
        "--sfx",
        action="store_true",
        help="Peak anlarına sentetik bass boom efekti ekle (varsayılan: kapalı)",
    )
    parser.add_argument(
        "--shake",
        action="store_true",
        help="Peak anlarına kamera sarsıntısı ekle (varsayılan: kapalı)",
    )
    parser.add_argument(
        "--flash",
        action="store_true",
        help="Peak anlarına beyaz flash ekle (varsayılan: kapalı)",
    )
    parser.add_argument(
        "--rgb",
        action="store_true",
        help="Peak anlarına RGB split ekle (varsayılan: kapalı)",
    )
    parser.add_argument(
        "--no-nvenc",
        action="store_true",
        help="NVIDIA NVENC yerine CPU (libx264) kullan",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Daha önce işlenmiş klipleri de tekrar indirip düzenle",
    )

    # --- Monetization Compilation Mode (62s+) ---
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Para kazanma şartlarına uygun 62+ sn geri sayım derlemesi (Top N + sesli giriş/anlatım) üret",
    )
    parser.add_argument(
        "--target-duration",
        type=float,
        default=64.0,
        help="--compile için minimum hedef süre (saniye, varsayılan: 64.0)",
    )
    parser.add_argument(
        "--narration",
        choices=["none", "tr", "en"],
        default="none",
        help="İsteğe bağlı sentetik TTS açılış sesi (varsayılan: none — gerçek mikrofon için --intro-audio kullanın)",
    )
    parser.add_argument(
        "--no-narration",
        action="store_true",
        help="Otomatik sesli giriş/anlatımı kapat",
    )
    parser.add_argument(
        "--intro-audio",
        default=None,
        help="Kendi mikrofon ses kaydın (.mp3/.wav) — YouTube YPP için en güvenli giriş anlatımı",
    )

    # --- Web UI ---
    parser.add_argument(
        "--web",
        action="store_true",
        help="Web arayüzünü başlat (http://127.0.0.1:5000)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Web arayüzü portu (varsayılan: 5000)",
    )

    # --- YouTube Studio Upload Automation ---
    parser.add_argument(
        "--prepare-uploads",
        action="store_true",
        help="output/ready içindeki tüm videolar için SEO başlık/açıklama/etiket ve upload_queue.json hazırla",
    )
    parser.add_argument(
        "--upload-queue",
        action="store_true",
        help="Hazır YouTube yükleme kuyruğunu (upload_queue.json) listele",
    )
    parser.add_argument(
        "--mark-uploaded",
        default=None,
        help="Belirtilen dosya gövdesini (stem) yüklendi/planlandı olarak işaretle",
    )
    parser.add_argument(
        "--upload-status",
        default="published",
        choices=["pending", "published", "scheduled", "draft"],
        help="--mark-uploaded için durum (varsayılan: published)",
    )
    parser.add_argument(
        "--upload-url",
        default="",
        help="--mark-uploaded için YouTube video URL'si",
    )
    return parser


def _build_edit_config(args: argparse.Namespace) -> EditConfig:
    return EditConfig(
        layout=args.layout,
        cam_corner=args.cam_corner,
        cut_dead_air=not args.no_cut_dead_air,
        camera_shake=args.shake,
        impact_flash=args.flash,
        rgb_split=args.rgb,
        add_sfx=args.sfx,
        music_path=Path(args.music) if args.music else None,
        use_nvenc=not args.no_nvenc,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args()

    if args.web:
        from clip_finder.web import run_web

        print(f"Web arayüzü başlatılıyor: http://127.0.0.1:{args.port}")
        run_web(port=args.port)
        return 0

    if args.mark_uploaded:
        data = mark_upload_result(
            stem=args.mark_uploaded,
            status=args.upload_status,
            ready_dir=DEFAULT_READY_DIR,
            video_url=args.upload_url,
            visibility="public" if args.upload_status == "published" else args.upload_status,
        )
        print(f"✅ Kuyruk güncellendi: {args.mark_uploaded} -> {args.upload_status} (Kalan: {data['pending_count']})")
        return 0

    if args.prepare_uploads or args.upload_queue:
        queue = sync_upload_queue(ready_dir=DEFAULT_READY_DIR, category=args.game)
        print(f"\n=== YouTube Studio Yükleme Kuyruğu ({queue['channel_name']} / {queue['channel_handle']}) ===")
        print(f"Toplam: {queue['total_ready']} video | Bekleyen: {queue['pending_count']}\n")
        for idx, item in enumerate(queue["items"], start=1):
            print(f"{idx}. [{item['status'].upper()}] {item['stem']} ({item.get('duration_seconds')}s)")
            print(f"   Başlık    : {item['title']}")
            print(f"   Hedef     : {item['recommended_visibility']} {item.get('publish_at_local') or ''}".strip())
            print(f"   Video Yolu: {item['video_path']}\n")
        return 0

    if args.edit_local:
        src = Path(args.edit_local)
        if not src.exists():
            print(f"Dosya bulunamadı: {src}", file=sys.stderr)
            return 1
        out = Path(args.out) if args.out else Path("output/ready") / f"{src.stem}_wspeed.mp4"
        cfg = _build_edit_config(args)
        print(f"Düzenleme başlıyor: {src} -> {out} (layout={cfg.layout})")
        rendered, analysis, transcript, lang = auto_edit_wspeed(
            src,
            out,
            hook_text=args.hook,
            whisper_model=args.whisper_model,
            language=args.language,
            config=cfg,
        )
        print(f"✅ Tamamlandı: {rendered.resolve()}")
        print(f"   Peak anları (sn): {analysis.hype_peaks}")
        print(f"   Dil: {lang} | Transkript: {transcript[:140]}")
        return 0

    platforms = [p.strip() for p in args.platform.split(",") if p.strip()]
    keywords = [k.strip() for k in args.keyword.split(",") if k.strip()] if args.keyword else None

    if args.compile:
        compiler = CompilationPipeline()
        cfg = _build_edit_config(args)
        cfg.camera_shake = True
        cfg.impact_flash = True
        cfg.add_sfx = True
        nar_lang = None if (args.no_narration or args.narration == "none") else args.narration
        print(
            f"💰 Para Kazanmaya Uygun Derleme (62+ sn) hazırlanıyor | Kategori: {args.game} | "
            f"Hedef Min Süre: {args.target_duration:.0f}s | Anlatım: {nar_lang or 'kapalı'}"
        )
        comp = compiler.build_compilation(
            category=args.game,
            platforms=platforms,
            period=args.period,
            sort_by=args.sort,
            min_views=args.min_views,
            language=args.language,
            keywords=keywords,
            target_min_duration=args.target_duration,
            whisper_model=args.whisper_model,
            narration_lang=nar_lang,
            intro_audio_path=args.intro_audio,
            edit_config=cfg,
            force=args.force,
        )
        print(f"\n✅ Derleme hazır ({comp.duration_seconds:.1f} sn, {len(comp.clips_used)} klip):")
        print(f"   Başlık   : {comp.title}")
        print(f"   Video    : {comp.output_path.resolve()}")
        print(f"   Metadata : {comp.metadata_path.resolve()}")
        print(f"   Kontrol  : {comp.monetization_checks}\n")
        return 0

    if args.farm:
        farmer = ClipFarmerPipeline()
        cfg = _build_edit_config(args)
        print(
            f"🚀 Clip Farming başlıyor | Kategori: {args.game} | "
            f"Adet: {args.farm_count} | Düzen: {args.layout} | Sıralama: {args.sort}"
        )
        results, errors = farmer.farm_top_clips(
            category=args.game,
            platforms=platforms,
            period=args.period,
            sort_by=args.sort,
            count=args.farm_count,
            min_views=args.min_views,
            max_duration=args.max_duration or 90.0,
            language=args.language,
            keywords=keywords,
            whisper_model=args.whisper_model,
            edit_config=cfg,
            hook_text=args.hook,
            show_badge=args.badge,
            force=args.force,
        )
        if errors:
            for key, err in errors.items():
                print(f"[UYARI - {key}]: {err}", file=sys.stderr)
        if not results:
            print("İşlenecek yeni klip bulunamadı (tümü daha önce işlenmiş veya kriter dışı).")
            return 0

        print(f"\n✅ {len(results)} video hazırlandı:\n")
        for idx, res in enumerate(results, start=1):
            low_note = " [UYARI: Düşük izlenmeli klip]" if res.clip.views < 3000 else ""
            print(f"{idx}. {res.metadata.viral_title} ({res.clip.views:,} izlenme){low_note}")
            print(f"   Video   : {res.output_path.resolve()}")
            print(f"   Metadata: {res.metadata_path.resolve()}")
            print(f"   Peaklar : {res.hype_peaks}\n")
        return 0

    engine = ClipFinderEngine()
    result = engine.search(
        category=args.game,
        platforms=platforms,
        period=args.period,
        limit_per_platform=args.limit,
        min_views=args.min_views,
        max_duration=args.max_duration,
        language=args.language,
        keywords=keywords,
        sort_by=args.sort,
    )

    if result.errors:
        for plat, err in result.errors.items():
            print(f"[UYARI - {plat}]: {err}", file=sys.stderr)

    if not result.clips:
        print("Kriterlere uyan klip bulunamadı.")
        return 0

    print(f"\n=== {args.game} | {args.period} | {len(result.clips)} klip ===\n")
    for idx, clip in enumerate(result.clips, start=1):
        print(
            f"{idx:>2}. [{clip.platform.upper():<6}] "
            f"{clip.views:>9,} izlenme | {clip.virality_score:>7.1f}/saat | "
            f"{clip.duration_seconds:>4.0f}s | {clip.channel_name}"
        )
        print(f"    {clip.title}")
        print(f"    {clip.url}\n")

    if args.export:
        out_path = Path(args.export)
        if out_path.suffix.lower() == ".csv":
            saved = engine.export_csv(result.clips, out_path)
        else:
            saved = engine.export_json(result.clips, out_path)
        print(f"Dışa aktarıldı: {saved.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
