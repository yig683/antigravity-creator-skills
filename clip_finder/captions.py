from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import threading

import numpy as np
import requests

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


_MONTSERRAT_URL = (
    "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Black.ttf"
)
_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, object] = {}
_TRANSLATE_LOCK = threading.Lock()
_TRANSLATE_CACHE: dict[tuple[str, str], str] = {}
_RTL_LANG_CODES = {"ar", "he", "fa", "ur"}
_HALLUCINATION_PHRASES = (
    "thank you for watching",
    "thanks for watching",
    "subtitles by",
    "amara.org",
    "please subscribe",
)


@dataclass
class WordTiming:
    text: str
    start: float
    end: float


@dataclass
class CaptionResult:
    ass_path: Path
    transcript: str
    language: str
    word_count: int


def ensure_montserrat_font(fonts_dir: str | Path = "assets/fonts") -> tuple[Path | None, str]:
    """Ensure Montserrat Black TTF is available locally; return (fonts_dir, font_family)."""
    fdir = Path(fonts_dir)
    fdir.mkdir(parents=True, exist_ok=True)
    ttf = fdir / "Montserrat-Black.ttf"
    if ttf.exists() and ttf.stat().st_size > 10_000:
        return fdir, "Montserrat Black"

    try:
        resp = requests.get(_MONTSERRAT_URL, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 10_000:
            ttf.write_bytes(resp.content)
            return fdir, "Montserrat Black"
    except Exception:
        pass
    return None, "Impact"


def _format_ass_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    cs = int(round(seconds * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _upper_locale(text: str, language: str = "") -> str:
    if (language or "").lower().startswith("tr"):
        return text.replace("i", "İ").replace("ı", "I").upper()
    return text.upper()


def _decode_audio_16k(media_path: str | Path) -> np.ndarray:
    """Decode audio to 16kHz mono float32 PCM via ffmpeg (bypasses PyAV metadata_errors issues)."""
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        return np.array([], dtype=np.float32)
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _get_whisper_model(model_size: str = "base", force_cpu: bool = False):
    from faster_whisper import WhisperModel

    # Default to CPU int8 because ctranslate2 CUDA can deadlock across sequential
    # Whisper calls on Windows without matching CUDA 12 cuBLAS/cuDNN DLLs.
    use_cuda = (not force_cpu) and (os.getenv("WHISPER_USE_CUDA") == "1")
    cache_key = f"{model_size}:{'cuda' if use_cuda else 'cpu'}"
    with _MODEL_LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]

        model = None
        if use_cuda:
            try:
                import ctranslate2

                if ctranslate2.get_cuda_device_count() > 0:
                    model = WhisperModel(model_size, device="cuda", compute_type="float16")
            except Exception:
                model = None

        if model is None:
            threads = min(os.cpu_count() or 4, 8)
            model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=threads,
            )

        _MODEL_CACHE[cache_key] = model
        return model


def _has_rtl_text(text: str) -> bool:
    return any(("\u0590" <= ch <= "\u06ff") or ("\u0750" <= ch <= "\u077f") for ch in text)


def _norm_compare(text: str) -> str:
    return re.sub(r"[^\w]+", " ", (text or "").lower()).strip()


def _wrap_orig_line(text: str, max_chars: int = 38) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    words = clean.split(" ")
    mid = len(clean) / 2.0
    best_idx = 1
    best_dist = 1e9
    cur = 0
    for idx in range(1, len(words)):
        cur += len(words[idx - 1]) + (1 if idx > 1 else 0)
        dist = abs(cur - mid)
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return " ".join(words[:best_idx]) + r"\N" + " ".join(words[best_idx:])


def _translate_to_english(text: str, source_lang: str = "auto") -> str:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        return ""
    sl = (source_lang or "auto").strip().lower()[:2] or "auto"
    if sl == "en":
        return clean
    cache_key = (sl, clean)
    with _TRANSLATE_LOCK:
        if cache_key in _TRANSLATE_CACHE:
            return _TRANSLATE_CACHE[cache_key]

    translated = ""
    try:
        resp = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": sl, "tl": "en", "dt": "t", "q": clean},
            timeout=6,
        )
        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, list) and payload and isinstance(payload[0], list):
                parts = [str(seg[0]) for seg in payload[0] if isinstance(seg, list) and seg and seg[0]]
                translated = " ".join(" ".join(parts).split()).strip()
    except Exception:
        translated = ""

    if translated:
        with _TRANSLATE_LOCK:
            _TRANSLATE_CACHE[cache_key] = translated
    return translated


def _extract_phrase_chunks(
    seg_list: list[object],
    *,
    max_words: int = 6,
    max_chars: int = 38,
    max_dur: float = 2.4,
) -> tuple[list[tuple[float, float, str]], list[WordTiming], str]:
    """Split Whisper output into tight phrase chunks and word timings."""
    words: list[WordTiming] = []
    texts: list[str] = []
    chunks: list[tuple[float, float, str]] = []

    for seg in seg_list:
        seg_text = " ".join(str(getattr(seg, "text", "") or "").split()).strip()
        if not seg_text or any(h in seg_text.lower() for h in _HALLUCINATION_PHRASES):
            continue
        texts.append(seg_text)

        seg_words_raw = getattr(seg, "words", None) or []
        seg_words: list[WordTiming] = []
        for w in seg_words_raw:
            tok = (getattr(w, "word", "") or "").strip()
            if not tok:
                continue
            wt = WordTiming(
                text=tok,
                start=float(w.start),
                end=max(float(w.end), float(w.start) + 0.08),
            )
            seg_words.append(wt)
            words.append(wt)

        if not seg_words:
            s_t = float(getattr(seg, "start", 0.0))
            e_t = max(float(getattr(seg, "end", s_t + 0.4)), s_t + 0.15)
            chunks.append((s_t, e_t, seg_text))
            continue

        cur: list[WordTiming] = []
        cur_chars = 0
        for w in seg_words:
            gap = (w.start - cur[-1].end) if cur else 0.0
            span = (w.end - cur[0].start) if cur else 0.0
            prev_punct = bool(cur and cur[-1].text[-1:] in {".", "!", "?", ";", ":"})
            exceeds = bool(
                cur
                and (
                    len(cur) >= max_words
                    or cur_chars + len(w.text) + 1 > max_chars
                    or span > max_dur
                    or gap > 0.35
                    or prev_punct
                )
            )
            if exceeds:
                chunks.append((cur[0].start, max(cur[-1].end, cur[0].start + 0.12), " ".join(x.text for x in cur)))
                cur = [w]
                cur_chars = len(w.text)
            else:
                cur.append(w)
                cur_chars += len(w.text) + (1 if cur_chars else 0)
        if cur:
            chunks.append((cur[0].start, max(cur[-1].end, cur[0].start + 0.12), " ".join(x.text for x in cur)))

    return chunks, words, " ".join(texts).strip()


def _distribute_words_in_window(text: str, start: float, end: float) -> list[WordTiming]:
    tokens = [tok for tok in (text or "").split() if tok.strip()]
    if not tokens:
        return []
    total_dur = max(end - start, 0.14 * len(tokens))
    weights = [max(len(re.sub(r"\W+", "", t)), 2) + (1 if t[-1:] in ".!?,;:" else 0) for t in tokens]
    weight_sum = float(sum(weights)) or float(len(tokens))
    out: list[WordTiming] = []
    cursor = start
    for tok, wt in zip(tokens, weights):
        dur = max(0.09, total_dur * (wt / weight_sum))
        w_end = cursor + dur
        out.append(WordTiming(text=tok, start=cursor, end=w_end))
        cursor = w_end
    return out


def transcribe_words(
    media_path: str | Path,
    *,
    model_size: str = "base",
    language: str | None = None,
    task: str = "transcribe",
) -> tuple[list[WordTiming], str, str, list[tuple[float, float, str]]]:
    """Transcribe or translate audio with phrase chunks and word-level timestamps."""
    audio = _decode_audio_16k(media_path)
    if audio.size == 0:
        return [], "", language or "", []

    kwargs: dict[str, object] = {
        "word_timestamps": True,
        "vad_filter": False,
        "condition_on_previous_text": False,
        "no_speech_threshold": 0.75,
        "beam_size": 1,
        "task": task,
    }
    if language:
        kwargs["language"] = language

    try:
        model = _get_whisper_model(model_size, force_cpu=False)
        segments, info = model.transcribe(audio, **kwargs)
        seg_list = list(segments)
    except Exception:
        # Fallback to CPU int8 if CUDA runtime DLLs (cuBLAS/cuDNN) are missing during inference
        model = _get_whisper_model(model_size, force_cpu=True)
        segments, info = model.transcribe(audio, **kwargs)
        seg_list = list(segments)

    chunks, words, full_text = _extract_phrase_chunks(seg_list)
    detected_lang = getattr(info, "language", "") or ""
    return words, full_text, detected_lang, chunks


def _group_words(words: list[WordTiming], max_words: int = 3, max_chars: int = 18) -> list[list[WordTiming]]:
    groups: list[list[WordTiming]] = []
    cur: list[WordTiming] = []
    cur_chars = 0

    for w in words:
        clean = w.text.strip()
        gap = (w.start - cur[-1].end) if cur else 0.0
        would_exceed = (
            len(cur) >= max_words
            or (cur and cur_chars + len(clean) + 1 > max_chars)
            or (cur and gap > 0.55)
        )
        if would_exceed:
            groups.append(cur)
            cur = [w]
            cur_chars = len(clean)
        else:
            cur.append(w)
            cur_chars += len(clean) + (1 if cur_chars else 0)

    if cur:
        groups.append(cur)
    return groups


def build_wspeed_ass(
    words: list[WordTiming],
    out_ass_path: str | Path,
    *,
    font_name: str = "Montserrat Black",
    hook_text: str = "",
    channel_badge: str = "",
    rank_label: str = "",
    video_duration: float = 60.0,
    language: str = "",
    skip_dialogue: bool = False,
    highlight_color_bgr: str = "&H0019EBFF&",  # Punchy Gold-Yellow in ASS BGR
    secondary_phrases: list[WordTiming] | None = None,
) -> Path:
    """Create a high-retention kinetic ASS subtitle file with optional small original line above."""
    ass_path = Path(out_ass_path)
    ass_path.parent.mkdir(parents=True, exist_ok=True)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WSpeed,{font_name},138,&H00FFFFFF&,&H0019EBFF&,&H00000000&,&HD4000000&,1,0,0,0,100,100,2,0,1,13,5,2,45,45,620,1
Style: OrigSub,Segoe UI,42,&H1AF2F6FA&,&H00FFFFFF&,&H28000000&,&H70000000&,1,0,0,0,100,100,0.4,0,1,3.5,2,2,72,72,792,1
Style: Hook,{font_name},72,&H0019EBFF&,&H00FFFFFF&,&H00000000&,&HC8000000&,1,0,0,0,100,100,2,0,1,8,4,8,45,45,860,1
Style: Badge,{font_name},44,&H00E6EDF3&,&H00FFFFFF&,&H00000000&,&H80000000&,1,0,0,0,100,100,1,0,1,4,2,8,45,45,245,1
Style: Rank,{font_name},56,&H0019EBFF&,&H00FFFFFF&,&H00000000&,&HB8000000&,1,0,0,0,100,100,1,0,1,6,3,7,40,40,54,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines: list[str] = [header]

    if rank_label.strip():
        raw_rank = rank_label.strip()
        rank_end = max(video_duration, 1.0)
        if " • " in raw_rank:
            r_num, r_rest = raw_rank.split(" • ", 1)
            rank_ass = (
                f"{{\\c&H0019EBFF&}}{_escape_ass(r_num)} "
                f"{{\\c&H00FFFFFF&\\fs36}}• {_escape_ass(r_rest)}"
            )
        else:
            rank_ass = _escape_ass(raw_rank)
        lines.append(
            f"Dialogue: 2,0:00:00.00,{_format_ass_time(rank_end)},Rank,,0,0,0,,"
            f"{{\\fad(90,0)\\fscx114\\fscy114\\t(0,140,\\fscx100\\fscy100)}}{rank_ass}"
        )

    # Only add hook/badge if explicitly requested
    if hook_text.strip():
        hook_end = min(max(video_duration, 1.5), 3.4)
        esc_hook = _escape_ass(_upper_locale(hook_text.strip(), language))
        lines.append(
            f"Dialogue: 2,0:00:00.00,{_format_ass_time(hook_end)},Hook,,0,0,0,,"
            f"{{\\fad(50,140)\\fscx112\\fscy112\\t(0,130,\\fscx100\\fscy100)}}{esc_hook}"
        )

    if channel_badge.strip():
        esc_badge = _escape_ass(channel_badge.strip())
        lines.append(
            f"Dialogue: 1,0:00:00.00,{_format_ass_time(max(video_duration, 1.0))},Badge,,0,0,0,,{{\\alpha&H35&}}{esc_badge}"
        )

    is_rtl_lang = (language or "").strip().lower()[:2] in _RTL_LANG_CODES
    has_rtl_glyphs = any(_has_rtl_text(w.text) for w in words)
    if skip_dialogue or not words or is_rtl_lang or has_rtl_glyphs:
        ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return ass_path

    if secondary_phrases:
        for p_idx, phrase in enumerate(secondary_phrases):
            txt = " ".join((phrase.text or "").split()).strip()
            if not txt or _has_rtl_text(txt):
                continue
            p_start = max(phrase.start, 0.0)
            next_p = secondary_phrases[p_idx + 1].start if p_idx + 1 < len(secondary_phrases) else phrase.end + 0.25
            p_end = min(max(phrase.end + 0.10, p_start + 0.20), next_p)
            if p_end <= p_start:
                continue
            wrapped = _escape_ass(_wrap_orig_line(txt, max_chars=38))
            lines.append(
                f"Dialogue: 2,{_format_ass_time(p_start)},{_format_ass_time(p_end)},OrigSub,,0,0,0,,"
                f"{{\\fad(35,35)}}{wrapped}"
            )

    groups = _group_words(words, max_words=2, max_chars=12)
    for g_idx, grp in enumerate(groups):
        next_group_start = groups[g_idx + 1][0].start if g_idx + 1 < len(groups) else grp[-1].end + 0.25

        for w_idx, active_word in enumerate(grp):
            seg_start = active_word.start
            if w_idx + 1 < len(grp):
                seg_end = max(active_word.end, grp[w_idx + 1].start)
            else:
                seg_end = min(max(active_word.end + 0.14, active_word.start + 0.11), next_group_start)

            if seg_end <= seg_start:
                seg_end = seg_start + 0.10

            parts: list[str] = []
            for j, token in enumerate(grp):
                upper_tok = _escape_ass(_upper_locale(token.text, language))
                if j == w_idx:
                    if "!" in token.text or "?" in token.text:
                        color = "&H0055FF33&"
                    elif (g_idx + w_idx) % 3 == 1:
                        color = "&H00EEEE22&"  # Vice-City Electric Cyan
                    else:
                        color = highlight_color_bgr
                    parts.append(
                        f"{{\\c{color}\\b1\\fscx85\\fscy85\\t(0,65,\\fscx130\\fscy130)\\t(65,130,\\fscx106\\fscy106)}}{upper_tok}"
                        f"{{\\c&H00FFFFFF&\\fscx100\\fscy100}}"
                    )
                else:
                    parts.append(upper_tok)

            text_line = " ".join(parts)
            lines.append(
                f"Dialogue: 3,{_format_ass_time(seg_start)},{_format_ass_time(seg_end)},WSpeed,,0,0,0,,{text_line}"
            )

    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ass_path


def generate_wspeed_captions(
    media_path: str | Path,
    out_ass_path: str | Path,
    *,
    model_size: str = "base",
    language: str | None = None,
    hook_text: str = "",
    channel_badge: str = "",
    rank_label: str = "",
    video_duration: float = 60.0,
    skip_dialogue: bool = False,
    target_language: str = "en",
    dual_sub: bool = True,
) -> CaptionResult:
    """Transcribe audio and build English primary ASS captions with small upper original-language line."""
    _, font_name = ensure_montserrat_font()
    words, orig_transcript, detected_lang, orig_chunks = transcribe_words(
        media_path,
        model_size=model_size,
        language=language,
        task="transcribe",
    )

    src_lang = (detected_lang or language or "").strip().lower()[:2]
    want_en = (target_language or "").strip().lower().startswith("en")
    final_words = words
    final_transcript = orig_transcript
    render_lang = src_lang
    secondary_phrases: list[WordTiming] | None = None

    if want_en and orig_chunks and src_lang != "en":
        en_words: list[WordTiming] = []
        en_texts: list[str] = []
        sec_list: list[WordTiming] = []
        any_translated = False

        for c_start, c_end, orig_text in orig_chunks:
            en_text = _translate_to_english(orig_text, src_lang or "auto")
            if en_text:
                any_translated = True
            else:
                en_text = orig_text
            en_texts.append(en_text)
            en_words.extend(_distribute_words_in_window(en_text, c_start, c_end))
            if dual_sub and not _has_rtl_text(orig_text) and _norm_compare(orig_text) != _norm_compare(en_text):
                sec_list.append(WordTiming(text=orig_text, start=c_start, end=c_end))

        if not any_translated:
            tr_words, tr_text, _, _ = transcribe_words(
                media_path,
                model_size=model_size,
                language=None,
                task="translate",
            )
            if tr_words:
                en_words = tr_words
                en_texts = [tr_text] if tr_text else en_texts
                if dual_sub:
                    sec_list = [
                        WordTiming(text=ot, start=cs, end=ce)
                        for cs, ce, ot in orig_chunks
                        if not _has_rtl_text(ot) and _norm_compare(ot) != _norm_compare(tr_text)
                    ]

        if en_words:
            final_words = en_words
            final_transcript = " ".join(en_texts).strip() or orig_transcript
            render_lang = "en"
            secondary_phrases = sec_list or None

    ass_path = build_wspeed_ass(
        final_words,
        out_ass_path,
        font_name=font_name,
        hook_text=hook_text,
        channel_badge=channel_badge,
        rank_label=rank_label,
        video_duration=video_duration,
        language=render_lang,
        skip_dialogue=skip_dialogue,
        secondary_phrases=secondary_phrases,
    )
    return CaptionResult(
        ass_path=ass_path,
        transcript=final_transcript,
        language=detected_lang,
        word_count=len(final_words),
    )
