"""Manual end-to-end CLI for PaulouPipeline, with REAL components.

Not part of CI (Decision Log D16): it needs GEMINI_API_KEY, network access
to the TTS service, the spaCy French model, Lexique400.tsv and a downloaded
free-phone recognizer -- exactly what the stub-based tests/unit/
test_pipeline.py deliberately avoids. Run it to see the whole pipeline work
(or fail) on a real sentence.

Commands (run from the repo root, `python -m experiments.runners.pipeline_cli`):

  analyze "Les enfants ont acheté des pommes."
      parser -> chunks -> units (words, phonemes, type). No TTS, no model.
  reference "..." --out-dir out/ [--slow]
      analyze + ONE TTS pass; writes reference.mp3, spans.json and one mp3
      clip per chunk and per unit (cut with slice_reference). --slow adds a
      second pass at rate 0.7 (D6) under out/slow/.
  score "..." --record [--chunk N|all] [--save-recording me.wav]
      analyze, show the text to read, record from your microphone until you
      press Enter, then score it. Needs `pip install sounddevice`.
  score "..." --audio my_recording.wav [--chunk N|all]
      same, but score an existing file (wav/flac/ogg/mp3...).
      --chunk N scores one chunk (default 0); --chunk all scores the whole
      sentence as one recording. The Gemini parser can chunk the same
      sentence differently on different runs, so prefer --record (analyze
      and record happen in ONE run) or --chunk all when using --audio.
  timings "..." [--rate 1.0] [--decode]
      DIAGNOSTIC for span problems: prints the TTS provider's raw word
      timings; with --decode also runs the free-phone recognizer over the
      whole audio and shows which word window each decoded phone falls in
      (phones outside every window are flagged "GAP" -- speech the word
      timings do not cover).
  selftest "..."
      the full loop with no microphone: analyze -> TTS -> cut each chunk ->
      decode + score that clip. Scoring TTS speech against its own canonical
      phonemes should come out clearly high; a low score on selftest points
      at the pipeline (G2P, spans, decoder), not at a learner.

CALIBRATION CAVEAT: no real native-corpus phone_stats exist yet (D11/D24).
Without --phone-stats FILE, scoring uses PLACEHOLDER stats (mean 0.5, std
0.2) for the phones in play, and says so. The numbers then only prove the
plumbing runs; they are not meaningful scores. --phone-stats takes a JSON
object {"a": {"mean": ..., "std": ..., "sample_size": ...}, ...}.
"""

import argparse
import dataclasses
import faulthandler
import io
import json
import sys
from pathlib import Path

from pydub import AudioSegment

from core.config import PipelineConfig
from core.models import PronunciationUnit, Sentence, UnitResult
from pipeline import PaulouPipeline
from stages.speech_assessment.calibration import PhoneStats

PLACEHOLDER_STATS = PhoneStats(mean=0.5, std=0.2, sample_size=1000)
DEFAULT_LEXIQUE_PATH = Path("data/Lexique400.tsv")
SLOW_RATE = 0.7  # Architecture Spec's example slow-pass rate (D6)
_SOUNDFILE_SAFE_SUFFIXES = {".wav", ".flac", ".ogg"}


# --- pure helpers (unit-tested) ---------------------------------------------


def load_phone_stats(path: Path) -> dict[str, PhoneStats]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {phone: PhoneStats(**fields) for phone, fields in raw.items()}


def fill_placeholder_stats(
    stats: dict[str, PhoneStats], units: list[PronunciationUnit]
) -> list[str]:
    """Add PLACEHOLDER_STATS for canonical phones missing from `stats`
    (mutating it in place) and return the phones that were filled."""
    filled = sorted({p for unit in units for p in unit.phonemes} - stats.keys())
    for phone in filled:
        stats[phone] = PLACEHOLDER_STATS
    return filled


def to_wav_bytes(audio: bytes, suffix: str) -> bytes:
    """The recognizer reads audio with soundfile, which does not reliably
    read MP3. Anything that is not wav/flac/ogg goes through pydub (ffmpeg)."""
    if suffix.lower() in _SOUNDFILE_SAFE_SUFFIXES:
        return audio
    segment = AudioSegment.from_file(io.BytesIO(audio), format=suffix.lstrip(".").lower())
    buf = io.BytesIO()
    segment.export(buf, format="wav")
    return buf.getvalue()


def assign_phones_to_words(phones, boundaries, timings):
    """For each decoded phone, the index of the TTS word whose
    [start_ms, end_ms] window contains the phone's midpoint, or None."""
    rows = []
    for phone, (start, end) in zip(phones, boundaries):
        mid = (start + end) / 2
        word_index = next(
            (i for i, t in enumerate(timings) if t.start_ms <= mid <= t.end_ms), None
        )
        rows.append((phone, start, end, word_index))
    return rows


def format_timings(timings, rows=None) -> str:
    lines = ["TTS word timings (ms):"]
    for i, t in enumerate(timings):
        gap = timings[i + 1].start_ms - t.end_ms if i + 1 < len(timings) else None
        gap_text = "" if gap is None else f"  gap_to_next={gap}"
        lines.append(f"  {i:>2} {t.word:<14} {t.start_ms:>6} - {t.end_ms:<6} dur={t.end_ms - t.start_ms}{gap_text}")
    if rows is not None:
        lines.append("Decoded phones over the whole audio (ms):")
        for phone, start, end, word_index in rows:
            where = "GAP (outside every word window)" if word_index is None else f"word {word_index} {timings[word_index].word!r}"
            lines.append(f"  {phone:<4} {start:>6} - {end:<6} {where}")
    return "\n".join(lines)


def frames_to_wav_bytes(samples, sample_rate: int) -> bytes:
    """float32 mono samples in [-1, 1] -> WAV bytes."""
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def record_until_enter(sample_rate: int = 16_000) -> bytes:
    """Record mono audio from the default microphone until Enter is pressed."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise SystemExit("Recording needs sounddevice: pip install sounddevice") from exc

    frames = []

    def on_audio(indata, _frames, _time, _status):
        frames.append(indata.copy())

    try:
        stream = sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32", callback=on_audio)
    except sd.PortAudioError:
        sample_rate = int(sd.query_devices(kind="input")["default_samplerate"])
        stream = sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32", callback=on_audio)

    with stream:
        input("Recording... press Enter to stop. ")
    if not frames:
        raise SystemExit("No audio captured.")
    return frames_to_wav_bytes(np.concatenate(frames).reshape(-1), sample_rate)


def format_sentence(sentence: Sentence) -> str:
    lines = [f"Sentence: {sentence.text}"]
    for i, chunk in enumerate(sentence.chunks):
        lines.append(f"  chunk {i}: {chunk.text}")
        for unit in chunk.units:
            lines.append(
                f"    {unit.id:<12} {unit.type:<14} {' + '.join(unit.words):<22} /{' '.join(unit.phonemes)}/"
            )
    return "\n".join(lines)


def format_results(units: list[PronunciationUnit], results: list[UnitResult]) -> str:
    by_id = {u.id: u for u in units}
    lines = []
    for result in results:
        unit = by_id.get(result.unit_id)
        label = " + ".join(unit.words) if unit else ""
        lines.append(f"    {result.unit_id:<12} {result.calibrated_score:>3}  {label}")
        for scored in result.scored_ops:
            op = scored.op
            lines.append(
                f"        {op.op_type:<12} {op.canonical_phoneme or '-':<4} -> "
                f"{op.decoded_phoneme or '-':<4} score={scored.accuracy_score}"
            )
        if result.feedback_text:
            lines.append(f"        feedback: {result.feedback_text}")
    return "\n".join(lines)


# --- pipeline construction --------------------------------------------------


def build_pipeline(args: argparse.Namespace) -> PaulouPipeline:
    config = PipelineConfig()
    for field in ("parser", "g2p", "tts", "free_decoder"):
        value = getattr(args, field)
        if value is not None:
            setattr(config, field, value)

    stage_kwargs: dict[str, dict] = {}
    if config.g2p == "lexique_espeak":
        from stages.chunk_analyzer.g2p.lexique_espeak import load_lexique400

        lexicon_path = Path(args.lexique_path)
        if not lexicon_path.exists():
            raise SystemExit(
                f"Lexique400 not found at {lexicon_path} (git-ignored, download "
                f"separately -- see SETUP.md). Pass --lexique-path to point elsewhere."
            )
        stage_kwargs["g2p"] = {"lexicon": load_lexique400(lexicon_path)}

    if args.timing_offset_ms is not None:
        if config.tts != "edge_tts":
            raise SystemExit("--timing-offset-ms is only supported for --tts edge_tts.")
        stage_kwargs["tts"] = {"timing_offset_ms": args.timing_offset_ms}

    phone_stats = load_phone_stats(Path(args.phone_stats)) if args.phone_stats else {}
    return PaulouPipeline(
        config,
        phone_stats,
        tts_cache_dir=args.tts_cache_dir,
        stage_kwargs=stage_kwargs,
    )


# --- commands ---------------------------------------------------------------


def _prepare_stats(pipe: PaulouPipeline, units: list[PronunciationUnit], using_real: bool) -> None:
    if using_real:
        return
    filled = fill_placeholder_stats(pipe.phone_stats, units)
    if filled:
        print(
            "WARNING: no --phone-stats; using PLACEHOLDER calibration for "
            f"{len(filled)} phone(s). Scores below prove the plumbing only.",
            file=sys.stderr,
        )


def _score_and_print(pipe, units, wav, using_real_stats) -> list[UnitResult]:
    _prepare_stats(pipe, units, using_real_stats)
    results = pipe.score_attempt(units, wav)
    print(format_results(units, results))
    return results


def cmd_analyze(pipe: PaulouPipeline, args) -> int:
    print(format_sentence(pipe.analyze_sentence(args.text)))
    return 0


def cmd_reference(pipe: PaulouPipeline, args) -> int:
    sentence = pipe.analyze_sentence(args.text)
    print(format_sentence(sentence))
    out = Path(args.out_dir)
    passes = [("", 1.0)] + ([("slow", SLOW_RATE)] if args.slow else [])
    for subdir, rate in passes:
        target = out / subdir
        target.mkdir(parents=True, exist_ok=True)
        ref = pipe.synthesize_reference(sentence, rate=rate)
        (target / "reference.mp3").write_bytes(ref.audio)
        for i, span in enumerate(ref.chunk_spans):
            (target / f"chunk_{i}.mp3").write_bytes(pipe.slice_reference(ref, span))
        for unit_id, span in ref.unit_spans.items():
            (target / f"{unit_id}.mp3").write_bytes(pipe.slice_reference(ref, span))
        (target / "spans.json").write_text(
            json.dumps(
                {"rate": rate, "chunk_spans": ref.chunk_spans, "unit_spans": ref.unit_spans},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {target}/ (rate {rate}): reference.mp3, spans.json, "
              f"{len(ref.chunk_spans)} chunk clip(s), {len(ref.unit_spans)} unit clip(s)")
    return 0


def cmd_score(pipe: PaulouPipeline, args) -> int:
    sentence = pipe.analyze_sentence(args.text)
    print(format_sentence(sentence))

    if args.chunk == "all":
        units = [u for chunk in sentence.chunks for u in chunk.units]
        target_text = sentence.text
    else:
        if not args.chunk.isdigit() or int(args.chunk) >= len(sentence.chunks):
            raise SystemExit(
                f"--chunk {args.chunk} out of range (0..{len(sentence.chunks) - 1}) or 'all'."
            )
        chunk = sentence.chunks[int(args.chunk)]
        units, target_text = chunk.units, chunk.text

    if args.record:
        print(f"\nRead aloud: {target_text}")
        wav = record_until_enter()
        if args.save_recording:
            Path(args.save_recording).write_bytes(wav)
            print(f"Saved recording to {args.save_recording}")
    else:
        audio_path = Path(args.audio)
        wav = to_wav_bytes(audio_path.read_bytes(), audio_path.suffix)

    print(f"\nScores for {args.chunk!r} ({target_text!r}):")
    _score_and_print(pipe, units, wav, bool(args.phone_stats))
    return 0


def cmd_timings(pipe: PaulouPipeline, args) -> int:
    audio, timings = pipe.tts.synthesize(args.text, rate=args.rate)
    rows = None
    if args.decode:
        phones, _conf, boundaries = pipe.free_decoder.decode(to_wav_bytes(audio, ".mp3"))
        rows = assign_phones_to_words(phones, boundaries, timings)
    print(format_timings(timings, rows))
    return 0


def cmd_selftest(pipe: PaulouPipeline, args) -> int:
    sentence = pipe.analyze_sentence(args.text)
    print(format_sentence(sentence))
    ref = pipe.synthesize_reference(sentence)
    all_results: dict[str, list[UnitResult]] = {}
    for i, (chunk, span) in enumerate(zip(sentence.chunks, ref.chunk_spans)):
        wav = to_wav_bytes(pipe.slice_reference(ref, span), ".mp3")
        print(f"\nSelf-score chunk {i} ({chunk.text!r}, {span[0]}-{span[1]} ms):")
        all_results[str(i)] = _score_and_print(pipe, chunk.units, wav, bool(args.phone_stats))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {i: [dataclasses.asdict(r) for r in rs] for i, rs in all_results.items()},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nWrote {args.json_out}")
    return 0


COMMANDS = {
    "analyze": cmd_analyze,
    "reference": cmd_reference,
    "score": cmd_score,
    "timings": cmd_timings,
    "selftest": cmd_selftest,
}


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("text", help="French sentence to practice")
    for name in ("parser", "g2p", "tts", "free_decoder"):
        common.add_argument(f"--{name.replace('_', '-')}", dest=name, default=None,
                            help=f"override PipelineConfig.{name}")
    common.add_argument("--lexique-path", default=str(DEFAULT_LEXIQUE_PATH))
    common.add_argument("--tts-cache-dir", default=None)
    common.add_argument("--timing-offset-ms", type=int, default=None,
                        help="edge_tts only: shift all TTS word timings later by N ms "
                             "(see edge_tts_provider.py TIMING note); try 0/50/80 and listen")
    common.add_argument("--hang-dump", type=int, default=None, metavar="SECONDS",
                        help="if still running after SECONDS (repeating), print every "
                             "thread's stack to stderr -- shows where a hang is")
    common.add_argument("--phone-stats", default=None, help="JSON calibration table (see module doc)")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("analyze", parents=[common])
    ref = sub.add_parser("reference", parents=[common])
    ref.add_argument("--out-dir", required=True)
    ref.add_argument("--slow", action="store_true", help="also synthesize a rate-0.7 pass")
    score = sub.add_parser("score", parents=[common])
    source = score.add_mutually_exclusive_group(required=True)
    source.add_argument("--audio", help="existing recording to score")
    source.add_argument("--record", action="store_true", help="record from the microphone")
    score.add_argument("--save-recording", default=None, help="with --record: also save the WAV here")
    score.add_argument("--chunk", default="0", help="chunk index, or 'all' for the whole sentence")
    timings = sub.add_parser("timings", parents=[common])
    timings.add_argument("--rate", type=float, default=1.0)
    timings.add_argument("--decode", action="store_true")
    selftest = sub.add_parser("selftest", parents=[common])
    selftest.add_argument("--json-out", default=None)
    return parser


def main(argv=None, pipeline_factory=build_pipeline) -> int:
    args = make_parser().parse_args(argv)
    if args.hang_dump:
        faulthandler.dump_traceback_later(args.hang_dump, repeat=True)
    return COMMANDS[args.command](pipeline_factory(args), args)


if __name__ == "__main__":
    sys.exit(main())