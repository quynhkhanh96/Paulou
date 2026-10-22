"""Unit tests for experiments/runners/benchmark_latency.py (stub pipeline)."""

import io
import json

import pytest
from pydub.generators import Sine

from core.models import (
    AlignmentOp, Chunk, PronunciationUnit, ReferenceAudio, ScoredAlignmentOp, Sentence, UnitResult,
)
from experiments.runners import benchmark_latency as bench
from pipeline import PaulouPipeline


def _unit(uid, words, phonemes):
    return PronunciationUnit(
        id=uid, type="single", words=words, phonemes=phonemes, ipa="".join(phonemes),
        syllables=[], liaison_consonant=None, note="", scoring_focus="phoneme_accuracy",
    )


def _mp3(ms):
    buf = io.BytesIO()
    Sine(440).to_audio_segment(duration=ms).export(buf, format="mp3")
    return buf.getvalue()


class StubDecoder:
    def __init__(self):
        self.calls = 0

    def decode(self, audio):
        assert audio[:4] == b"RIFF"
        self.calls += 1
        return ["b"], [0.9], [(0, 10)]


class StubPipeline:
    slice_reference = staticmethod(PaulouPipeline.slice_reference)

    def __init__(self):
        self.phone_stats = {}
        self.parser = self.g2p = self.tts = object()
        self.free_decoder = StubDecoder()
        self.analyze_calls = 0
        self.tts_calls = 0

    def analyze_sentence(self, text):
        self.analyze_calls += 1
        return Sentence(text, [
            Chunk("bon", [_unit("c0_unit_0", ["bon"], ["b"])]),
            Chunk("jour", [_unit("c1_unit_0", ["jour"], ["ʒ"])]),
        ])

    def synthesize_reference(self, sentence, rate=1.0):
        self.tts_calls += 1
        return ReferenceAudio(_mp3(1000), [(0, 400), (500, 900)], {"c0_unit_0": (0, 400), "c1_unit_0": (500, 900)})

    def score_attempt(self, units, audio):
        self.free_decoder.decode(audio)
        op = AlignmentOp("match", units[0].id, "b", "b", 0.9, 0, 10)
        return [UnitResult(units[0].id, 90, [ScoredAlignmentOp(op, 90)], "")]


def test_summarize_median_p90_min_max():
    s = bench.summarize([5.0, 1.0, 3.0, 2.0, 4.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    assert s == {"n": 10, "median_s": 5.5, "p90_s": 9.0, "min_s": 1.0, "max_s": 10.0}


def test_summarize_single_value():
    assert bench.summarize([2.0])["p90_s"] == 2.0


def test_run_benchmark_measures_every_step_and_clip():
    pipe = StubPipeline()

    report = bench.run_benchmark(pipe, ["bon jour"], [], repeats=2)

    assert set(report["stage_init_s"]) == {"g2p", "parser", "tts", "free_decoder"}
    assert report["first_decode_s"] is not None
    entry = report["sentences"][0]
    assert pipe.analyze_calls == 2 and pipe.tts_calls == 2
    assert [c["label"] for c in entry["clips"]] == ["whole sentence", "chunk 0", "chunk 1"]
    whole = entry["clips"][0]
    assert whole["num_units"] == 2 and whole["decode"]["n"] == 2
    assert 0.9 < whole["audio_s"] < 1.1
    assert set(pipe.phone_stats) == {"b", "ʒ"}


def test_audio_files_are_decoded_only(tmp_path):
    pipe = StubPipeline()
    path = tmp_path / "me.mp3"
    path.write_bytes(_mp3(500))

    report = bench.run_benchmark(pipe, [], [path], repeats=3)

    assert report["sentences"] == []
    assert report["audio_files"][0]["decode"]["n"] == 3
    assert pipe.free_decoder.calls == 4  # first (warm-up) + 3 repeats


def test_main_prints_report_and_writes_json(tmp_path, capsys):
    out = tmp_path / "lat.json"

    bench.main(["--sentence", "bon jour", "--repeats", "1", "--out", str(out)],
               pipeline_factory=lambda args: StubPipeline())

    printed = capsys.readouterr().out
    assert "Stage construction" in printed and "whole sentence" in printed and "RTF" in printed
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sentences"][0]["text"] == "bon jour"


def test_repeats_must_be_positive():
    with pytest.raises(SystemExit):
        bench.main(["--repeats", "0"], pipeline_factory=lambda args: StubPipeline())