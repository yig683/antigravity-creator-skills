"""Multi-provider Turkish neural TTS and word-aligned timeline builder."""

from __future__ import annotations

import asyncio
import difflib
import json
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

import edge_tts
import numpy as np

from .config import (
    CHATTERBOX_PYTHON,
    DEFAULT_TTS_PROVIDER,
    DEFAULT_TTS_RATE,
    DEFAULT_TTS_VOICE,
    FFMPEG_EXE,
)

_WHISPER_MODEL: Any = None
_STUDIO_DIR = Path(__file__).resolve().parent


def _get_whisper_model() -> Any:
    """Lazy-load a single CPU faster-whisper model instance for word alignment."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        from faster_whisper import WhisperModel

        _WHISPER_MODEL = WhisperModel("small", device="cpu", compute_type="int8")
    return _WHISPER_MODEL


def _decode_audio_to_16k_f32(audio_path: Path) -> np.ndarray:
    """Decode any audio format to mono 16kHz float32 PCM via FFmpeg (bypasses PyAV)."""
    cmd = [
        FFMPEG_EXE,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "f32le",
        "-",
    ]
    res = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(res.stdout, dtype=np.float32)


def _trim_and_normalize_to_48k(src_audio: Path, dst_wav: Path, target_rms_db: float = -18.0) -> float:
    """Resample audio to 48kHz mono s16, trim dead lead/tail breath, and level-match."""
    tmp_wav = dst_wav.with_name(dst_wav.stem + "_tmp48k.wav")
    cmd = [
        FFMPEG_EXE,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src_audio),
        "-ar",
        "48000",
        "-ac",
        "1",
        "-sample_fmt",
        "s16",
        str(tmp_wav),
    ]
    subprocess.run(cmd, check=True)

    with wave.open(str(tmp_wav), "rb") as wf:
        sr = wf.getframerate()
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    tmp_wav.unlink(missing_ok=True)

    if pcm.size == 0:
        raise RuntimeError(f"Empty audio file produced from {src_audio}")

    # Envelope-based trim: cut weak lead-in and trailing breath tails without clipping words
    hop = max(1, int(round(0.01 * sr)))  # 10ms frames
    pad_frames = (hop - (len(pcm) % hop)) % hop
    padded = np.pad(pcm, (0, pad_frames))
    frame_rms = np.sqrt(np.mean(padded.reshape(-1, hop) ** 2, axis=1) + 1e-12)
    peak_rms = float(np.max(frame_rms))
    thresh = max(0.008, peak_rms * 0.045)

    active = np.flatnonzero(frame_rms >= thresh)
    if active.size > 0:
        lead_samples = max(0, (int(active[0]) * hop) - int(0.03 * sr))
        tail_samples = min(len(pcm), ((int(active[-1]) + 1) * hop) + int(0.08 * sr))
        pcm = pcm[lead_samples:tail_samples]

    # Per-beat RMS normalization so voice loudness never jumps across beats
    active_rms = float(np.sqrt(np.mean(pcm ** 2) + 1e-12))
    target_linear = 10.0 ** (target_rms_db / 20.0)
    if active_rms > 1e-5:
        gain = min(3.5, target_linear / active_rms)
        pcm = pcm * gain

    peak = float(np.max(np.abs(pcm)))
    if peak > 0.92:
        pcm = pcm * (0.92 / peak)

    # Smooth micro-fades to eliminate edge clicks
    fade_in = min(int(0.015 * sr), len(pcm) // 4)
    fade_out = min(int(0.035 * sr), len(pcm) // 3)
    if fade_in > 0:
        pcm[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    if fade_out > 0:
        pcm[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)

    out_i16 = np.clip(pcm * 32767.0, -32768.0, 32767.0).astype(np.int16)
    with wave.open(str(dst_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(out_i16.tobytes())

    return len(out_i16) / float(sr)


def _norm_tr_token(token: str) -> str:
    tr_map = str.maketrans("IİĞÜŞÖÇ", "ıiğüşöç")
    cleaned = token.translate(tr_map).lower()
    return re.sub(r"[^\w]", "", cleaned, flags=re.UNICODE)


def _align_whisper_to_canonical(
    canonical_text: str,
    whisper_words: list[dict[str, Any]],
    speech_dur: float,
) -> list[dict[str, Any]]:
    """Transfer Whisper spoken timestamps onto exact canonical Turkish subtitle tokens."""
    canon_tokens = [tok for tok in canonical_text.strip().split() if tok]
    if not canon_tokens:
        return []

    if not whisper_words:
        # Uniform fallback if ASR returns zero tokens
        weights = [max(2, len(_norm_tr_token(t))) for t in canon_tokens]
        total_w = float(sum(weights))
        t_cur = 0.0
        out: list[dict[str, Any]] = []
        for tok, w in zip(canon_tokens, weights):
            dur = (w / total_w) * speech_dur
            out.append({"text": tok, "start": t_cur, "duration": max(0.08, dur)})
            t_cur += dur
        return out

    canon_norm = [_norm_tr_token(t) for t in canon_tokens]
    whisp_norm = [_norm_tr_token(str(w["text"])) for w in whisper_words]
    matcher = difflib.SequenceMatcher(None, canon_norm, whisp_norm, autojunk=False)

    starts: list[float | None] = [None] * len(canon_tokens)
    ends: list[float | None] = [None] * len(canon_tokens)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                w = whisper_words[j1 + k]
                starts[i1 + k] = float(w["start"])
                ends[i1 + k] = float(w["end"])
        elif tag == "replace" and (i2 - i1) > 0 and (j2 - j1) > 0:
            span_start = float(whisper_words[j1]["start"])
            span_end = float(whisper_words[j2 - 1]["end"])
            count = i2 - i1
            step = max(0.08, (span_end - span_start) / float(count))
            for k in range(count):
                starts[i1 + k] = span_start + k * step
                ends[i1 + k] = min(speech_dur, span_start + (k + 1) * step)

    # Interpolate any unmatched insertions cleanly between neighbor boundaries
    idx = 0
    while idx < len(canon_tokens):
        if starts[idx] is not None:
            idx += 1
            continue
        run_end = idx
        while run_end < len(canon_tokens) and starts[run_end] is None:
            run_end += 1
        t0 = ends[idx - 1] if idx > 0 and ends[idx - 1] is not None else 0.0
        t1 = starts[run_end] if run_end < len(canon_tokens) and starts[run_end] is not None else speech_dur
        if t1 <= t0:
            t1 = min(speech_dur, t0 + 0.14 * (run_end - idx))
        step = max(0.06, (t1 - t0) / float(run_end - idx))
        for k in range(run_end - idx):
            starts[idx + k] = t0 + k * step
            ends[idx + k] = min(speech_dur, t0 + (k + 1) * step)
        idx = run_end

    aligned: list[dict[str, Any]] = []
    for tok, s, e in zip(canon_tokens, starts, ends):
        st = max(0.0, float(s or 0.0))
        en = min(speech_dur, max(st + 0.08, float(e or (st + 0.12))))
        aligned.append({"text": tok, "start": st, "duration": en - st})
    return aligned


def _extract_whisper_words(wav_path: Path, canonical_text: str, speech_dur: float) -> list[dict[str, Any]]:
    """Run Whisper word timestamps on a beat WAV and align to canonical narration text."""
    model = _get_whisper_model()
    audio = _decode_audio_to_16k_f32(wav_path)
    segs, _ = model.transcribe(audio, language="tr", word_timestamps=True, vad_filter=False)
    whisp_words: list[dict[str, Any]] = []
    whisp_texts: list[str] = []
    for seg in segs:
        if seg.text:
            whisp_texts.append(seg.text.strip())
        for w in seg.words or []:
            tok = (w.word or "").strip()
            if tok:
                whisp_words.append({"text": tok, "start": float(w.start), "end": float(w.end)})
    print(f"[Whisper] {wav_path.name} -> {' '.join(whisp_texts)}", flush=True)
    return _align_whisper_to_canonical(canonical_text, whisp_words, speech_dur)


async def _synth_edge_beat_async(
    text: str,
    mp3_path: Path,
    voice: str,
    rate: str,
) -> list[dict[str, Any]]:
    """Fallback cloud synthesis via Microsoft Edge Neural TTS with native WordBoundary."""
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words: list[dict[str, Any]] = []
    with mp3_path.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append(
                    {
                        "text": chunk["text"],
                        "start": chunk["offset"] / 10_000_000.0,
                        "duration": chunk["duration"] / 10_000_000.0,
                    }
                )
    return words


def _synth_chatterbox_beats(
    beats: list[dict[str, Any]],
    tts_dir: Path,
    voice_prompt: Path | None = None,
) -> list[Path]:
    """Invoke the isolated .venv_tts GPU Chatterbox worker once for all beats."""
    if not CHATTERBOX_PYTHON.exists():
        raise FileNotFoundError(
            f"Chatterbox venv not found at {CHATTERBOX_PYTHON}. "
            "Run with --tts-provider edge or create makine_studio/.venv_tts."
        )
    worker_py = _STUDIO_DIR / "chatterbox_worker.py"
    job_path = tts_dir / "chatterbox_job.json"
    manifest_path = tts_dir / "chatterbox_manifest.json"
    job_payload = {
        "beats": [
            {
                "id": b["id"],
                "text": b.get("tts_text", b["narration"]),
                "raw_wav": str(tts_dir / f"beat_{idx:02d}_raw.wav"),
            }
            for idx, b in enumerate(beats)
        ],
        "voice_prompt": str(voice_prompt.resolve()) if voice_prompt else None,
        "exaggeration": 0.45,
        "cfg_weight": 0.58,
        "temperature": 0.62,
        "repetition_penalty": 2.0,
        "seed": 1042,
        "manifest_out": str(manifest_path),
    }
    job_path.write_text(json.dumps(job_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    cmd = [str(CHATTERBOX_PYTHON), str(worker_py), str(job_path)]
    print(f"[TTS] Running GPU Chatterbox Multilingual on {len(beats)} beats...", flush=True)
    subprocess.run(cmd, check=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [Path(m["raw_wav"]) for m in manifest]


def _resolve_external_beats(beats: list[dict[str, Any]], narration_dir: Path) -> list[Path]:
    """Locate pre-recorded user narration files beat_00..beat_NN (.wav/.mp3/.m4a/.flac)."""
    resolved: list[Path] = []
    exts = (".wav", ".mp3", ".m4a", ".flac", ".ogg")
    for idx, beat in enumerate(beats):
        found: Path | None = None
        for stem in (f"beat_{idx:02d}", str(beat["id"])):
            for ext in exts:
                cand = narration_dir / f"{stem}{ext}"
                if cand.exists():
                    found = cand
                    break
            if found is not None:
                break
        if found is None:
            raise FileNotFoundError(
                f"External narration missing for beat {idx} ({beat['id']}) in {narration_dir}"
            )
        resolved.append(found)
    return resolved


def _build_subtitle_cues(
    words: list[dict[str, Any]],
    max_words: int = 6,
    max_chars: int = 44,
) -> list[dict[str, Any]]:
    """Group word timestamps into readable 1-2 line subtitle cues."""
    cues: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []

    def flush() -> None:
        if not buf:
            return
        text = " ".join(w["text"] for w in buf)
        cues.append(
            {
                "text": text,
                "start": buf[0]["start"],
                "end": max(buf[-1]["end"], buf[0]["start"] + 0.35),
            }
        )
        buf.clear()

    for w in words:
        candidate = " ".join([x["text"] for x in buf] + [w["text"]])
        gap = (w["start"] - buf[-1]["end"]) if buf else 0.0
        if buf and (len(buf) >= max_words or len(candidate) > max_chars or gap > 0.55):
            flush()
        buf.append(w)
        if w["text"].endswith((".", "!", "?", ":")):
            flush()
    flush()
    return cues


def _format_srt_time(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    hrs, rem = divmod(ms, 3_600_000)
    mins, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def write_srt(cues: list[dict[str, Any]], srt_path: Path) -> None:
    """Export subtitle cues to standard SRT format for YouTube upload."""
    lines: list[str] = []
    for idx, cue in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(cue['start'])} --> {_format_srt_time(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def build_narration_timeline(
    beats: list[dict[str, Any]],
    work_dir: Path,
    fps: int = 24,
    voice: str = DEFAULT_TTS_VOICE,
    rate: str = DEFAULT_TTS_RATE,
    provider: str = DEFAULT_TTS_PROVIDER,
    voice_prompt: Path | None = None,
    narration_dir: Path | None = None,
) -> dict[str, Any]:
    """Synthesize or ingest all beats, extract word timestamps, and emit frame-aligned timeline."""
    tts_dir = work_dir / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    pcm_chunks: list[np.ndarray] = []
    sample_rate = 48000
    all_words: list[dict[str, Any]] = []
    beat_timings: list[dict[str, Any]] = []

    lead_in_sec = 0.08
    pcm_chunks.append(np.zeros(int(round(lead_in_sec * sample_rate)), dtype=np.int16))
    cursor = lead_in_sec

    raw_audio_paths: list[Path] = []
    edge_word_lists: list[list[dict[str, Any]]] | None = None

    effective_provider = provider
    if provider == "auto":
        if CHATTERBOX_PYTHON.exists():
            effective_provider = "chatterbox"
        else:
            print(
                f"[TTS] Chatterbox venv not found at {CHATTERBOX_PYTHON}; falling back to 'edge' backend.",
                flush=True,
            )
            effective_provider = "edge"

    if effective_provider == "chatterbox":
        raw_audio_paths = _synth_chatterbox_beats(beats, tts_dir, voice_prompt=voice_prompt)
    elif effective_provider == "external":
        if narration_dir is None:
            raise ValueError("--narration-dir is required when --tts-provider external")
        raw_audio_paths = _resolve_external_beats(beats, narration_dir)
    elif effective_provider == "edge":
        async def _run_all() -> list[list[dict[str, Any]]]:
            results = []
            for idx, beat in enumerate(beats):
                mp3_path = tts_dir / f"beat_{idx:02d}.mp3"
                beat_rate = beat.get("tts_rate", rate)
                words = await _synth_edge_beat_async(beat["narration"], mp3_path, voice, beat_rate)
                results.append(words)
            return results

        edge_word_lists = asyncio.run(_run_all())
        raw_audio_paths = [tts_dir / f"beat_{idx:02d}.mp3" for idx in range(len(beats))]
    else:
        raise ValueError(f"Unsupported TTS provider '{provider}'")

    for idx, (beat, src_audio) in enumerate(zip(beats, raw_audio_paths)):
        wav_path = tts_dir / f"beat_{idx:02d}.wav"
        speech_dur = _trim_and_normalize_to_48k(src_audio, wav_path)

        if edge_word_lists is not None:
            raw_words = edge_word_lists[idx]
        else:
            raw_words = _extract_whisper_words(wav_path, beat["narration"], speech_dur)

        with wave.open(str(wav_path), "rb") as wf:
            arr = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

        pause_after = float(beat.get("pause_after", 0.10))
        min_dur = float(beat.get("min_duration", 0.0))
        total_beat_dur = max(speech_dur + pause_after, min_dur)
        pad_sec = max(0.0, total_beat_dur - speech_dur)

        pcm_chunks.append(arr)
        if pad_sec > 0:
            pcm_chunks.append(np.zeros(int(round(pad_sec * sample_rate)), dtype=np.int16))

        beat_start = cursor
        beat_end = cursor + total_beat_dur

        for w in raw_words:
            w_start = beat_start + w["start"]
            w_end = min(beat_start + speech_dur, w_start + max(0.08, w["duration"]))
            all_words.append(
                {
                    "text": w["text"],
                    "start": round(w_start, 4),
                    "end": round(w_end, 4),
                    "beat_id": beat["id"],
                }
            )

        beat_timings.append(
            {
                "id": beat["id"],
                "index": idx,
                "start": round(beat_start, 4),
                "speech_end": round(beat_start + speech_dur, 4),
                "end": round(beat_end, 4),
                "frame_start": int(round(beat_start * fps)) + 1,
                "frame_end": int(round(beat_end * fps)),
                "headline": beat.get("headline", []),
                "narration": beat["narration"],
                "sfx": beat.get("sfx", []),
            }
        )
        cursor = beat_end

    # Ensure beat frame ranges stay contiguous from frame 1 to total_frames
    tail_pad_sec = 0.45
    pcm_chunks.append(np.zeros(int(round(tail_pad_sec * sample_rate)), dtype=np.int16))
    total_duration = cursor + tail_pad_sec
    total_frames = max(1, int(round(total_duration * fps)))

    if beat_timings:
        beat_timings[0]["frame_start"] = 1
        for i in range(len(beat_timings) - 1):
            beat_timings[i + 1]["frame_start"] = beat_timings[i]["frame_end"] + 1
        beat_timings[-1]["frame_end"] = total_frames

    full_pcm = np.concatenate(pcm_chunks)
    narration_wav = work_dir / "narration.wav"
    with wave.open(str(narration_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(full_pcm.tobytes())

    subtitles = _build_subtitle_cues(all_words)
    write_srt(subtitles, work_dir / "subtitles.srt")

    timeline = {
        "fps": fps,
        "total_duration": round(total_duration, 4),
        "total_frames": total_frames,
        "tts_provider": effective_provider,
        "voice": voice if effective_provider == "edge" else (str(voice_prompt) if voice_prompt else effective_provider),
        "rate": rate,
        "narration_wav": str(narration_wav),
        "beats": beat_timings,
        "words": all_words,
        "subtitles": subtitles,
    }
    (work_dir / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return timeline
