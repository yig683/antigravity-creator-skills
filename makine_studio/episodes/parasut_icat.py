"""Episode #02: 'Paraşütü Nasıl İcat Edersin?' — Hook-First, Multi-Angle, 30/60FPS & TikTok-Ready 3D Scene."""

from __future__ import annotations

import math
from typing import Any

EPISODE_ID = "parasut_icat"

EPISODE_META = {
    "title": "Paraşütü Nasıl İcat Edersin? 🪂⚙️",
    "cover_lines": [
        ("PARAŞÜTÜ NASIL", "white"),
        ("İCAT EDERSİN?", "cyan"),
    ],
    "header_tag": "PROJE #02 // AERODİNAMİK FREN SİSTEMİ",
    "description": (
        "4.000 metreden düşerken kumaşın tepesindeki küçücük delik olmasa saniyeler içinde takla atardın!\n\n"
        "Uçaktan atlayıştan hava direncine, düz tahtanın neden ters döndüğünden "
        "geniş kubbeye, tepe hava deliğinin salınımı durdurmasına ve gövde kemerine kadar "
        "paraşüt mühendisliğini adım adım sıfırdan keşfet.\n\n"
        "👇 Sıradaki videoda hangi makineyi icat edelim? Yorumlarda yaz!\n\n"
        "#mühendislik #icat #paraşüt #nasılicatedersin #3d #bilim #mekanik #shorts"
    ),
    "pinned_comment": "Sıradaki videoda neyi icat edelim? En çok beğeni alan icadı 3D blueprint olarak yapıyoruz! 👇🪂",
    "tags": [
        "paraşüt nasıl icat edilir",
        "nasıl icat edersin",
        "paraşüt çalışma prensibi",
        "paraşüt tepe deliği",
        "hava direnci mekaniği",
        "mühendislik shorts",
        "3d mekanik animasyon",
        "makine stüdyo",
    ],
}

_CORE_PRE_PAYOFF: list[dict[str, Any]] = [
    {
        "id": "shock_hook",
        "narration": (
            "Dört bin metreden düşerken kumaşın tepesindeki bu küçük delik olmasa "
            "anında düşerdin."
        ),
        "pause_after": 0.08,
        "headline": [("TEPE DELİĞİ ", "red"), ("HAYAT KURTARIR", "amber")],
        "sfx": [
            {"name": "riser", "offset": 0.0, "gain": 0.45},
            {"name": "whoosh", "offset": 0.65, "gain": 0.65},
            {"name": "alert", "offset": 1.15, "gain": 0.72},
            {"name": "pop", "offset": 2.35, "gain": 0.55},
        ],
    },
    {
        "id": "hook_plane",
        "narration": (
            "Hadi sıfırdan icat edelim. Bozulan bir uçaktan atlamak zorundasın "
            "ama altında yalnızca boşluk var."
        ),
        "pause_after": 0.08,
        "headline": [("4.000 METRE ", "white"), ("// ADIM ADIM İCAT", "cyan")],
        "sfx": [
            {"name": "motor", "offset": 0.05, "gain": 0.36},
            {"name": "pop", "offset": 0.45, "gain": 0.48},
            {"name": "whoosh", "offset": 2.30, "gain": 0.58},
        ],
    },
    {
        "id": "freefall_pain",
        "narration": (
            "İlk saniyelerde hava direnci yetersiz; yer çekimi seni saatte "
            "iki yüz kilometre hıza fırlatır."
        ),
        "pause_after": 0.09,
        "headline": [("200 KM/SA ", "red"), ("SERBEST DÜŞÜŞ", "white")],
        "sfx": [
            {"name": "riser", "offset": 0.35, "gain": 0.52},
            {"name": "alert", "offset": 2.15, "gain": 0.68},
        ],
    },
    {
        "id": "board_fail",
        "narration": (
            "Altına düz bir tahta veya küçük şemsiye koysan hava kenardan kaçar, "
            "ters dönüp kontrolden çıkarsın."
        ),
        "pause_after": 0.09,
        "headline": [("DÜZ KANAT ", "white"), ("TERS DÖNER", "red")],
        "sfx": [
            {"name": "pop", "offset": 0.25, "gain": 0.45},
            {"name": "clank", "offset": 1.80, "gain": 0.62},
            {"name": "alert", "offset": 3.45, "gain": 0.68},
        ],
    },
    {
        "id": "canopy_discovery",
        "narration": (
            "Çözüm geniş ve esnek bir kumaş kubbe açmak. Altta sıkışan hava "
            "yukarı güçlü bir kaldırma kuvveti üretir."
        ),
        "pause_after": 0.10,
        "headline": [("GENİŞ KUBBE ", "white"), ("= HAVA FRENİ", "cyan")],
        "sfx": [
            {"name": "whoosh", "offset": 0.15, "gain": 0.65},
            {"name": "boom", "offset": 0.38, "gain": 0.72},
            {"name": "ding", "offset": 3.85, "gain": 0.46},
        ],
    },
    {
        "id": "vent_stability",
        "narration": (
            "Ama büyük bir sorun var: Altta biriken hava kenarlardan taşar, kubbe sarkaç gibi sallanır. "
            "Tepeye küçük bir delik açınca hava dengelenir, savrulma durur."
        ),
        "pause_after": 0.10,
        "headline": [("TEPE DELİĞİ // ", "amber"), ("DENGE KİLİDİ", "green")],
        "sfx": [
            {"name": "alert", "offset": 1.65, "gain": 0.65},
            {"name": "pop", "offset": 4.10, "gain": 0.55},
            {"name": "whoosh", "offset": 4.30, "gain": 0.52},
            {"name": "ding", "offset": 6.10, "gain": 0.55},
        ],
    },
    {
        "id": "risers_harness",
        "narration": (
            "Paraşüt açılırken tek ip belini kırabilir; bu yüzden yük gövde kemerine "
            "dağılan çoklu taşıma iplerine bölünür."
        ),
        "pause_after": 0.10,
        "headline": [("GÖVDE KEMERİ ", "amber"), ("+ TAŞIMA İPLERİ", "cyan")],
        "sfx": [
            {"name": "snap", "offset": 0.45, "gain": 0.68},
            {"name": "pop", "offset": 2.95, "gain": 0.48},
            {"name": "clank", "offset": 4.60, "gain": 0.65},
        ],
    },
]

_TIKTOK_DEPTH_BEATS: list[dict[str, Any]] = [
    {
        "id": "drogue_chute",
        "narration": (
            "Ama dev ana kubbe yüksek hızda birden açılırsa kemerini ve sırtını parçalayacak kadar sert şok vurur. "
            "Bu yüzden önce minik bir kılavuz paraşüt rüzgara fırlayıp ana kubbeyi sırayla çeker."
        ),
        "pause_after": 0.12,
        "headline": [("KILAVUZ KUBBE ", "cyan"), ("// ŞOK ÖNLEYİCİ", "white")],
        "sfx": [
            {"name": "pop", "offset": 0.35, "gain": 0.48},
            {"name": "alert", "offset": 3.40, "gain": 0.60},
            {"name": "whoosh", "offset": 6.40, "gain": 0.65},
        ],
    },
    {
        "id": "reserve_chute",
        "narration": (
            "Ana kubbe havada ters dönse veya kalın ipler birbirine dolaşsa bile sırttaki ikinci yedek paraşüt "
            "tek kol çekişiyle saniyeler içinde seni güvenle kurtarır."
        ),
        "pause_after": 0.12,
        "headline": [("ÇİFT EMNİYET ", "green"), ("// YEDEK KUBBE", "amber")],
        "sfx": [
            {"name": "snap", "offset": 0.45, "gain": 0.68},
            {"name": "pop", "offset": 3.60, "gain": 0.50},
            {"name": "ding", "offset": 7.40, "gain": 0.58},
        ],
    },
]

_PAYOFF_BEAT: dict[str, Any] = {
    "id": "modern_payoff",
    "narration": (
        "Hepsini katlayıp küçük bir sırt çantasına sığdırdığında tek çekişle gökyüzünde süzülür, "
        "hedefe yumuşakça inersin. Tabii ipi çekmeyi unutmazsan."
    ),
    "pause_after": 0.25,
    "headline": [("MODERN ", "white"), ("PARAŞÜT SİSTEMİ", "green")],
    "sfx": [
        {"name": "whoosh", "offset": 0.35, "gain": 0.52},
        {"name": "ding", "offset": 3.90, "gain": 0.72},
        {"name": "muzak", "offset": 4.65, "gain": 0.42},
    ],
}


def get_beats(profile: str = "shorts") -> list[dict[str, Any]]:
    """Return episode beat list tailored for short-form or 61-64s TikTok duration."""
    if profile == "tiktok":
        return [dict(b) for b in [*_CORE_PRE_PAYOFF, *_TIKTOK_DEPTH_BEATS, _PAYOFF_BEAT]]
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
    """Construct and keyframe the physically grounded 3D parachute engineering scene."""
    import bmesh
    import bpy
    from mathutils import Matrix, Vector

    from studio.blender_scene_api import (
        CameraRig,
        HUDTracker,
        MannequinRig,
        add_box,
        add_cylinder,
        add_empty,
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
    # Materials (Blueprint palette + fabric + carbon + glowing gauges)
    # ------------------------------------------------------------------
    fuselage_mat = make_material("PlaneMetal", (0.58, 0.65, 0.74), metallic=0.72, roughness=0.30, noise_bump=0.05)
    dark_steel = make_material("DarkSteel", (0.16, 0.21, 0.28), metallic=0.82, roughness=0.35, noise_bump=0.06)
    prop_mat = make_material("PropCarbon", (0.09, 0.11, 0.15), metallic=0.65, roughness=0.25)
    timber_mat = make_material(
        "PlywoodBoard",
        (0.90, 0.65, 0.30),
        metallic=0.0,
        roughness=0.52,
        emission=(0.82, 0.58, 0.26),
        emission_strength=0.16,
        noise_bump=0.12,
    )
    canopy_white = make_material("CanopyWhite", (0.90, 0.94, 0.99), metallic=0.04, roughness=0.45, noise_bump=0.06)
    canopy_cyan = make_material("CanopyCyan", (0.12, 0.64, 0.92), metallic=0.05, roughness=0.42, noise_bump=0.06)
    canopy_orange = make_material("DrogueOrange", (0.98, 0.44, 0.10), metallic=0.04, roughness=0.40, emission=(0.95, 0.38, 0.08), emission_strength=0.25)
    amber_mat = make_material("AmberHardware", (1.0, 0.64, 0.12), metallic=0.25, roughness=0.35, emission=(1.0, 0.60, 0.10), emission_strength=0.45)
    red_glow = make_material("AlertRed", (1.0, 0.22, 0.25), roughness=0.25, emission=(1.0, 0.20, 0.22), emission_strength=1.5)
    cyan_glow = make_material("AirflowCyan", (0.24, 0.85, 1.0), roughness=0.18, emission=(0.24, 0.85, 1.0), emission_strength=1.35, alpha=0.72)
    green_glow = make_material("SafeGreen", (0.22, 0.92, 0.56), roughness=0.20, emission=(0.22, 0.92, 0.56), emission_strength=1.3)
    ground_mat = make_material("LandingDeck", (0.12, 0.18, 0.26), metallic=0.12, roughness=0.72, noise_bump=0.10)
    cloud_mat = make_material("CloudWisp", (0.82, 0.90, 0.98), roughness=0.90, emission=(0.75, 0.86, 0.98), emission_strength=0.15, alpha=0.14)
    cord_mat = make_material("KevlarCord", (0.82, 0.90, 0.98), metallic=0.15, roughness=0.38)
    harness_mat = make_material("HarnessStrap", (0.14, 0.17, 0.22), roughness=0.65)
    pack_mat = make_material("RigPack", (0.13, 0.20, 0.30), metallic=0.15, roughness=0.48)

    # ------------------------------------------------------------------
    # Helper builders: Curved bmesh dome segments + dynamic tension cords
    # ------------------------------------------------------------------
    def create_gore_dome(
        name: str,
        r_outer: float,
        r_inner: float,
        dome_height: float,
        n_gores: int = 16,
        n_rings: int = 8,
        alternate_mats: tuple[Any, Any] | None = None,
        parent: Any = None,
        solidify_t: float = 0.025,
    ) -> bpy.types.Object:
        """Build a ribbed dome canopy (open apex if r_inner > 0, closed cap otherwise)."""
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()

        rings: list[list[Any]] = []
        for ri in range(n_rings + 1):
            frac = ri / n_rings
            # Smooth quarter-ellipse dome curve from skirt (frac=0) to inner aperture (frac=1)
            ang = frac * (math.pi * 0.48 if r_inner > 0.001 else math.pi * 0.50)
            rad = r_inner + (r_outer - r_inner) * math.cos(ang)
            z = dome_height * math.sin(ang)
            ring_verts = []
            for gi in range(n_gores):
                theta = (2.0 * math.pi * gi) / n_gores
                # Slight scalloped inflation bulge midway along radial gores when outer rings inflate
                bulge = 1.0 + 0.035 * math.sin(frac * math.pi)
                x = rad * bulge * math.cos(theta)
                y = rad * bulge * math.sin(theta)
                ring_verts.append(bm.verts.new((x, y, z)))
            rings.append(ring_verts)

        for ri in range(n_rings):
            for gi in range(n_gores):
                gn = (gi + 1) % n_gores
                face = bm.faces.new((
                    rings[ri][gi],
                    rings[ri][gn],
                    rings[ri + 1][gn],
                    rings[ri + 1][gi],
                ))
                face.material_index = gi % 2 if alternate_mats else 0
                face.smooth = True

        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()

        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        if alternate_mats:
            obj.data.materials.append(alternate_mats[0])
            obj.data.materials.append(alternate_mats[1])
        sol = obj.modifiers.new("Solidify", "SOLIDIFY")
        sol.thickness = solidify_t
        sol.offset = 0.0
        if parent:
            obj.parent = parent
        return obj

    def make_cord(name: str, radius: float = 0.014, mat: Any = None, parent: Any = None) -> bpy.types.Object:
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=radius, depth=1.0, location=(0, 0, 0))
        obj = bpy.context.active_object
        obj.name = name
        obj.data.materials.append(mat or cord_mat)
        obj.rotation_mode = "QUATERNION"
        if parent:
            obj.parent = parent
        return obj

    def place_cord_static(obj: Any, p1: Vector, p2: Vector) -> None:
        vec = p2 - p1
        length = max(0.01, vec.length)
        mid = (p1 + p2) * 0.5
        quat = vec.normalized().to_track_quat("Z", "Y")
        obj.location = (mid.x, mid.y, mid.z)
        obj.scale = (1.0, 1.0, length)
        obj.rotation_quaternion = quat

    def key_cord_span(obj: Any, frame: int, p1: Vector, p2: Vector) -> None:
        place_cord_static(obj, p1, p2)
        obj.keyframe_insert(data_path="location", frame=frame)
        obj.keyframe_insert(data_path="scale", frame=frame)
        obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    # ------------------------------------------------------------------
    # 1. Ground Landing Deck (z = 0) & Altitude Blueprint Rings
    # ------------------------------------------------------------------
    ground_root = add_empty("GroundPad_Root", (0, 0, 0))
    add_box("GroundSlab", (18.0, 14.0, 0.35), (0, 0, -0.175), material=ground_mat, parent=ground_root)
    for ri, (rad, thick, mat) in enumerate([
        (2.4, 0.05, cyan_glow),
        (1.5, 0.05, amber_mat),
        (0.7, 0.06, green_glow),
    ]):
        bpy.ops.mesh.primitive_torus_add(major_radius=rad, minor_radius=thick, major_segments=48, minor_segments=10, location=(0, 0, 0.02 + ri * 0.002))
        ring = bpy.context.active_object
        ring.name = f"TargetRing_{ri}"
        ring.data.materials.append(mat)
        ring.parent = ground_root
    target_anchor = add_empty("Anchor_Target", (0.85, -0.3, 0.35), parent=ground_root)

    # Soft layered translucent cumulus puffs (zero harsh boxy shadows)
    cloud_root = add_empty("CloudLayers_Root", (0, 0, 0))
    cloud_specs = [
        (-4.5, 4.2, 5.5, 1.4),
        (4.8, 4.8, 12.0, 1.5),
        (-4.8, 5.0, 21.5, 1.6),
        (4.5, 4.6, 23.0, 1.4),
    ]
    for ci, (cx, cy, cz, sc) in enumerate(cloud_specs):
        for pi, (ox, oy, oz, r_mul) in enumerate([(0, 0, 0, 1.0), (-0.9 * sc, 0.2, -0.1, 0.72), (0.9 * sc, -0.1, -0.15, 0.78)]):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=0.95 * sc * r_mul, location=(cx + ox, cy + oy, cz + oz))
            puff = bpy.context.active_object
            puff.name = f"CloudPuff_{ci}_{pi}"
            puff.scale = (1.6, 0.9, 0.45)
            puff.data.materials.append(cloud_mat)
            if hasattr(puff, "visible_shadow"):
                puff.visible_shadow = False
            for poly in puff.data.polygons:
                poly.use_smooth = True
            puff.parent = cloud_root

    # Dynamic vertical wind streaks (moving upward past jumper to convey fall speed)
    wind_root = add_empty("WindStreaks_Root", (0, 0, 0))
    wind_bars: list[tuple[Any, float, float, float]] = []
    for wi in range(14):
        wx = -2.4 + (wi % 7) * 0.8 + (0.25 if wi >= 7 else 0.0)
        wy = -0.7 if wi % 2 == 0 else 1.1
        wlen = 0.9 + (wi % 3) * 0.45
        wb = add_cylinder(f"WindStreak_{wi}", 0.018, wlen, (wx, wy, 0), vertices=8, material=cyan_glow, parent=wind_root)
        wind_bars.append((wb, wx, wy, (wi * 0.53) % 5.0))

    # ------------------------------------------------------------------
    # 2. High-Altitude Transport Plane & Rear Cargo Ramp (Beat 1 Hook)
    # ------------------------------------------------------------------
    PLANE_Z = 27.5
    plane_root = add_empty("CargoPlane_Root", (0.0, 0.0, PLANE_Z))
    add_box("Plane_Fuselage", (5.0, 2.0, 1.75), (-1.1, 0.2, 1.15), material=fuselage_mat, bevel=0.28, parent=plane_root)
    add_box("Plane_LiveryStripe", (4.8, 2.06, 0.22), (-1.1, 0.2, 1.18), material=canopy_cyan, bevel=0.02, parent=plane_root)
    add_cylinder("Plane_NoseCone", 0.72, 1.4, (-4.1, 0.2, 0.92), rotation_deg=(0, 90, 0), vertices=20, material=fuselage_mat, parent=plane_root)
    add_box("Plane_CockpitGlass", (0.85, 1.35, 0.45), (-3.55, 0.2, 1.48), rotation_deg=(0, -18, 0), material=dark_steel, bevel=0.06, parent=plane_root)
    add_box("Plane_Wing", (1.9, 7.6, 0.22), (-1.5, 0.2, 2.08), material=fuselage_mat, bevel=0.06, parent=plane_root)
    add_box("Plane_TailFin", (1.2, 0.20, 1.80), (1.25, 0.2, 2.80), material=amber_mat, bevel=0.05, parent=plane_root)
    add_box("Plane_CargoRamp", (1.8, 1.45, 0.14), (2.15, 0.2, 0.22), rotation_deg=(0, 14, 0), material=dark_steel, bevel=0.02, parent=plane_root)
    add_box("Plane_WarningLip", (0.14, 1.48, 0.16), (2.92, 0.2, 0.04), material=red_glow, parent=plane_root)
    props: list[Any] = []
    for side_idx, py in enumerate((-2.0, 2.4)):
        add_cylinder(f"Plane_Engine_{side_idx}", 0.28, 1.1, (-2.0, py, 1.92), rotation_deg=(0, 90, 0), vertices=16, material=dark_steel, parent=plane_root)
        prop_hub = add_empty(f"Plane_Prop_{side_idx}", (-2.62, py, 1.92), parent=plane_root)
        add_box(f"PropBladeA_{side_idx}", (0.04, 0.14, 1.25), (0, 0, 0), material=prop_mat, parent=prop_hub)
        add_box(f"PropBladeB_{side_idx}", (0.04, 1.25, 0.14), (0, 0, 0), material=prop_mat, parent=prop_hub)
        props.append(prop_hub)
    plane_door_anchor = add_empty("Anchor_PlaneDoor", (2.25, -0.5, 0.9), parent=plane_root)

    # ------------------------------------------------------------------
    # 3. Parachute System Rig (Assembly pivot swings smoothly as pendulum)
    # ------------------------------------------------------------------
    # Assembly origin sits right at Canopy Skirt center (Z_offset = +3.30 above mannequin feet)
    # Rotating canopy_pendulum pivots cleanly overhead while carrying dome + lines + mannequin!
    ASSEMBLY_LIFT = 3.25
    pendulum_root = add_empty("ParachuteAssembly_Root", (0, 0, 20.0))

    # Main dome canopy (radius 1.92m, circular apex vent radius 0.36m)
    CANOPY_R = 1.92
    VENT_R = 0.36
    DOME_H = 1.12
    canopy_shell = create_gore_dome(
        "Canopy_MainDome",
        r_outer=CANOPY_R,
        r_inner=VENT_R,
        dome_height=DOME_H,
        n_gores=16,
        n_rings=8,
        alternate_mats=(canopy_cyan, canopy_white),
        parent=pendulum_root,
    )
    # Structural meridian seam ribs for crisp engineering look
    canopy_ribs_root = add_empty("Canopy_Ribs", (0, 0, 0), parent=pendulum_root)
    for ri in range(8):
        th = (2.0 * math.pi * ri) / 8
        rib_mid = Vector((math.cos(th) * (CANOPY_R + VENT_R) * 0.5, math.sin(th) * (CANOPY_R + VENT_R) * 0.5, DOME_H * 0.55))
        rib_top = Vector((math.cos(th) * VENT_R, math.sin(th) * VENT_R, DOME_H * 0.99))
        rib_bot = Vector((math.cos(th) * CANOPY_R, math.sin(th) * CANOPY_R, 0.0))
        rib = make_cord(f"CanopyRib_{ri}", radius=0.016, mat=dark_steel, parent=canopy_ribs_root)
        place_cord_static(rib, rib_bot, rib_top)

    # Separate top center plug cap (visible ONLY when vent is closed -> Beats 4 & 5a)
    apex_cap_root = add_empty("Canopy_ApexCapRoot", (0, 0, 0), parent=pendulum_root)
    create_gore_dome(
        "Canopy_ApexCap",
        r_outer=VENT_R + 0.02,
        r_inner=0.002,
        dome_height=DOME_H + 0.06,
        n_gores=16,
        n_rings=4,
        alternate_mats=(canopy_white, canopy_cyan),
        parent=apex_cap_root,
    )
    # Give apex cap exact Z alignment at rim height
    # Small inner plug starts at frac=0 -> z=0, so create clean shallow crown seated at z = DOME_H * sin(0.48*pi)
    bpy.data.objects["Canopy_ApexCap"].location = (0, 0, 0)
    # Actually let's replace Canopy_ApexCap cleanly using scaled cap from DOME_H*0.97 to DOME_H*1.12:
    bpy.data.objects.remove(bpy.data.objects["Canopy_ApexCap"], do_unlink=True)
    apex_disc = create_gore_dome(
        "Canopy_ApexCap",
        r_outer=VENT_R + 0.03,
        r_inner=0.0,
        dome_height=0.14,
        n_gores=16,
        n_rings=3,
        alternate_mats=(canopy_white, canopy_cyan),
        parent=apex_cap_root,
    )
    apex_disc.location = (0, 0, DOME_H * math.sin(math.pi * 0.48) - 0.01)

    # Reinforced glowing Amber Vent Collar + rising airflow jet through the apex vent hole
    vent_fx_root = add_empty("VentFX_Root", (0, 0, 0), parent=pendulum_root)
    vent_z = DOME_H * math.sin(math.pi * 0.48)
    bpy.ops.mesh.primitive_torus_add(major_radius=VENT_R + 0.015, minor_radius=0.042, major_segments=32, minor_segments=10, location=(0, 0, vent_z))
    vent_ring = bpy.context.active_object
    vent_ring.name = "VentCollarRing"
    vent_ring.data.materials.append(amber_mat)
    vent_ring.parent = vent_fx_root

    vent_plume_root = add_empty("VentPlume_Root", (0, 0, vent_z), parent=pendulum_root)
    add_cylinder("VentJetCore", 0.20, 1.35, (0, 0, 0.70), vertices=20, material=cyan_glow, parent=vent_plume_root)
    for pi in range(3):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.25 + pi * 0.11, minor_radius=0.025, major_segments=24, minor_segments=8, location=(0, 0, 0.25 + pi * 0.45))
        vr = bpy.context.active_object
        vr.name = f"VentVortex_{pi}"
        vr.data.materials.append(cyan_glow)
        vr.parent = vent_plume_root

    # Under-canopy lifting airflow rings (Beat 4 air cushion visual)
    under_air_root = add_empty("UnderCanopyAir_Root", (0, 0, 0), parent=pendulum_root)
    for ui, ux in enumerate((-0.85, 0.0, 0.85)):
        add_cylinder(f"UpAirShaft_{ui}", 0.045, 0.95, (ux, 0.0, -0.45), vertices=12, material=cyan_glow, parent=under_air_root)
        add_cylinder(f"UpAirHead_{ui}", 0.11, 0.22, (ux, 0.0, 0.08), vertices=12, material=cyan_glow, parent=under_air_root)

    # 12 Taut Kevlar Suspension Cords converging cleanly to Left & Right Riser Clusters + Yellow Toggles
    lines_root = add_empty("SuspensionLines_Root", (0, 0, 0), parent=pendulum_root)
    for li in range(12):
        th = (2.0 * math.pi * li) / 12
        sk_pt = Vector((CANOPY_R * math.cos(th), CANOPY_R * math.sin(th), 0.01))
        # Left cluster (x < 0) vs Right cluster (x >= 0) risers above shoulders
        side_x = -0.22 if math.cos(th) < 0 else 0.22
        riser_top = Vector((side_x, 0.0, -ASSEMBLY_LIFT + 1.48))
        cord = make_cord(f"SuspLine_{li}", radius=0.012, mat=cord_mat, parent=lines_root)
        place_cord_static(cord, riser_top, sk_pt)

    # Two sturdy main riser straps + bright yellow steering toggle handles at hand level
    riser_l = make_cord("MainRiser_L", radius=0.024, mat=amber_mat, parent=lines_root)
    riser_r = make_cord("MainRiser_R", radius=0.024, mat=amber_mat, parent=lines_root)
    place_cord_static(riser_l, Vector((-0.18, 0.0, -ASSEMBLY_LIFT + 0.96)), Vector((-0.22, 0.0, -ASSEMBLY_LIFT + 1.48)))
    place_cord_static(riser_r, Vector((0.18, 0.0, -ASSEMBLY_LIFT + 0.96)), Vector((0.22, 0.0, -ASSEMBLY_LIFT + 1.48)))
    add_box("SteeringToggle_L", (0.09, 0.05, 0.14), (-0.23, -0.05, -ASSEMBLY_LIFT + 1.15), material=amber_mat, bevel=0.01, parent=lines_root)
    add_box("SteeringToggle_R", (0.09, 0.05, 0.14), (0.23, -0.05, -ASSEMBLY_LIFT + 1.15), material=amber_mat, bevel=0.01, parent=lines_root)

    # HUD anchors attached to canopy & harness
    canopy_top_anchor = add_empty("Anchor_CanopyVent", (0.0, -0.15, vent_z + 0.08), parent=pendulum_root)
    canopy_skirt_anchor = add_empty("Anchor_CanopyLift", (-1.1, -0.25, -0.10), parent=pendulum_root)
    lines_mid_anchor = add_empty("Anchor_SuspLines", (0.65, -0.18, -1.25), parent=pendulum_root)

    # ------------------------------------------------------------------
    # 4. Mannequin + Fitted Chest Harness + Backpack (Separate / Parented cleanly)
    # ------------------------------------------------------------------
    man = MannequinRig("HeroSkydiver", scale_factor=0.72)

    # Fitted harness straps mounted directly to Mannequin body root (follow body rotation smoothly)
    harness_root = add_empty("Harness_Root", (0, 0, 0), parent=man.root)
    for sx in (-0.13, 0.13):
        add_box(f"ShoulderStrap_{sx:.2f}", (0.055, 0.24, 0.36), (sx, 0.0, 0.92), material=harness_mat, bevel=0.01, parent=harness_root)
        add_box(f"LegStrap_{sx:.2f}", (0.05, 0.21, 0.12), (sx * 0.95, 0.0, 0.54), material=amber_mat, bevel=0.008, parent=harness_root)
    add_box("ChestBuckleBar", (0.30, 0.22, 0.065), (0.0, 0.0, 0.85), material=amber_mat, bevel=0.01, parent=harness_root)
    harness_anchor = add_empty("Anchor_Harness", (0.26, -0.15, 0.86), parent=man.root)

    # Main backpack container (on back +Y side of mannequin torso — note Mannequin faces -Y!)
    pack_root = add_empty("Backpack_Root", (0.0, 0.16, 0.86), parent=man.root)
    add_box("Pack_Body", (0.30, 0.16, 0.44), (0, 0, 0), material=pack_mat, bevel=0.03, parent=pack_root)
    add_box("Pack_TopReserveFlap", (0.28, 0.17, 0.18), (0, 0.01, 0.14), material=amber_mat, bevel=0.02, parent=pack_root)
    add_box("Pack_RipcordRing", (0.08, 0.05, 0.08), (-0.18, -0.18, -0.05), material=red_glow, bevel=0.01, parent=pack_root)
    pack_anchor = add_empty("Anchor_Backpack", (0.24, 0.16, 0.95), parent=man.root)

    # ------------------------------------------------------------------
    # 5. Naive Flat Plywood Board / Umbrella Fail Prop (Beat 3)
    # ------------------------------------------------------------------
    board_fail_root = add_empty("BoardFail_Root", (0, 0, 0))
    add_box("FlatBoard_Wood", (2.15, 1.35, 0.07), (0, 0, 0.42), material=timber_mat, bevel=0.015, parent=board_fail_root)
    add_cylinder("FlatBoard_Handle", 0.028, 0.82, (0, 0, 0.02), vertices=12, material=fuselage_mat, parent=board_fail_root)
    board_anchor = add_empty("Anchor_BoardFail", (0.65, -0.25, 0.45), parent=board_fail_root)

    # ------------------------------------------------------------------
    # 6. Miniature Orange Drogue / Pilot Chute + Bridle (TikTok Depth Beat)
    # ------------------------------------------------------------------
    drogue_root = add_empty("DrogueChute_Root", (0, 0, 0))
    create_gore_dome(
        "Drogue_OrangeDome",
        r_outer=0.58,
        r_inner=0.0,
        dome_height=0.38,
        n_gores=10,
        n_rings=4,
        alternate_mats=(canopy_orange, canopy_white),
        parent=drogue_root,
        solidify_t=0.018,
    )
    for di in range(4):
        th = (2.0 * math.pi * di) / 4
        dc = make_cord(f"DrogueLine_{di}", radius=0.009, mat=amber_mat, parent=drogue_root)
        place_cord_static(dc, Vector((0, 0, -0.58)), Vector((0.58 * math.cos(th), 0.58 * math.sin(th), 0.0)))
    bridle_cord = make_cord("DrogueBridle", radius=0.014, mat=amber_mat)
    drogue_anchor = add_empty("Anchor_Drogue", (0.45, -0.15, 0.25), parent=drogue_root)

    # Helper to cleanly reset all conditional props before keying a beat
    def hide_all_optional(frame: int) -> None:
        for obj in (
            plane_root, ground_root, cloud_root, wind_root, pendulum_root,
            apex_cap_root, vent_fx_root, vent_plume_root, under_air_root,
            lines_root, harness_root, pack_root, board_fail_root,
            drogue_root, bridle_cord,
        ):
            set_visibility(obj, frame, False)

    def hang_man_under(pz: float, swing_deg: float) -> tuple[float, float, float]:
        """Compute exact world (x, y, z) under pendulum_root using Blender's +Y rotation matrix."""
        off = Matrix.Rotation(math.radians(swing_deg), 3, "Y") @ Vector((0.0, 0.0, -ASSEMBLY_LIFT))
        return (off.x, off.y, pz + off.z)

    def show_canopy_state(frame: int, *, apex_closed: bool, show_plume: bool = False, show_under_air: bool = False) -> None:
        set_visibility(pendulum_root, frame, True)
        set_visibility(canopy_shell, frame, True)
        set_visibility(canopy_ribs_root, frame, True)
        set_visibility(lines_root, frame, True)
        # Re-apply explicit child rules after pendulum_root True!
        set_visibility(apex_cap_root, frame, apex_closed)
        set_visibility(vent_fx_root, frame, not apex_closed)
        set_visibility(vent_plume_root, frame, (not apex_closed) and show_plume)
        set_visibility(under_air_root, frame, show_under_air)

    cam = CameraRig(lens=30.0)
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
    # BEAT 0: SHOCK HOOK — 4000m Violent Swing -> Apex Vent Stabilizes!
    # ==================================================================
    b0 = beats["shock_hook"]
    f0s, f0e = b0["frame_start"], b0["frame_end"]
    f0_cut = f0s + int((f0e - f0s) * 0.44)
    f0_stabilize = f0s + int((f0e - f0s) * 0.42)

    hide_all_optional(f0s)
    set_visibility(wind_root, f0s, True)
    set_visibility(harness_root, f0s, True)
    set_visibility(pack_root, f0s, True)
    show_canopy_state(f0s, apex_closed=True, show_plume=False, show_under_air=False)
    # Switch to apex open right at f0_stabilize
    show_canopy_state(f0_stabilize, apex_closed=False, show_plume=True, show_under_air=False)

    for f in _sample_frames(f0s, f0e, step=kf_step):
        frac = (f - f0s) / max(1, (f0e - f0s))
        pz = 21.0 - frac * 2.2
        if f < f0_stabilize:
            swing = 26.0 * math.sin(frac * math.pi * 3.8)
        else:
            damped = 1.0 - min(1.0, (f - f0_stabilize) / max(1, (f0e - f0_stabilize) * 0.65))
            swing = 14.0 * damped * math.sin(frac * math.pi * 3.0)
        set_keyframe(pendulum_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, swing, 0))
        mx, my, mz = hang_man_under(pz, swing)
        set_keyframe(man.root, f, location=(mx, my, mz), rotation_deg=(0, swing, -14))
        for wb, wx, wy, phase in wind_bars:
            wz = mz - 1.2 + ((phase + frac * 14.0) % 7.5)
            set_keyframe(wb, f, location=(wx, wy, wz))

    man.animate_panic(f0s, max(f0s + 1, f0_stabilize - 1), fps=fps)
    man.animate_relaxed_celebrate(f0_stabilize, f0e, fps=fps)

    # Cut 1 (0 -> 44%): Dynamic wide-angle canopy tilting violently -> Cut 2: Macro close-up on top apex vent opening!
    cam_cut(f0s, (0.6, -9.2, 20.0), (0.0, 0.0, 19.8), 32.0)
    cam_cut(f0_cut, (0.3, -5.2, 21.4), (0.0, 0.0, 21.0), 38.0)

    hud.add("b0_warn", canopy_top_anchor, "alert", f0s + 2, f0_stabilize - 1, label="SALINIM TEHLİKESİ!", color="red", offset_px=(150, -55))
    hud.add("b0_vent", canopy_top_anchor, "callout", f0_stabilize, f0e, label="TEPE HAVA DELİĞİ", color="amber", offset_px=(145, -70))
    hud.add("b0_safe", canopy_top_anchor, "badge", f0_cut + 2, f0e, label="DENGE SAĞLANDI", color="green", offset_px=(-165, -75))

    # ==================================================================
    # BEAT 1: REWIND TO 4.000m PLANE RAMP LEAP
    # ==================================================================
    b1 = beats["hook_plane"]
    f1s, f1e = b1["frame_start"], b1["frame_end"]
    f1_jump = f1s + int((f1e - f1s) * 0.45)

    hide_all_optional(f1s)
    set_visibility(plane_root, f1s, True)
    set_visibility(cloud_root, f1s, True)
    set_visibility(ground_root, f1s, True)

    for f in _sample_frames(f1s, f1e, step=kf_step):
        frac = (f - f1s) / max(1, (f1e - f1s))
        for pi, ph in enumerate(props):
            set_keyframe(ph, f, rotation_deg=(frac * 1440.0 * (1 if pi == 0 else -1), 0, 0))
        if f < f1_jump:
            walk_t = f - f1s
            mx = 0.8 + 1.55 * (walk_t / max(1, f1_jump - f1s))
            mz = PLANE_Z + 0.35 - 0.32 * (walk_t / max(1, f1_jump - f1s))
            mrot = (0, 0, -86)
        else:
            jt = (f - f1_jump) / max(1, f1e - f1_jump)
            mx = 2.35 + 1.85 * jt
            mz = PLANE_Z + 0.05 + 0.45 * math.sin(jt * math.pi * 0.5) - 3.6 * (jt ** 2)
            mrot = (0, -28 * jt, -80)
        set_keyframe(man.root, f, location=(mx, 0.2, mz), rotation_deg=mrot)

    man.animate_climb_cycle(f1s, max(f1s + 1, f1_jump - 1), fps=fps)
    man.animate_panic(f1_jump, f1e, fps=fps)

    # Cut 1: Side-3/4 view showing entire airplane & open red cargo lip -> Cut 2: Closer leap view
    cam_cut(f1s, (1.0, -9.2, PLANE_Z + 1.5), (0.3, 0.2, PLANE_Z + 0.8), 32.0)
    cam_cut(f1_jump, (2.6, -9.6, PLANE_Z - 0.4), (2.2, 0.2, PLANE_Z - 0.7), 32.0)

    hud.add("b1_alt", plane_door_anchor, "badge", f1s + 4, f1e, label="4.000 M // BOZULAN UÇAK", color="cyan", offset_px=(100, -125))

    # ==================================================================
    # BEAT 2: FREEFALL PAIN — 200 KM/H Acceleration & Fast Wind Streaks
    # ==================================================================
    b2 = beats["freefall_pain"]
    f2s, f2e = b2["frame_start"], b2["frame_end"]
    f2_cut = f2s + int((f2e - f2s) * 0.48)

    hide_all_optional(f2s)
    set_visibility(wind_root, f2s, True)

    for f in _sample_frames(f2s, f2e, step=kf_step):
        frac = (f - f2s) / max(1, (f2e - f2s))
        mz = 19.5 - 3.2 * (frac ** 1.25)
        wobble = 6.0 * math.sin(frac * math.pi * 5.0)
        set_keyframe(man.root, f, location=(0.0, 0.0, mz), rotation_deg=(-68.0, wobble, -12.0))
        for wb, wx, wy, phase in wind_bars:
            wz = mz - 3.2 + ((phase + frac * 28.0) % 9.0)
            set_keyframe(wb, f, location=(wx, wy, wz))

    man.animate_panic(f2s, f2e, fps=fps)

    # Track the falling diver directly on camera so diver stays dead-center!
    cam_cut(f2s, (0.5, -6.4, 19.7), (0.0, 0.0, 19.3), 34.0)
    cam_cut(f2_cut, (0.4, -4.8, 18.2), (0.0, 0.0, 17.8), 38.0)
    cam_set(f2e, (0.4, -5.0, 16.5), (0.0, 0.0, 16.1), 38.0)

    hud.add("b2_speed", man.alert_anchor, "alert", f2s + 2, f2e, label="200 KM/SA DÜŞÜŞ!", color="red", offset_px=(95, -55))

    # ==================================================================
    # BEAT 3: NAIVE FLAT PLYWOOD BOARD / UMBRELLA FLIPS & FAILS
    # ==================================================================
    b3 = beats["board_fail"]
    f3s, f3e = b3["frame_start"], b3["frame_end"]
    f3_cut = f3s + int((f3e - f3s) * 0.45)

    hide_all_optional(f3s)
    set_visibility(wind_root, f3s, True)
    set_visibility(board_fail_root, f3s, True)

    for f in _sample_frames(f3s, f3e, step=kf_step):
        frac = (f - f3s) / max(1, (f3e - f3s))
        mz = 16.0 - 4.0 * frac
        # Air spills asymmetrically around rigid edges -> board violently pitches & rolls sideways!
        flip_y = 65.0 * math.sin(frac * math.pi * 2.2)
        flip_x = 32.0 * math.cos(frac * math.pi * 1.8)
        set_keyframe(man.root, f, location=(0.0, 0.0, mz), rotation_deg=(flip_x * 0.45, flip_y * 0.45, -16.0))
        set_keyframe(board_fail_root, f, location=(0.0, 0.0, mz + 1.38), rotation_deg=(flip_x, flip_y, 12.0 * math.sin(frac * math.pi)))
        for wb, wx, wy, phase in wind_bars:
            wz = mz - 2.0 + ((phase + frac * 22.0) % 8.5)
            set_keyframe(wb, f, location=(wx, wy, wz))

    man.animate_panic(f3s, f3e, fps=fps)

    cam_cut(f3s, (0.7, -7.8, 15.8), (0.0, 0.0, 15.5), 32.0)
    cam_cut(f3_cut, (-0.5, -5.8, 13.8), (0.0, 0.0, 13.5), 36.0)

    hud.add("b3_board", board_anchor, "callout", f3s + 2, f3e, label="KENARDAN HAVA KAÇIYOR", color="amber", offset_px=(115, -95))
    hud.add("b3_flip", man.alert_anchor, "alert", f3_cut, f3e, label="KONTROLSÜZ DÖNÜŞ!", color="red", offset_px=(-245, 75))

    # ==================================================================
    # BEAT 4: WIDE FABRIC CANOPY BLOOMS + UPWARD AIR CUSHION
    # ==================================================================
    b4 = beats["canopy_discovery"]
    f4s, f4e = b4["frame_start"], b4["frame_end"]
    f4_bloom = f4s + int((f4e - f4s) * 0.25)
    f4_cut = f4s + int((f4e - f4s) * 0.46)

    hide_all_optional(f4s)
    set_visibility(wind_root, f4s, True)
    show_canopy_state(f4s, apex_closed=True, show_plume=False, show_under_air=True)

    for f in _sample_frames(f4s, f4e, step=kf_step):
        frac = (f - f4s) / max(1, (f4e - f4s))
        # Canopy smoothly inflates from folded narrow bundle to full 1.92m dome during first 25%
        open_t = min(1.0, frac / 0.25)
        bloom_s = 0.28 + 0.72 * (0.5 - 0.5 * math.cos(math.pi * open_t))
        pz = 14.5 - frac * 1.4
        set_keyframe(pendulum_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, 0, 0), scale=(bloom_s, bloom_s, 1.0))
        set_keyframe(man.root, f, location=(0.0, 0.0, pz - ASSEMBLY_LIFT), rotation_deg=(0, 0, -10))
        # Gentle slow downward wind streaks inside under_air highlight
        for wb, wx, wy, phase in wind_bars:
            wz = pz - 4.0 + ((phase + frac * 9.0) % 7.5)
            set_keyframe(wb, f, location=(wx, wy, wz))

    # Restore uniform scale right after Beat 4 just in case
    set_keyframe(pendulum_root, f4e, scale=(1.0, 1.0, 1.0))
    man.key_pose(f4s, torso_rot=(0, 0, 0), head_rot=(-10, 0, 0), sh_l=(115, 16, 0), sh_r=(115, -16, 0), el_l=(35, 0, 0), el_r=(35, 0, 0))
    man.key_pose(f4e, torso_rot=(0, 0, 0), head_rot=(-6, 0, 0), sh_l=(112, 16, 0), sh_r=(112, -16, 0), el_l=(35, 0, 0), el_r=(35, 0, 0))

    cam_cut(f4s, (0.8, -10.5, 13.0), (0.0, 0.0, 12.8), 32.0)
    cam_cut(f4_cut, (0.5, -7.2, 12.6), (0.0, 0.0, 12.5), 36.0)

    hud.add("b4_lift", canopy_skirt_anchor, "callout", f4_bloom, f4e, label="HAVA DİRENCİ = FREN", color="cyan", offset_px=(-155, -80))

    # ==================================================================
    # BEAT 5: PENDULUM OSCILLATION PROBLEM -> APEX VENT STABILIZES IT!
    # ==================================================================
    b5 = beats["vent_stability"]
    f5s, f5e = b5["frame_start"], b5["frame_end"]
    f5_vent = f5s + int((f5e - f5s) * 0.48)
    f5_cut2 = f5s + int((f5e - f5s) * 0.74)

    hide_all_optional(f5s)
    set_visibility(wind_root, f5s, True)
    show_canopy_state(f5s, apex_closed=True, show_plume=False, show_under_air=False)
    show_canopy_state(f5_vent, apex_closed=False, show_plume=True, show_under_air=False)

    for f in _sample_frames(f5s, f5e, step=kf_step):
        frac = (f - f5s) / max(1, (f5e - f5s))
        pz = 12.6 - frac * 1.4
        if f < f5_vent:
            swing = 25.0 * math.sin(((f - f5s) / max(1, f5_vent - f5s)) * math.pi * 3.0)
        else:
            damped = max(0.0, 1.0 - (f - f5_vent) / max(1, (f5e - f5_vent) * 0.55))
            swing = 16.0 * damped * math.sin(((f - f5_vent) / max(1, f5e - f5_vent)) * math.pi * 2.2)
        set_keyframe(pendulum_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, swing, 0), scale=(1.0, 1.0, 1.0))
        mx, my, mz = hang_man_under(pz, swing)
        set_keyframe(man.root, f, location=(mx, my, mz), rotation_deg=(0, swing, -10))
        for wb, wx, wy, phase in wind_bars:
            wz = pz - 4.0 + ((phase + frac * 8.0) % 7.5)
            set_keyframe(wb, f, location=(wx, wy, wz))

    man.animate_panic(f5s, max(f5s + 1, f5_vent - 1), fps=fps)
    man.key_pose(f5_vent, torso_rot=(0, 0, 0), head_rot=(-10, 0, 0), sh_l=(118, 16, 0), sh_r=(118, -16, 0), el_l=(32, 0, 0), el_r=(32, 0, 0))
    man.key_pose(f5e, torso_rot=(0, 0, 0), head_rot=(-4, 0, 0), sh_l=(118, 16, 0), sh_r=(118, -16, 0), el_l=(32, 0, 0), el_r=(32, 0, 0))

    # Cut 1 (wide swing) -> Cut 2 (tight macro right onto the top hole + amber ring + cyan airflow!) -> Cut 3 (calm glide!)
    cam_cut(f5s, (0.7, -10.5, 11.4), (0.0, 0.0, 11.2), 32.0)
    cam_cut(f5_vent, (0.3, -5.4, 12.4), (0.0, 0.0, 12.1), 38.0)
    cam_cut(f5_cut2, (0.8, -9.2, 10.6), (0.0, 0.0, 10.4), 33.0)

    hud.add("b5_osc", canopy_top_anchor, "alert", f5s + 2, f5_vent - 1, label="SARKAÇ SALINIMI!", color="red", offset_px=(145, -55))
    hud.add("b5_vent", canopy_top_anchor, "callout", f5_vent, f5e, label="TEPE HAVA DELİĞİ", color="amber", offset_px=(135, -75))
    hud.add("b5_calm", canopy_top_anchor, "badge", f5_cut2, f5e, label="SAVRULMA DURDU", color="green", offset_px=(-165, -75))

    # ==================================================================
    # BEAT 6: LOAD-DISTRIBUTING SUSPENSION LINES + CHEST HARNESS
    # ==================================================================
    b6 = beats["risers_harness"]
    f6s, f6e = b6["frame_start"], b6["frame_end"]
    f6_cut = f6s + int((f6e - f6s) * 0.45)

    hide_all_optional(f6s)
    set_visibility(wind_root, f6s, True)
    set_visibility(harness_root, f6s, True)
    show_canopy_state(f6s, apex_closed=False, show_plume=True, show_under_air=False)

    for f in _sample_frames(f6s, f6e, step=kf_step):
        frac = (f - f6s) / max(1, (f6e - f6s))
        pz = 10.4 - frac * 1.2
        bank = 8.0 * math.sin(frac * math.pi)
        set_keyframe(pendulum_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, bank, 0), scale=(1.0, 1.0, 1.0))
        mx, my, mz = hang_man_under(pz, bank)
        set_keyframe(man.root, f, location=(mx, my, mz), rotation_deg=(0, bank, -12))
        for wb, wx, wy, phase in wind_bars:
            wz = pz - 3.8 + ((phase + frac * 7.0) % 7.5)
            set_keyframe(wb, f, location=(wx, wy, wz))

    # Hands securely grip amber steering toggles while banking gently
    man.key_pose(f6s, torso_rot=(0, 0, 0), head_rot=(-6, 0, 0), sh_l=(120, 14, 0), sh_r=(120, -14, 0), el_l=(36, 0, 0), el_r=(36, 0, 0))
    man.key_pose(f6e, torso_rot=(0, 0, 0), head_rot=(-4, 0, 0), sh_l=(128, 12, 0), sh_r=(112, -14, 0), el_l=(44, 0, 0), el_r=(32, 0, 0))

    # Cut 1: Macro on taut 12 suspension lines fan -> Cut 2: Tight shot on Mannequin torso + aligned toggles + chest harness
    cam_cut(f6s, (0.4, -5.6, 10.0), (0.0, 0.0, 9.7), 40.0)
    cam_cut(f6_cut, (0.35, -5.6, 8.2), (0.0, 0.0, 7.8), 36.0)

    hud.add("b6_lines", lines_mid_anchor, "callout", f6s + 2, f6_cut - 1, label="ÇOKLU TAŞIMA İPLERİ", color="cyan", offset_px=(120, -75))
    hud.add("b6_harness", harness_anchor, "callout", f6_cut, f6e, label="YÜK DAĞITAN GÖVDE KEMERİ", color="amber", offset_px=(135, -80))

    # ==================================================================
    # OPTIONAL TIKTOK DEPTH BEATS (61-64s): DROGUE PILOT + RESERVE PACK
    # ==================================================================
    if "drogue_chute" in beats:
        bd = beats["drogue_chute"]
        fds, fde = bd["frame_start"], bd["frame_end"]
        fd_cut = fds + int((fde - fds) * 0.46)

        hide_all_optional(fds)
        set_visibility(wind_root, fds, True)
        set_visibility(harness_root, fds, True)
        set_visibility(pack_root, fds, True)
        set_visibility(drogue_root, fds, True)
        set_visibility(bridle_cord, fds, True)
        show_canopy_state(fds, apex_closed=False, show_plume=True, show_under_air=False)

        for f in _sample_frames(fds, fde, step=kf_step):
            frac = (f - fds) / max(1, (fde - fds))
            pz = 9.0 - frac * 0.9
            set_keyframe(pendulum_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, 0, 0), scale=(1.0, 1.0, 1.0))
            set_keyframe(man.root, f, location=(0.0, 0.0, pz - ASSEMBLY_LIFT), rotation_deg=(0, 0, -18))

            d_pos = Vector((-0.65 - 0.15 * math.sin(frac * math.pi), 0.75, pz + 1.55))
            p_pack = Vector((0.0, 0.25, pz - ASSEMBLY_LIFT + 1.05))
            set_keyframe(drogue_root, f, location=(d_pos.x, d_pos.y, d_pos.z), rotation_deg=(12, -16, 0))
            key_cord_span(bridle_cord, f, p_pack, Vector((d_pos.x, d_pos.y, d_pos.z - 0.56)))
            for wb, wx, wy, phase in wind_bars:
                wz = pz - 3.5 + ((phase + frac * 7.0) % 7.5)
                set_keyframe(wb, f, location=(wx, wy, wz))

        man.key_pose(fds, torso_rot=(0, 0, 0), head_rot=(-4, 0, 0), sh_l=(118, 14, 0), sh_r=(118, -14, 0), el_l=(34, 0, 0), el_r=(34, 0, 0))
        man.key_pose(fde, torso_rot=(0, 0, 0), head_rot=(-2, 0, 0), sh_l=(118, 14, 0), sh_r=(118, -14, 0), el_l=(34, 0, 0), el_r=(34, 0, 0))

        cam_cut(fds, (0.9, -9.2, 8.6), (-0.1, 0.2, 8.3), 33.0)
        cam_cut(fd_cut, (-0.3, -5.2, 9.8), (-0.5, 0.5, 9.6), 40.0)

        hud.add("bd_drogue", drogue_anchor, "callout", fds + 2, fde, label="KILAVUZ PARAŞÜT", color="cyan", offset_px=(120, -75))
        hud.add("bd_stage", canopy_skirt_anchor, "badge", fd_cut, fde, label="KADEMELİ AÇILMA", color="amber", offset_px=(-160, 45))

    if "reserve_chute" in beats:
        br = beats["reserve_chute"]
        frs, fre = br["frame_start"], br["frame_end"]
        fr_cut = frs + int((fre - frs) * 0.62)

        hide_all_optional(frs)
        set_visibility(wind_root, frs, True)
        set_visibility(harness_root, frs, True)
        set_visibility(pack_root, frs, True)
        show_canopy_state(frs, apex_closed=False, show_plume=True, show_under_air=False)

        for f in _sample_frames(frs, fre, step=kf_step):
            frac = (f - frs) / max(1, (fre - frs))
            pz = 8.1 - frac * 1.1
            set_keyframe(pendulum_root, f, location=(0.0, 0.0, pz), rotation_deg=(0, 0, 0), scale=(1.0, 1.0, 1.0))
            set_keyframe(man.root, f, location=(0.0, 0.0, pz - ASSEMBLY_LIFT), rotation_deg=(0, 0, -18))
            for wb, wx, wy, phase in wind_bars:
                wz = pz - 3.5 + ((phase + frac * 7.0) % 7.5)
                set_keyframe(wb, f, location=(wx, wy, wz))

        man.key_pose(frs, torso_rot=(0, 0, 0), head_rot=(-2, 0, 0), sh_l=(118, 14, 0), sh_r=(118, -14, 0), el_l=(34, 0, 0), el_r=(34, 0, 0))
        man.key_pose(fre, torso_rot=(0, 0, 0), head_rot=(-4, 0, 0), sh_l=(115, 16, 0), sh_r=(115, -16, 0), el_l=(34, 0, 0), el_r=(34, 0, 0))

        # Orbit to rear 3/4 macro (+Y side) to showcase dual backpack reserve flap & red ripcord ring, then widen
        cam_cut(frs, (1.6, 2.8, 5.75), (0.0, 0.16, 5.35), 40.0)
        cam_cut(fr_cut, (1.2, -9.4, 5.8), (0.0, 0.0, 5.6), 32.0)

        hud.add("bd_reserve", pack_anchor, "callout", frs + 2, fr_cut - 1, label="HAZIR YEDEK KUBBE", color="amber", offset_px=(145, -80))
        hud.add("bd_safe", pack_anchor, "badge", fr_cut, fre, label="ÇİFT EMNİYET SİSTEMİ", color="green", offset_px=(145, -75))

    # ==================================================================
    # FINAL BEAT: BACKPACK TO SMOOTH TARGET LANDING!
    # ==================================================================
    b7 = beats["modern_payoff"]
    f7s, f7e = b7["frame_start"], b7["frame_end"]
    f7_touchdown = f7s + int((f7e - f7s) * 0.72)
    f7_cut = f7s + int((f7e - f7s) * 0.45)

    hide_all_optional(f7s)
    set_visibility(ground_root, f7s, True)
    set_visibility(cloud_root, f7s, True)
    set_visibility(harness_root, f7s, True)
    set_visibility(pack_root, f7s, True)
    show_canopy_state(f7s, apex_closed=False, show_plume=True, show_under_air=False)

    for f in _sample_frames(f7s, f7e, step=kf_step):
        frac = (f - f7s) / max(1, (f7e - f7s))
        glide_frac = min(1.0, frac / 0.72)
        smooth_g = 0.5 - 0.5 * math.cos(math.pi * glide_frac)
        mz = (6.8 - 6.8 * smooth_g)
        mx = -1.6 + 1.6 * smooth_g
        pz = mz + ASSEMBLY_LIFT
        # Gentle flare pitch back just before touchdown, then stand tall on pad
        flare = 12.0 * math.sin(glide_frac * math.pi) if glide_frac < 1.0 else 0.0
        canopy_drop = 0.0 if f <= f7_touchdown else min(0.65, (f - f7_touchdown) / max(1, f7e - f7_touchdown) * 0.85)
        set_keyframe(pendulum_root, f, location=(mx - canopy_drop * 0.4, 0.0, pz - canopy_drop), rotation_deg=(0, flare * 0.6 - canopy_drop * 22.0, 0), scale=(1.0, 1.0, 1.0))
        set_keyframe(man.root, f, location=(mx, 0.0, mz), rotation_deg=(0, flare * 0.35, -14))

    man.key_pose(f7s, torso_rot=(0, 0, 0), head_rot=(-6, 0, 0), sh_l=(118, 16, 0), sh_r=(118, -16, 0), el_l=(36, 0, 0), el_r=(36, 0, 0))
    man.animate_relaxed_celebrate(f7_touchdown, f7e, fps=fps)

    # Cut 1: Backpack close-up / upper glide -> Cut 2: Smooth bullseye touchdown on the Blueprint pad!
    cam_cut(f7s, (-0.4, -7.8, 6.2), (-0.4, 0.0, 5.6), 34.0)
    cam_cut(f7_cut, (0.7, -8.8, 2.8), (0.0, 0.0, 2.1), 34.0)
    cam_set(f7e, (0.9, -9.0, 2.6), (0.0, 0.0, 2.0), 34.0)

    hud.add("b7_pack", pack_anchor, "callout", f7s + 2, f7_cut - 1, label="KOMPAKT SIRT ÇANTASI", color="cyan", offset_px=(-165, -80))
    hud.add("b7_land", target_anchor, "badge", f7_cut + 8, f7e, label="HEDEF // YUMUŞAK İNİŞ", color="green", offset_px=(155, -75))

    return {
        "scene": scene,
        "camera": cam.cam,
        "hud_tracker": hud,
        "hero_frame": f7_cut + int((f7e - f7_cut) * 0.35),
    }
