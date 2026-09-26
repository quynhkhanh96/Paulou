"""Compare multiple FreePhoneRecognizer candidates on the D43/D44
diagnostic set — per Codebase Conventions' "compare_<stage>.py" pattern
("If the decision to adopt it isn't obvious, write an experiment... Add a
runner under experiments/runners/compare_<stage>.py using the shared
diagnostic set, and record the result under experiments/results/").

Reuses canonicalizer_bias_check.run_bias_check for each candidate rather
than duplicating its logic — this script's only job is to loop over
candidates and lay the results side by side.

Does NOT change any PipelineConfig default (none exists yet — no
pipeline.py) and does not itself decide which candidate to adopt; per
Codebase Conventions, that's a separate step (a Decision Log entry once a
result justifies it).
"""

import argparse
import json
from pathlib import Path

import stages.speech_assessment.free_decode  # noqa: F401 -- runs @register decorators
from core.registry import build
from experiments.runners.canonicalizer_bias_check import DEFAULT_FIXTURE_DIR, run_bias_check


def compare(recognizer_keys: list[str], fixture_dir: Path) -> dict[str, dict]:
    results = {}
    for key in recognizer_keys:
        print(f"Running {key}...")
        recognizer = build("free_decoder", key)
        results[key] = run_bias_check(recognizer, fixture_dir)
    return results


def print_comparison_table(results: dict[str, dict]) -> None:
    print("\n=== Comparison: bias rate by candidate ===")
    print(f"{'candidate':<25} {'bias_rate':>10} {'honest':>8} {'biased':>8} {'ambiguous':>10}")
    for key, report in results.items():
        counts = report["verdict_counts"]
        print(f"{key:<25} {report['bias_rate']:>9.1%} {counts['honest']:>8} "
              f"{counts['biased']:>8} {counts['ambiguous']:>10}")

    print("\n=== Native-audio anomalies by candidate ===")
    for key, report in results.items():
        anomaly_files = [
            rel_path for rel_path, r in report["native_results"].items() if r["anomalies"]
        ]
        print(f"{key}: {len(anomaly_files)} file(s) with anomalies on native audio"
              + (f" -> {anomaly_files}" if anomaly_files else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recognizers", nargs="+", required=True,
        help="Registry keys under 'free_decoder' to compare, e.g. "
             "wav2vec2_cnam wav2vec2_bofenghuang",
    )
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument(
        "--out", type=Path,
        default=Path("experiments/results/canonicalizer_bias/comparison.json"),
    )
    args = parser.parse_args()

    results = compare(args.recognizers, args.fixture_dir)
    print_comparison_table(results)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()