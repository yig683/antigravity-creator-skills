"""Portable short-form QA inspector: checks stream specs, LUFS/peak loudness, and renders visual QA frames."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def run_qa(video_path: Path, out_dir: Path) -> int:
    if not video_path.exists():
        print(f"Video not found: {video_path}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== FFPROBE: {video_path.name} ===")
    subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
            "-show_entries",
            "format=duration,bit_rate",
            "-of",
            "default=noprint_wrappers=1",
            str(video_path),
        ],
        check=True,
    )

    print("\n=== VOLUMEDETECT ===")
    vol = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    for line in vol.stderr.splitlines():
        if "mean_volume" in line or "max_volume" in line:
            print(line.strip())

    snaps = [
        ("qa_beat1.png", "0.35"),
        ("qa_beat2.png", "1.05"),
        ("qa_beat3.png", "1.95"),
    ]
    for fname, ts in snaps:
        dst = out_dir / fname
        subprocess.run(
            ["ffmpeg", "-y", "-ss", ts, "-i", str(video_path), "-frames:v", "1", str(dst), "-loglevel", "error"],
            check=True,
        )

    sheet = out_dir / "qa_sheet.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "fps=1/3.8,scale=270:480,tile=6x3",
            "-frames:v",
            "1",
            str(sheet),
            "-loglevel",
            "error",
        ],
        check=True,
    )
    print(f"\nSaved visual QA frames to: {out_dir.resolve()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect short-form vertical video specs, loudness, and visual frames.")
    parser.add_argument("video", type=Path, help="Path to rendered MP4 file")
    parser.add_argument("--out-dir", type=Path, default=Path("qa_frames"), help="Output directory for PNG checks")
    args = parser.parse_args()
    return run_qa(args.video, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
