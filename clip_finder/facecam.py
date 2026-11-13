from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import requests

_YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)


@dataclass
class FramingPlan:
    """Detected optimal 9:16 vertical framing strategy and visual quality hints."""

    mode: Literal["split_cam", "face_center", "full_center"]
    cam_box: tuple[float, float, float, float] | None = None  # normalized (x, y, w, h)
    face_center_x: float = 0.5  # normalized x center for face_center mode
    motion_score: float = 15.0
    has_baked_subs: bool = False
    is_broken_screen: bool = False


def ensure_yunet_model(model_path: str | Path = "assets/models/face_detection_yunet_2023mar.onnx") -> Path | None:
    p = Path(model_path)
    if p.exists() and p.stat().st_size > 100_000:
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(_YUNET_URL, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 100_000:
            p.write_bytes(resp.content)
            return p
    except Exception:
        pass
    return None


def detect_framing_plan(video_path: str | Path) -> FramingPlan:
    """Analyze sampled frames to detect stationary corner webcams vs full-screen face/gameplay."""
    model_path = ensure_yunet_model()
    if not model_path:
        return FramingPlan(mode="full_center")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return FramingPlan(mode="full_center")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 100
    detector = cv2.FaceDetectorYN.create(str(model_path), "", (640, 360), 0.65, 0.3, 50)

    corner_faces: list[tuple[float, float, float, float]] = []
    center_faces: list[tuple[float, float, float, float]] = []
    prev_gray: np.ndarray | None = None
    motion_diffs: list[float] = []
    sub_masks: list[np.ndarray] = []
    broken_frames = 0

    for frac in (0.06, 0.14, 0.22, 0.30, 0.38, 0.46, 0.54, 0.62, 0.70, 0.78, 0.86, 0.94):
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(total_frames * frac), 0))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        small = cv2.resize(frame, (640, 360))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        blocks = gray[:352, :640].astype(np.float32).reshape(22, 16, 40, 16).swapaxes(1, 2).reshape(-1, 256)
        bmean = np.mean(blocks, axis=1)
        bstd = np.std(blocks, axis=1)
        # Only non-black flat blocks catch BRB cards / SMPTE test bars without penalizing dark moody scenes
        bright_flat = float(np.mean((bstd < 1.2) & (bmean >= 28.0)))
        hsv_sm = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        sat_high = float(np.mean((hsv_sm[:, :, 1] > 180) & (hsv_sm[:, :, 2] > 120)))
        if bright_flat >= 0.42 or (bright_flat >= 0.30 and sat_high >= 0.28):
            broken_frames += 1
        if prev_gray is not None:
            motion_diffs.append(float(np.mean(cv2.absdiff(gray, prev_gray))))
        prev_gray = gray

        # Only detect LARGE centered TikTok/Shorts subtitles inside [0.58..0.78] so
        # tiny bottom game cutscene subs or stream tickers (y > 0.80) never suppress ours.
        roi = gray[int(360 * 0.58):int(360 * 0.78), int(640 * 0.22):int(640 * 0.78)]
        edges = cv2.Canny(roi, 140, 255)
        dil = cv2.dilate(edges, np.ones((3, 3), np.uint8))
        sub_masks.append(((roi > 235) & (dil > 0)).astype(np.float32))

        _, faces = detector.detect(small)
        if faces is None:
            continue
        for f in faces:
            x, y, fw, fh, score = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[14])
            if score < 0.70:
                continue
            cx = (x + fw / 2.0) / 640.0
            cy = (y + fh / 2.0) / 360.0
            nw = fw / 640.0
            nh = fh / 360.0

            # Ignore tiny background game NPCs unless in a side/corner webcam zone
            in_edge_x = cx < 0.27 or cx > 0.73
            in_valid_y = 0.08 <= cy <= 0.92
            if in_edge_x and in_valid_y and 0.020 <= nw <= 0.165 and 0.045 <= nh <= 0.25:
                corner_faces.append((cx, cy, nw, nh))
            elif nw >= 0.06 and nh >= 0.12:
                center_faces.append((cx, cy, nw, nh))

    cap.release()

    # Use median frame diff so 1-2 scene cuts don't mask an otherwise static screen
    motion_score = round(float(np.median(motion_diffs)) if motion_diffs else 0.0, 2)
    toggles = [
        float(np.mean(np.abs(sub_masks[i] - sub_masks[i - 1])))
        for i in range(1, len(sub_masks))
    ]
    avg_tog = sum(toggles) / max(len(toggles), 1)
    max_tog = max(toggles, default=0.0)
    has_baked_subs = avg_tog >= 0.032 and max_tog >= 0.060
    is_broken = broken_frames >= 2

    # Confirm a stationary side/corner webcam (allows natural head lean inside cam frame)
    if len(corner_faces) >= 3:
        sides: dict[tuple[bool, bool], list[tuple[float, float, float, float]]] = {}
        for item in corner_faces:
            q = (item[0] > 0.5, item[1] > 0.55)
            sides.setdefault(q, []).append(item)

        best_group = max(sides.values(), key=len)
        if len(best_group) >= 3:
            cxs = [g[0] for g in best_group]
            cys = [g[1] for g in best_group]
            nws = [g[2] for g in best_group]
            nhs = [g[3] for g in best_group]
            is_stationary = (
                (max(cxs) - min(cxs)) <= 0.12
                and (max(cys) - min(cys)) <= 0.14
                and (max(nws) - min(nws)) <= 0.06
            )
            if is_stationary:
                avg_cx = sum(cxs) / len(best_group)
                avg_cy = sum(cys) / len(best_group)
                avg_w = sum(nws) / len(best_group)
                avg_h = sum(nhs) / len(best_group)

                # Frame webcam cleanly around head+shoulders even for small corner cams
                box_w = min(max(avg_w * 2.55, 0.16), 0.25)
                box_h = min(max(avg_h * 2.15, 0.20), 0.30)
                target_cy = avg_cy + avg_h * 0.10
                bx = max(0.0, min(avg_cx - box_w / 2.0, 1.0 - box_w))
                by = max(0.0, min(target_cy - box_h / 2.0, 1.0 - box_h))
                if bx < 0.03:
                    bx = 0.012
                if bx + box_w > 0.97:
                    bx = 0.988 - box_w
                if by < 0.03:
                    by = 0.012
                if by + box_h > 0.97:
                    by = 0.988 - box_h

                return FramingPlan(
                    mode="split_cam",
                    cam_box=(bx, by, box_w, box_h),
                    motion_score=motion_score,
                    has_baked_subs=has_baked_subs,
                    is_broken_screen=is_broken,
                )

    if len(center_faces) >= 2:
        sorted_cx = sorted(g[0] for g in center_faces)
        med_cx = sorted_cx[len(sorted_cx) // 2]
        return FramingPlan(
            mode="face_center",
            face_center_x=max(0.22, min(med_cx, 0.78)),
            motion_score=motion_score,
            has_baked_subs=has_baked_subs,
            is_broken_screen=is_broken,
        )

    return FramingPlan(
        mode="full_center",
        motion_score=motion_score,
        has_baked_subs=has_baked_subs,
        is_broken_screen=is_broken,
    )
