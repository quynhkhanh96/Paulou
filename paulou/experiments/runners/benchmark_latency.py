"""Latency benchmark for PaulouPipeline with REAL components (Decision Log D15).

D15 left the `/attempts` API shape open (synchronous vs. background job)
until recognizer latency was measured. This runner measures, on THIS
machine, every step a backend would run:

- stage construction (cold, once per process): Lexique400 load, Gemini
  client, TTS provider, wav2vec2 model load;
- `analyze_sentence` (Gemini network call + spaCy + G2P) -- runs when a
  user submits a sentence;
- `synthesize_reference` (edge-tts network call) -- same moment;
- per recording: `free_decoder.decode` alone, and the full
  `score_attempt` (decode + align + merge + feedback) -- runs on EVERY
  attempt, which is the number D15 is about.

The audio scored is the TTS reference itself (the whole sentence and each
chunk clip), so no microphone is needed; decode time depends on audio
length, not on who speaks. `--audio FILE` adds real recordings (decode
only, since no text is attached to them).

The first decode in a process is reported separately (`first_decode_s`):
it includes one-off torch warm-up, which a long-running server pays once.
All other timings are "warm" and summarized as median / p90 over
`--repeats` runs. RTF = decode time / audio duration (below 1 = faster
than real time).

Not part of CI (D16). Needs everything `docs/pipeline_cli.md` lists.

    python -m experiments.runners.benchmark_latency --repeats 5 --timing-offset-ms 50
"""

import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from experiments.runners import pipeline_cli as cli

DEFAULT_SENTENCES = [
    "Bonjour.",
    "Les enfants ont acheté des pommes.",
    "Nous sommes allés au marché avec nos amis hier matin.",
    "Quand les étudiants sont arrivés à l'université, ils ont découvert "
    "que les cours avaient été annulés à cause de la grève.",
]


# --- pure helpers (unit-tested) ---------------------------------------------


def timed(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - start


def summarize(times: list[float]) -> dict:
    ordered = sorted(times)
    p90_index = min(len(ordered) - 1, max(0, round(0.9 * len(ordered)) - 1))
    return {
        "n": len(ordered),
        "median_s": statistics.median(ordered),
        "p90_s": ordered[p90_index],
        "min_s": ordered[0],
        "max_s": ordered[-1],
    }


def wav_duration_s(wav: bytes) -> float:
    import io

    import soundfile as sf

    info = sf.info(io.BytesIO(wav))
    return info.frames / info.samplerate


def environment_info() -> dict:
    info = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["torch_threads"] = torch.get_num_threads()
        info["cuda_available"] = torch.cuda.is_available()
    except ImportError:
        info["torch"] = None
    return info


def format_report(report: dict) -> str:
    lines = ["Environment:"]
    for key, value in report["environment"].items():
        lines.append(f"  {key}: {value}")
    lines.append("\nStage construction (cold, once per process):")
    for stage, seconds in report["stage_init_s"].items():
        lines.append(f"  {stage:<14} {seconds:8.2f} s")
    if report.get("first_decode_s") is not None:
        lines.append(f"  {'first decode':<14} {report['first_decode_s']:8.2f} s  (torch warm-up included)")

    for entry in report["sentences"]:
        lines.append(f"\nSentence: {entry['text']}")
        for step in ("analyze_sentence", "synthesize_reference"):
            s = entry[step]
            lines.append(f"  {step:<22} median {s['median_s']:6.2f} s   p90 {s['p90_s']:6.2f} s   (n={s['n']})")
        lines.append("  clip                      audio    decode med   RTF    score_attempt med   p90")
        for clip in entry["clips"]:
            d, sc = clip["decode"], clip["score_attempt"]
            lines.append(
                f"  {clip['label']:<24} {clip['audio_s']:5.2f} s   {d['median_s']:6.3f} s   "
                f"{d['median_s'] / clip['audio_s']:5.2f}   {sc['median_s']:6.3f} s        {sc['p90_s']:6.3f} s"
            )

    if report["audio_files"]:
        lines.append("\nRecordings (decode only):")
        for entry in report["audio_files"]:
            d = entry["decode"]
            lines.append(
                f"  {entry['path']:<40} {entry['audio_s']:5.2f} s   decode median {d['median_s']:6.3f} s   "
                f"RTF {d['median_s'] / entry['audio_s']:5.2f}"
            )
    return "\n".join(lines)


# --- measurement ------------------------------------------------------------


def run_benchmark(pipe, sentences: list[str], audio_paths: list[Path], repeats: int) -> dict:
    report: dict = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "environment": environment_info(),
        "repeats": repeats,
        "stage_init_s": {},
        "first_decode_s": None,
        "sentences": [],
        "audio_files": [],
    }

    for stage in ("g2p", "parser", "tts", "free_decoder"):
        _, seconds = timed(getattr, pipe, stage)
        report["stage_init_s"][stage] = seconds

    for text in sentences:
        analyze_times, sentence = [], None
        for _ in range(repeats):
            result, seconds = timed(pipe.analyze_sentence, text)
            analyze_times.append(seconds)
            sentence = sentence or result  # keep the first chunking for the rest

        tts_times, reference = [], None
        for _ in range(repeats):
            result, seconds = timed(pipe.synthesize_reference, sentence)
            tts_times.append(seconds)
            reference = reference or result

        clips = [("whole sentence", [u for c in sentence.chunks for u in c.units],
                  cli.to_wav_bytes(reference.audio, ".mp3"))]
        for i, (chunk, span) in enumerate(zip(sentence.chunks, reference.chunk_spans)):
            clips.append((f"chunk {i}", chunk.units,
                          cli.to_wav_bytes(pipe.slice_reference(reference, span), ".mp3")))

        clip_reports = []
        for label, units, wav in clips:
            cli.fill_placeholder_stats(pipe.phone_stats, units)
            if report["first_decode_s"] is None:
                _, report["first_decode_s"] = timed(pipe.free_decoder.decode, wav)
            decode_times = [timed(pipe.free_decoder.decode, wav)[1] for _ in range(repeats)]
            score_times = [timed(pipe.score_attempt, units, wav)[1] for _ in range(repeats)]
            clip_reports.append({
                "label": label,
                "audio_s": wav_duration_s(wav),
                "num_units": len(units),
                "decode": summarize(decode_times) | {"raw_s": decode_times},
                "score_attempt": summarize(score_times) | {"raw_s": score_times},
            })

        report["sentences"].append({
            "text": text,
            "num_chunks": len(sentence.chunks),
            "analyze_sentence": summarize(analyze_times) | {"raw_s": analyze_times},
            "synthesize_reference": summarize(tts_times) | {"raw_s": tts_times},
            "clips": clip_reports,
        })

    for path in audio_paths:
        wav = cli.to_wav_bytes(path.read_bytes(), path.suffix)
        if report["first_decode_s"] is None:
            _, report["first_decode_s"] = timed(pipe.free_decoder.decode, wav)
        decode_times = [timed(pipe.free_decoder.decode, wav)[1] for _ in range(repeats)]
        report["audio_files"].append({
            "path": str(path),
            "audio_s": wav_duration_s(wav),
            "decode": summarize(decode_times) | {"raw_s": decode_times},
        })

    return report


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sentence", action="append", dest="sentences",
                        help="sentence to benchmark (repeatable); default: 4 built-in sentences, short to long")
    parser.add_argument("--audio", action="append", default=[], help="extra recording to decode (repeatable)")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--threads", type=int, default=None, help="torch.set_num_threads(N) before running")
    parser.add_argument("--out", default=None, help="JSON report path (default: experiments/results/latency/latency_<time>.json)")
    for name in ("parser", "g2p", "tts", "free_decoder"):
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, default=None)
    parser.add_argument("--lexique-path", default=str(cli.DEFAULT_LEXIQUE_PATH))
    parser.add_argument("--timing-offset-ms", type=int, default=None)
    parser.add_argument("--tts-cache-dir", default=None,
                        help="leave unset to measure real TTS calls (a cache makes repeats near-zero)")
    parser.add_argument("--phone-stats", default=None)
    return parser


def main(argv=None, pipeline_factory=cli.build_pipeline) -> int:
    args = make_parser().parse_args(argv)
    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")
    if args.threads is not None:
        import torch

        torch.set_num_threads(args.threads)

    pipe = pipeline_factory(args)
    report = run_benchmark(pipe, args.sentences or DEFAULT_SENTENCES, [Path(p) for p in args.audio], args.repeats)
    print(format_report(report))

    out = Path(args.out) if args.out else Path("experiments/results/latency") / (
        f"latency_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    if not args.phone_stats:
        print("Note: placeholder calibration stats were used; they do not affect timing.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())