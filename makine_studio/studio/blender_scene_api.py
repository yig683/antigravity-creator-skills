"""Reusable Blender 5.2 3D stage, lighting, articulated mannequin, and HUD projection API."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import bpy
import bpy_extras
from mathutils import Vector


def reset_scene(
    res_x: int = 1080,
    res_y: int = 1040,
    fps: int = 24,
    samples: int = 16,
) -> bpy.types.Scene:
    """Clear the scene and configure Blender EEVEE for fast GPU rendering."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    scene.eevee.taa_render_samples = samples
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = False

    # Clean vibrant color management
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.05
    return scene


def setup_world_and_lighting(
    sky_color: tuple[float, float, float] = (0.025, 0.068, 0.135),
    key_energy: float = 4.2,
) -> None:
    """Create blueprint-matched dark navy sky and dramatic studio 3-point lighting."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new("BlueprintWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (*sky_color, 1.0)
        bg.inputs["Strength"].default_value = 0.9

    # Warm directional sun key light casting long shadows
    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = key_energy
    key_data.color = (1.0, 0.95, 0.88)
    key_data.angle = math.radians(3.0)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.rotation_euler = (math.radians(52), math.radians(18), math.radians(-38))

    # Cool blue fill area light from opposite side
    fill_data = bpy.data.lights.new("CoolFill", type="AREA")
    fill_data.energy = 260.0
    fill_data.size = 10.0
    fill_data.color = (0.45, 0.72, 1.0)
    fill_obj = bpy.data.objects.new("CoolFill", fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-8.0, -6.0, 7.0)
    fill_obj.rotation_euler = (math.radians(55), 0.0, math.radians(-45))

    # Subtle cyan back rim light to separate character & steel edges from dark sky
    rim_data = bpy.data.lights.new("RimLight", type="AREA")
    rim_data.energy = 320.0
    rim_data.size = 8.0
    rim_data.color = (0.55, 0.86, 1.0)
    rim_obj = bpy.data.objects.new("RimLight", rim_data)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = (2.0, 9.0, 8.0)
    rim_obj.rotation_euler = (math.radians(-50), 0.0, 0.0)


def make_material(
    name: str,
    color: tuple[float, float, float],
    metallic: float = 0.0,
    roughness: float = 0.5,
    emission: tuple[float, float, float] | None = None,
    emission_strength: float = 0.0,
    alpha: float = 1.0,
    noise_bump: float = 0.0,
    noise_scale: float = 18.0,
) -> bpy.types.Material:
    """Create a Blender 5.2 Principled BSDF material with optional procedural surface texture."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0 and hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.5
    if emission is not None and emission_strength > 0 and "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength

    if noise_bump > 0:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise_scale
        tex.inputs["Detail"].default_value = 6.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = noise_bump
        bump.inputs["Distance"].default_value = 0.04
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

        # Subtle color variation driven by noise
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (
            max(0.0, color[0] * 0.78),
            max(0.0, color[1] * 0.78),
            max(0.0, color[2] * 0.78),
            1.0,
        )
        ramp.color_ramp.elements[1].color = (
            min(1.0, color[0] * 1.15),
            min(1.0, color[1] * 1.15),
            min(1.0, color[2] * 1.15),
            1.0,
        )
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    return mat


def _apply_smooth_bevel(obj: bpy.types.Object, bevel_width: float = 0.0, smooth: bool = True) -> None:
    if bevel_width > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel_width
        mod.segments = 2
        mod.limit_method = "ANGLE"
    if smooth and obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = True


def add_box(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float] = (0, 0, 0),
    rotation_deg: tuple[float, float, float] = (0, 0, 0),
    material: bpy.types.Material | None = None,
    bevel: float = 0.012,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    obj.rotation_euler = tuple(math.radians(a) for a in rotation_deg)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    _apply_smooth_bevel(obj, bevel_width=bevel, smooth=False)
    if parent:
        obj.parent = parent
    return obj


def add_cylinder(
    name: str,
    radius: float,
    depth: float,
    location: tuple[float, float, float] = (0, 0, 0),
    rotation_deg: tuple[float, float, float] = (0, 0, 0),
    vertices: int = 24,
    material: bpy.types.Material | None = None,
    bevel: float = 0.0,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=tuple(math.radians(a) for a in rotation_deg),
    )
    obj = bpy.context.active_object
    obj.name = name
    if material:
        obj.data.materials.append(material)
    _apply_smooth_bevel(obj, bevel_width=bevel, smooth=True)
    if parent:
        obj.parent = parent
    return obj


def add_sphere(
    name: str,
    radius: float,
    location: tuple[float, float, float] = (0, 0, 0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    segments: int = 24,
    material: bpy.types.Material | None = None,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=16,
        radius=radius,
        location=location,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    _apply_smooth_bevel(obj, bevel_width=0.0, smooth=True)
    if parent:
        obj.parent = parent
    return obj


def add_empty(
    name: str,
    location: tuple[float, float, float] = (0, 0, 0),
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.empty_display_size = 0.15
    if parent:
        obj.parent = parent
    return obj


def set_keyframe(
    obj: bpy.types.Object,
    frame: int,
    location: tuple[float, float, float] | None = None,
    rotation_deg: tuple[float, float, float] | None = None,
    scale: tuple[float, float, float] | None = None,
) -> None:
    if location is not None:
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame)
    if rotation_deg is not None:
        obj.rotation_euler = tuple(math.radians(a) for a in rotation_deg)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def set_visibility(obj: bpy.types.Object, frame: int, visible: bool) -> None:
    """Toggle render and viewport visibility at a specific frame (recursive for hierarchy)."""
    obj.hide_render = not visible
    obj.hide_viewport = not visible
    obj.keyframe_insert(data_path="hide_render", frame=frame)
    obj.keyframe_insert(data_path="hide_viewport", frame=frame)
    for child in obj.children:
        set_visibility(child, frame, visible)


def attach_follow_location(obj: bpy.types.Object, target: bpy.types.Object) -> None:
    """Pin an object's world position to target while keeping vertical gravity orientation."""
    con = obj.constraints.new(type="COPY_LOCATION")
    con.target = target


class CameraRig:
    """Smooth tracked camera controller."""

    def __init__(self, lens: float = 38.0) -> None:
        self.target = add_empty("CamTarget", (0.0, 0.0, 1.2))
        cam_data = bpy.data.cameras.new("MainCamera")
        cam_data.lens = lens
        cam_data.clip_start = 0.05
        cam_data.clip_end = 250.0
        self.cam = bpy.data.objects.new("MainCamera", cam_data)
        bpy.context.collection.objects.link(self.cam)
        self.cam.location = (0.0, -7.5, 2.2)

        track = self.cam.constraints.new(type="TRACK_TO")
        track.target = self.target
        track.track_axis = "TRACK_NEGATIVE_Z"
        track.up_axis = "UP_Y"
        bpy.context.scene.camera = self.cam

    def key(
        self,
        frame: int,
        location: tuple[float, float, float],
        target: tuple[float, float, float],
        lens: float | None = None,
    ) -> None:
        set_keyframe(self.cam, frame, location=location)
        set_keyframe(self.target, frame, location=target)
        if lens is not None:
            self.cam.data.lens = lens
            self.cam.data.keyframe_insert(data_path="lens", frame=frame)


class MannequinRig:
    """Articulated off-white 3D clay mannequin matching @makineleşelim style."""

    def __init__(self, name: str = "Mannequin", scale_factor: float = 1.0) -> None:
        self.name = name
        self.root = add_empty(f"{name}_Root", (0, 0, 0))
        self.root.scale = (scale_factor, scale_factor, scale_factor)

        body_mat = make_material(
            "MannequinClay",
            color=(0.78, 0.80, 0.84),
            metallic=0.02,
            roughness=0.40,
        )
        joint_mat = make_material(
            "MannequinJoint",
            color=(0.62, 0.65, 0.70),
            metallic=0.05,
            roughness=0.45,
        )
        shoe_mat = make_material(
            "MannequinShoe",
            color=(0.07, 0.07, 0.09),
            metallic=0.05,
            roughness=0.48,
        )

        # Spine hierarchy (Z=0 is ground under shoes; hip pivot at Z=0.90)
        self.pelvis = add_empty(f"{name}_Pelvis", (0, 0, 0.90), parent=self.root)
        add_sphere(f"{name}_PelvisMesh", 0.13, (0, 0, 0.02), (1.15, 0.85, 0.95), material=body_mat, parent=self.pelvis)

        self.torso = add_empty(f"{name}_Torso", (0, 0, 0.14), parent=self.pelvis)
        add_sphere(f"{name}_WaistMesh", 0.12, (0, 0, 0.08), (1.05, 0.80, 1.05), material=body_mat, parent=self.torso)
        add_sphere(f"{name}_ChestMesh", 0.16, (0, 0, 0.25), (1.18, 0.82, 1.25), material=body_mat, parent=self.torso)

        self.head = add_empty(f"{name}_Head", (0, 0, 0.44), parent=self.torso)
        add_cylinder(f"{name}_NeckMesh", 0.045, 0.09, (0, 0, 0.03), material=joint_mat, parent=self.head)
        add_sphere(f"{name}_HeadMesh", 0.115, (0, 0, 0.16), (0.88, 0.95, 1.15), material=body_mat, parent=self.head)
        self.alert_anchor = add_empty(f"{name}_AlertAnchor", (0, 0, 0.44), parent=self.head)

        # Arms
        self.shoulders: dict[str, bpy.types.Object] = {}
        self.elbows: dict[str, bpy.types.Object] = {}
        self.hands: dict[str, bpy.types.Object] = {}
        for side, sign in [("L", -1.0), ("R", 1.0)]:
            sh = add_empty(f"{name}_Shoulder_{side}", (sign * 0.21, 0, 0.34), parent=self.torso)
            add_sphere(f"{name}_ShCap_{side}", 0.055, (0, 0, 0), material=joint_mat, parent=sh)
            add_cylinder(f"{name}_UpperArm_{side}", 0.048, 0.25, (0, 0, -0.13), material=body_mat, parent=sh)

            el = add_empty(f"{name}_Elbow_{side}", (0, 0, -0.26), parent=sh)
            add_sphere(f"{name}_ElCap_{side}", 0.045, (0, 0, 0), material=joint_mat, parent=el)
            add_cylinder(f"{name}_Forearm_{side}", 0.042, 0.24, (0, 0, -0.12), material=body_mat, parent=el)
            add_sphere(f"{name}_Hand_{side}", 0.048, (0, 0, -0.26), (0.85, 0.85, 1.10), material=body_mat, parent=el)
            grip = add_empty(f"{name}_HandGrip_{side}", (0.0, -0.02, -0.27), parent=el)

            self.shoulders[side] = sh
            self.elbows[side] = el
            self.hands[side] = grip

        # Legs
        self.hips: dict[str, bpy.types.Object] = {}
        self.knees: dict[str, bpy.types.Object] = {}
        self.ankles: dict[str, bpy.types.Object] = {}
        for side, sign in [("L", -1.0), ("R", 1.0)]:
            hp = add_empty(f"{name}_Hip_{side}", (sign * 0.10, 0, -0.02), parent=self.pelvis)
            add_sphere(f"{name}_HipCap_{side}", 0.062, (0, 0, 0), material=joint_mat, parent=hp)
            add_cylinder(f"{name}_Thigh_{side}", 0.062, 0.39, (0, 0, -0.20), material=body_mat, parent=hp)

            kn = add_empty(f"{name}_Knee_{side}", (0, 0, -0.41), parent=hp)
            add_sphere(f"{name}_KneeCap_{side}", 0.052, (0, 0, 0), material=joint_mat, parent=kn)
            add_cylinder(f"{name}_Shin_{side}", 0.050, 0.39, (0, 0, -0.20), material=body_mat, parent=kn)

            ak = add_empty(f"{name}_Ankle_{side}", (0, 0, -0.41), parent=kn)
            # Rounded dark shoe oriented forward (-Y is toward camera if facing front; +Y is forward in Blender?
            # We define character local forward as -Y so default front/3/4 view sees face and front of shoes!)
            add_box(
                f"{name}_Shoe_{side}",
                (0.095, 0.18, 0.075),
                (0, -0.04, -0.02),
                material=shoe_mat,
                bevel=0.025,
                parent=ak,
            )

            self.hips[side] = hp
            self.knees[side] = kn
            self.ankles[side] = ak

    def key_pose(
        self,
        frame: int,
        pelvis_z_offset: float = 0.0,
        pelvis_rot: tuple[float, float, float] = (0, 0, 0),
        torso_rot: tuple[float, float, float] = (0, 0, 0),
        head_rot: tuple[float, float, float] = (0, 0, 0),
        sh_l: tuple[float, float, float] = (0, 12, 0),
        el_l: tuple[float, float, float] = (-18, 0, 0),
        sh_r: tuple[float, float, float] = (0, -12, 0),
        el_r: tuple[float, float, float] = (-18, 0, 0),
        hip_l: tuple[float, float, float] = (0, 0, 0),
        knee_l: tuple[float, float, float] = (0, 0, 0),
        hip_r: tuple[float, float, float] = (0, 0, 0),
        knee_r: tuple[float, float, float] = (0, 0, 0),
        ankle_l: tuple[float, float, float] = (0, 0, 0),
        ankle_r: tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        set_keyframe(self.pelvis, frame, location=(0, 0, 0.90 + pelvis_z_offset), rotation_deg=pelvis_rot)
        set_keyframe(self.torso, frame, rotation_deg=torso_rot)
        set_keyframe(self.head, frame, rotation_deg=head_rot)
        set_keyframe(self.shoulders["L"], frame, rotation_deg=sh_l)
        set_keyframe(self.elbows["L"], frame, rotation_deg=el_l)
        set_keyframe(self.shoulders["R"], frame, rotation_deg=sh_r)
        set_keyframe(self.elbows["R"], frame, rotation_deg=el_r)
        set_keyframe(self.hips["L"], frame, rotation_deg=hip_l)
        set_keyframe(self.knees["L"], frame, rotation_deg=knee_l)
        set_keyframe(self.hips["R"], frame, rotation_deg=hip_r)
        set_keyframe(self.knees["R"], frame, rotation_deg=knee_r)
        set_keyframe(self.ankles["L"], frame, rotation_deg=ankle_l)
        set_keyframe(self.ankles["R"], frame, rotation_deg=ankle_r)

    def animate_climb_cycle(
        self,
        frame_start: int,
        frame_end: int,
        step_frames: int | None = None,
        fatigue: float = 0.0,
        fps: int = 30,
    ) -> None:
        """Keyframe climbing/walking step cycles across [frame_start, frame_end]."""
        stride = step_frames if step_frames is not None else max(2, round(0.28 * fps))
        f = frame_start
        phase = 0
        while f <= frame_end:
            frac = (f - frame_start) / max(1, (frame_end - frame_start))
            tire = fatigue * frac
            lean = 12.0 + 22.0 * tire  # +X tilts +Z spine forward (-Y)
            bob = -0.05 * abs(math.sin(phase * math.pi * 0.5)) - 0.04 * tire

            if phase % 2 == 0:
                hl, kl, hr, kr = (-42, 68, 16, 18)
                sl, sr = (20 - 10 * tire, -26 - 10 * tire)
            else:
                hl, kl, hr, kr = (16, 18, -42, 68)
                sl, sr = (-26 - 10 * tire, 20 - 10 * tire)

            self.key_pose(
                f,
                pelvis_z_offset=bob,
                torso_rot=(lean, 0, 0),
                head_rot=(-8.0 + 18.0 * tire, 0, 0),
                sh_l=(sl, 14, 0),
                el_l=(-45, 0, 0),
                sh_r=(sr, -14, 0),
                el_r=(-45, 0, 0),
                hip_l=(hl, 0, 0),
                knee_l=(kl, 0, 0),
                hip_r=(hr, 0, 0),
                knee_r=(kr, 0, 0),
            )
            f += stride
            phase += 1

    def animate_exhausted(self, frame: int) -> None:
        """Bent forward clutching knees / lower back in exhaustion."""
        self.key_pose(
            frame,
            pelvis_z_offset=-0.12,
            pelvis_rot=(10, 0, 0),
            torso_rot=(44, 0, 0),
            head_rot=(12, 0, 0),
            sh_l=(-45, 8, -14),
            el_l=(-55, 0, 0),
            sh_r=(-45, -8, 14),
            el_r=(-55, 0, 0),
            hip_l=(-28, 0, 0),
            knee_l=(46, 0, 0),
            hip_r=(-22, 0, 0),
            knee_r=(38, 0, 0),
        )

    def animate_pull_rope_cycle(
        self,
        frame_start: int,
        frame_end: int,
        step_frames: int | None = None,
        fps: int = 30,
    ) -> None:
        """Frantic rope-pulling cycle (reaching up and yanking down)."""
        stride = step_frames if step_frames is not None else max(2, round(0.28 * fps))
        f = frame_start
        phase = 0
        while f <= frame_end:
            if phase % 2 == 0:
                self.key_pose(
                    f,
                    pelvis_z_offset=-0.04,
                    torso_rot=(-8, 0, 0),
                    head_rot=(-22, 0, 0),
                    sh_l=(-135, 8, 10),
                    el_l=(-25, 0, 0),
                    sh_r=(-95, -8, -10),
                    el_r=(-45, 0, 0),
                    hip_l=(-18, 0, 0),
                    knee_l=(32, 0, 0),
                    hip_r=(14, 0, 0),
                    knee_r=(16, 0, 0),
                )
            else:
                self.key_pose(
                    f,
                    pelvis_z_offset=-0.12,
                    torso_rot=(16, 0, 0),
                    head_rot=(-12, 0, 0),
                    sh_l=(-75, 10, 12),
                    el_l=(-70, 0, 0),
                    sh_r=(-130, -10, -12),
                    el_r=(-25, 0, 0),
                    hip_l=(-22, 0, 0),
                    knee_l=(40, 0, 0),
                    hip_r=(12, 0, 0),
                    knee_r=(20, 0, 0),
                )
            f += stride
            phase += 1

    def animate_panic(self, frame_start: int, frame_end: int, fps: int = 30) -> None:
        """Arms thrown up in shock during free-fall/snap beats."""
        stride = max(2, round(0.21 * fps))
        f = frame_start
        phase = 0
        while f <= frame_end:
            wobble = 6.0 if phase % 2 == 0 else -6.0
            self.key_pose(
                f,
                pelvis_z_offset=-0.06,
                torso_rot=(-6, wobble, 0),
                head_rot=(-18, -wobble, 0),
                sh_l=(-148, 22, -15),
                el_l=(-25, 0, 0),
                sh_r=(-148, -22, 15),
                el_r=(-25, 0, 0),
                hip_l=(-24, 0, 0),
                knee_l=(44, 0, 0),
                hip_r=(-20, 0, 0),
                knee_r=(38, 0, 0),
            )
            f += stride
            phase += 1

    def animate_relaxed_celebrate(self, frame_start: int, frame_end: int, fps: int = 30) -> None:
        """Relaxed victorious pose riding smoothly inside final elevator."""
        stride = max(2, round(0.25 * fps))
        f = frame_start
        phase = 0
        while f <= frame_end:
            wave = -115 + 14 * math.sin(phase * 1.1)
            self.key_pose(
                f,
                pelvis_z_offset=0.0,
                torso_rot=(0, 0, 0),
                head_rot=(4, 0, 8 * math.sin(phase * 0.7)),
                sh_l=(0, 12, 0),
                el_l=(-18, 0, 0),
                sh_r=(wave, -26, 0),
                el_r=(-35, 0, 0),
                hip_l=(0, 0, 0),
                knee_l=(4, 0, 0),
                hip_r=(0, 0, 0),
                knee_r=(4, 0, 0),
            )
            f += stride
            phase += 1


class HUDTracker:
    """Collects 3D anchor objects and exports screen-space coordinates per frame."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(
        self,
        item_id: str,
        anchor: bpy.types.Object,
        kind: str,
        frame_start: int,
        frame_end: int,
        label: str = "",
        color: str = "cyan",
        offset_px: tuple[int, int] = (140, -90),
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.items.append(
            {
                "id": item_id,
                "anchor_name": anchor.name,
                "kind": kind,
                "label": label,
                "color": color,
                "frame_start": int(frame_start),
                "frame_end": int(frame_end),
                "offset_px": list(offset_px),
                "extra": extra or {},
            }
        )

    def export(self, scene: bpy.types.Scene, cam: bpy.types.Object, out_path: Path) -> None:
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        frames_data: dict[str, list[dict[str, Any]]] = {}

        for f in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            active: list[dict[str, Any]] = []
            for item in self.items:
                if not (item["frame_start"] <= f <= item["frame_end"]):
                    continue
                obj = bpy.data.objects.get(item["anchor_name"])
                if obj is None:
                    continue
                world_pos = obj.matrix_world.translation
                ndc = bpy_extras.object_utils.world_to_camera_view(scene, cam, world_pos)
                if ndc.z <= 0:
                    continue
                px = float(ndc.x * res_x)
                py = float((1.0 - ndc.y) * res_y)
                if -120 <= px <= res_x + 120 and -120 <= py <= res_y + 120:
                    active.append(
                        {
                            "id": item["id"],
                            "kind": item["kind"],
                            "label": item["label"],
                            "color": item["color"],
                            "x": round(px, 1),
                            "y": round(py, 1),
                            "offset_px": item["offset_px"],
                            "extra": item["extra"],
                        }
                    )
            frames_data[str(f)] = active

        out_path.write_text(
            json.dumps({"res_x": res_x, "res_y": res_y, "frames": frames_data}, ensure_ascii=False),
            encoding="utf-8",
        )
