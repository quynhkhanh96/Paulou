"""D10's canonicalizer-bias diagnostic check, automated via align_phonemes.

Named/located per D10's own text ("See Experiment Log and
experiments/runners/canonicalizer_bias_check.py"). Runs a real
FreePhoneRecognizer over the D43/D44 diagnostic audio set
(tests/fixtures/diagnostic_audio/) and classifies each perturbed case as
HONEST or BIASED by running the real align_phonemes (D38) — not by reading
decoded phonemes by eye, which is how the first real result (Cnam-LMSSC,
chat discussion) was read before this script existed.

Verdict logic (chat discussion, not specified anywhere before this):
- deletion case: find the AlignmentOp consuming canonical_phonemes at
  `target_index` (walking ops in order, counting only non-insertion ops,
  since only those consume a canonical phoneme — same convention
  align_phonemes itself uses, D38). op_type == "deletion" -> HONEST
  (recognizer correctly reported the phone as absent). op_type == "match"
  -> BIASED (recognizer hallucinated exactly the deleted phone back).
  op_type == "substitution" -> AMBIGUOUS (heard something, but not
  silence and not the exact canonical phone either — flagged separately,
  not counted as clean bias or clean honesty).
- insertion case: check whether ANY "insertion" op exists anywhere in the
  alignment. Present -> HONEST (recognizer reported the extra sound).
  Absent -> BIASED (decoded sequence lines up with canonical as if the
  extra sound were never there).
- substitution case: find the op at `target_index` (same counting rule).
  op_type == "substitution" with decoded_phoneme == injected_phoneme ->
  HONEST. op_type == "match" -> BIASED (recognizer "corrected" the
  mispronunciation back to canonical). Anything else -> AMBIGUOUS.
- native case: not a bias question (nothing to be honest/dishonest
  about) — reported separately as a baseline match-rate sanity check,
  not counted into the bias rate.

This is a genuinely new piece of classification logic, not previously
specified in the Architecture Spec, Decision Log, or Testing Conventions —
worth a Decision Log entry once the overall D10 check itself is written up
(see chat discussion).
"""

import argparse
import json
from pathlib import Path

import stages.speech_assessment.free_decode  # noqa: F401 -- runs @register decorators, see its __init__.py
from core.interfaces import FreePhoneRecognizer
from core.models import AlignmentOp
from core.registry import build
from stages.speech_assessment.align import align_phonemes

DEFAULT_FIXTURE_DIR = Path("tests/fixtures/diagnostic_audio")


def _canonical_consuming_ops(ops: list[AlignmentOp]) -> list[AlignmentOp]:
    """Ops that consume one canonical phoneme each, in canonical order —
    i.e. everything except "insertion" (D38: insertion has no canonical
    counterpart). Index i of this list corresponds to canonical_phonemes[i].
    """
    return [op for op in ops if op.op_type != "insertion"]


def classify_deletion(ops: list[AlignmentOp], target_index: int) -> str:
    op = _canonical_consuming_ops(ops)[target_index]
    if op.op_type == "deletion":
        return "honest"
    if op.op_type == "match":
        return "biased"
    return "ambiguous"  # substitution: heard something, but not silence


def classify_insertion(ops: list[AlignmentOp], injected_phoneme: str) -> str:
    """Requires the SPECIFIC injected phoneme to appear as an insertion, not
    just any insertion anywhere. Tightened after real data (bofenghuang's
    et_amis) showed an unrelated insertion ('l', an unrelated recognition
    slip at the start of the utterance) co-occurring with the real one
    ('z') — the old "any insertion" check happened to still give the right
    verdict there, but only by coincidence; a case with an unrelated
    insertion and NO real one would have been wrongly marked "honest".
    """
    return "honest" if any(
        op.op_type == "insertion" and op.decoded_phoneme == injected_phoneme for op in ops
    ) else "biased"


def classify_substitution(
    ops: list[AlignmentOp], target_index: int, injected_phoneme: str
) -> str:
    op = _canonical_consuming_ops(ops)[target_index]
    if op.op_type == "substitution" and op.decoded_phoneme == injected_phoneme:
        return "honest"
    if op.op_type == "match":
        return "biased"
    return "ambiguous"


def analyze_native(ops: list[AlignmentOp]) -> dict:
    """Baseline sanity check for a NATIVE (unperturbed) recording — nothing
    was perturbed, so this isn't a bias verdict, but a match_rate alone can
    silently hide a real problem: caught during verification (chat
    discussion) when un_héros's NATIVE audio produced a spurious
    "insertion" op (the model hallucinated /n/ on genuinely liaison-free
    audio) while its match_rate over the OTHER phones still looked fine.
    So every non-match op on native audio is surfaced explicitly as an
    anomaly, not just averaged away.
    """
    consuming_ops = _canonical_consuming_ops(ops)
    matches = sum(1 for op in consuming_ops if op.op_type == "match")
    match_rate = matches / len(consuming_ops) if consuming_ops else 0.0
    anomalies = [
        f"{op.op_type}(canonical={op.canonical_phoneme!r}, decoded={op.decoded_phoneme!r})"
        for op in ops
        if op.op_type != "match"
    ]
    return {"match_rate": match_rate, "anomalies": anomalies}


def run_bias_check(
    recognizer: FreePhoneRecognizer, fixture_dir: Path = DEFAULT_FIXTURE_DIR
) -> dict:
    """Run one recognizer over every case in the diagnostic set, returning
    a report dict: per-case verdicts plus a summary bias rate (over
    deletion/insertion/substitution cases only — native cases are reported
    separately as a baseline, not folded into the bias rate, since there is
    nothing to be honest or biased ABOUT in a native rendering).
    """
    metadata = json.loads((fixture_dir / "metadata.json").read_text(encoding="utf-8"))

    per_case: dict[str, dict] = {}
    native_results: dict[str, dict] = {}
    verdict_counts = {"honest": 0, "biased": 0, "ambiguous": 0}

    for rel_path, case_meta in metadata.items():
        audio_bytes = (fixture_dir / rel_path).read_bytes()
        decoded_phonemes, decoded_confidences, decoded_boundaries = recognizer.decode(audio_bytes)

        canonical_phonemes = case_meta["canonical_phonemes"]
        unit_ids = case_meta["unit_ids"]
        ops = align_phonemes(
            canonical_phonemes, unit_ids, decoded_phonemes, decoded_confidences, decoded_boundaries
        )

        perturbation_type = case_meta["perturbation_type"]
        is_native = rel_path.startswith("native/")

        if is_native:
            native_analysis = analyze_native(ops)
            native_results[rel_path] = native_analysis
            per_case[rel_path] = {
                "kind": "native",
                "decoded_phonemes": decoded_phonemes,
                **native_analysis,
            }
            continue

        if perturbation_type == "deletion":
            verdict = classify_deletion(ops, case_meta["target_index"])
        elif perturbation_type == "insertion":
            verdict = classify_insertion(ops, case_meta["injected_phoneme"])
        elif perturbation_type == "substitution":
            verdict = classify_substitution(
                ops, case_meta["target_index"], case_meta["injected_phoneme"]
            )
        else:
            raise ValueError(f"Unknown perturbation_type: {perturbation_type!r}")

        verdict_counts[verdict] += 1
        per_case[rel_path] = {
            "kind": perturbation_type,
            "verdict": verdict,
            "decoded_phonemes": decoded_phonemes,
        }

    total_perturbed = sum(verdict_counts.values())
    bias_rate = verdict_counts["biased"] / total_perturbed if total_perturbed else 0.0

    return {
        "per_case": per_case,
        "verdict_counts": verdict_counts,
        "bias_rate": bias_rate,
        "native_results": native_results,
    }


def print_report(report: dict, recognizer_label: str) -> None:
    print(f"=== Canonicalizer bias check: {recognizer_label} ===\n")
    for rel_path, result in sorted(report["per_case"].items()):
        if result["kind"] == "native":
            flag = " <-- ANOMALY on native audio!" if result["anomalies"] else ""
            print(f"  [native]  {rel_path}: match_rate={result['match_rate']:.2f}  "
                  f"decoded={result['decoded_phonemes']}{flag}")
            for anomaly in result["anomalies"]:
                print(f"      anomaly: {anomaly}")
        else:
            print(f"  [{result['kind']:>12}] {rel_path}: {result['verdict'].upper():<9} "
                  f"decoded={result['decoded_phonemes']}")
    print(f"\nVerdict counts: {report['verdict_counts']}")
    print(f"Bias rate (over deletion/insertion/substitution cases): "
          f"{report['bias_rate']:.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recognizer", default="wav2vec2_cnam",
        help="Registry key under 'free_decoder' (see stages/speech_assessment/free_decode/)",
    )
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="If given, write the full report as JSON to this path "
             "(defaults to experiments/results/canonicalizer_bias/<recognizer>.json)",
    )
    args = parser.parse_args()

    recognizer = build("free_decoder", args.recognizer)
    report = run_bias_check(recognizer, args.fixture_dir)
    print_report(report, args.recognizer)

    out_path = args.out or Path(f"experiments/results/canonicalizer_bias/{args.recognizer}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()