"""Reusable episode scaffold for Makine Studio.

Copy this file to `episodes/<new_episode>.py`, customize `EPISODE_ID`,
`EPISODE_META`, `BEATS`, and `build_blender_scene(...)`, then run:
    python -m studio.pipeline --episode <new_episode> --mode preview
"""

from __future__ import annotations

from typing import Any

EPISODE_ID = "template_episode"

EPISODE_META = {
    "title": "<Makineyi> Nasıl İcat Edersin? ⚙️",
    "cover_lines": [
        ("<MAKİNEYİ> NASIL", "white"),
        ("İCAT EDERSİN?", "cyan"),
    ],
    "header_tag": "PROJE #00 // MÜHENDİSLİK ŞEMASI",
    "description": (
        "<Problem kancası 1 cümle>\n\n"
        "👇 Sıradaki videoda neyi icat edelim? Yorumlara yaz!\n\n"
        "#mühendislik #icat #nasılicatedersin #3d #shorts"
    ),
    "pinned_comment": "Sıradaki videoda neyi icat edelim? 👇⚙️",
    "tags": ["nasıl icat edersin", "mühendislik shorts", "3d animasyon", "makine stüdyo"],
}

BEATS: list[dict[str, Any]] = [
    {
        "id": "shock_hook",
        "narration": "Bu mekanizma kritik bir anda koparsa hayatını kurtaracak o parça nasıl çalışır?",
        "pause_after": 0.10,
        "headline": [("KRİTİK AN // ", "red"), ("TEHLİKE KANCASI", "amber")],
        "sfx": [{"name": "boom", "offset": 0.0, "gain": 0.65}],
    },
    {
        "id": "hook_problem",
        "narration": "Hadi en baştan icat edelim: günlük hayatta çözmen gereken büyük bir mekanik sorunun var.",
        "pause_after": 0.10,
        "headline": [("PROBLEMİ ", "white"), ("TANI", "cyan")],
        "sfx": [{"name": "pop", "offset": 0.2, "gain": 0.48}],
    },
    {
        "id": "naive_fail",
        "narration": "İlk denemede basit bir yöntem denersin ama tek başına yeterli olmaz.",
        "pause_after": 0.11,
        "headline": [("İLK DENEME ", "white"), ("YETERSİZ", "red")],
        "sfx": [{"name": "alert", "offset": 1.4, "gain": 0.80}],
    },
    {
        "id": "key_invention",
        "narration": "Asıl mühendislik sırrı, mekanizmaya akıllı bir denge ve güvenlik parçası eklemektir.",
        "pause_after": 0.11,
        "headline": [("MÜHENDİSLİK ", "white"), ("ÇÖZÜMÜ", "amber")],
        "sfx": [{"name": "clank", "offset": 1.2, "gain": 0.85}],
    },
    {
        "id": "final_payoff",
        "narration": "Tüm parçalar birleştiğinde sistem kusursuz ve zahmetsiz biçimde çalışır.",
        "pause_after": 0.18,
        "headline": [("MODERN ", "white"), ("MAKİNE", "green")],
        "sfx": [{"name": "ding", "offset": 1.5, "gain": 0.85}],
    },
]


def get_beats(profile: str = "shorts") -> list[dict[str, Any]]:
    """Return profile-tailored beat list (extend here for tiktok 61-64s beats)."""
    return BEATS


def build_blender_scene(timeline: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Minimal template scene showing CameraRig, MannequinRig, and HUDTracker usage."""
    from studio.blender_scene_api import (
        CameraRig,
        HUDTracker,
        MannequinRig,
        add_box,
        make_material,
        reset_scene,
        set_keyframe,
        setup_world_and_lighting,
    )

    fps = int(timeline["fps"])
    total_frames = int(timeline["total_frames"])
    scene = reset_scene(
        res_x=int(cfg["stage_w"]),
        res_y=int(cfg["stage_h"]),
        fps=fps,
        samples=int(cfg["samples"]),
    )
    scene.frame_start = 1
    scene.frame_end = total_frames
    setup_world_and_lighting()

    steel = make_material("TemplateSteel", (0.65, 0.72, 0.82), metallic=0.85, roughness=0.25)
    add_box("BasePlatform", (4.0, 2.5, 0.2), (0, 0, -0.1), material=steel, bevel=0.02)

    man = MannequinRig("HeroMannequin")
    set_keyframe(man.root, 1, location=(0, 0, 0), rotation_deg=(0, 0, -15))
    man.animate_relaxed_celebrate(1, total_frames, fps=fps)

    cam = CameraRig(lens=36.0)
    cam.key(1, (1.5, -7.5, 2.2), (0.0, 0.0, 1.0))
    cam.key(total_frames, (-1.2, -7.2, 2.4), (0.0, 0.0, 1.0))

    hud = HUDTracker()
    hud.add("demo_callout", man.alert_anchor, "callout", 1, total_frames, label="PROTO-TİP", color="cyan", offset_px=(120, -60))

    return {
        "scene": scene,
        "camera": cam.cam,
        "hud_tracker": hud,
        "hero_frame": max(1, total_frames // 2),
    }
