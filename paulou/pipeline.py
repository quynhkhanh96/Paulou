"""PaulouPipeline: composes the stages into the three operations the app needs.

Glue/composition code, not a Protocol/registry stage (Decision Log D12) --
same category as `analyze_chunk` and `score_chunk`, scoped to the whole
pipeline. All model-backed stages are built LAZILY (first use), so creating
a pipeline imports no model library and needs no API key; a test or a
caller that only uses `analyze_sentence` never constructs the TTS provider
or the free-phone recognizer.

Registration (D12): `@register` decorators only run when their module is
imported. `_STAGE_MODULES` maps each known (stage, key) to the module that
registers it, and `_build_stage` imports that module only if the key is not
already registered (so a test can register a stub under a real key's name
space without pulling in torch or google-genai). A key that is neither
registered nor listed raises the registry's own KeyError.

Operations:
- `analyze_sentence(text)`: parser -> Chunk Analyzer per chunk -> Sentence.
  Unit ids are re-namespaced `c{i}_{local_id}` so they are unique across
  the sentence (`assemble_units` numbers from 0 in every chunk). Chunks
  that yield no units (punctuation only) are dropped: nothing can be
  practiced or located in them.
- `synthesize_reference(sentence, rate)`: ONE TTS pass over the whole
  sentence (D5), spans located by `locate_spans`. The slow pass (D6) is a
  second call with a lower `rate`.
- `score_attempt(units, audio)`: `score_chunk` with this pipeline's
  recognizer and calibration stats. Takes units (not a Chunk) so it also
  works for a single-unit drill.
- `slice_reference(reference, span)`: cuts a clip out of a ReferenceAudio.
  `AUDIO_FORMAT` is the one place the TTS output format is stated: both
  providers return MP3 and `ReferenceAudio` does not carry a format.
"""

import importlib
from dataclasses import replace
from functools import cached_property

from core.config import PipelineConfig
from core.interfaces import FreePhoneRecognizer, G2PProvider, SentenceParser, TTSProvider
from core.models import Chunk, PronunciationUnit, ReferenceAudio, Sentence, UnitResult
from core.registry import build, is_registered
from stages.chunk_analyzer.chunk_analyzer import analyze_chunk
from stages.speech_assessment.calibration import PhoneStats
from stages.speech_assessment.speech_assessment import score_chunk
from stages.tts.audio_slicing import slice_audio
from stages.tts.caching import CachingTTSProvider
from stages.tts.timing_alignment import locate_spans

AUDIO_FORMAT = "mp3"

_STAGE_MODULES: dict[tuple[str, str], str] = {
    ("parser", "gemini"): "stages.parsing.gemini_parser",
    ("g2p", "lexique_espeak"): "stages.chunk_analyzer.g2p.lexique_espeak",
    ("tts", "edge_tts"): "stages.tts.edge_tts_provider",
    ("tts", "azure_neural"): "stages.tts.azure_tts",
    ("free_decoder", "wav2vec2_cnam"): "stages.speech_assessment.free_decode.wav2vec2_cnam",
    (
        "free_decoder",
        "wav2vec2_bofenghuang",
    ): "stages.speech_assessment.free_decode.wav2vec2_bofenghuang",
}


def _build_stage(stage: str, key: str, **kwargs):
    if not is_registered(stage, key) and (stage, key) in _STAGE_MODULES:
        importlib.import_module(_STAGE_MODULES[(stage, key)])
    return build(stage, key, **kwargs)


class PaulouPipeline:
    def __init__(
        self,
        config: PipelineConfig,
        phone_stats: dict[str, PhoneStats],
        fallback_phone_class: dict[str, str] | None = None,
        tts_cache_dir: str | None = None,
        stage_kwargs: dict[str, dict] | None = None,
    ):
        self.config = config
        self.phone_stats = phone_stats
        self.fallback_phone_class = fallback_phone_class
        self.tts_cache_dir = tts_cache_dir
        # Constructor kwargs per stage name ("parser", "g2p", "tts",
        # "free_decoder"). Needed because `build()` constructs with no
        # arguments by default, but e.g. the G2P needs its lexicon: found by
        # trying the real stages (a stub-only test could not have shown it).
        self.stage_kwargs = stage_kwargs or {}

    def _kwargs(self, stage: str) -> dict:
        return self.stage_kwargs.get(stage, {})

    @cached_property
    def parser(self) -> SentenceParser:
        return _build_stage("parser", self.config.parser, **self._kwargs("parser"))

    @cached_property
    def g2p(self) -> G2PProvider:
        return _build_stage("g2p", self.config.g2p, **self._kwargs("g2p"))

    @cached_property
    def tts(self) -> TTSProvider:
        provider = _build_stage("tts", self.config.tts, **self._kwargs("tts"))
        if self.tts_cache_dir is not None:
            provider = CachingTTSProvider(provider, self.tts_cache_dir)
        return provider

    @cached_property
    def free_decoder(self) -> FreePhoneRecognizer:
        return _build_stage("free_decoder", self.config.free_decoder, **self._kwargs("free_decoder"))

    def analyze_sentence(self, text: str) -> Sentence:
        chunks: list[Chunk] = []
        for chunk_text in self.parser.parse(text):
            units = analyze_chunk(chunk_text, self.g2p)
            if not units:
                continue
            index = len(chunks)
            units = [replace(unit, id=f"c{index}_{unit.id}") for unit in units]
            chunks.append(Chunk(text=chunk_text, units=units))
        return Sentence(text=text, chunks=chunks)

    def synthesize_reference(self, sentence: Sentence, rate: float = 1.0) -> ReferenceAudio:
        audio, word_timings = self.tts.synthesize(sentence.text, rate=rate)
        chunk_spans, unit_spans = locate_spans(sentence, word_timings)
        return ReferenceAudio(audio=audio, chunk_spans=chunk_spans, unit_spans=unit_spans)

    def score_attempt(self, units: list[PronunciationUnit], audio: bytes) -> list[UnitResult]:
        return score_chunk(
            units, audio, self.free_decoder, self.phone_stats, self.fallback_phone_class
        )

    @staticmethod
    def slice_reference(reference: ReferenceAudio, span: tuple[int, int]) -> bytes:
        return slice_audio(reference.audio, span[0], span[1], audio_format=AUDIO_FORMAT)