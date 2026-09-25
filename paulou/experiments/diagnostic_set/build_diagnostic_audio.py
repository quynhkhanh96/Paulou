"""Generate the D10 diagnostic audio set via Piper phoneme injection (D43).

CANNOT BE RUN IN THE SANDBOX THIS WAS WRITTEN IN — no network access to
huggingface.co to download a Piper voice model there. This is the script
Khanh needs to run locally to do the verification D43's Status still
requires (confirm a real French voice's config.json phoneme coverage, and
listen to / measure the resulting audio) before D43 can be locked in.

Per D43, this is `experiments/` tooling, NOT a `stages/tts/` TTSProvider —
it is not registered, and produces diagnostic audio for validating stage 5
(Speech Assessment), not user-facing practice audio for stage 3.

Usage (once a French Piper voice is downloaded, e.g. fr_FR-siwis-medium):
    python -m experiments.diagnostic_set.build_diagnostic_audio \\
        --model path/to/fr_FR-siwis-medium.onnx \\
        --config path/to/fr_FR-siwis-medium.onnx.json \\
        --out-dir experiments/results/diagnostic_set

Output layout (matches tests/fixtures/diagnostic_audio/'s eventual shape,
so promoting a finalized version there later is a straight copy):
    <out-dir>/
      native/<case_id>.wav
      substitution/<case_id>.wav   (only for substitution-type cases)
      deletion/<case_id>.wav       (only for deletion-type cases)
      insertion/<case_id>.wav      (only for insertion-type cases)
      metadata.json
"""

import argparse
import json
import wave
from pathlib import Path

import numpy as np
from piper import PiperVoice
from piper.config import SynthesisConfig

from experiments.diagnostic_set.cases import DiagnosticCase, build_cases
from experiments.diagnostic_set.perturbation import apply_perturbation
from experiments.diagnostic_set.piper_phonemes import to_piper_phonemes

# Piper's VITS decoder samples Gaussian noise INSIDE the ONNX graph itself
# (noise_scale for the flow/decoder, noise_w_scale for the stochastic
# duration predictor) unless told not to -- confirmed by reading
# piper/voice.py::phoneme_ids_to_audio, which forwards these straight into
# the model's `scales` input. Left at their voice-config defaults, the SAME
# phoneme sequence produces a DIFFERENT-duration audio clip on every call,
# which defeats the point of a pinned diagnostic fixture (D43) -- this is
# what caused native and deletion/liaison_deletion_les_amis.wav to come out
# with near-identical durations on one run despite differing by a whole
# phoneme. Zeroing both gives a deterministic ("clean") rendering, which is
# arguably more appropriate for a controlled diagnostic anyway.
#
# length_scale is UNRELATED to determinism -- it's overall speaking rate
# (1.0 = model's normal pace, higher = slower). Exposed as a CLI option and
# defaulted slower than normal (see DEFAULT_LENGTH_SCALE_FOR_REVIEW below):
# at the model's default pace, manually verifying a single deleted/inserted
# phoneme by ear is genuinely harder than it needs to be. This is separate
# from word_boundary_before below, which controls PAUSES (not overall
# speed) at specific junctions.
DEFAULT_LENGTH_SCALE_FOR_REVIEW = 1.3


def synthesize(
    voice: PiperVoice,
    phonemes: list[str],
    length_scale: float,
    word_boundary_before: set[int] | None = None,
) -> tuple[np.ndarray, int]:
    """Synthesize audio directly from a phoneme list, bypassing voice.phonemize().

    Uses the low-level phonemes_to_ids -> phoneme_ids_to_audio path (see
    D43's Rationale) so the phoneme sequence used is EXACTLY the one we
    built, with no text/G2P step in between. Noise is zeroed for
    deterministic, reproducible output; length_scale controls speaking rate
    only. word_boundary_before inserts a word-boundary pause token at the
    given phoneme indices -- used ONLY where two words are NOT connected by
    an intact liaison in this specific rendering (see DiagnosticCase's
    native_word_boundary_index / perturbed_word_boundary_index; never
    within an actual liaison_group, per D35).
    """
    syn_config = SynthesisConfig(
        noise_scale=0.0, noise_w_scale=0.0, length_scale=length_scale
    )
    piper_phonemes = to_piper_phonemes(phonemes, word_boundary_before)
    phoneme_ids = voice.phonemes_to_ids(piper_phonemes)
    audio = voice.phoneme_ids_to_audio(phoneme_ids, syn_config=syn_config)
    if isinstance(audio, tuple):
        audio = audio[0]  # alignments not requested, but guard anyway
    return audio, voice.config.sample_rate


def write_wav(path: Path, audio_float: np.ndarray, sample_rate: int) -> None:
    """Write a float32 [-1, 1] array as 16-bit PCM mono WAV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    audio_int16 = np.clip(audio_float * 32767.0, -32767.0, 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())


def build_metadata_entry(case: DiagnosticCase, perturbed: list[str]) -> dict:
    """Schema agreed in this conversation (point (c)) — one entry per case."""
    return {
        "sentence_text": case.sentence_text,
        "canonical_phonemes": case.canonical_phonemes,
        "perturbed_phonemes": perturbed,
        "perturbation_type": case.perturbation_type,
        "target_index": case.target_index,
        "injected_phoneme": case.injected_phoneme,
        "unit_ids": case.unit_ids,
        "note": case.perturbation_note,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Path to .onnx voice model")
    parser.add_argument("--config", help="Path to .onnx.json (defaults to model+.json)")
    parser.add_argument(
        "--out-dir",
        default="experiments/results/diagnostic_set",
        help="Output dir (experiments/results/ during iteration, per D43 — "
             "NOT tests/fixtures/diagnostic_audio/ until a version is promoted)",
    )
    parser.add_argument(
        "--length-scale",
        type=float,
        default=DEFAULT_LENGTH_SCALE_FOR_REVIEW,
        help=f"Speaking-rate multiplier (1.0 = model's normal pace, higher "
             f"= slower). Defaults to {DEFAULT_LENGTH_SCALE_FOR_REVIEW} to "
             f"make a single deleted/inserted phoneme easier to verify by "
             f"ear; pass --length-scale 1.0 for normal pace.",
    )
    args = parser.parse_args()

    voice = PiperVoice.load(args.model, config_path=args.config)
    print(f"Loaded voice: sample_rate={voice.config.sample_rate}, "
          f"phoneme_type={voice.config.phoneme_type}, "
          f"num_phoneme_ids={len(voice.config.phoneme_id_map)}")

    out_dir = Path(args.out_dir)
    metadata: dict[str, dict] = {}

    for case in build_cases():
        # Check this VOICE's actual phoneme_id_map, not just the DEFAULT one
        # (see D43 Tradeoffs — the two are not guaranteed identical).
        for label, phonemes, boundary_index in [
            ("native", case.canonical_phonemes, case.native_word_boundary_index),
            (case.perturbation_type, apply_perturbation(case),
             case.perturbed_word_boundary_index),
        ]:
            word_boundary_before = {boundary_index} if boundary_index is not None else None
            piper_phonemes = to_piper_phonemes(phonemes, word_boundary_before)
            missing = [p for p in piper_phonemes if p not in voice.config.phoneme_id_map]
            if missing:
                print(f"SKIPPING {case.case_id} [{label}]: phonemes missing from "
                      f"this voice's phoneme_id_map: {missing}")
                continue

            audio, sample_rate = synthesize(
                voice, phonemes, args.length_scale, word_boundary_before
            )
            subdir = "native" if label == "native" else case.perturbation_type
            filename = f"{case.case_id}.wav"
            wav_path = out_dir / subdir / filename
            write_wav(wav_path, audio, sample_rate)
            print(f"Wrote {wav_path}  ({len(audio) / sample_rate:.3f}s)")

            metadata[f"{subdir}/{filename}"] = build_metadata_entry(
                case, phonemes if label == "native" else apply_perturbation(case)
            )

    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {metadata_path}")


if __name__ == "__main__":
    main()