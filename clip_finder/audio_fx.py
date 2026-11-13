from __future__ import annotations

import math
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class AudioSegment:
    start: float
    end: float
    is_silent: bool


@dataclass
class AudioAnalysis:
    duration: float
    hype_peaks: list[float]
    climax_time: float | None
    segments: list[AudioSegment]


def _write_wav_mono(path: Path, samples: np.ndarray, sample_rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def _pink_noise(rng: np.random.Generator, n: int, sr: int = 44100) -> np.ndarray:
    """Generate warm 1/f pink noise via FFT spectral shaping (no harsh white-noise hiss)."""
    white = rng.normal(0.0, 1.0, n)
    spec = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    scale = 1.0 / np.sqrt(np.maximum(freqs, 24.0))
    scale[0] = 0.0
    pink = np.fft.irfft(spec * scale, n=n)
    peak = np.max(np.abs(pink)) or 1.0
    return pink / peak


def _fft_band(sig: np.ndarray, sr: int, f_lo: float, f_hi: float) -> np.ndarray:
    """Soft cosine-tapered FFT bandpass filter for natural studio foley textures."""
    n = len(sig)
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    lo_edge = np.clip((freqs - f_lo * 0.65) / max(f_lo * 0.70, 1.0), 0.0, 1.0)
    hi_edge = np.clip((f_hi * 1.45 - freqs) / max(f_hi * 0.75, 1.0), 0.0, 1.0)
    mask = (0.5 - 0.5 * np.cos(np.pi * lo_edge)) * (0.5 - 0.5 * np.cos(np.pi * hi_edge))
    return np.fft.irfft(spec * mask, n=n)


def ensure_sfx_pack(sfx_dir: str | Path = "assets/sfx") -> dict[str, Path]:
    """Provide real royalty-free studio SFX (Mixkit CC/free WAVs trimmed to 0ms onset) + offline fallback."""
    import shutil

    out = Path(sfx_dir)
    out.mkdir(parents=True, exist_ok=True)
    studio_dir = Path(__file__).resolve().parent.parent / "assets" / "sfx" / "studio"
    marker = out / ".v8_studio"
    required = ("bass_boom", "whoosh", "pop", "lock_clack", "glitch", "riser", "hype_bed")

    if studio_dir.exists() and all((studio_dir / f"{k}.wav").exists() for k in required):
        result: dict[str, Path] = {}
        need_sync = not marker.exists()
        for key in required:
            src = studio_dir / f"{key}.wav"
            dst = out / f"{key}.wav"
            if need_sync or not dst.exists() or dst.stat().st_size != src.stat().st_size:
                if src.resolve() != dst.resolve():
                    shutil.copy2(src, dst)
            result[key] = dst
        if need_sync:
            for old_m in (out / ".v4_studio", out / ".v5_cinema", out / ".v6_punch"):
                if old_m.exists():
                    old_m.unlink(missing_ok=True)
            marker.write_text("v8_studio", encoding="utf-8")
        return result

    sr = 44100
    rebuild = not marker.exists()

    # 1. Viral Vine-Boom + Cinema Sub Impact (0.50s) - saturated mid-punch (audible on PC speakers) + deep sub
    boom_path = out / "bass_boom.wav"
    if rebuild or not boom_path.exists():
        dur = 0.50
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        sub_f = 42.0 + 115.0 * np.exp(-t * 22.0)
        sub_ph = 2.0 * np.pi * np.cumsum(sub_f) / sr
        sub = np.tanh(np.sin(sub_ph) * 2.1) * np.exp(-t * 5.2)
        chest_f = 135.0 + 180.0 * np.exp(-t * 36.0)
        chest = np.tanh(np.sin(2.0 * np.pi * np.cumsum(chest_f) / sr) * 2.4) * np.exp(-t * 14.0)
        crack = _fft_band(_pink_noise(np.random.default_rng(11), n, sr), sr, 180.0, 1400.0) * np.exp(-t * 26.0)
        env = np.minimum(t / 0.003, 1.0)
        thump = (sub * 1.15 + chest * 0.95 + crack * 0.55) * env
        peak = np.max(np.abs(thump)) or 1.0
        _write_wav_mono(boom_path, (thump / peak) * 0.94, sr)

    # 2. Snappy Doppler Whip Whoosh (0.24s) - resonant pitch-swept air cut
    whoosh_path = out / "whoosh.wav"
    if rebuild or not whoosh_path.exists():
        dur = 0.24
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        u = t / dur
        noise = _pink_noise(np.random.default_rng(42), n, sr)
        b_low = _fft_band(noise, sr, 240.0, 760.0)
        b_mid = _fft_band(noise, sr, 650.0, 2100.0)
        b_hi = _fft_band(noise, sr, 1800.0, 5200.0)
        swish_f = 980.0 - 720.0 * (u ** 0.8)
        swish = np.sin(2.0 * np.pi * np.cumsum(swish_f) / sr) * 0.35
        w_mid = np.sin(np.pi * u) ** 1.05
        w_hi = np.sin(np.pi * np.clip((u - 0.12) / 0.72, 0.0, 1.0)) ** 1.8
        env = (np.sin(np.pi * u) ** 0.95) * np.minimum(t / 0.006, 1.0)
        whoosh = (b_low * 0.75 + b_mid * w_mid * 1.25 + b_hi * w_hi * 1.1 + swish * w_mid) * env
        peak = np.max(np.abs(whoosh)) or 1.0
        _write_wav_mono(whoosh_path, (whoosh / peak) * 0.90, sr)

    # 3. Crisp UI Pop (0.045s)
    pop_path = out / "pop.wav"
    if rebuild or not pop_path.exists():
        dur = 0.045
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        pop_tone = np.sin(2.0 * np.pi * (420.0 * np.exp(-t * 35.0) + 180.0) * t)
        tap = _fft_band(_pink_noise(np.random.default_rng(19), n, sr), sr, 350.0, 1600.0)
        env = np.minimum(t / 0.002, 1.0) * np.exp(-t * 55.0)
        raw_p = (pop_tone * 0.7 + tap * 0.6) * env
        peak = np.max(np.abs(raw_p)) or 1.0
        _write_wav_mono(pop_path, (raw_p / peak) * 0.65, sr)

    # 4. Vault Lock Double-Clack + Bright Alert Chime (0.28s)
    lock_path = out / "lock_clack.wav"
    if rebuild or not lock_path.exists():
        dur = 0.28
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        rng = np.random.default_rng(77)
        c1_raw = _fft_band(_pink_noise(rng, n, sr), sr, 900.0, 4200.0) * np.exp(-t * 75.0)
        t2 = np.maximum(t - 0.055, 0.0)
        gate2 = (t >= 0.055).astype(np.float64)
        c2_hi = _fft_band(_pink_noise(rng, n, sr), sr, 600.0, 3200.0) * np.exp(-t2 * 55.0) * gate2
        c2_body = np.sin(2.0 * np.pi * 165.0 * t2) * np.exp(-t2 * 32.0) * gate2
        ping1 = np.sin(2.0 * np.pi * 880.0 * t) * np.exp(-t * 28.0) * 0.45
        ping2 = np.sin(2.0 * np.pi * 1318.5 * t2) * np.exp(-t2 * 22.0) * gate2 * 0.60
        clack = c1_raw * 0.85 + c2_hi * 1.05 + c2_body * 0.85 + ping1 + ping2
        peak = np.max(np.abs(clack)) or 1.0
        _write_wav_mono(lock_path, (clack / peak) * 0.92, sr)

    # 5. Tension Cinema Synth + Air Riser Swell (1.10s)
    riser_path = out / "riser.wav"
    if rebuild or not riser_path.exists():
        dur = 1.10
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        u = t / dur
        noise = _pink_noise(np.random.default_rng(7), n, sr)
        r_mid = _fft_band(noise, sr, 380.0, 1800.0)
        r_hi = _fft_band(noise, sr, 1500.0, 4800.0)
        pitch = 190.0 + 780.0 * (u ** 1.75)
        ph = 2.0 * np.pi * np.cumsum(pitch) / sr
        synth = (0.55 * np.sin(ph) + 0.30 * np.sin(2.0 * ph) + 0.15 * np.tanh(2.0 * np.sin(0.5 * ph))) * (u ** 1.1)
        pulse = 0.72 + 0.28 * np.sin(2.0 * np.pi * (4.5 + 8.5 * u) * t)
        mix = (r_mid * (u ** 0.75) * 0.85 + r_hi * (u ** 1.6) * 1.05 + synth * 0.90) * pulse
        env = (u ** 1.4) * np.minimum((dur - t) / 0.020, 1.0)
        riser = mix * env
        peak = np.max(np.abs(riser)) or 1.0
        _write_wav_mono(riser_path, (riser / peak) * 0.88, sr)

    # 6. Speaker-Audible 120 BPM Vice-City Trap/Synthwave Beat Loop (4.0s, zero copyright risk)
    bed_path = out / "hype_bed.wav"
    if rebuild or not bed_path.exists():
        dur = 4.0
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        sig = np.zeros(n, dtype=np.float64)
        rng = np.random.default_rng(108)

        for beat_idx in range(8):
            bt = beat_idx * 0.50
            k_start = int(bt * sr)
            k_len = min(int(0.20 * sr), n - k_start)
            kt = np.arange(k_len) / sr
            kf = 52.0 + 128.0 * np.exp(-kt * 28.0)
            k_phase = 2.0 * np.pi * np.cumsum(kf) / sr
            kick = np.tanh(np.sin(k_phase) * 1.85) * np.minimum(kt / 0.003, 1.0) * np.exp(-kt * 14.0)
            sig[k_start : k_start + k_len] += kick * 0.65

            if beat_idx % 2 == 1:
                c_len = min(int(0.14 * sr), n - k_start)
                ct = np.arange(c_len) / sr
                clap_tone = np.sin(2.0 * np.pi * 210.0 * ct) * np.exp(-ct * 35.0)
                clap_snap = _fft_band(_pink_noise(rng, c_len, sr), sr, 1200.0, 4800.0) * np.exp(-ct * 26.0)
                clap_p = np.max(np.abs(clap_snap)) or 1.0
                sig[k_start : k_start + c_len] += clap_tone * 0.38 + (clap_snap / clap_p) * 0.44

            for sub_off in (0.125, 0.25, 0.375):
                ht_start = int((bt + sub_off) * sr)
                if ht_start >= n:
                    continue
                h_len = min(int(0.042 * sr), n - ht_start)
                ht = np.arange(h_len) / sr
                hat = _fft_band(_pink_noise(rng, h_len, sr), sr, 2400.0, 6200.0) * np.exp(-ht * 70.0)
                hp = np.max(np.abs(hat)) or 1.0
                vel = 0.24 if sub_off == 0.25 else 0.11
                sig[ht_start : ht_start + h_len] += (hat / hp) * vel

        # Dark Vice-City Synthwave Pluck Arp (A minor: A3..G4, audible on PC & laptop speakers)
        arp_freqs = [220.0, 261.63, 329.63, 392.0, 329.63, 261.63, 220.0, 246.94] * 2
        step_dur = dur / len(arp_freqs)
        for s_i, f0 in enumerate(arp_freqs):
            s_start = int(s_i * step_dur * sr)
            s_len = min(int(0.24 * sr), n - s_start)
            st = np.arange(s_len) / sr
            mod = np.sin(2.0 * np.pi * f0 * 2.0 * st) * (1.8 * np.exp(-st * 16.0))
            pluck = (0.72 * np.sin(2.0 * np.pi * f0 * st + mod) + 0.28 * np.sin(2.0 * np.pi * f0 * 0.5 * st))
            pluck *= np.minimum(st / 0.005, 1.0) * np.exp(-st * 10.5)
            sig[s_start : s_start + s_len] += pluck * 0.36

        # Warm pulsing bassline (A2 110Hz -> G2 98Hz)
        bass_freq = np.where(t < 2.0, 110.0, 98.0)
        b_ph = 2.0 * np.pi * np.cumsum(bass_freq) / sr
        bass_pulse = 0.55 + 0.45 * np.maximum(np.sin(2.0 * np.pi * 2.0 * t - 0.8), 0.0)
        bass = np.tanh((np.sin(b_ph) + 0.45 * np.sin(2.0 * b_ph)) * 1.4) * bass_pulse * 0.28

        fade_edge = np.minimum(t / 0.015, 1.0) * np.minimum((dur - t) / 0.015, 1.0)
        bed = (sig + bass) * fade_edge
        peak = np.max(np.abs(bed)) or 1.0
        _write_wav_mono(bed_path, (bed / peak) * 0.78, sr)

    # 7. Crisp fallback digital glitch zap (0.20s)
    glitch_path = out / "glitch.wav"
    if rebuild or not glitch_path.exists():
        dur = 0.20
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        nz = _fft_band(_pink_noise(np.random.default_rng(55), n, sr), sr, 1400.0, 5600.0)
        fm = np.sin(2.0 * np.pi * (620.0 + 380.0 * np.sign(np.sin(2.0 * np.pi * 42.0 * t))) * t)
        env = np.minimum(t / 0.002, 1.0) * np.exp(-t * 16.0)
        gl = (nz * 0.65 + fm * 0.35) * env
        peak = np.max(np.abs(gl)) or 1.0
        _write_wav_mono(glitch_path, (gl / peak) * 0.85, sr)

    if rebuild:
        for old_m in (out / ".v4_studio", out / ".v5_cinema", out / ".v6_punch"):
            if old_m.exists():
                old_m.unlink(missing_ok=True)
        marker.write_text("v8_fallback", encoding="utf-8")

    return {
        "bass_boom": boom_path,
        "whoosh": whoosh_path,
        "pop": pop_path,
        "lock_clack": lock_path,
        "glitch": glitch_path,
        "riser": riser_path,
        "hype_bed": bed_path,
    }


def extract_pcm_rms(video_path: Path, window_sec: float = 0.05, sample_rate: int = 16000) -> tuple[np.ndarray, float]:
    """Decode audio to 16kHz mono PCM via ffmpeg and return per-window RMS and duration."""
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        return np.array([], dtype=np.float32), 0.0

    audio = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    duration = len(audio) / float(sample_rate)
    win_samples = max(int(sample_rate * window_sec), 1)
    n_windows = len(audio) // win_samples
    if n_windows == 0:
        return np.array([], dtype=np.float32), duration

    trimmed = audio[: n_windows * win_samples].reshape(n_windows, win_samples)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1))
    return rms, duration


def analyze_audio(
    video_path: str | Path,
    *,
    window_sec: float = 0.05,
    min_silence_sec: float = 0.65,
    min_peak_gap_sec: float = 2.6,
    max_peaks: int = 7,
) -> AudioAnalysis:
    """Detect hype peak moments (screams/reactions) and silent dead-air gaps."""
    path = Path(video_path)
    rms, duration = extract_pcm_rms(path, window_sec=window_sec)
    if rms.size == 0 or duration <= 0.0:
        return AudioAnalysis(duration=duration, hype_peaks=[], climax_time=None, segments=[])

    # Silence threshold relative to clip median/90th percentile so quiet clips still work cleanly
    p90 = float(np.percentile(rms, 90))
    silence_thresh = max(p90 * 0.14, 0.006)
    is_silent_win = rms < silence_thresh

    # Merge contiguous windows into AudioSegments, keeping only >= min_silence_sec as true dead-air
    raw_segments: list[AudioSegment] = []
    cur_state = bool(is_silent_win[0])
    start_idx = 0
    for idx in range(1, len(is_silent_win)):
        if bool(is_silent_win[idx]) != cur_state:
            s_t = start_idx * window_sec
            e_t = idx * window_sec
            raw_segments.append(AudioSegment(start=s_t, end=e_t, is_silent=cur_state))
            cur_state = bool(is_silent_win[idx])
            start_idx = idx
    raw_segments.append(AudioSegment(start=start_idx * window_sec, end=duration, is_silent=cur_state))

    # Demote short silent pauses (< min_silence_sec) to active so natural word gaps aren't chopped
    normalized: list[AudioSegment] = []
    for seg in raw_segments:
        silent = seg.is_silent and (seg.end - seg.start) >= min_silence_sec
        if normalized and normalized[-1].is_silent == silent:
            normalized[-1].end = seg.end
        else:
            normalized.append(AudioSegment(start=seg.start, end=seg.end, is_silent=silent))

    # Hype peak detection: score each window by suddenness + absolute loudness
    smooth = np.convolve(rms, np.ones(4) / 4.0, mode="same")
    mean_rms = float(np.mean(smooth))
    std_rms = float(np.std(smooth))
    threshold = max(mean_rms + 0.95 * std_rms, p90 * 0.65)

    # Candidate indices sorted by energy descending
    margin_wins = int(0.6 / window_sec)
    valid_range = range(margin_wins, max(margin_wins, len(smooth) - margin_wins))
    candidates = [i for i in valid_range if smooth[i] >= threshold]
    candidates.sort(key=lambda i: float(smooth[i]), reverse=True)

    selected_times: list[float] = []
    for idx in candidates:
        t = round(idx * window_sec, 2)
        if all(abs(t - prev) >= min_peak_gap_sec for prev in selected_times):
            selected_times.append(t)
        if len(selected_times) >= max_peaks:
            break

    climax_time = selected_times[0] if selected_times else None
    if not selected_times and duration >= 3.0:
        # Fallback: pick top 1-2 dynamic moments in the clip so edit always feels alive
        step = max(duration / 3.0, 2.5)
        selected_times = [round(min(step * k, duration - 1.0), 2) for k in (1, 2) if step * k < duration - 0.8]
        climax_time = selected_times[0] if selected_times else None

    selected_times.sort()
    return AudioAnalysis(
        duration=duration,
        hype_peaks=selected_times,
        climax_time=climax_time,
        segments=normalized,
    )
