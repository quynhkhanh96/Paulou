"""Unit tests for experiments/runners/pipeline_cli.py with a stub pipeline.

The CLI's real-component behavior can only be checked by running it for
real (network, API key, models); these tests cover argument handling, file
output, and the pure helpers.
"""

import io
import json

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from core.models import (
    AlignmentOp, Chunk, PronunciationUnit, ReferenceAudio, ScoredAlignmentOp, Sentence, UnitResult,
)
from experiments.runners import pipeline_cli as cli
from pipeline import PaulouPipeline
from stages.speech_assessment.calibration import PhoneStats


def _unit(uid, words, phonemes):
    return PronunciationUnit(
        id=uid, type="single", words=words, phonemes=phonemes, ipa="".join(phonemes),
        syllables=[], liaison_consonant=None, note="", scoring_focus="phoneme_accuracy",
    )


def _mp3(ms=1000):
    buf = io.BytesIO()
    Sine(440).to_audio_segment(duration=ms).export(buf, format="mp3")
    return buf.getvalue()


class StubPipeline:
    slice_reference = staticmethod(PaulouPipeline.slice_reference)

    def __init__(self):
        self.phone_stats = {}
        self.scored = []
        self.rates = []
        self.sentence = Sentence("bon jour", [
            Chunk("bon", [_unit("c0_unit_0", ["bon"], ["b", "ɔ̃"])]),
            Chunk("jour", [_unit("c1_unit_0", ["jour"], ["ʒ", "u", "ʁ"])]),
        ])

    def analyze_sentence(self, text):
        return self.sentence

    def synthesize_reference(self, sentence, rate=1.0):
        self.rates.append(rate)
        return ReferenceAudio(
            audio=_mp3(),
            chunk_spans=[(0, 400), (500, 900)],
            unit_spans={"c0_unit_0": (0, 400), "c1_unit_0": (500, 900)},
        )

    def score_attempt(self, units, audio):
        self.scored.append((units, audio))
        op = AlignmentOp("match", units[0].id, units[0].phonemes[0], units[0].phonemes[0], 0.9, 0, 10)
        return [UnitResult(units[0].id, 88, [ScoredAlignmentOp(op, 88)], "")]


def run(argv, stub):
    return cli.main(argv, pipeline_factory=lambda args: stub)


def test_fill_placeholder_stats_only_adds_missing_phones():
    real = PhoneStats(0.7, 0.1, 500)
    stats = {"b": real}
    units = [_unit("u", ["x"], ["b", "a"])]

    filled = cli.fill_placeholder_stats(stats, units)

    assert filled == ["a"]
    assert stats["b"] is real
    assert stats["a"] is cli.PLACEHOLDER_STATS


def test_load_phone_stats_roundtrip(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps({"a": {"mean": 0.6, "std": 0.1, "sample_size": 50}}))

    assert cli.load_phone_stats(path) == {"a": PhoneStats(0.6, 0.1, 50)}


def test_to_wav_bytes_passes_wav_through_and_converts_mp3():
    assert cli.to_wav_bytes(b"raw", ".wav") == b"raw"

    wav = cli.to_wav_bytes(_mp3(300), ".mp3")

    assert AudioSegment.from_file(io.BytesIO(wav), format="wav").duration_seconds > 0.2


def test_analyze_prints_units(capsys):
    assert run(["analyze", "bon jour"], StubPipeline()) == 0
    out = capsys.readouterr().out
    assert "chunk 1: jour" in out and "c0_unit_0" in out and "ʒ u ʁ" in out


def test_reference_writes_clips_and_spans(tmp_path):
    stub = StubPipeline()

    run(["reference", "bon jour", "--out-dir", str(tmp_path), "--slow"], stub)

    for name in ("reference.mp3", "chunk_0.mp3", "chunk_1.mp3", "c0_unit_0.mp3", "spans.json"):
        assert (tmp_path / name).exists()
        assert (tmp_path / "slow" / name).exists()
    assert stub.rates == [1.0, cli.SLOW_RATE]
    assert json.loads((tmp_path / "spans.json").read_text())["chunk_spans"] == [[0, 400], [500, 900]]


def test_score_picks_requested_chunk_and_warns_about_placeholder_stats(tmp_path, capsys):
    stub = StubPipeline()
    wav = tmp_path / "me.wav"
    wav.write_bytes(b"wavbytes")

    run(["score", "bon jour", "--audio", str(wav), "--chunk", "1"], stub)

    units, audio = stub.scored[0]
    assert [u.id for u in units] == ["c1_unit_0"] and audio == b"wavbytes"
    assert set(stub.phone_stats) == {"ʒ", "u", "ʁ"}
    assert "PLACEHOLDER" in capsys.readouterr().err


def test_score_rejects_out_of_range_chunk(tmp_path):
    wav = tmp_path / "me.wav"
    wav.write_bytes(b"x")

    with pytest.raises(SystemExit, match="out of range"):
        run(["score", "bon jour", "--audio", str(wav), "--chunk", "5"], StubPipeline())


def test_selftest_scores_every_chunk_with_wav_audio_and_writes_json(tmp_path):
    stub = StubPipeline()
    out = tmp_path / "r.json"

    run(["selftest", "bon jour", "--json-out", str(out)], stub)

    assert len(stub.scored) == 2
    for _, audio in stub.scored:
        assert audio[:4] == b"RIFF"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data) == {"0", "1"} and data["0"][0]["calibrated_score"] == 88


def test_build_pipeline_applies_overrides_and_reports_missing_lexique(tmp_path):
    args = cli.make_parser().parse_args(
        ["analyze", "x", "--tts", "azure_neural", "--lexique-path", str(tmp_path / "nope.tsv")]
    )

    with pytest.raises(SystemExit, match="Lexique400 not found"):
        cli.build_pipeline(args)

    args = cli.make_parser().parse_args(["analyze", "x", "--tts", "azure_neural", "--g2p", "other"])
    pipe = cli.build_pipeline(args)
    assert pipe.config.tts == "azure_neural" and pipe.config.g2p == "other"


def test_assign_phones_to_words_uses_midpoint_and_flags_gaps():
    from core.models import WordTiming

    timings = [WordTiming("a", 0, 100), WordTiming("b", 200, 300)]
    rows = cli.assign_phones_to_words(
        ["x", "y", "z"], [(10, 50), (120, 180), (190, 230)], timings
    )

    assert [r[3] for r in rows] == [0, None, 1]


def test_timings_command_prints_words_and_flags_phones_outside_windows(capsys):
    from core.models import WordTiming

    class Stub:
        class tts:
            @staticmethod
            def synthesize(text, rate=1.0):
                return _mp3(300), [WordTiming("Bonjour", 0, 100), WordTiming("tous", 150, 250)]

        class free_decoder:
            @staticmethod
            def decode(audio):
                assert audio[:4] == b"RIFF"
                return ["b", "t"], [0.9, 0.9], [(10, 60), (110, 140)]

    run(["timings", "Bonjour tous", "--decode"], Stub())

    out = capsys.readouterr().out
    assert "gap_to_next=50" in out
    assert "word 0 'Bonjour'" in out
    assert "GAP" in out


def test_timing_offset_flag_reaches_tts_stage_kwargs_and_is_edge_only(tmp_path):
    lex = tmp_path / "lex.tsv"
    lex.write_text("1_Mot\t3_Phono_IPA\nbonjour\tbɔ̃ʒuʁ\n", encoding="utf-8")
    parse = cli.make_parser().parse_args
    pipe = cli.build_pipeline(parse(["analyze", "x", "--lexique-path", str(lex), "--timing-offset-ms", "50"]))
    assert pipe.stage_kwargs["tts"] == {"timing_offset_ms": 50}

    with pytest.raises(SystemExit, match="only supported"):
        cli.build_pipeline(parse(
            ["analyze", "x", "--lexique-path", str(lex), "--tts", "azure_neural", "--timing-offset-ms", "50"]
        ))