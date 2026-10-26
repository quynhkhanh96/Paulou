"""Unit tests for pipeline.py using registered stubs (no models, no network)."""

import io

import pytest
from pydub.generators import Sine

import pipeline as pipeline_module
from core import registry
from core.config import PipelineConfig
from core.models import PronunciationUnit, WordTiming
from pipeline import PaulouPipeline
from stages.speech_assessment.calibration import PhoneStats


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(registry, "_REGISTRY", {})


def _unit(uid, words, phonemes):
    return PronunciationUnit(
        id=uid, type="single", words=words, phonemes=phonemes, ipa="".join(phonemes),
        syllables=[], liaison_consonant=None, note="", scoring_focus="phoneme_accuracy",
    )


STATS = {p: PhoneStats(mean=0.0, std=1.0, sample_size=100) for p in "abkl"}


def _register_stubs(parse_result=("Bonjour", "le monde"), constructed=None):
    @registry.register("parser", "stub")
    class Parser:
        def __init__(self):
            if constructed is not None:
                constructed.append("parser")

        def parse(self, sentence):
            return list(parse_result)

    @registry.register("g2p", "stub")
    class G2P:
        def phonemize(self, word):
            return list(word[:1]), "stub"

    @registry.register("tts", "stub")
    class TTS:
        voice = "stub-voice"
        calls = []

        def __init__(self):
            if constructed is not None:
                constructed.append("tts")

        def synthesize(self, text, rate=1.0):
            TTS.calls.append((text, rate))
            words = text.split()
            timings = [WordTiming(w, i * 100, i * 100 + 90) for i, w in enumerate(words)]
            return b"audio", timings

    @registry.register("free_decoder", "stub")
    class Decoder:
        def decode(self, audio):
            return ["b"], [0.9], [(0, 100)]

    return TTS


CONFIG = PipelineConfig(parser="stub", g2p="stub", tts="stub", free_decoder="stub")


def test_construction_builds_no_stage():
    constructed = []
    _register_stubs(constructed=constructed)

    PaulouPipeline(CONFIG, STATS)

    assert constructed == []


def test_stage_is_built_once_and_reused():
    constructed = []
    _register_stubs(constructed=constructed)
    pipe = PaulouPipeline(CONFIG, STATS)

    assert pipe.parser is pipe.parser
    assert constructed == ["parser"]


def test_analyze_sentence_namespaces_unit_ids_across_chunks(monkeypatch):
    _register_stubs()
    monkeypatch.setattr(
        pipeline_module, "analyze_chunk",
        lambda text, g2p: [_unit("unit_0", text.split(), ["a"]), _unit("unit_1", ["x"], ["b"])],
    )
    pipe = PaulouPipeline(CONFIG, STATS)

    sentence = pipe.analyze_sentence("Bonjour le monde")

    ids = [u.id for c in sentence.chunks for u in c.units]
    assert ids == ["c0_unit_0", "c0_unit_1", "c1_unit_0", "c1_unit_1"]
    assert [c.text for c in sentence.chunks] == ["Bonjour", "le monde"]
    assert sentence.text == "Bonjour le monde"


def test_analyze_sentence_drops_chunks_without_units_and_renumbers(monkeypatch):
    _register_stubs(parse_result=("...", "salut"))
    monkeypatch.setattr(
        pipeline_module, "analyze_chunk",
        lambda text, g2p: [] if text == "..." else [_unit("unit_0", [text], ["a"])],
    )
    pipe = PaulouPipeline(CONFIG, STATS)

    sentence = pipe.analyze_sentence("... salut")

    assert [u.id for c in sentence.chunks for u in c.units] == ["c0_unit_0"]


def test_synthesize_text_returns_audio_for_free_text_without_a_sentence():
    TTS = _register_stubs()
    pipe = PaulouPipeline(CONFIG, STATS)

    assert pipe.synthesize_text("ici", rate=0.7) == b"audio"
    assert pipe.synthesize_text("vie") == b"audio"
    assert TTS.calls[-2:] == [("ici", 0.7), ("vie", 1.0)]


def test_synthesize_reference_runs_one_pass_and_locates_spans(monkeypatch):
    TTS = _register_stubs()
    monkeypatch.setattr(
        pipeline_module, "analyze_chunk",
        lambda text, g2p: [_unit("unit_" + str(i), [w], ["a"]) for i, w in enumerate(text.split())],
    )
    pipe = PaulouPipeline(CONFIG, STATS)
    sentence = pipe.analyze_sentence("Bonjour le monde")

    ref = pipe.synthesize_reference(sentence, rate=0.7)

    assert TTS.calls == [("Bonjour le monde", 0.7)]
    assert ref.audio == b"audio"
    assert ref.unit_spans == {"c0_unit_0": (0, 90), "c1_unit_0": (100, 190), "c1_unit_1": (200, 290)}
    assert ref.chunk_spans == [(0, 90), (100, 290)]


def test_score_attempt_uses_configured_recognizer():
    _register_stubs()
    pipe = PaulouPipeline(CONFIG, STATS)

    results = pipe.score_attempt([_unit("u0", ["b"], ["b"])], b"wav")

    assert [r.unit_id for r in results] == ["u0"]


def test_tts_cache_dir_wraps_provider_in_cache(tmp_path):
    TTS = _register_stubs()
    TTS.calls.clear()
    pipe = PaulouPipeline(CONFIG, STATS, tts_cache_dir=str(tmp_path))

    pipe.tts.synthesize("a b")
    pipe.tts.synthesize("a b")

    assert len(TTS.calls) == 1


def test_unknown_key_raises_registry_keyerror():
    _register_stubs()
    pipe = PaulouPipeline(PipelineConfig(parser="nope"), STATS)

    with pytest.raises(KeyError, match="No implementation registered"):
        pipe.parser


def test_known_key_imports_its_module_when_unregistered(monkeypatch):
    imported = []
    monkeypatch.setattr(pipeline_module.importlib, "import_module", lambda m: imported.append(m))
    _register_stubs()

    with pytest.raises(KeyError):
        pipeline_module._build_stage("tts", "edge_tts")

    assert imported == ["stages.tts.edge_tts_provider"]


def test_slice_reference_returns_audio_of_span_plus_padding():
    ref_audio = io.BytesIO()
    Sine(440).to_audio_segment(duration=1000).export(ref_audio, format="mp3")
    from core.models import ReferenceAudio
    ref = ReferenceAudio(audio=ref_audio.getvalue(), chunk_spans=[(0, 1000)], unit_spans={})

    clip = PaulouPipeline.slice_reference(ref, (200, 600))

    from pydub import AudioSegment
    seg = AudioSegment.from_file(io.BytesIO(clip), format="mp3")
    assert 400 + 2 * 50 - 60 < len(seg) < 400 + 2 * 50 + 60


def test_stage_kwargs_are_passed_to_the_stage_constructor():
    received = {}

    @registry.register("g2p", "needs_lexicon")
    class G2P:
        def __init__(self, lexicon):
            received["lexicon"] = lexicon

    pipe = PaulouPipeline(
        PipelineConfig(g2p="needs_lexicon"), STATS, stage_kwargs={"g2p": {"lexicon": {"a": ["a"]}}}
    )

    pipe.g2p

    assert received == {"lexicon": {"a": ["a"]}}


def test_parser_cache_dir_wraps_parser_in_cache(tmp_path):
    from stages.parsing.caching import CachingSentenceParser

    _register_stubs()
    pipe = PaulouPipeline(CONFIG, STATS, parser_cache_dir=str(tmp_path))

    assert isinstance(pipe.parser, CachingSentenceParser)
    assert pipe.parser.parse("Bonjour le monde") == ["Bonjour", "le monde"]
    assert list(tmp_path.glob("*.json"))


def test_no_parser_cache_dir_leaves_parser_unwrapped():
    from stages.parsing.caching import CachingSentenceParser

    _register_stubs()
    pipe = PaulouPipeline(CONFIG, STATS)

    assert not isinstance(pipe.parser, CachingSentenceParser)
