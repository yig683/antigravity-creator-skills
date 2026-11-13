"""Render a 2560x1440 3D Blender EEVEE engineering blueprint banner backdrop.

Places rich mechanical hero assemblies (steel hoist + brass pulleys on left,
interlocking brass/steel spur gear train + truss arch on right) flanking an
open dark central corridor so YouTube Desktop/TV/Mobile HUD text reads clearly.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy


STUDIO_ROOT = Path(__file__).resolve().parent.parent
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio.blender_scene_api import (  # noqa: E402
    CameraRig,
    add_box,
    add_cylinder,
    add_empty,
    add_sphere,
    make_material,
    reset_scene,
    setup_world_and_lighting,
)


def add_spur_gear(
    name: str,
    location: tuple[float, float, float],
    rotation_deg: tuple[float, float, float],
    radius: float,
    thickness: float,
    teeth: int,
    ring_mat: bpy.types.Material,
    hub_mat: bpy.types.Material,
    bolt_mat: bpy.types.Material,
) -> bpy.types.Object:
    """Build a precision mechanical 3D spur gear with hub, rim, spokes, and bolts."""
    root = add_empty(name, location)
    root.rotation_euler = tuple(math.radians(a) for a in rotation_deg)

    # Main wheel disc & outer toothed crown
    add_cylinder(
        f"{name}_Disc",
        radius=radius * 0.88,
        depth=thickness,
        vertices=max(32, teeth * 2),
        material=ring_mat,
        bevel=0.014,
        parent=root,
    )
    add_cylinder(
        f"{name}_Hub",
        radius=radius * 0.34,
        depth=thickness * 1.45,
        vertices=32,
        material=hub_mat,
        bevel=0.012,
        parent=root,
    )
    add_cylinder(
        f"{name}_Axle",
        radius=radius * 0.14,
        depth=thickness * 1.9,
        vertices=24,
        material=bolt_mat,
        bevel=0.008,
        parent=root,
    )

    # Individual precision beveled gear teeth around perimeter
    tooth_h = radius * 0.19
    tooth_w = (2.0 * math.pi * radius / teeth) * 0.44
    for i in range(teeth):
        ang = (2.0 * math.pi * i) / teeth
        tx = (radius * 0.91) * math.cos(ang)
        ty = (radius * 0.91) * math.sin(ang)
        add_box(
            f"{name}_T{i:02d}",
            size=(tooth_h, tooth_w, thickness * 0.92),
            location=(tx, ty, 0.0),
            rotation_deg=(0.0, 0.0, math.degrees(ang)),
            material=ring_mat,
            bevel=0.01,
            parent=root,
        )

    # Radial hub bolts
    for b in range(6):
        ang = (2.0 * math.pi * b) / 6.0
        bx = (radius * 0.56) * math.cos(ang)
        by = (radius * 0.56) * math.sin(ang)
        add_cylinder(
            f"{name}_Bolt{b}",
            radius=radius * 0.05,
            depth=thickness * 1.25,
            location=(bx, by, 0.0),
            vertices=14,
            material=bolt_mat,
            bevel=0.005,
            parent=root,
        )

    return root


def add_sheave_pulley(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    brass_mat: bpy.types.Material,
    steel_mat: bpy.types.Material,
    cyan_mat: bpy.types.Material,
) -> bpy.types.Object:
    root = add_empty(name, location)
    # Outer flanged rim rotated so wheel faces camera (+Y/-Y)
    add_cylinder(
        f"{name}_FlangeF",
        radius=radius,
        depth=0.06,
        location=(0, -0.09, 0),
        rotation_deg=(90, 0, 0),
        vertices=36,
        material=brass_mat,
        bevel=0.01,
        parent=root,
    )
    add_cylinder(
        f"{name}_FlangeB",
        radius=radius,
        depth=0.06,
        location=(0, 0.09, 0),
        rotation_deg=(90, 0, 0),
        vertices=36,
        material=brass_mat,
        bevel=0.01,
        parent=root,
    )
    add_cylinder(
        f"{name}_Groove",
        radius=radius * 0.84,
        depth=0.14,
        location=(0, 0, 0),
        rotation_deg=(90, 0, 0),
        vertices=32,
        material=steel_mat,
        bevel=0.008,
        parent=root,
    )
    add_cylinder(
        f"{name}_Center",
        radius=radius * 0.25,
        depth=0.28,
        location=(0, 0, 0),
        rotation_deg=(90, 0, 0),
        vertices=24,
        material=cyan_mat,
        bevel=0.008,
        parent=root,
    )
    return root


def build_banner_scene(out_png: Path) -> None:
    scene = reset_scene(res_x=2560, res_y=1440, fps=24, samples=32)
    scene.render.film_transparent = False
    setup_world_and_lighting(sky_color=(0.008, 0.020, 0.048), key_energy=2.2)

    # Controlled crisp rim accents preserving metallic contrast & avoiding blown highlights
    for lname, loc, color, energy in (
        ("LeftCyanAccent", (-6.0, -4.5, 2.8), (0.20, 0.78, 1.0), 115.0),
        ("RightWarmRim", (6.2, -4.2, 2.6), (1.0, 0.72, 0.30), 95.0),
        ("SoftCenterBlue", (0.0, -5.0, 4.0), (0.28, 0.65, 1.0), 45.0),
    ):
        ldata = bpy.data.lights.new(lname, type="AREA")
        ldata.energy = energy
        ldata.size = 6.0
        ldata.color = color
        lobj = bpy.data.objects.new(lname, ldata)
        bpy.context.collection.objects.link(lobj)
        lobj.location = loc
        lobj.rotation_euler = (math.radians(65), 0, 0)

    steel = make_material("SteelFrame", (0.19, 0.26, 0.37), metallic=0.84, roughness=0.30)
    dark_steel = make_material("DarkSteel", (0.08, 0.13, 0.21), metallic=0.78, roughness=0.38)
    brass = make_material("SatinBrass", (0.78, 0.50, 0.11), metallic=0.88, roughness=0.26)
    cyan_glow = make_material(
        "CyanHolo",
        (0.16, 0.78, 0.96),
        metallic=0.2,
        roughness=0.2,
        emission=(0.14, 0.72, 0.95),
        emission_strength=1.55,
    )
    glass = make_material(
        "CabGlass",
        (0.32, 0.78, 0.98),
        metallic=0.05,
        roughness=0.14,
        alpha=0.24,
    )
    grid_line_mat = make_material(
        "GridFloor",
        (0.05, 0.22, 0.38),
        emission=(0.05, 0.28, 0.48),
        emission_strength=0.22,
        alpha=0.35,
    )

    # Wide camera at y=-12.8: Desktop 2560x423 strip maps to Z ~ 0.36..2.54; full 16:9 covers Z ~ -2.2..5.1
    cam = CameraRig(lens=35.0)
    cam.key(1, location=(0.0, -12.8, 1.48), target=(0.0, 0.0, 1.45), lens=35.0)

    # Subtle receding 3D drafting grid lines along studio floor
    for gx in range(-10, 11, 1):
        add_box(f"GridX_{gx}", (0.012, 16.0, 0.008), (gx * 0.95, 2.5, -1.25), material=grid_line_mat, bevel=0.0)
    for gy in range(-4, 10, 1):
        add_box(f"GridY_{gy}", (20.0, 0.012, 0.008), (0.0, gy * 1.1, -1.25), material=grid_line_mat, bevel=0.0)

    # === LEFT WING (Centered inside Desktop Y-band so pulleys + glass cab + counterweight show cleanly) ===
    left = add_empty("LeftElevatorWing", (-4.65, 0.30, 0.0))
    left.rotation_euler = (0.0, 0.0, math.radians(15.0))

    for sx in (-1.05, 1.05):
        add_box(f"ShaftCol_{sx}", (0.15, 0.15, 6.2), (sx, 0.0, 1.65), material=steel, bevel=0.015, parent=left)
    add_box("DesktopTopCross", (2.45, 0.28, 0.16), (0.0, 0.0, 2.50), material=steel, bevel=0.014, parent=left)
    add_box("UpperCrownBeam", (2.55, 0.22, 0.20), (0.0, 0.0, 4.10), material=dark_steel, bevel=0.014, parent=left)
    add_box("MotorBody", (0.65, 0.38, 0.34), (-0.52, 0.0, 2.78), material=dark_steel, bevel=0.014, parent=left)
    add_cylinder("MotorDrum", 0.20, 0.56, (0.20, 0.0, 2.75), (0, 90, 0), 24, material=brass, bevel=0.01, parent=left)

    p1 = add_sheave_pulley("MainPulley", (-0.18, -0.05, 2.08), 0.42, brass, dark_steel, cyan_glow)
    p1.parent = left
    p2 = add_sheave_pulley("GuidePulley", (0.58, 0.02, 1.98), 0.28, brass, steel, cyan_glow)
    p2.parent = left

    for cx, cz_top, h_len in ((-0.32, 2.08, 1.15), (-0.04, 2.08, 1.15), (0.58, 1.98, 2.15)):
        add_cylinder(
            f"Cable_{cx}",
            radius=0.015,
            depth=h_len,
            location=(cx, -0.02, cz_top - h_len / 2.0),
            vertices=12,
            material=cyan_glow,
            parent=left,
        )

    cab = add_empty("GlassCab", (-0.18, -0.02, 0.88), parent=left)
    add_box("CabFloor", (0.94, 0.72, 0.07), (0, 0, -0.44), material=steel, bevel=0.01, parent=cab)
    add_box("CabRoof", (0.94, 0.72, 0.07), (0, 0, 0.44), material=steel, bevel=0.01, parent=cab)
    for rx in (-0.42, 0.42):
        for ry in (-0.30, 0.30):
            add_box(f"CabPost_{rx}_{ry}", (0.045, 0.045, 0.88), (rx, ry, 0.0), material=cyan_glow, bevel=0.005, parent=cab)
    add_box("CabGlassWall", (0.82, 0.60, 0.82), (0, 0, 0.0), material=glass, bevel=0.01, parent=cab)
    add_box("Counterweight", (0.34, 0.20, 0.72), (0.58, 0.02, 0.65), material=brass, bevel=0.012, parent=left)

    # === RIGHT WING (Centered directly inside Desktop Z=0.5..2.4 band, full gear assembly visible) ===
    right = add_empty("RightGearWing", (4.55, 0.30, 0.0))
    right.rotation_euler = (0.0, 0.0, math.radians(-15.0))

    g1 = add_spur_gear("HeroGearBrass", (0.05, 0.12, 1.48), (86, 0, 12), radius=0.92, thickness=0.20, teeth=18, ring_mat=brass, hub_mat=dark_steel, bolt_mat=cyan_glow)
    g1.parent = right
    g2 = add_spur_gear("UpperSteelGear", (1.10, -0.08, 2.25), (86, 0, 28), radius=0.56, thickness=0.18, teeth=12, ring_mat=steel, hub_mat=brass, bolt_mat=cyan_glow)
    g2.parent = right
    g3 = add_spur_gear("LowerSteelGear", (-0.82, -0.15, 0.68), (86, 0, -18), radius=0.55, thickness=0.16, teeth=12, ring_mat=steel, hub_mat=brass, bolt_mat=dark_steel)
    g3.parent = right
    g4 = add_spur_gear("PinionGear", (0.98, 0.22, 0.68), (86, 0, 5), radius=0.42, thickness=0.16, teeth=10, ring_mat=brass, hub_mat=steel, bolt_mat=cyan_glow)
    g4.parent = right

    # Structural trusses spanning Desktop into TV top & bottom regions
    add_box("TrussDiag1", (0.12, 0.12, 5.4), (0.25, 0.55, 1.60), rotation_deg=(0, 28, 0), material=dark_steel, bevel=0.01, parent=right)
    add_box("TrussDiag2", (0.10, 0.10, 5.0), (0.25, 0.55, 1.60), rotation_deg=(0, -28, 0), material=steel, bevel=0.01, parent=right)

    bpy.ops.mesh.primitive_torus_add(
        major_radius=1.42,
        minor_radius=0.015,
        major_segments=64,
        minor_segments=12,
        location=(0.05, -0.25, 1.48),
        rotation=(math.radians(86), 0, 0),
    )
    holo_ring = bpy.context.active_object
    holo_ring.data.materials.append(cyan_glow)
    holo_ring.parent = right

    # Far outer atmospheric cyan blueprint orbs
    add_sphere("LeftOrb", 0.06, (-6.2, 0.6, 2.8), material=cyan_glow)
    add_sphere("RightOrb", 0.06, (6.3, 0.6, 2.7), material=cyan_glow)

    scene.frame_set(1)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out_png)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered 3D banner backdrop -> {out_png}")


if __name__ == "__main__":
    default_out = STUDIO_ROOT / "branding" / "raw_banner_3d.png"
    out_arg = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else default_out
    build_banner_scene(out_arg)
