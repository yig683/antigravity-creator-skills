from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from clip_finder.audio_fx import ensure_sfx_pack
from clip_finder.captions import WordTiming, build_wspeed_ass
from clip_finder.compiler import _format_mmss, _is_offtopic_title
from clip_finder.editor import EditConfig, _build_wspeed_motion_terms, _build_zoompan_exprs
from clip_finder.facecam import detect_framing_plan
from clip_finder.graphics import (
    render_gta_logo_png,
    render_hook_card_png,
    render_mystery_lock_png,
    render_neon_divider_png,
    render_progress_bar_layers,
    render_rank_pill_png,
)
from clip_finder.history import ClipHistory
from clip_finder.metadata import generate_viral_metadata
from clip_finder.models import Clip
from clip_finder.uploader import mark_upload_result, sync_upload_queue
from clip_finder.web import create_app


class TestClipFarmerComponents(unittest.TestCase):
    def test_history_persistence_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out_mp4 = root / "done.mp4"
            out_mp4.write_bytes(b"fake-mp4")

            hist = ClipHistory(root / "history.json")
            self.assertFalse(hist.is_processed("twitch", "clip1"))
            hist.mark("twitch", "clip1", "done", output_path=str(out_mp4))
            self.assertTrue(hist.is_processed("twitch", "clip1"))

            reloaded = ClipHistory(root / "history.json")
            self.assertTrue(reloaded.is_processed("twitch", "clip1"))

    def test_sfx_pack_generation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sfx = ensure_sfx_pack(td)
            for name in ("bass_boom", "whoosh", "pop", "lock_clack", "glitch", "riser", "hype_bed"):
                self.assertIn(name, sfx)
                self.assertTrue(sfx[name].exists())
                self.assertGreater(sfx[name].stat().st_size, 1000)

    def test_wspeed_ass_generation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ass_path = Path(td) / "test.ass"
            words = [
                WordTiming("BU", 0.1, 0.3),
                WordTiming("NE!", 0.31, 0.7),
                WordTiming("ABI", 0.8, 1.1),
            ]
            build_wspeed_ass(
                words,
                ass_path,
                hook_text="SONUNA KADAR İZLE",
                channel_badge="@RRaenee",
                rank_label="#1",
                video_duration=10.0,
            )
            content = ass_path.read_text(encoding="utf-8")
            self.assertIn("PlayResX: 1080", content)
            self.assertIn("PlayResY: 1920", content)
            self.assertIn("SONUNA KADAR İZLE", content)
            self.assertIn("@RRaenee", content)
            self.assertIn("#1", content)
            self.assertIn("Dialogue:", content)

    def test_compiler_timestamp_format(self) -> None:
        self.assertEqual(_format_mmss(0), "00:00")
        self.assertEqual(_format_mmss(65.4), "01:05")

    def test_motion_expressions(self) -> None:
        z, sx, sy, fl, rgb = _build_wspeed_motion_terms(
            [2.0, 5.5],
            EditConfig(camera_shake=True, impact_flash=True, rgb_split=True),
        )
        self.assertIn("between(t,2.00,2.70)", z)
        self.assertIn("sin(t*85)", sx)
        self.assertIn("cos(t*105)", sy)
        self.assertIn("between(t,2.00,2.08)", fl)
        self.assertIn("between(t,5.50,5.62)", rgb)

    def test_zoompan_expressions(self) -> None:
        z, x, y = _build_zoompan_exprs(
            [1.8, 4.2],
            duration=8.0,
            fps=60,
            config=EditConfig(camera_shake=True),
        )
        self.assertIn("1.045+0.075*min(on/480,1)", z)
        self.assertIn("exp(-4.6*(it-1.80))", z)
        self.assertIn("iw/2-(iw/zoom/2)", x)
        self.assertIn("sin(it*85)", x)
        self.assertIn("cos(it*105)", y)

    def test_skip_dialogue_captions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ass_path = Path(td) / "skip.ass"
            build_wspeed_ass(
                [WordTiming("HELLO", 0.1, 0.4), WordTiming("WORLD", 0.5, 0.9)],
                ass_path,
                video_duration=5.0,
                skip_dialogue=True,
            )
            content = ass_path.read_text(encoding="utf-8")
            self.assertNotIn(",Default,", content)

    def test_graphics_overlays(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pill = render_rank_pill_png(1, "Jynxzi", 50200, root / "pill.png")
            pill_cjk = render_rank_pill_png(
                6,
                "みつきさんです",
                11478,
                root / "pill_cjk.png",
                fallback_handle="mitsuki_mitsuu",
            )
            hook = render_hook_card_png("TOP 7 GTA 6", "WHAT DID #1\nJUST SEE?!", "THE ENDING BROKE EVERYONE", root / "hook.png")
            lock = render_mystery_lock_png("UNLOCKS AT #1", "50.2K VIEWS · WATCH TO END", root / "lock.png")
            logo = render_gta_logo_png(root / "logo.png", width=320)
            divider = render_neon_divider_png(width=1080, height=6, out_path=root / "div.png")
            track, fill = render_progress_bar_layers(width=1080, height=9, out_dir=root / "ui")
            for p in (pill, pill_cjk, hook, lock, logo, divider, track, fill):
                self.assertTrue(p.exists())
                with Image.open(p) as im:
                    self.assertEqual(im.mode, "RGBA")
                    self.assertGreater(im.width, 100)
                    self.assertGreater(im.height, 4)

    def test_viral_metadata(self) -> None:
        clip = Clip(
            platform="kick",
            clip_id="abc123",
            title="mal npc herkesi ezdi",
            views=18000,
            duration_seconds=23,
            url="https://kick.com/rraenee/clips/abc123",
            thumbnail_url="",
            channel_name="RRaenee",
            channel_url="https://kick.com/rraenee",
            category="Grand Theft Auto VI",
            created_at="2026-11-11T16:00:00Z",
            language="tr",
        )
        meta = generate_viral_metadata(clip, transcript="bu ne abi", detected_language="tr")
        self.assertIn("#gta6", meta.hashtags)
        self.assertIn("#shorts", meta.youtube_shorts_title)
        self.assertIn("RRaenee", meta.tiktok_caption)
        self.assertEqual(meta.hook_banner, "")

    def test_web_routes(self) -> None:
        app = create_app()
        client = app.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        r = client.get("/api/ready")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("items", data)

    def test_broken_screen_detection_flags_color_bars(self) -> None:
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as td:
            smpte_mp4 = Path(td) / "smpte.mp4"
            writer = cv2.VideoWriter(str(smpte_mp4), cv2.VideoWriter_fourcc(*"mp4v"), 15.0, (640, 360))
            bars = np.zeros((360, 640, 3), dtype=np.uint8)
            colors = [(255, 255, 255), (0, 255, 255), (255, 255, 0), (0, 255, 0), (255, 0, 255), (0, 0, 255), (255, 0, 0)]
            bw = 640 // len(colors)
            for idx, bgr in enumerate(colors):
                bars[:, idx * bw:(idx + 1) * bw] = bgr
            for _ in range(18):
                writer.write(bars)
            writer.release()

            fp = detect_framing_plan(smpte_mp4)
            self.assertTrue(fp.is_broken_screen)

    def test_rtl_captions_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ass_out = Path(td) / "rtl.ass"
            build_wspeed_ass(
                [WordTiming(text="مرحبا", start=0.1, end=0.5)],
                ass_out,
                language="ar",
            )
            content = ass_out.read_text(encoding="utf-8")
            self.assertNotIn("WSpeed", content.split("[Events]")[1])

    def test_dual_sub_secondary_line_above_english(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ass_out = Path(td) / "dual.ass"
            build_wspeed_ass(
                [WordTiming(text="LOOK", start=0.1, end=0.4), WordTiming(text="NOW!", start=0.42, end=0.9)],
                ass_out,
                language="en",
                secondary_phrases=[WordTiming(text="Вы посмотрите!", start=0.1, end=0.9)],
            )
            content = ass_out.read_text(encoding="utf-8")
            events = content.split("[Events]")[1]
            self.assertIn("Style: OrigSub", content)
            self.assertIn(",OrigSub,", events)
            self.assertIn("Вы посмотрите!", events)
            self.assertIn(",WSpeed,", events)

    def test_offtopic_gta6_title_filter(self) -> None:
        bad = Clip(
            platform="kick",
            clip_id="bad1",
            title="FiveM RP Warzone CoD highlights",
            views=500,
            duration_seconds=20,
            url="https://kick.com/test/clips/bad1",
            thumbnail_url="",
            channel_name="test",
            channel_url="",
            category="Grand Theft Auto VI",
            created_at="",
        )
        good = Clip(
            platform="twitch",
            clip_id="good1",
            title="GTA 6 trailer reaction INSANE",
            views=5000,
            duration_seconds=20,
            url="https://twitch.tv/test/clip/good1",
            thumbnail_url="",
            channel_name="test2",
            channel_url="",
            category="Grand Theft Auto VI",
            created_at="",
        )
        self.assertTrue(_is_offtopic_title(bad, "Grand Theft Auto VI"))
        self.assertFalse(_is_offtopic_title(good, "Grand Theft Auto VI"))

    def test_uploader_unique_seo_packages_and_queue_sync(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ready = Path(td)
            for idx, (stem, transcript, streamers) in enumerate(
                [
                    ("compilation_1", "goosebumps", "Fanum, Rubius, KaiCenat"),
                    ("compilation_2", "learn so much spanish", "elxokas, KaiCenat, Jynxzi"),
                ],
                start=1,
            ):
                mp4 = ready / f"{stem}.mp4"
                mp4.write_bytes(b"fake_mp4")
                js = ready / f"{stem}.json"
                js.write_text(
                    json.dumps(
                        {
                            "viral_title": "Top 11 Most Watched GTA 6 Moments (#1 is Wild)",
                            "description": "Top 11\n\nChapters:\n00:00 Intro\n\nCredits:\n#1 Test: https://twitch.tv/test\n\n#gta6",
                            "streamer": streamers,
                            "transcript": transcript,
                            "duration_seconds": 70.0 + idx,
                            "credits": [f"#{i} Test" for i in range(1, 12)],
                        }
                    ),
                    encoding="utf-8",
                )

            queue = sync_upload_queue(ready_dir=ready)
            self.assertEqual(queue["total_ready"], 2)
            self.assertEqual(queue["pending_count"], 2)
            titles = [it["title"] for it in queue["items"]]
            self.assertEqual(len(set(titles)), 2)
            for it in queue["items"]:
                self.assertLessEqual(len(it["title"]), 100)
                self.assertIn("#shorts", it["title"].lower())
                self.assertLessEqual(sum(len(t) + 2 for t in it["tags"]), 500)

            # Second sync should remain idempotent (Chapters not duplicated)
            queue2 = sync_upload_queue(ready_dir=ready)
            desc = Path(queue2["items"][0]["json_path"]).read_text(encoding="utf-8")
            self.assertEqual(json.loads(desc)["description"].count("Chapters:"), 1)

            mark_upload_result(queue2["items"][0]["stem"], "published", ready_dir=ready, video_url="https://youtube.com/shorts/abc")
            queue3 = sync_upload_queue(ready_dir=ready)
            self.assertEqual(queue3["pending_count"], 1)


if __name__ == "__main__":
    unittest.main()
