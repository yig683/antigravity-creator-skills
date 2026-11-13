"""Pilot Episode v3: 'Asansörü Nasıl İcat Edersin?' — Hook-First, Multi-Angle, 30/60FPS & TikTok-Ready 3D Scene."""

from __future__ import annotations

import math
from typing import Any

EPISODE_ID = "asansor_icat"

EPISODE_META = {
    "title": "Asansörü Nasıl İcat Edersin? 🛗⚙️",
    "cover_lines": [
        ("ASANSÖRÜ NASIL", "white"),
        ("İCAT EDERSİN?", "cyan"),
    ],
    "header_tag": "PROJE #01 // DİKEY TAŞIMA SİSTEMİ",
    "description": (
        "10. kattan düşerken çelik halat aniden kopsa seni aşağı çakılmaktan kurtaran o minik yay nasıl çalışır?\n\n"
        "1. kattan başlayıp makaralardan karşı ağırlık dengesine, çelik kılavuz raylardan Elisha Otis'in "
        "yaylı emniyet frenine kadar asansör mühendisliğini adım adım sıfırdan keşfet.\n\n"
        "👇 Sıradaki videoda hangi makineyi icat edelim? Yorumlarda yaz!\n\n"
        "#mühendislik #icat #asansör #nasılicatedersin #3d #bilim #mekanik #shorts"
    ),
    "pinned_comment": "Sıradaki videoda neyi icat edelim? En çok beğeni alan fikri 3D blueprint olarak yapıyoruz! 👇⚙️",
    "tags": [
        "asansör nasıl icat edilir",
        "nasıl icat edersin",
        "asansör çalışma prensibi",
        "elisha otis emniyet freni",
        "karşı ağırlık nedir",
        "mühendislik shorts",
        "3d mekanik animasyon",
        "makine stüdyo",
    ],
}

_CORE_PRE_PAYOFF: list[dict[str, Any]] = [
    {
        "id": "shock_hook",
        "narration": (
            "Onuncu kattan düşerken bu çelik halat aniden kopsa, "
            "hayatını kurtaran o minik yay nasıl çalışır?"
        ),
        "pause_after": 0.08,
        "headline": [("HALAT KOPTU! ", "red"), ("HAYAT KURTARAN YAY", "amber")],
        "sfx": [
            {"name": "riser", "offset": 0.0, "gain": 0.45},
            {"name": "snap", "offset": 0.80, "gain": 0.88},
            {"name": "boom", "offset": 0.82, "gain": 0.72},
            {"name": "clank", "offset": 1.28, "gain": 0.85},
        ],
    },
    {
        "id": "hook_building",
        "narration": (
            "Hadi birinci kattan sıfırdan icat edelim. "
            "Elinde ağır poşetlerle onuncu kata çıkmanın kolay bir yolu gerek."
        ),
        "pause_after": 0.08,
        "headline": [("10 KATLI BİNA ", "white"), ("// ADIM ADIM İCAT", "cyan")],
        "sfx": [
            {"name": "pop", "offset": 0.15, "gain": 0.50},
            {"name": "boom", "offset": 2.0, "gain": 0.52},
        ],
    },
    {
        "id": "stairs_pain",
        "narration": (
            "Merdivenden yürümeyi denesen, daha üçüncü katta nefesin kesilir "
            "ve bu iş böyle gitmez dersin."
        ),
        "pause_after": 0.09,
        "headline": [("MERDİVENDE ", "white"), ("TÜKENDİN", "red")],
        "sfx": [
            {"name": "step", "offset": 0.35, "gain": 0.55},
            {"name": "step", "offset": 0.75, "gain": 0.55},
            {"name": "step", "offset": 1.15, "gain": 0.55},
            {"name": "alert", "offset": 2.1, "gain": 0.65},
        ],
    },
    {
        "id": "pulley_fail",
        "narration": (
            "Peki tepeye bir makara takıp halatı aşağıdan sen çeksen? "
            "Platform kalkar ama tüm ağırlık kollarına biner, tek başına kaldıramazsın."
        ),
        "pause_after": 0.09,
        "headline": [("TEK BAŞINA ", "white"), ("MAKARA", "amber"), (" YETMEZ", "white")],
        "sfx": [
            {"name": "pop", "offset": 0.20, "gain": 0.45},
            {"name": "alert", "offset": 3.5, "gain": 0.62},
        ],
    },
    {
        "id": "counterweight",
        "narration": (
            "İşte pratik çözüm: Halatın öbür ucuna kabin ağırlığında bir karşı ağırlık bağlamak. "
            "İki taraf dengelenince artık neredeyse hiç güç gerekmez."
        ),
        "pause_after": 0.10,
        "headline": [("KARŞI ", "white"), ("AĞIRLIK", "cyan"), (" DENGESİ", "white")],
        "sfx": [
            {"name": "clank", "offset": 0.95, "gain": 0.68},
            {"name": "ding", "offset": 3.8, "gain": 0.62},
        ],
    },
    {
        "id": "guide_rails",
        "narration": (
            "Ama büyük bir sorun var: Kabin sağa sola savrulup duvarlara çarpıyor. "
            "Bunu da şaft boyunca uzanan çelik kılavuz raylar ve tekerleklerle tamamen önlersin."
        ),
        "pause_after": 0.10,
        "headline": [("ÇELİK ", "white"), ("KILAVUZ RAYLAR", "cyan")],
        "sfx": [
            {"name": "alert", "offset": 0.85, "gain": 0.62},
            {"name": "clank", "offset": 3.4, "gain": 0.72},
        ],
    },
    {
        "id": "safety_brake",
        "narration": (
            "Şimdi başa dönelim: Ana halat koptuğu an Elisha Otis’in yaylı freni gerilimi kaybedip "
            "dışarı fırlar, raylara kilitlenip düşüşü anında durdurur."
        ),
        "tts_text": (
            "Şimdi başa dönelim: Ana halat koptuğu an Elişa Otis'in yaylı freni gerilimi kaybedip "
            "dışarı fırlar, raylara kilitlenip düşüşü anında durdurur."
        ),
        "pause_after": 0.10,
        "headline": [("OTIS ", "red"), ("EMNİYET FRENİ", "amber")],
        "sfx": [
            {"name": "riser", "offset": 0.15, "gain": 0.55},
            {"name": "snap", "offset": 1.55, "gain": 0.88},
            {"name": "clank", "offset": 2.45, "gain": 0.90},
            {"name": "ding", "offset": 4.4, "gain": 0.62},
        ],
    },
]

_TIKTOK_DEPTH_BEAT: dict[str, Any] = {
    "id": "dual_safety_pit",
    "narration": (
        "Güvenliği ikiye katlamak için tek halat yerine yükü paylaşan dört ayrı çelik halat bağlanır; "
        "tek başına her biri tüm kabini taşır. "
        "Kuyu dibindeki yağ basınçlı tampon pistonlar ise olası sert düşüşü anında yumuşatır."
    ),
    "pause_after": 0.12,
    "headline": [("4x ÇELİK HALAT ", "cyan"), ("+ KUYU TAMPONU", "amber")],
    "sfx": [
        {"name": "pop", "offset": 0.35, "gain": 0.48},
        {"name": "clank", "offset": 4.2, "gain": 0.62},
        {"name": "boom", "offset": 8.0, "gain": 0.68},
        {"name": "ding", "offset": 10.4, "gain": 0.55},
    ],
}

_PAYOFF_BEAT: dict[str, Any] = {
    "id": "modern_payoff",
    "narration": (
        "Son olarak tepeye güçlü bir elektrik motoru, cam kabin ve kat düğmeleri eklediğinde "
        "on katı saniyeler içinde çıkarsın. Tabii asansör müziğiyle."
    ),
    "pause_after": 0.25,
    "headline": [("MODERN ", "white"), ("ELEKTRİKLİ ASANSÖR", "green")],
    "sfx": [
        {"name": "motor", "offset": 0.25, "gain": 0.58},
        {"name": "ding", "offset": 3.8, "gain": 0.72},
        {"name": "muzak", "offset": 4.5, "gain": 0.42},
    ],
}


def get_beats(profile: str = "shorts") -> list[dict[str, Any]]:
    """Return episode beat list tailored for short-form or 62+ sec TikTok duration."""
    if profile == "tiktok":
        return [dict(b) for b in [*_CORE_PRE_PAYOFF, _TIKTOK_DEPTH_BEAT, _PAYOFF_BEAT]]
    return [dict(b) for b in [*_CORE_PRE_PAYOFF, _PAYOFF_BEAT]]


BEATS: list[dict[str, Any]] = get_beats("shorts")


def _sample_frames(start: int, end: int, step: int = 2) -> list[int]:
    """Return inclusive sampled frames plus exact endpoint."""
    step = max(1, int(step))
    frames = list(range(start, end + 1, step))
    if not frames or frames[-1] != end:
        frames.append(end)
    return frames


def build_blender_scene(timeline: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Construct and keyframe the physically accurate 10-story elevator blueprint scene."""
    import bpy
    from mathutils import Vector

    from studio.blender_scene_api import (
        CameraRig,
        HUDTracker,
        MannequinRig,
        add_box,
        add_cylinder,
        add_empty,
        attach_follow_location,
        make_material,
        reset_scene,
        set_keyframe,
        set_visibility,
        setup_world_and_lighting,
    )

    stage_w = int(cfg["stage_w"])
    stage_h = int(cfg["stage_h"])
    fps = int(timeline["fps"])
    total_frames = int(timeline["total_frames"])
    samples = int(cfg["samples"])
    kf_step = max(1, round(fps / 15))

    scene = reset_scene(res_x=stage_w, res_y=stage_h, fps=fps, samples=samples)
    scene.frame_start = 1
    scene.frame_end = total_frames
    setup_world_and_lighting(sky_color=(0.025, 0.068, 0.135), key_energy=4.4)

    beats = {b["id"]: b for b in timeline["beats"]}

    # ------------------------------------------------------------------
    # Architectural Scale Constants (True 10 Stories!)
    # ------------------------------------------------------------------
    NUM_FLOORS = 10
    FLOOR_H = 1.60
    TOP_DECK_Z = NUM_FLOORS * FLOOR_H
    PULLEY_Z = TOP_DECK_Z - 0.90
    MAIN_PULLEY_X = 0.52
    MAIN_PULLEY_R = 0.52
    CW_PULLEY_X = 2.00
    CW_PULLEY_R = 0.42
    CW_LANE_X = CW_PULLEY_X + CW_PULLEY_R

    # ------------------------------------------------------------------
    # Materials
    # ------------------------------------------------------------------
    concrete_mat = make_material("Concrete", (0.28, 0.34, 0.42), metallic=0.0, roughness=0.86, noise_bump=0.30, noise_scale=22.0)
    concrete_dark = make_material("ConcreteDark", (0.14, 0.18, 0.25), metallic=0.05, roughness=0.84, noise_bump=0.22, noise_scale=18.0)
    steel_mat = make_material("BrushedSteel", (0.68, 0.74, 0.82), metallic=0.88, roughness=0.26)
    rail_steel = make_material("RailSteel", (0.84, 0.89, 0.96), metallic=0.92, roughness=0.18)
    brass_mat = make_material("BrassPulley", (0.88, 0.64, 0.22), metallic=0.85, roughness=0.26)
    wood_deck = make_material("WoodDeck", (0.50, 0.32, 0.17), metallic=0.0, roughness=0.66, noise_bump=0.15, noise_scale=16.0)
    iron_mat = make_material("CastIron", (0.13, 0.16, 0.22), metallic=0.72, roughness=0.42, noise_bump=0.18, noise_scale=28.0)
    cyan_glow = make_material("CyanGlow", (0.18, 0.82, 0.98), metallic=0.1, roughness=0.25, emission=(0.18, 0.82, 0.98), emission_strength=2.2)
    amber_mat = make_material("SafetyAmber", (0.96, 0.56, 0.08), metallic=0.45, roughness=0.32, emission=(0.95, 0.45, 0.05), emission_strength=0.45)
    red_brake_mat = make_material("BrakeRed", (0.94, 0.18, 0.16), metallic=0.35, roughness=0.30, emission=(0.90, 0.12, 0.12), emission_strength=0.65)
    green_glow = make_material("GreenPanel", (0.20, 0.90, 0.48), metallic=0.0, roughness=0.20, emission=(0.20, 0.90, 0.48), emission_strength=2.6)
    glass_mat = make_material("CabinGlass", (0.62, 0.88, 1.0), metallic=0.05, roughness=0.05, alpha=0.12)
    bag_kraft = make_material("GroceryBag", (0.76, 0.58, 0.36), metallic=0.0, roughness=0.82, noise_bump=0.12, noise_scale=30.0)
    bag_veggie = make_material("BagAccent", (0.22, 0.72, 0.34), metallic=0.0, roughness=0.65)
    cable_mat = make_material("SteelCable", (0.56, 0.62, 0.70), metallic=0.80, roughness=0.34)
    belt_mat = make_material("DriveBelt", (0.24, 0.28, 0.34), metallic=0.35, roughness=0.45)

    # ------------------------------------------------------------------
    # True 10-Story Cutaway Building + Continuous Zigzag Staircases
    # ------------------------------------------------------------------
    building_root = add_empty("Building_Root", (0, 0, 0))
    add_box("BaseSlab", (8.4, 2.4, 0.36), (-0.5, 0.1, -0.18), material=concrete_dark, bevel=0.02, parent=building_root)
    add_box("RearWall", (8.0, 0.24, TOP_DECK_Z + 0.2), (-0.5, 0.98, TOP_DECK_Z * 0.5), material=concrete_dark, bevel=0.02, parent=building_root)
    add_box("LeftOuterCol", (0.28, 1.45, TOP_DECK_Z + 0.2), (-4.35, 0.1, TOP_DECK_Z * 0.5), material=concrete_mat, bevel=0.02, parent=building_root)
    add_box("ShaftLeftWall", (0.22, 1.45, TOP_DECK_Z), (-1.35, 0.1, TOP_DECK_Z * 0.5), material=concrete_mat, bevel=0.02, parent=building_root)
    add_box("ShaftRightWall", (0.22, 1.45, TOP_DECK_Z), (1.35, 0.1, TOP_DECK_Z * 0.5), material=concrete_mat, bevel=0.02, parent=building_root)
    add_box("CWOuterWall", (0.26, 1.45, TOP_DECK_Z), (3.35, 0.1, TOP_DECK_Z * 0.5), material=concrete_mat, bevel=0.02, parent=building_root)

    add_box("TopHeaderBeam_L", (4.83, 1.75, 0.32), (-2.235, 0.1, TOP_DECK_Z + 0.16), material=concrete_mat, bevel=0.02, parent=building_root)
    add_box("TopHeaderBeam_R", (2.79, 1.75, 0.32), (2.255, 0.1, TOP_DECK_Z + 0.16), material=concrete_mat, bevel=0.02, parent=building_root)
    add_box("TopHeaderBeam_Back", (0.72, 0.50, 0.32), (0.52, 0.72, TOP_DECK_Z + 0.16), material=concrete_dark, bevel=0.015, parent=building_root)

    penthouse_root = add_empty("Penthouse_Root", (0, 0, 0))
    add_box("PenthouseColL", (0.24, 1.2, 2.0), (-1.35, 0.1, TOP_DECK_Z + 1.15), material=concrete_mat, bevel=0.015, parent=penthouse_root)
    add_box("PenthouseColR", (0.24, 1.2, 2.0), (3.35, 0.1, TOP_DECK_Z + 1.15), material=concrete_mat, bevel=0.015, parent=penthouse_root)
    add_box("PenthouseBackWall", (4.7, 0.20, 2.0), (1.0, 0.85, TOP_DECK_Z + 1.15), material=concrete_dark, bevel=0.015, parent=penthouse_root)
    add_box("PenthouseRoof", (5.1, 1.65, 0.24), (1.0, 0.1, TOP_DECK_Z + 2.22), material=concrete_mat, bevel=0.02, parent=penthouse_root)

    stair_root = add_empty("Stairs_Root", (0, 0, 0), parent=building_root)
    for k in range(NUM_FLOORS):
        z_bot = k * FLOOR_H
        z_top = (k + 1) * FLOOR_H
        even_top = ((k + 1) % 2 == 0)

        add_box(f"FloorTick_{k+1}", (0.34, 0.06, 0.05), (-4.35, -0.60, z_top), material=cyan_glow, parent=building_root)
        if k == NUM_FLOORS - 1:
            add_box(f"Landing_{k+1}", (2.95, 1.38, 0.14), (-2.85, 0.1, z_top), material=concrete_mat, bevel=0.015, parent=building_root)
            add_box(f"FloorStrip_{k+1}", (2.95, 0.04, 0.05), (-2.85, -0.60, z_top), material=cyan_glow, parent=building_root)
        elif even_top:
            add_box(f"Landing_{k+1}", (0.72, 1.38, 0.14), (-3.87, 0.1, z_top), material=concrete_mat, bevel=0.015, parent=building_root)
            add_box(f"FloorStrip_{k+1}", (0.72, 0.04, 0.05), (-3.87, -0.60, z_top), material=cyan_glow, parent=building_root)
        else:
            add_box(f"Landing_{k+1}", (0.82, 1.38, 0.14), (-1.86, 0.1, z_top), material=concrete_mat, bevel=0.015, parent=building_root)
            add_box(f"FloorStrip_{k+1}", (0.82, 0.04, 0.05), (-1.86, -0.60, z_top), material=cyan_glow, parent=building_root)

        going_right = (k % 2 == 0)
        x_start = -3.54 if going_right else -2.26
        x_end = -2.26 if going_right else -3.54
        y_lane = -0.18 if going_right else 0.36
        dx = x_end - x_start
        dz = FLOOR_H
        slope_len = math.hypot(dx, dz)
        slope_deg = math.degrees(math.atan2(dz, abs(dx))) * (-1.0 if going_right else 1.0)

        add_box(
            f"Stringer_{k+1}",
            (slope_len, 0.72, 0.10),
            ((x_start + x_end) * 0.5, y_lane, (z_bot + z_top) * 0.5 - 0.05),
            rotation_deg=(0, slope_deg, 0),
            material=concrete_dark,
            bevel=0.01,
            parent=stair_root,
        )
        n_steps = 6
        for s in range(n_steps):
            frac = (s + 0.5) / n_steps
            add_box(
                f"Step_{k+1}_{s}",
                (abs(dx) / n_steps * 1.15, 0.76, 0.16),
                (x_start + dx * frac, y_lane, z_bot + dz * frac),
                material=concrete_mat,
                bevel=0.01,
                parent=stair_root,
            )

    floor1_anchor = add_empty("Anchor_Floor1", (-4.35, -0.5, 1.60), parent=building_root)
    floor5_anchor = add_empty("Anchor_Floor5", (-4.35, -0.5, 8.00), parent=building_root)
    floor10_anchor = add_empty("Anchor_Floor10", (-4.35, -0.5, 16.00), parent=building_root)
    top_pulley_anchor = add_empty("Anchor_TopPulley", (MAIN_PULLEY_X, -0.45, PULLEY_Z), parent=building_root)

    # ------------------------------------------------------------------
    # Overhead Bolted Pulley Wheels + Hanger Brackets
    # ------------------------------------------------------------------
    main_pulley = add_empty("MainPulley_Pivot", (MAIN_PULLEY_X, 0.0, PULLEY_Z))
    add_cylinder("MainPulley_Rim", MAIN_PULLEY_R, 0.18, (0, 0, 0), rotation_deg=(90, 0, 0), vertices=32, material=brass_mat, bevel=0.015, parent=main_pulley)
    add_cylinder("MainPulley_Hub", 0.18, 0.28, (0, 0, 0), rotation_deg=(90, 0, 0), vertices=24, material=iron_mat, parent=main_pulley)
    add_box("MainPulley_Spoke1", (MAIN_PULLEY_R * 1.65, 0.05, 0.07), (0, 0, 0), material=steel_mat, parent=main_pulley)
    add_box("MainPulley_Spoke2", (0.07, 0.05, MAIN_PULLEY_R * 1.65), (0, 0, 0), material=steel_mat, parent=main_pulley)

    hanger_root = add_empty("PulleyHangers_Root", (0, 0, 0))
    for px, name_tag in [(MAIN_PULLEY_X, "Main"), (CW_PULLEY_X, "CW")]:
        h_dist = (TOP_DECK_Z + 0.05) - PULLEY_Z
        for hy in (-0.18, 0.18):
            add_box(f"{name_tag}Hanger_{hy:.2f}", (0.14, 0.06, h_dist), (px, hy, PULLEY_Z + h_dist * 0.5), material=steel_mat, bevel=0.008, parent=hanger_root)
        add_box(f"{name_tag}BasePlate", (0.48, 0.52, 0.10), (px, 0.0, TOP_DECK_Z - 0.02), material=iron_mat, bevel=0.01, parent=hanger_root)
        add_cylinder(f"{name_tag}AxlePin", 0.06, 0.46, (px, 0.0, PULLEY_Z), rotation_deg=(90, 0, 0), material=steel_mat, parent=hanger_root)

    cw_pulley = add_empty("CWPulley_Pivot", (CW_PULLEY_X, 0.0, PULLEY_Z))
    add_cylinder("CWPulley_Rim", CW_PULLEY_R, 0.16, (0, 0, 0), rotation_deg=(90, 0, 0), vertices=28, material=brass_mat, bevel=0.012, parent=cw_pulley)
    add_cylinder("CWPulley_Hub", 0.14, 0.24, (0, 0, 0), rotation_deg=(90, 0, 0), vertices=20, material=iron_mat, parent=cw_pulley)
    add_box("CWPulley_Spoke", (CW_PULLEY_R * 1.65, 0.05, 0.06), (0, 0, 0), material=steel_mat, parent=cw_pulley)

    rope_coil_root = add_empty("GroundRopeCoil", (CW_LANE_X, 0.0, 0.05))
    add_cylinder("RopeCoil_Outer", 0.24, 0.09, (0, 0, 0), vertices=24, material=cable_mat, bevel=0.02, parent=rope_coil_root)
    add_cylinder("RopeCoil_Inner", 0.14, 0.12, (0, 0, 0.04), vertices=20, material=cable_mat, bevel=0.02, parent=rope_coil_root)

    # ------------------------------------------------------------------
    # Platform + Guide Rollers + Otis Safety Brake Crosshead
    # ------------------------------------------------------------------
    platform_root = add_empty("Platform_Root", (0.0, 0.0, 0.35))
    YOKE_Z = 1.82
    add_box("Platform_Deck", (1.36, 1.15, 0.12), (0, 0, 0.0), material=wood_deck, bevel=0.015, parent=platform_root)
    add_box("Platform_SteelFrame", (1.44, 1.22, 0.08), (0, 0, -0.05), material=steel_mat, bevel=0.01, parent=platform_root)
    add_box("Platform_StileL", (0.08, 0.14, 1.86), (-0.68, 0, 0.90), material=steel_mat, bevel=0.01, parent=platform_root)
    add_box("Platform_StileR", (0.08, 0.14, 1.86), (0.68, 0, 0.90), material=steel_mat, bevel=0.01, parent=platform_root)
    add_box("Platform_TopYoke", (1.46, 0.22, 0.12), (0, 0, YOKE_Z), material=steel_mat, bevel=0.015, parent=platform_root)

    rollers_root = add_empty("Platform_Rollers", (0, 0, 0), parent=platform_root)
    for rx in (-0.76, 0.76):
        for rz in (0.08, YOKE_Z):
            add_cylinder(f"Roller_{rx:.2f}_{rz:.2f}", 0.065, 0.10, (rx, 0, rz), rotation_deg=(90, 0, 0), material=cyan_glow, parent=rollers_root)
    roller_anchor = add_empty("Anchor_Roller", (0.76, -0.20, YOKE_Z), parent=rollers_root)

    brake_drawbar = add_box("Brake_DrawbarShackle", (0.14, 0.14, 0.28), (0, 0, YOKE_Z + 0.16), material=cyan_glow, bevel=0.01, parent=platform_root)
    brake_spring = add_box("Brake_LeafSpring", (0.86, 0.10, 0.05), (0, 0, YOKE_Z + 0.09), material=amber_mat, bevel=0.008, parent=platform_root)
    brake_link_l = add_box("Brake_LinkL", (0.34, 0.05, 0.045), (-0.36, -0.10, YOKE_Z + 0.05), material=steel_mat, parent=platform_root)
    brake_link_r = add_box("Brake_LinkR", (0.34, 0.05, 0.045), (0.36, -0.10, YOKE_Z + 0.05), material=steel_mat, parent=platform_root)
    brake_wedge_l = add_box("Brake_WedgeL", (0.18, 0.20, 0.22), (-0.56, 0, YOKE_Z), material=red_brake_mat, bevel=0.012, parent=platform_root)
    brake_wedge_r = add_box("Brake_WedgeR", (0.18, 0.20, 0.22), (0.56, 0, YOKE_Z), material=red_brake_mat, bevel=0.012, parent=platform_root)

    def key_brake_state(frame: int, locked: bool) -> None:
        if not locked:
            set_keyframe(brake_drawbar, frame, location=(0, 0, YOKE_Z + 0.16))
            set_keyframe(brake_spring, frame, location=(0, 0, YOKE_Z + 0.09), scale=(1.0, 1.0, 1.0))
            set_keyframe(brake_link_l, frame, location=(-0.34, -0.10, YOKE_Z + 0.06), rotation_deg=(0, 14, 0))
            set_keyframe(brake_link_r, frame, location=(0.34, -0.10, YOKE_Z + 0.06), rotation_deg=(0, -14, 0))
            set_keyframe(brake_wedge_l, frame, location=(-0.56, 0, YOKE_Z))
            set_keyframe(brake_wedge_r, frame, location=(0.56, 0, YOKE_Z))
        else:
            set_keyframe(brake_drawbar, frame, location=(0, 0, YOKE_Z + 0.08))
            set_keyframe(brake_spring, frame, location=(0, 0, YOKE_Z + 0.05), scale=(1.18, 1.0, 1.25))
            set_keyframe(brake_link_l, frame, location=(-0.44, -0.10, YOKE_Z + 0.02), rotation_deg=(0, 2, 0))
            set_keyframe(brake_link_r, frame, location=(0.44, -0.10, YOKE_Z + 0.02), rotation_deg=(0, -2, 0))
            set_keyframe(brake_wedge_l, frame, location=(-0.74, 0, YOKE_Z))
            set_keyframe(brake_wedge_r, frame, location=(0.74, 0, YOKE_Z))

    platform_anchor = add_empty("Anchor_Platform", (0.0, -0.45, 0.15), parent=platform_root)
    platform_up_anchor = add_empty("Anchor_PlatformUp", (-0.82, -0.45, 0.90), parent=platform_root)
    brake_anchor = add_empty("Anchor_SafetyBrake", (-0.58, -0.25, YOKE_Z + 0.05), parent=platform_root)

    # ------------------------------------------------------------------
    # Full-Height Guide Rails, Counterweight, and Hydraulic Pit Buffer
    # ------------------------------------------------------------------
    rails_root = add_empty("GuideRails_Root", (0, 0, 0))
    for side, rx in [("L", -0.82), ("R", 0.82)]:
        add_box(f"GuideRail_{side}", (0.08, 0.11, TOP_DECK_Z), (rx, 0.0, TOP_DECK_Z * 0.5), material=rail_steel, bevel=0.008, parent=rails_root)
        for bz in (1.5, 3.8, 6.1, 8.4, 10.7, 13.0, 15.2):
            wall_dir = -1.0 if side == "L" else 1.0
            add_box(
                f"RailBracket_{side}_{bz:.1f}",
                (0.45, 0.16, 0.09),
                (rx + wall_dir * 0.24, 0.0, bz),
                material=iron_mat,
                bevel=0.006,
                parent=rails_root,
            )
    rail_anchor = add_empty("Anchor_GuideRail", (-0.82, -0.20, 10.6), parent=rails_root)

    cw_tracks_root = add_empty("CWTracks_Root", (0, 0, 0))
    for tr_x in (CW_LANE_X - 0.44, CW_LANE_X + 0.44):
        add_box(f"CWGuide_{tr_x:.2f}", (0.06, 0.10, TOP_DECK_Z), (tr_x, 0.0, TOP_DECK_Z * 0.5), material=rail_steel, parent=cw_tracks_root)

    cw_root = add_empty("Counterweight_Root", (CW_LANE_X, 0.0, 11.0))
    add_box("CW_Frame", (0.76, 0.54, 1.30), (0, 0, 0.65), material=iron_mat, bevel=0.02, parent=cw_root)
    for pi in range(5):
        add_box(f"CW_Plate_{pi}", (0.64, 0.46, 0.16), (0, 0, 0.22 + pi * 0.22), material=steel_mat, bevel=0.01, parent=cw_root)
    add_box("CW_AccentBand", (0.78, 0.56, 0.10), (0, 0, 0.65), material=amber_mat, bevel=0.005, parent=cw_root)
    cw_anchor = add_empty("Anchor_Counterweight", (0.0, -0.35, 0.65), parent=cw_root)

    # Shaft Pit Hydraulic Buffer Pistons (revealed in TikTok depth beat & final modern shaft)
    buffer_root = add_empty("PitBuffer_Root", (0, 0, 0))
    buffer_pistons: list[bpy.types.Object] = []
    for bi, bx in enumerate((-0.42, 0.42)):
        add_cylinder(f"BufferBase_{bi}", 0.14, 0.65, (bx, 0.0, 0.325), vertices=24, material=iron_mat, parent=buffer_root)
        add_cylinder(f"BufferRing_{bi}", 0.16, 0.08, (bx, 0.0, 0.66), vertices=24, material=amber_mat, parent=buffer_root)
        pist = add_cylinder(f"BufferPiston_{bi}", 0.085, 0.68, (bx, 0.0, 0.90), vertices=20, material=rail_steel, parent=buffer_root)
        add_box(f"BufferPad_{bi}", (0.26, 0.26, 0.08), (bx, 0.0, 0.36), material=amber_mat, parent=pist)
        buffer_pistons.append(pist)
    buffer_anchor = add_empty("Anchor_PitBuffer", (0.42, -0.25, 0.95), parent=buffer_root)

    # ------------------------------------------------------------------
    # Modern Glass Cabin + Physically Coupled Electric Motor
    # ------------------------------------------------------------------
    cabin_root = add_empty("ModernCabin_Root", (0, 0, 0), parent=platform_root)
    for cx in (-0.64, 0.64):
        for cy in (-0.50, 0.50):
            add_box(f"CabinPost_{cx:.2f}_{cy:.2f}", (0.055, 0.055, 1.76), (cx, cy, 0.90), material=rail_steel, bevel=0.008, parent=cabin_root)
    add_box("Cabin_Roof", (1.36, 1.12, 0.08), (0, 0, 1.74), material=steel_mat, bevel=0.01, parent=cabin_root)
    add_box("Cabin_CeilingLight", (0.96, 0.72, 0.03), (0, 0, 1.69), material=cyan_glow, parent=cabin_root)
    add_box("Cabin_BackGlass", (1.24, 0.025, 1.64), (0, 0.48, 0.86), material=glass_mat, parent=cabin_root)
    add_box("Cabin_FrontGlass", (1.24, 0.02, 1.64), (0, -0.48, 0.86), material=glass_mat, parent=cabin_root)
    add_box("Cabin_LeftGlass", (0.025, 0.96, 1.64), (-0.62, 0, 0.86), material=glass_mat, parent=cabin_root)
    add_box("Cabin_RightGlass", (0.025, 0.96, 1.64), (0.62, 0, 0.86), material=glass_mat, parent=cabin_root)
    add_box("Cabin_ButtonPanel", (0.12, 0.05, 0.55), (0.48, -0.39, 1.00), material=iron_mat, bevel=0.01, parent=cabin_root)
    add_box("Cabin_FloorScreen", (0.09, 0.025, 0.12), (0.48, -0.41, 1.20), material=green_glow, bevel=0.005, parent=cabin_root)
    for bi in range(4):
        add_box(f"Cabin_Btn_{bi}", (0.035, 0.02, 0.035), (0.48, -0.41, 0.80 + bi * 0.08), material=cyan_glow, parent=cabin_root)
    panel_anchor = add_empty("Anchor_Panel", (0.48, -0.45, 1.18), parent=cabin_root)

    motor_root = add_empty("ElectricMotor_Root", (0.0, 0.0, TOP_DECK_Z + 0.32))
    add_box("Motor_Base", (1.45, 0.85, 0.16), (0.15, 0, 0.06), material=iron_mat, bevel=0.015, parent=motor_root)
    add_cylinder("Motor_Body", 0.34, 0.90, (-0.18, 0, 0.45), rotation_deg=(0, 90, 0), vertices=28, material=steel_mat, bevel=0.02, parent=motor_root)
    add_cylinder("Motor_GlowRing", 0.36, 0.08, (-0.02, 0, 0.45), rotation_deg=(0, 90, 0), vertices=28, material=cyan_glow, parent=motor_root)
    motor_rotor = add_cylinder("Motor_DriveWheel", 0.22, 0.16, (0.52, 0.0, 0.45), rotation_deg=(90, 0, 0), vertices=24, material=amber_mat, parent=motor_root)
    belt_drop = (TOP_DECK_Z + 0.32 + 0.45) - PULLEY_Z
    add_box("DriveBelt_Left", (0.04, 0.12, belt_drop), (0.34, 0, 0.45 - belt_drop * 0.5), material=belt_mat, parent=motor_root)
    add_box("DriveBelt_Right", (0.04, 0.12, belt_drop), (0.70, 0, 0.45 - belt_drop * 0.5), material=belt_mat, parent=motor_root)
    motor_anchor = add_empty("Anchor_ElectricMotor", (-0.18, -0.40, 0.45), parent=motor_root)

    # ------------------------------------------------------------------
    # Dynamic Quaternion Steel Cables
    # ------------------------------------------------------------------
    def make_cable(name: str, radius: float = 0.028) -> bpy.types.Object:
        cyl = add_cylinder(name, radius, 1.0, (0, 0, 0), vertices=12, material=cable_mat)
        cyl.rotation_mode = "QUATERNION"
        return cyl

    def key_cable_span(cable: bpy.types.Object, frame: int, p0: Vector, p1: Vector) -> None:
        vec = p1 - p0
        length = max(0.05, vec.length)
        mid = (p0 + p1) * 0.5
        quat = vec.normalized().to_track_quat("Z", "Y")
        cable.location = (mid.x, mid.y, mid.z)
        cable.scale = (1.0, 1.0, length)
        cable.rotation_quaternion = quat
        cable.keyframe_insert(data_path="location", frame=frame)
        cable.keyframe_insert(data_path="scale", frame=frame)
        cable.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    cable_main = make_cable("Cable_Main")
    cable_top = make_cable("Cable_TopBridge")
    cable_cw = make_cable("Cable_Counterweight")
    cable_pull = make_cable("Cable_ManualPull")
    cable_snap_upper = make_cable("Cable_SnapUpper")
    aux_cables = [make_cable(f"Cable_Aux_{i}", radius=0.020) for i in range(3)]
    dual_rope_anchor = add_empty("Anchor_DualRopes", (0.12, -0.18, 13.8))

    for f in (1, total_frames):
        key_cable_span(
            cable_top,
            f,
            Vector((MAIN_PULLEY_X, 0.0, PULLEY_Z + MAIN_PULLEY_R)),
            Vector((CW_PULLEY_X, 0.0, PULLEY_Z + CW_PULLEY_R)),
        )

    # ------------------------------------------------------------------
    # Mannequin & Bags
    # ------------------------------------------------------------------
    man = MannequinRig("HeroMannequin", scale_factor=0.72)

    bag_roots: list[bpy.types.Object] = []
    for side in ("L", "R"):
        broot = add_empty(f"BagRoot_{side}", (0, 0, 0))
        attach_follow_location(broot, man.hands[side])
        add_box(f"BagBody_{side}", (0.18, 0.13, 0.24), (0.0, 0.0, -0.17), material=bag_kraft, bevel=0.02, parent=broot)
        add_box(f"BagTop_{side}", (0.15, 0.10, 0.05), (0.0, 0.0, -0.04), material=bag_veggie, bevel=0.008, parent=broot)
        add_cylinder(f"BagHandle_{side}", 0.03, 0.04, (0.0, 0.0, -0.01), rotation_deg=(90, 0, 0), material=bag_kraft, parent=broot)
        bag_roots.append(broot)

    cabin_bags = add_empty("Bags_CabinFloor", (-0.34, -0.15, 0.19), parent=platform_root)
    add_box("CabinBag_1", (0.18, 0.13, 0.24), (0, 0, 0), material=bag_kraft, bevel=0.02, parent=cabin_bags)
    add_box("CabinBag_2", (0.17, 0.13, 0.22), (0.22, 0.08, -0.01), material=bag_kraft, bevel=0.02, parent=cabin_bags)
    add_box("CabinBagTop_1", (0.14, 0.09, 0.05), (0, 0, 0.13), material=bag_veggie, bevel=0.008, parent=cabin_bags)

    def key_bags_hand(frame: int, visible: bool) -> None:
        for broot in bag_roots:
            set_visibility(broot, frame, visible)

    def hide_all_retrofits(frame: int) -> None:
        for obj in (
            platform_root, main_pulley, cw_pulley, hanger_root, rope_coil_root,
            rails_root, rollers_root, cw_tracks_root, cw_root, cabin_root,
            penthouse_root, motor_root, cabin_bags, buffer_root,
            cable_main, cable_top, cable_cw, cable_pull, cable_snap_upper,
            *aux_cables,
        ):
            set_visibility(obj, frame, False)

    cam = CameraRig(lens=28.0)
    cam_state: dict[str, Any] = {}

    def cam_set(frame: int, pos: tuple[float, float, float], tgt: tuple[float, float, float], lens: float) -> None:
        cam.key(frame, pos, tgt, lens=lens)
        cam_state["pos"], cam_state["tgt"], cam_state["lens"] = pos, tgt, lens

    def cam_cut(frame: int, pos: tuple[float, float, float], tgt: tuple[float, float, float], lens: float) -> None:
        if frame > 1 and "pos" in cam_state:
            cam.key(frame - 1, cam_state["pos"], cam_state["tgt"], lens=cam_state["lens"])
        cam_set(frame, pos, tgt, lens)

    hud = HUDTracker()

    # ==================================================================
    # BEAT 0: Immediate Crisis/Climax Shock Hook (0.0 -> 1.5s Snap + Lock!)
    # ==================================================================
    b0 = beats["shock_hook"]
    f0s, f0e = b0["frame_start"], b0["frame_end"]
    f0_snap = f0s + max(2, round(0.80 * fps))
    f0_lock = f0_snap + max(3, round(0.38 * fps))
    f0_cut1 = f0s + max(2, round(0.65 * fps))
    f0_cut2 = f0s + max(4, round(2.25 * fps))

    hide_all_retrofits(1)
    key_bags_hand(1, False)
    for obj in (
        platform_root, main_pulley, cw_pulley, hanger_root, rails_root, rollers_root,
        cw_tracks_root, cw_root, cable_main, cable_top, cable_cw, cable_snap_upper,
    ):
        set_visibility(obj, 1, True)
    # Keep glass cabin & floor bags hidden (children of platform_root) so naked brake mechanism stays clear
    for child in (cabin_root, cabin_bags):
        set_visibility(child, 1, False)

    key_brake_state(1, False)
    key_brake_state(f0_snap - 1, False)
    key_brake_state(f0_lock, True)
    key_brake_state(f0e, True)

    for f in _sample_frames(1, f0e, step=1):
        if f < f0_snap:
            pz = 12.10
        elif f <= f0_lock:
            drop_t = (f - f0_snap) / max(1, (f0_lock - f0_snap))
            pz = 12.10 - 0.65 * (drop_t ** 1.6)
        else:
            pz = 11.45
        set_keyframe(platform_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, 0, 0))
        set_keyframe(cw_root, f, location=(CW_LANE_X, 0.0, 3.2), rotation_deg=(0, 0, 0))
        set_keyframe(man.root, f, location=(0.0, 0.0, pz + 0.07), rotation_deg=(0, 0, -10))

        shackle_pt = Vector((0.0, 0.0, pz + YOKE_Z + (0.28 if f < f0_snap else 0.18)))
        if f < f0_snap:
            key_cable_span(cable_main, f, shackle_pt, Vector((0.0, 0.0, PULLEY_Z)))
            key_cable_span(cable_snap_upper, f, shackle_pt, Vector((0.0, 0.0, PULLEY_Z)))
        else:
            recoil = min(2.2, ((f - f0_snap) / max(1, fps)) * 5.8)
            key_cable_span(cable_main, f, shackle_pt, Vector((-0.24, -0.06, pz + YOKE_Z + 0.38)))
            key_cable_span(cable_snap_upper, f, Vector((0.08, 0.0, 14.05 + recoil * 0.55)), Vector((0.0, 0.0, PULLEY_Z)))
        key_cable_span(cable_cw, f, Vector((CW_LANE_X, 0.0, 3.2 + 1.30)), Vector((CW_LANE_X, 0.0, PULLEY_Z)))

    man.animate_panic(1, min(f0e, f0_lock + max(2, round(0.30 * fps))), fps=fps)
    man.key_pose(f0e, torso_rot=(4, 0, 0), head_rot=(-14, 0, 0), sh_l=(-25, 16, 0), el_l=(-55, 0, 0), sh_r=(-25, -16, 0), el_r=(-55, 0, 0))

    cam_set(1, (0.0, -4.4, 13.7), (0.0, 0.0, 13.7), 44.0)
    cam_cut(f0_cut1, (0.5, -5.6, 13.2), (0.0, 0.0, 13.1), 38.0)
    cam_cut(f0_cut2, (-0.85, -4.0, 12.6), (-0.42, 0.0, 13.1), 44.0)

    hud.add("b0_snap", brake_anchor, "alert", f0_snap, f0_cut2, label="HALAT KOPTU!", color="red", offset_px=(145, -75))
    hud.add("b0_spring", brake_anchor, "callout", f0_lock, f0e, label="OTIS EMNİYET YAYI", color="amber", offset_px=(-155, -80))

    # ==================================================================
    # BEAT 1: Hard Cut Back to Floor 1 + Full 10F Building Reveal
    # ==================================================================
    b1 = beats["hook_building"]
    f1s, f1e = b1["frame_start"], b1["frame_end"]
    f1_pull = f1s + int((f1e - f1s) * 0.44)

    hide_all_retrofits(f1s)
    key_bags_hand(f1s, True)

    cam_cut(f1s, (-1.8, -8.2, 1.5), (-2.6, 0.0, 1.25), 36.0)
    cam_set(f1_pull - 1, (-1.6, -10.4, 2.2), (-2.4, 0.0, 2.0), 34.0)
    cam_cut(f1_pull, (1.2, -22.2, 8.5), (-0.8, 0.0, 8.2), 26.0)
    cam_set(f1e, (1.4, -22.6, 8.6), (-0.8, 0.0, 8.3), 26.0)

    set_keyframe(man.root, f1s - 1, location=(-3.6, -0.35, 0.0), rotation_deg=(0, 0, -18))
    set_keyframe(man.root, f1s, location=(-3.6, -0.35, 0.0), rotation_deg=(0, 0, -18))
    set_keyframe(man.root, f1e, location=(-3.6, -0.35, 0.0), rotation_deg=(0, 0, -10))
    man.key_pose(f1s, torso_rot=(-4, 0, 0), head_rot=(-24, 0, 0), sh_l=(-6, 12, 0), el_l=(-16, 0, 0), sh_r=(-6, -12, 0), el_r=(-16, 0, 0))
    man.key_pose(f1e, torso_rot=(-2, 0, 0), head_rot=(-32, 0, 0), sh_l=(-8, 12, 0), el_l=(-18, 0, 0), sh_r=(-8, -12, 0), el_r=(-18, 0, 0))

    hud.add("b1_bags", man.hands["R"], "badge", f1s + max(1, round(0.12 * fps)), f1_pull - 1, label="1. KAT // 18 KG YÜK", color="amber", offset_px=(145, -25), extra={"leader": True})
    hud.add("b1_10f", floor10_anchor, "callout", f1_pull, f1e, label="10. KAT // HEDEF", color="cyan", offset_px=(150, -35))
    hud.add("b1_5f", floor5_anchor, "badge", f1_pull + 2, f1e, label="5. KAT", color="cyan", offset_px=(-95, 0))
    hud.add("b1_1f", floor1_anchor, "badge", f1_pull + 2, f1e, label="1. KAT", color="cyan", offset_px=(-95, 0))

    # ==================================================================
    # BEAT 2: Climbing Connected Stair Flights (Floors 1 -> 3)
    # ==================================================================
    b2 = beats["stairs_pain"]
    f2s, f2e = b2["frame_start"], b2["frame_end"]
    f2_turn = f2s + int((f2e - f2s) * 0.34)
    f2_stop = f2s + int((f2e - f2s) * 0.65)
    f2_t1 = f2s + int((f2e - f2s) * 0.32)
    f2_t2 = f2s + int((f2e - f2s) * 0.63)

    set_keyframe(man.root, f2s - 1, location=(-3.6, -0.35, 0.0), rotation_deg=(0, 0, -10))
    set_keyframe(man.root, f2s, location=(-3.54, -0.18, 0.05), rotation_deg=(0, 0, 90))
    set_keyframe(man.root, f2_turn, location=(-2.12, -0.18, 1.66), rotation_deg=(0, 0, 90))
    set_keyframe(man.root, f2_turn + 2, location=(-2.12, 0.34, 1.66), rotation_deg=(0, 0, -90))
    set_keyframe(man.root, f2_stop, location=(-3.72, 0.34, 3.26), rotation_deg=(0, 0, -90))
    set_keyframe(man.root, f2e, location=(-3.72, 0.34, 3.26), rotation_deg=(0, 0, -65))

    man.animate_climb_cycle(f2s, f2_stop - 2, fatigue=0.95, fps=fps)
    man.animate_exhausted(f2_stop + 2)
    man.animate_exhausted(f2e)

    cam_cut(f2s, (-3.0, -5.8, 1.8), (-3.0, 0.0, 1.1), 40.0)
    cam_cut(f2_turn, (-2.6, -5.9, 2.9), (-2.6, 0.0, 2.3), 40.0)
    cam_cut(f2_stop, (-3.0, -4.9, 4.1), (-3.4, 0.25, 3.85), 45.0)
    cam_set(f2e, (-3.0, -4.7, 4.1), (-3.45, 0.25, 3.9), 46.0)

    hud.add("b2_f1", man.alert_anchor, "badge", f2s, f2_t1, label="1 / 10 KAT", color="cyan", offset_px=(145, -55))
    hud.add("b2_f2", man.alert_anchor, "badge", f2_t1 + 1, f2_t2, label="2 / 10 KAT", color="amber", offset_px=(145, -55))
    hud.add("b2_f3", man.alert_anchor, "badge", f2_t2 + 1, f2e, label="3 / 10 KAT", color="red", offset_px=(145, -55))
    hud.add("b2_alert", man.alert_anchor, "alert", f2_stop, f2e, label="NEFES TÜKENDİ!", color="red", offset_px=(115, 25))

    # ==================================================================
    # BEAT 3: Top Pulley Macro -> Wide Manual Rope Fail
    # ==================================================================
    b3 = beats["pulley_fail"]
    f3s, f3e = b3["frame_start"], b3["frame_end"]
    f3_cut = f3s + int((f3e - f3s) * 0.42)
    f3_mid = f3s + int((f3e - f3s) * 0.56)

    key_bags_hand(f3s, False)
    key_brake_state(f3s, False)
    for obj in (platform_root, main_pulley, cw_pulley, hanger_root, rope_coil_root, cable_main, cable_top, cable_pull):
        set_visibility(obj, f3s, True)
    for child in (rollers_root, cabin_root, cabin_bags):
        set_visibility(child, f3s, False)

    set_keyframe(man.root, f3s - 1, location=(-3.55, 0.34, 3.26), rotation_deg=(0, 0, -65))
    set_keyframe(man.root, f3s, location=(2.18, 0.0, 0.0), rotation_deg=(0, 0, 90))
    set_keyframe(man.root, f3e, location=(2.18, 0.0, 0.0), rotation_deg=(0, 0, 90))
    man.animate_pull_rope_cycle(f3s, f3e, fps=fps)

    set_keyframe(platform_root, f3s, location=(0.0, 0.0, 0.35), rotation_deg=(0, 0, 0))
    set_keyframe(platform_root, f3_mid, location=(0.0, 0.0, 3.10), rotation_deg=(0, 2.0, 0))
    set_keyframe(platform_root, f3e, location=(0.0, 0.0, 2.10), rotation_deg=(0, -3.0, 0))

    set_keyframe(main_pulley, f3s, rotation_deg=(0, 0, 0))
    set_keyframe(main_pulley, f3_mid, rotation_deg=(0, -180, 0))
    set_keyframe(main_pulley, f3e, rotation_deg=(0, -110, 0))
    set_keyframe(cw_pulley, f3s, rotation_deg=(0, 0, 0))
    set_keyframe(cw_pulley, f3_mid, rotation_deg=(0, -210, 0))
    set_keyframe(cw_pulley, f3e, rotation_deg=(0, -130, 0))

    for f in _sample_frames(f3s, f3e, step=kf_step):
        if f <= f3_mid:
            t = (f - f3s) / max(1, (f3_mid - f3s))
            pz = 0.35 + (3.10 - 0.35) * t
        else:
            t = (f - f3_mid) / max(1, (f3e - f3_mid))
            pz = 3.10 + (2.10 - 3.10) * t
        key_cable_span(cable_main, f, Vector((0.0, 0.0, pz + YOKE_Z + 0.12)), Vector((0.0, 0.0, PULLEY_Z)))
        key_cable_span(cable_pull, f, Vector((CW_LANE_X, 0.0, 0.08)), Vector((CW_LANE_X, 0.0, PULLEY_Z)))

    # Cut 1: Close-up on overhead brass pulley wheel -> Cut 2: Wide full-shaft effort
    cam_cut(f3s, (0.7, -5.8, 14.9), (0.65, 0.0, 14.85), 42.0)
    cam_cut(f3_cut, (1.1, -17.6, 8.1), (0.6, 0.0, 7.9), 29.0)
    cam_set(f3e, (1.1, -16.8, 7.9), (0.7, 0.0, 7.8), 29.0)

    hud.add("b3_pulley", top_pulley_anchor, "callout", f3s + 2, f3e, label="TEPE MAKARASI", color="cyan", offset_px=(-165, -20))
    hud.add("b3_load", platform_anchor, "arrow", f3_cut + 2, f3e, label="80 KG AĞIRLIK", color="amber", offset_px=(0, 95))
    hud.add("b3_alert", man.alert_anchor, "alert", f3_mid, f3e, label="AŞIRI YÜK!", color="red", offset_px=(75, -95))

    # ==================================================================
    # BEAT 4: Counterweight Balance (Wide -> Mid-Shaft Passing Close-up)
    # ==================================================================
    b4 = beats["counterweight"]
    f4s, f4e = b4["frame_start"], b4["frame_end"]
    f4_cut = f4s + int((f4e - f4s) * 0.48)

    set_visibility(cable_pull, f4s, False)
    set_visibility(rope_coil_root, f4s, False)
    set_visibility(cw_tracks_root, f4s, True)
    set_visibility(cw_root, f4s, True)
    set_visibility(cable_cw, f4s, True)

    set_keyframe(man.root, f4s - 1, location=(2.18, 0.0, 0.0), rotation_deg=(0, 0, 90))
    for f in _sample_frames(f4s, f4e, step=kf_step):
        frac = (f - f4s) / max(1, (f4e - f4s))
        smooth = 0.5 - 0.5 * math.cos(math.pi * frac)
        pz = 1.8 + 8.6 * smooth
        cwz = 11.4 - 8.6 * smooth
        set_keyframe(platform_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, 0, 0))
        set_keyframe(cw_root, f, location=(CW_LANE_X, 0.0, cwz), rotation_deg=(0, 0, 0))
        set_keyframe(man.root, f, location=(0.0, 0.0, pz + 0.07), rotation_deg=(0, 0, -14))
        key_cable_span(cable_main, f, Vector((0.0, 0.0, pz + YOKE_Z + 0.12)), Vector((0.0, 0.0, PULLEY_Z)))
        key_cable_span(cable_cw, f, Vector((CW_LANE_X, 0.0, cwz + 1.30)), Vector((CW_LANE_X, 0.0, PULLEY_Z)))

    man.key_pose(f4s, head_rot=(-6, 0, 0), sh_l=(-10, 14, 0), el_l=(-25, 0, 0), sh_r=(-10, -14, 0), el_r=(-25, 0, 0))
    man.key_pose(f4e, head_rot=(2, 0, -8), sh_l=(-18, 16, 0), el_l=(-35, 0, 0), sh_r=(-70, -20, 0), el_r=(-45, 0, 0))

    set_keyframe(main_pulley, f4s, rotation_deg=(0, -110, 0))
    set_keyframe(main_pulley, f4e, rotation_deg=(0, -680, 0))
    set_keyframe(cw_pulley, f4s, rotation_deg=(0, -130, 0))
    set_keyframe(cw_pulley, f4e, rotation_deg=(0, -820, 0))

    cam_cut(f4s, (1.6, -19.8, 8.2), (1.1, 0.0, 8.2), 29.0)
    cam_cut(f4_cut, (1.4, -10.6, 8.0), (1.1, 0.0, 7.9), 34.0)
    cam_set(f4e, (1.5, -10.0, 9.2), (1.1, 0.0, 8.9), 34.0)

    hud.add("b4_cw", cw_anchor, "callout", f4s + max(2, round(0.2 * fps)), f4e, label="KARŞI AĞIRLIK: 80 KG", color="amber", offset_px=(145, -55))
    hud.add("b4_up", platform_up_anchor, "arrow", f4s + max(3, round(0.35 * fps)), f4e, label="YUKARI", color="green", offset_px=(0, -95), extra={"oscillate": True})
    hud.add("b4_badge", cw_anchor, "badge", f4_cut, f4e, label="DENGELİ GÜÇ", color="green", offset_px=(145, 65))

    # ==================================================================
    # BEAT 5: Sway Instability -> Tight Rail & Roller Lock Macro
    # ==================================================================
    b5 = beats["guide_rails"]
    f5s, f5e = b5["frame_start"], b5["frame_end"]
    f5_fix = f5s + int((f5e - f5s) * 0.50)

    set_visibility(rails_root, f5_fix, True)
    set_visibility(rollers_root, f5_fix, True)

    for f in _sample_frames(f5s, f5e, step=kf_step):
        frac = (f - f5s) / max(1, (f5e - f5s))
        pz = 8.4 + 1.4 * math.sin(frac * math.pi)
        cwz = 5.4 - 1.4 * math.sin(frac * math.pi)
        if f < f5_fix:
            t_sec = (f - f5s) / max(1, fps)
            sway_ang = 8.5 * math.sin(t_sec * 11.04)
            sway_x = 0.20 * math.sin(t_sec * 11.04)
        else:
            t_fix = (f - f5_fix) / max(1, fps)
            damp = max(0.0, 1.0 - t_fix / 0.34)
            sway_ang = 4.0 * damp * math.sin(t_fix * 13.2)
            sway_x = 0.06 * damp * math.sin(t_fix * 13.2)

        rad = math.radians(sway_ang)
        shackle_world = Vector((sway_x + (YOKE_Z + 0.12) * math.sin(rad), 0.0, pz + (YOKE_Z + 0.12) * math.cos(rad)))

        set_keyframe(platform_root, f, location=(sway_x, 0.0, pz), rotation_deg=(0, sway_ang, 0))
        set_keyframe(cw_root, f, location=(CW_LANE_X, 0.0, cwz), rotation_deg=(0, 0, 0))
        set_keyframe(man.root, f, location=(sway_x, 0.0, pz + 0.07), rotation_deg=(0, sway_ang, -10))
        key_cable_span(cable_main, f, shackle_world, Vector((0.0, 0.0, PULLEY_Z)))
        key_cable_span(cable_cw, f, Vector((CW_LANE_X, 0.0, cwz + 1.30)), Vector((CW_LANE_X, 0.0, PULLEY_Z)))

    man.animate_panic(f5s, f5_fix - 1, fps=fps)
    man.key_pose(f5_fix + max(2, round(0.16 * fps)), torso_rot=(0, 0, 0), head_rot=(0, 0, 0), sh_l=(-8, 14, 0), sh_r=(-8, -14, 0))
    man.key_pose(f5e, torso_rot=(0, 0, 0), head_rot=(0, 0, 0), sh_l=(-8, 14, 0), sh_r=(-8, -14, 0))

    cam_cut(f5s, (0.0, -9.6, 9.6), (0.0, 0.0, 9.6), 36.0)
    cam_cut(f5_fix, (1.1, -5.1, 11.2), (0.65, 0.0, 11.1), 43.0)
    cam_set(f5e, (0.6, -6.2, 10.2), (0.2, 0.0, 10.1), 39.0)

    hud.add("b5_sway", man.alert_anchor, "alert", f5s + 2, f5_fix - 1, label="YALPALAMA RİSKİ!", color="red", offset_px=(135, -45))
    hud.add("b5_rails", rail_anchor, "callout", f5_fix, f5e, label="ÇELİK KILAVUZ RAY", color="cyan", offset_px=(-155, -50))
    hud.add("b5_roller", roller_anchor, "callout", f5_fix, f5e, label="DENGE TEKERLEĞİ", color="green", offset_px=(145, -35))

    # ==================================================================
    # BEAT 6: Otis Spring & Wedge Lock Full Payoff Breakdown
    # ==================================================================
    b6 = beats["safety_brake"]
    f6s, f6e = b6["frame_start"], b6["frame_end"]
    f6_snap = f6s + int((f6e - f6s) * 0.28)
    f6_lock = f6_snap + max(3, round(0.38 * fps))
    f6_cut = f6_lock + max(2, round(0.45 * fps))

    set_visibility(cable_snap_upper, f6_snap, True)
    key_brake_state(f6s, False)
    key_brake_state(f6_snap - 1, False)
    key_brake_state(f6_lock, True)
    key_brake_state(f6e, True)

    for f in _sample_frames(f6s, f6e, step=1):
        if f < f6_snap:
            pz = 8.40
        elif f <= f6_lock:
            drop_t = (f - f6_snap) / max(1, (f6_lock - f6_snap))
            pz = 8.40 - 0.65 * (drop_t ** 1.6)
        else:
            pz = 7.75
        set_keyframe(platform_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, 0, 0))
        set_keyframe(cw_root, f, location=(CW_LANE_X, 0.0, 5.4), rotation_deg=(0, 0, 0))
        set_keyframe(man.root, f, location=(0.0, 0.0, pz + 0.07), rotation_deg=(0, 0, -10))

        shackle_pt = Vector((0.0, 0.0, pz + YOKE_Z + (0.28 if f < f6_snap else 0.18)))
        if f < f6_snap:
            key_cable_span(cable_main, f, shackle_pt, Vector((0.0, 0.0, PULLEY_Z)))
            key_cable_span(cable_snap_upper, f, shackle_pt, Vector((0.0, 0.0, PULLEY_Z)))
        else:
            recoil = min(2.4, ((f - f6_snap) / max(1, fps)) * 6.0)
            key_cable_span(cable_main, f, shackle_pt, Vector((-0.24, -0.06, pz + YOKE_Z + 0.38)))
            key_cable_span(cable_snap_upper, f, Vector((0.05, 0.0, 11.2 + recoil * 0.8)), Vector((0.0, 0.0, PULLEY_Z)))
        key_cable_span(cable_cw, f, Vector((CW_LANE_X, 0.0, 5.4 + 1.30)), Vector((CW_LANE_X, 0.0, PULLEY_Z)))

    man.key_pose(f6s, torso_rot=(0, 0, 0), head_rot=(-4, 0, 0))
    man.animate_panic(f6_snap, min(f6e, f6_lock + max(2, round(0.25 * fps))), fps=fps)
    man.key_pose(f6e, torso_rot=(4, 0, 0), head_rot=(-12, 0, 0), sh_l=(-25, 16, 0), el_l=(-55, 0, 0), sh_r=(-25, -16, 0), el_r=(-55, 0, 0))

    cam_cut(f6s, (0.0, -6.4, 9.7), (0.0, 0.0, 9.7), 41.0)
    cam_cut(f6_lock, (1.0, -5.0, 9.3), (-0.2, 0.0, 9.4), 43.0)
    cam_cut(f6_cut, (0.0, -7.2, 9.1), (0.0, 0.0, 9.0), 36.0)

    hud.add("b6_snap", man.alert_anchor, "alert", f6_snap, f6_lock + 4, label="HALAT KOPTU!", color="red", offset_px=(130, -55))
    hud.add("b6_brake", brake_anchor, "callout", f6_snap + 2, f6e, label="YAYLI EMNİYET FRENİ", color="amber", offset_px=(-160, -75))
    hud.add("b6_lock", brake_anchor, "badge", f6_lock + 1, f6e, label="RAYLARA KİLİTLENDİ", color="green", offset_px=(180, -105), extra={"leader": True})

    # ==================================================================
    # OPTIONAL TIKTOK DEPTH BEAT: 4x Redundant Steel Ropes + Pit Hydraulic Buffer
    # ==================================================================
    if "dual_safety_pit" in beats:
        bd = beats["dual_safety_pit"]
        fds, fde = bd["frame_start"], bd["frame_end"]
        fd_c1 = fds + int((fde - fds) * 0.22)
        fd_c2 = fds + int((fde - fds) * 0.44)
        fd_c3 = fds + int((fde - fds) * 0.75)

        set_visibility(cable_snap_upper, fds, False)
        set_visibility(buffer_root, fds, True)
        for ac in aux_cables:
            set_visibility(ac, fds, True)
        key_brake_state(fds, False)

        for f in _sample_frames(fds, fde, step=kf_step):
            frac = (f - fds) / max(1, (fde - fds))
            if frac < 0.44:
                pz = 7.8 - 6.1 * (frac / 0.44)
                comp = 0.0
            else:
                local_t = (frac - 0.44) / 0.56
                comp = 0.36 * math.sin(local_t * math.pi)
                pz = 1.70 - comp * 1.15
            cwz = 11.2 - pz * 0.72
            set_keyframe(platform_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, 0, 0))
            set_keyframe(cw_root, f, location=(CW_LANE_X, 0.0, cwz), rotation_deg=(0, 0, 0))
            set_keyframe(man.root, f, location=(0.0, 0.0, pz + 0.07), rotation_deg=(0, 0, -10))
            for bi, pist in enumerate(buffer_pistons):
                bx = -0.42 if bi == 0 else 0.42
                set_keyframe(pist, f, location=(bx, 0.0, 0.90 - comp))

            shackle_z = pz + YOKE_Z + 0.16
            key_cable_span(cable_main, f, Vector((0.0, 0.0, shackle_z)), Vector((0.0, 0.0, PULLEY_Z)))
            for ai, (ax_off, ac) in enumerate(zip((-0.14, 0.14, 0.26), aux_cables)):
                key_cable_span(ac, f, Vector((ax_off, 0.05 if ai != 1 else -0.05, shackle_z)), Vector((ax_off, 0.05 if ai != 1 else -0.05, PULLEY_Z)))
            key_cable_span(cable_cw, f, Vector((CW_LANE_X, 0.0, cwz + 1.30)), Vector((CW_LANE_X, 0.0, PULLEY_Z)))

        man.key_pose(fds, torso_rot=(0, 0, 0), head_rot=(-6, 0, 0), sh_l=(-8, 12, 0), sh_r=(-8, -12, 0))
        man.key_pose(fde, torso_rot=(0, 0, 0), head_rot=(-4, 0, 0), sh_l=(-8, 12, 0), sh_r=(-8, -12, 0))

        # 4 sharp camera cuts (~every 2.7s) across ~11s TikTok beat
        cam_cut(fds, (0.8, -14.8, 11.2), (0.3, 0.0, 11.0), 32.0)
        cam_cut(fd_c1, (0.4, -5.0, 14.2), (0.15, 0.0, 13.8), 42.0)
        cam_cut(fd_c2, (0.9, -4.9, 1.4), (0.0, 0.0, 1.0), 42.0)
        cam_cut(fd_c3, (1.2, -11.2, 5.2), (0.2, 0.0, 4.8), 33.0)

        hud.add("bd_ropes", dual_rope_anchor, "callout", fds + 2, fd_c2 - 1, label="4x YEDEK ÇELİK HALAT", color="cyan", offset_px=(140, -90))
        hud.add("bd_pit", buffer_anchor, "callout", fd_c2, fd_c3 - 1, label="HİDROLİK KUYU TAMPONU", color="amber", offset_px=(135, -100))
        hud.add("bd_safe", buffer_anchor, "badge", fd_c3, fde, label="12x GÜVENLİK FAKTÖRÜ", color="green", offset_px=(215, -75))

    # ==================================================================
    # FINAL BEAT: Penthouse Electric Motor -> Smooth Glass Cabin 10th Floor!
    # ==================================================================
    b7 = beats["modern_payoff"]
    f7s, f7e = b7["frame_start"], b7["frame_end"]
    f7_cut = f7s + int((f7e - f7s) * 0.42)

    set_visibility(cable_snap_upper, f7s, False)
    set_visibility(penthouse_root, f7s, True)
    set_visibility(cabin_root, f7s, True)
    set_visibility(motor_root, f7s, True)
    set_visibility(cabin_bags, f7s, True)
    key_brake_state(f7s, False)

    for f in _sample_frames(f7s, f7e, step=kf_step):
        frac = (f - f7s) / max(1, (f7e - f7s))
        smooth = 0.5 - 0.5 * math.cos(math.pi * frac)
        pz = 9.0 + 3.8 * smooth
        cwz = 6.2 - 3.8 * smooth
        set_keyframe(platform_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, 0, 0))
        set_keyframe(cw_root, f, location=(CW_LANE_X, 0.0, cwz), rotation_deg=(0, 0, 0))
        set_keyframe(man.root, f, location=(0.12, 0.0, pz + 0.07), rotation_deg=(0, 0, -14))
        key_cable_span(cable_main, f, Vector((0.0, 0.0, pz + YOKE_Z + 0.16)), Vector((0.0, 0.0, PULLEY_Z)))
        if "dual_safety_pit" in beats:
            for ai, (ax_off, ac) in enumerate(zip((-0.14, 0.14, 0.26), aux_cables)):
                key_cable_span(ac, f, Vector((ax_off, 0.05 if ai != 1 else -0.05, pz + YOKE_Z + 0.16)), Vector((ax_off, 0.05 if ai != 1 else -0.05, PULLEY_Z)))
        key_cable_span(cable_cw, f, Vector((CW_LANE_X, 0.0, cwz + 1.30)), Vector((CW_LANE_X, 0.0, PULLEY_Z)))

    man.animate_relaxed_celebrate(f7s, f7e, fps=fps)
    set_keyframe(main_pulley, f7s, rotation_deg=(0, -680, 0))
    set_keyframe(main_pulley, f7e, rotation_deg=(0, -1360, 0))
    set_keyframe(cw_pulley, f7s, rotation_deg=(0, -820, 0))
    set_keyframe(cw_pulley, f7e, rotation_deg=(0, -1640, 0))
    set_keyframe(motor_rotor, f7s, rotation_deg=(0, 0, 0))
    set_keyframe(motor_rotor, f7e, rotation_deg=(0, -1440, 0))

    # Cut 1: Overhead Machine Penthouse Electric Motor close-up -> Cut 2: Gleaming Glass Cabin Arrival!
    cam_cut(f7s, (0.2, -6.2, 16.5), (0.2, 0.0, 16.4), 40.0)
    cam_cut(f7_cut, (1.5, -13.4, 13.0), (0.3, 0.0, 13.2), 32.0)
    cam_set(f7e, (1.6, -13.6, 13.6), (0.3, 0.0, 13.8), 32.0)

    hud.add("b7_motor", motor_anchor, "callout", f7s + 2, f7_cut + int(0.6 * fps), label="ELEKTRİK MOTORU", color="cyan", offset_px=(-175, -35))
    hud.add("b7_panel", panel_anchor, "callout", f7_cut, f7e, label="CAM KABİN & KAT PANELİ", color="green", offset_px=(165, -20))
    hud.add("b7_floor", panel_anchor, "badge", f7_cut + max(2, round(0.25 * fps)), f7e, label="10. KAT // ULAŞILDI", color="green", offset_px=(165, 70))
    hud.add("b7_music", man.alert_anchor, "note", f7s + int((f7e - f7s) * 0.55), f7e, label="ASANSÖR MÜZİĞİ", color="cyan", offset_px=(-235, -15))

    hero_frame = f7s + int((f7e - f7s) * 0.68)
    return {
        "scene": scene,
        "camera": cam.cam,
        "hud_tracker": hud,
        "hero_frame": hero_frame,
    }
