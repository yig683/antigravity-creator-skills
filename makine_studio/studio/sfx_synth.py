"""Cinematic SFX synthesis, vocal broadcast mastering, and audio mixdown."""

from __future__ import annotations

import json
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np

from .config import FFMPEG_EXE, SFX_DIR

SR = 48000


def _trim_zero_ms(data: np.ndarray, lead_ratio: float = 0.012, tail_ratio: float = 0.004) -> np.ndarray:
    """Trim dead leading/trailing silence so foley hits cleanly at t=0ms."""
    if len(data) == 0:
        return data
    peak = float(np.max(np.abs(data)))
    if peak < 1e-6:
        return data
    lead_idx = np.flatnonzero(np.abs(data) >= peak * lead_ratio)
    tail_idx = np.flatnonzero(np.abs(data) >= peak * tail_ratio)
    start = int(lead_idx[0]) if len(lead_idx) else 0
    end = int(tail_idx[-1]) + 1 if len(tail_idx) else len(data)
    if end <= start:
        return data
    out = data[start:end].copy()
    fade_out = min(120, max(16, len(out) // 12))
    if len(out) > fade_out:
        out[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
    return out


def _load_wav_mono(path: Path, trim_silence: bool = True) -> np.ndarray:
    """Decode any WAV/audio asset to float32 mono at 48kHz using FFmpeg."""
    tmp = path.with_suffix(".tmp48k.wav")
    subprocess.run(
        [
            FFMPEG_EXE,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-ar",
            str(SR),
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            str(tmp),
        ],
        check=True,
    )
    with wave.open(str(tmp), "rb") as wf:
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    tmp.unlink(missing_ok=True)
    return _trim_zero_ms(data) if trim_silence else data


def _master_final_wav(raw_wav: Path, out_wav: Path) -> None:
    """Master mixed track to -14 LUFS broadcast band with soft limiter headroom guard."""
    null_sink = "NUL" if Path("C:/").exists() else "/dev/null"
    p1 = subprocess.run(
        [
            FFMPEG_EXE,
            "-y",
            "-i",
            str(raw_wav),
            "-af",
            "loudnorm=I=-14:TP=-1.2:LRA=7:print_format=json",
            "-f",
            "null",
            null_sink,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    stats: dict[str, Any] = {}
    if p1.returncode == 0:
        m = re.search(r"\{[\s\S]*?\}", p1.stderr)
        if m:
            try:
                stats = json.loads(m.group(0))
            except json.JSONDecodeError:
                stats = {}

    if {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"} <= stats.keys():
        af = (
            "loudnorm=I=-14:TP=-1.2:LRA=7:linear=true:"
            f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
            f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
            f"offset={stats['target_offset']},"
            "alimiter=limit=0.891:attack=3:release=50:level=disabled"
        )
    else:
        af = "loudnorm=I=-14:TP=-1.2:LRA=7,alimiter=limit=0.891:attack=3:release=50:level=disabled"

    p2 = subprocess.run(
        [
            FFMPEG_EXE,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_wav),
            "-af",
            af,
            "-ar",
            str(SR),
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            str(out_wav),
        ],
        check=False,
    )
    if p2.returncode == 0 and out_wav.exists():
        raw_wav.unlink(missing_ok=True)
    else:
        raw_wav.replace(out_wav)


def _master_narration_wav(src_wav: Path, dst_wav: Path) -> np.ndarray:
    """Polish narrator speech with broadcast EQ, light compression, and -15 LUFS loudnorm."""
    af = (
        "highpass=f=85,"
        "equalizer=f=210:t=q:w=1.2:g=1.8,"
        "equalizer=f=3100:t=q:w=1.5:g=2.0,"
        "acompressor=threshold=-20dB:ratio=2.5:attack=12:release=150:makeup=1.5,"
        "loudnorm=I=-15:TP=-2.0:LRA=9"
    )
    subprocess.run(
        [
            FFMPEG_EXE,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src_wav),
            "-af",
            af,
            "-ar",
            str(SR),
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            str(dst_wav),
        ],
        check=True,
    )
    with wave.open(str(dst_wav), "rb") as wf:
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def _synth_alert_ping() -> np.ndarray:
    """Crisp soft double-blip UI warning chime without harsh sine fatigue."""
    n = int(SR * 0.34)
    out = np.zeros(n, dtype=np.float32)
    for start_s, freq in [(0.0, 740.0), (0.11, 988.0)]:
        d = int(SR * 0.16)
        t = np.linspace(0.0, 0.16, d, endpoint=False)
        env = np.minimum(t / 0.008, 1.0) * np.exp(-t * 22.0)
        tone = 0.7 * np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2.0 * t)
        idx = int(start_s * SR)
        out[idx : idx + d] += (tone * env * 0.55).astype(np.float32)
    return out


def _synth_snap_clank() -> np.ndarray:
    """Metallic cable whip snap followed by heavy steel brake jaw lock."""
    n = int(SR * 0.55)
    t = np.linspace(0.0, 0.55, n, endpoint=False)
    rng = np.random.default_rng(77)

    # Sharp initial whip snap at t=0
    whip = rng.normal(0.0, 1.0, n) * np.exp(-t * 45.0) * 0.65
    # Heavy mechanical metallic lock impact at t=0.06s
    t_lock = np.maximum(0.0, t - 0.055)
    mask = (t >= 0.055).astype(np.float32)
    ring = mask * (
        0.55 * np.sin(2 * np.pi * 165.0 * t_lock) * np.exp(-t_lock * 18.0)
        + 0.42 * np.sin(2 * np.pi * 510.0 * t_lock) * np.exp(-t_lock * 24.0)
        + 0.28 * np.sin(2 * np.pi * 1080.0 * t_lock) * np.exp(-t_lock * 32.0)
        + 0.45 * rng.normal(0.0, 1.0, n) * np.exp(-t_lock * 38.0)
    )
    return np.clip(whip + ring, -1.0, 1.0).astype(np.float32)


def _synth_elevator_ding() -> np.ndarray:
    """Warm hotel-style two-tone brass elevator bell."""
    out = np.zeros(int(SR * 1.05), dtype=np.float32)
    for start_s, base_f, dur in [(0.0, 659.25, 0.55), (0.20, 880.0, 0.85)]:
        d = int(SR * dur)
        t = np.linspace(0.0, dur, d, endpoint=False)
        env = np.minimum(t / 0.005, 1.0) * np.exp(-t * 5.2)
        bell = (
            0.65 * np.sin(2 * np.pi * base_f * t)
            + 0.22 * np.sin(2 * np.pi * base_f * 2.0 * t) * np.exp(-t * 4.0)
            + 0.10 * np.sin(2 * np.pi * base_f * 3.0 * t) * np.exp(-t * 8.0)
        )
        idx = int(start_s * SR)
        out[idx : idx + d] += (bell * env * 0.55).astype(np.float32)
    return np.clip(out, -1.0, 1.0)


def _synth_footstep() -> np.ndarray:
    """Muted low-thud stair step tap."""
    d = int(SR * 0.11)
    t = np.linspace(0.0, 0.11, d, endpoint=False)
    rng = np.random.default_rng(19)
    thud = 0.65 * np.sin(2 * np.pi * 115.0 * np.exp(-t * 14.0) * t) * np.exp(-t * 36.0)
    grit = 0.25 * rng.normal(0.0, 1.0, d) * np.exp(-t * 55.0)
    return np.clip(thud + grit, -1.0, 1.0).astype(np.float32)


def _synth_motor_whir() -> np.ndarray:
    """Clean futuristic electric traction motor spin-up ramp (~2.5s)."""
    dur = 2.5
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, endpoint=False)
    freq = 95.0 + 135.0 * (1.0 - np.exp(-t * 1.4))
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    env = np.minimum(t / 0.35, 1.0) * np.clip((dur - t) / 0.5, 0.0, 1.0)
    sig = 0.45 * np.sin(phase) + 0.18 * np.sin(phase * 2.0) + 0.08 * np.sin(phase * 4.0)
    return (sig * env * 0.35).astype(np.float32)


def _synth_elevator_muzak() -> np.ndarray:
    """Short warm electric-piano bossa chord tag for the elevator music joke."""
    dur = 1.95
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, endpoint=False)
    out = np.zeros(n, dtype=np.float32)

    # Warm Cmaj9 -> Fmaj9 jazz lounge elevator progression
    chords = [
        (0.00, 0.72, [261.63, 329.63, 392.00, 493.88, 587.33]),
        (0.68, 0.58, [293.66, 349.23, 440.00, 523.25]),
        (1.22, 0.72, [329.63, 392.00, 493.88, 659.25]),
    ]
    for start_s, cdur, freqs in chords:
        d = int(SR * cdur)
        ct = np.linspace(0.0, cdur, d, endpoint=False)
        env = np.minimum(ct / 0.03, 1.0) * np.exp(-ct * 2.8)
        chord_sig = np.zeros(d, dtype=np.float32)
        for fi, f in enumerate(freqs):
            chord_sig += (0.28 / (1.0 + fi * 0.25)) * np.sin(2.0 * np.pi * f * ct)
        idx = int(start_s * SR)
        end = min(n, idx + d)
        out[idx:end] += (chord_sig[: end - idx] * env[: end - idx] * 0.55).astype(np.float32)

    fade_out = np.clip((dur - t) / 0.35, 0.0, 1.0)
    return np.clip(out * fade_out, -1.0, 1.0).astype(np.float32)


def _synth_clean_bed(duration_sec: float) -> np.ndarray:
    """Ultra-subtle warm ambient pulse + quiet blueprint clock tick (no buzzy hum)."""
    n = int(round(duration_sec * SR))
    t = np.linspace(0.0, duration_sec, n, endpoint=False)
    out = np.zeros(n, dtype=np.float32)

    # Soft muted 90 BPM marimba/tick pulse (gentle transient only, zero continuous drone)
    beat_interval = 60.0 / 90.0
    beat_times = np.arange(0.25, max(0.25, duration_sec - 0.5), beat_interval)
    tick_len = int(SR * 0.12)
    tt = np.linspace(0.0, 0.12, tick_len, endpoint=False)
    tick_env = np.minimum(tt / 0.004, 1.0) * np.exp(-tt * 28.0)

    for bi, bt in enumerate(beat_times):
        idx = int(round(bt * SR))
        if idx + tick_len >= n:
            break
        freq = 146.83 if (bi % 4 == 0) else 196.0
        tone = 0.65 * np.sin(2 * np.pi * freq * tt) + 0.18 * np.sin(2 * np.pi * freq * 2.0 * tt)
        amp = 0.20 if (bi % 4 == 0) else 0.11
        out[idx : idx + tick_len] += (tone * tick_env * amp).astype(np.float32)

    fade_out = np.clip((duration_sec - t) / 0.8, 0.0, 1.0)
    return (out * fade_out).astype(np.float32)


def _load_sfx_bank() -> dict[str, np.ndarray]:
    bank: dict[str, np.ndarray] = {
        "alert": _synth_alert_ping(),
        "clank": _synth_snap_clank(),
        "snap": _synth_snap_clank(),
        "ding": _synth_elevator_ding(),
        "step": _synth_footstep(),
        "motor": _synth_motor_whir(),
        "muzak": _synth_elevator_muzak(),
    }
    for key, fname in [
        ("pop", "pop.wav"),
        ("whoosh", "whoosh.wav"),
        ("boom", "bass_boom.wav"),
        ("riser", "riser.wav"),
        ("step", "step.wav"),
        ("clank", "clank.wav"),
        ("ding", "ding.wav"),
        ("alert", "alert.wav"),
        ("motor", "motor.wav"),
        ("snap", "cable_snap.wav"),
    ]:
        p = SFX_DIR / fname
        if p.exists():
            bank[key] = _load_wav_mono(p, trim_silence=True)
    return bank


def build_master_audio(timeline: dict[str, Any], work_dir: Path) -> Path:
    """Master narration WAV and mix crisp SFX + ducked subtle rhythmic bed."""
    raw_narration = Path(timeline["narration_wav"])
    mastered_narr_path = work_dir / "narration_mastered.wav"
    narr = _master_narration_wav(raw_narration, mastered_narr_path)

    total_samples = len(narr)
    duration_sec = total_samples / float(SR)

    bed = _synth_clean_bed(duration_sec) * 0.25
    sfx_mix = np.zeros(total_samples, dtype=np.float32)
    bank = _load_sfx_bank()

    def add_sfx(name: str, time_sec: float, gain: float = 0.25) -> None:
        clip = bank.get(name)
        if clip is None:
            return
        idx = int(round(max(0.0, time_sec) * SR))
        if idx >= total_samples:
            return
        end = min(total_samples, idx + len(clip))
        sfx_mix[idx:end] += clip[: end - idx] * gain

    for beat in timeline["beats"]:
        if beat["index"] > 0 and "whoosh" in bank:
            add_sfx("whoosh", max(0.0, beat["start"] - 0.12), gain=0.14)
        for cue in beat.get("sfx", []):
            offset = float(cue.get("offset", 0.0))
            # Allow crisp foley transients to punch cleanly while loudnorm+alimiter guards peaks
            gain = min(0.68, float(cue.get("gain", 0.32)) * 0.65)
            add_sfx(cue["name"], beat["start"] + offset, gain=gain)

    # Smooth ducking on bed + gentle SFX ducking during active syllables
    speech_env = np.convolve(np.abs(narr), np.ones(int(SR * 0.14)) / (SR * 0.14), mode="same")
    bed_duck = np.clip(1.0 - speech_env * 3.0, 0.28, 1.0)
    sfx_duck = np.clip(1.0 - speech_env * 1.4, 0.55, 1.0)

    mixed = narr * 0.92 + bed * bed_duck + sfx_mix * sfx_duck

    peak = float(np.max(np.abs(mixed))) if len(mixed) else 1.0
    if peak > 0.94:
        mixed = mixed * (0.92 / peak)

    raw_wav = work_dir / "raw_master_audio.wav"
    out_wav = work_dir / "master_audio.wav"
    pcm16 = np.clip(mixed * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(raw_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm16.tobytes())

    _master_final_wav(raw_wav, out_wav)
    return out_wav
