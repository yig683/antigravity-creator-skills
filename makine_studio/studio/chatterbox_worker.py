"""Standalone GPU TTS worker executed inside makine_studio/.venv_tts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Windows compatibility shim: newer Python / wheels omit Perth's native extension.
import perth

if getattr(perth, "PerthImplicitWatermarker", None) is None:
    perth.PerthImplicitWatermarker = perth.DummyWatermarker

import torch
import torchaudio as ta
from chatterbox.mtl_tts import ChatterboxMultilingualTTS


def _normalize_turkish_tts_text(text: str) -> str:
    """Normalize punctuation and symbols for crisp Turkish neural pronunciation."""
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "—": ", ",
        "–": ", ",
        "dâhice": "dahice",
    }
    out = text
    for k, v in replacements.items():
        out = out.replace(k, v)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: chatterbox_worker.py <job.json>")

    job_path = Path(sys.argv[1])
    job = json.loads(job_path.read_text(encoding="utf-8"))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ChatterboxMultilingualTTS.from_pretrained(device=device)

    voice_prompt = job.get("voice_prompt") or None
    exaggeration = float(job.get("exaggeration", 0.45))
    cfg_weight = float(job.get("cfg_weight", 0.55))
    temperature = float(job.get("temperature", 0.70))
    repetition_penalty = float(job.get("repetition_penalty", 2.0))
    base_seed = int(job.get("seed", 1042))

    manifest: list[dict[str, object]] = []
    for idx, item in enumerate(job["beats"]):
        raw_text = str(item["text"])
        tts_text = _normalize_turkish_tts_text(raw_text)
        word_count = max(1, len(tts_text.split()))
        # Turkish speech sits ~0.40-0.50s/word; cap protects against Chatterbox token_repetition tails
        max_reasonable_sec = max(7.5, word_count * 0.62 + 1.8)

        best_wav = None
        best_dur = float("inf")
        for attempt in range(4):
            seed = base_seed + idx + attempt * 97
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)

            cand_wav = model.generate(
                tts_text,
                language_id="tr",
                audio_prompt_path=voice_prompt,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
                repetition_penalty=repetition_penalty,
            )
            cand_dur = float(cand_wav.shape[-1]) / float(model.sr)
            if cand_dur < best_dur:
                best_wav = cand_wav
                best_dur = cand_dur
            if cand_dur <= max_reasonable_sec:
                break
            print(
                f"[Chatterbox] beat_{idx:02d} attempt {attempt + 1} too long ({cand_dur:.2f}s > {max_reasonable_sec:.2f}s), retrying...",
                flush=True,
            )

        assert best_wav is not None
        out_wav = Path(item["raw_wav"])
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        ta.save(str(out_wav), best_wav.cpu(), model.sr)
        print(
            f"[Chatterbox] beat_{idx:02d} ({best_dur:.2f}s): {tts_text}",
            flush=True,
        )
        manifest.append(
            {
                "id": item["id"],
                "raw_wav": str(out_wav),
                "sr": int(model.sr),
                "duration": round(best_dur, 4),
            }
        )

    Path(job["manifest_out"]).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
