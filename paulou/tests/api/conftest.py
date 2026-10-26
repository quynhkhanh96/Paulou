"""Fixtures for the API tests: a stub pipeline and an app wired to it.

Per Testing Conventions, API tests mock `PaulouPipeline` rather than run it:
"is the pipeline correct" belongs to unit/contract/model tests, "does the API
wire things together" belongs here. The stub is as real as it can cheaply be:
real MP3 audio, the real `locate_spans`, the real `slice_audio`, and the real
`score_chunk` (align + merge + feedback) behind a fake decoder, so the API
tests also exercise the response data the frontend will render.
"""

import io
import threading
import time
from pathlib import Path

import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from pydub import AudioSegment
from pydub.generators import Sine

from backend.api.main import create_app
from backend.api.settings import Settings
from core.models import Chunk, PronunciationUnit, ReferenceAudio, Sentence, WordTiming
from stages.speech_assessment.calibration import PhoneStats
from stages.speech_assessment.speech_assessment import score_chunk
from stages.tts.audio_slicing import slice_audio
from stages.tts.timing_alignment import locate_spans

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
WORD_MS = 400


def mp3_bytes(duration_ms: int) -> bytes:
    buf = io.BytesIO()
    Sine(440).to_audio_segment(duration=duration_ms).export(buf, format="mp3")
    return buf.getvalue()


def wav_bytes(duration_ms: int, rate: int = 16_000) -> bytes:
    buf = io.BytesIO()
    AudioSegment.silent(duration=duration_ms, frame_rate=rate).export(buf, format="wav")
    return buf.getvalue()


class StubDecoder:
    """Records what it was given; returns the canonical phones minus the
    second one, so every scored chunk shows one deletion."""

    def __init__(self):
        self.audios: list[bytes] = []
        self.active = 0
        self.max_active = 0
        self.delay_s = 0.0
        self.canonical: list[str] = []
        self.warm_up_started = threading.Event()
        self.block_warm_up = threading.Event()
        self.block_warm_up.set()
        self.warm_up_calls = 0

    def decode(self, audio: bytes):
        self.audios.append(audio)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if not self.canonical:  # warm-up call, before any attempt
                self.warm_up_calls += 1
                self.warm_up_started.set()
                self.block_warm_up.wait(timeout=5)
                return [], [], []
            sf.read(io.BytesIO(audio))  # must be a readable WAV (the whole point of conversion)
            time.sleep(self.delay_s)
            decoded = list(self.canonical)
            if len(decoded) > 1:
                del decoded[1]
            confidences = [0.9] * len(decoded)
            boundaries = [(i * 100, i * 100 + 90) for i in range(len(decoded))]
            return decoded, confidences, boundaries
        finally:
            self.active -= 1


class StubPipeline:
    """Stands in for PaulouPipeline: same four operations plus `free_decoder`
    and `phone_stats`. Words become `single` units whose phonemes are their
    letters; chunks are runs of two words."""

    def __init__(self, phone_stats=None):
        self.free_decoder = StubDecoder()
        self.phone_stats = phone_stats if phone_stats is not None else {}
        self.analyze_calls: list[str] = []
        self.tts_calls: list[tuple[str, float]] = []
        self.fail_analyze: Exception | None = None
        self.fail_tts: Exception | None = None
        self.analyze_delay_s = 0.0
        self.synthesize_text_calls: list[tuple[str, float]] = []
        self.fail_synthesize_text: Exception | None = None

    def analyze_sentence(self, text: str) -> Sentence:
        self.analyze_calls.append(text)
        time.sleep(self.analyze_delay_s)
        if self.fail_analyze:
            raise self.fail_analyze
        words = [w for w in text.split() if any(c.isalpha() for c in w)]
        chunks = []
        for start in range(0, len(words), 2):
            index = len(chunks)
            units = [
                PronunciationUnit(
                    id=f"c{index}_unit_{n}",
                    type="single",
                    words=[w],
                    phonemes=[c for c in w.lower() if c.isalpha()],
                    ipa="".join(c for c in w.lower() if c.isalpha()),
                    syllables=[],
                    liaison_consonant=None,
                    note="",
                    scoring_focus="phoneme_accuracy",
                )
                for n, w in enumerate(words[start : start + 2])
            ]
            chunks.append(Chunk(text=" ".join(words[start : start + 2]), units=units))
        return Sentence(text=text, chunks=chunks)

    def synthesize_reference(self, sentence: Sentence, rate: float = 1.0) -> ReferenceAudio:
        self.tts_calls.append((sentence.text, rate))
        if self.fail_tts:
            raise self.fail_tts
        if any(c.isdigit() for c in sentence.text):
            raise ValueError("TTS words and sentence units do not spell the same text")
        words = sentence.text.split()
        step = int(WORD_MS / rate)
        timings = [WordTiming(w, i * step, i * step + step - 20) for i, w in enumerate(words)]
        chunk_spans, unit_spans = locate_spans(sentence, timings)
        return ReferenceAudio(
            audio=mp3_bytes(step * len(words)), chunk_spans=chunk_spans, unit_spans=unit_spans
        )

    def synthesize_text(self, text: str, rate: float = 1.0) -> bytes:
        self.synthesize_text_calls.append((text, rate))
        if self.fail_synthesize_text:
            raise self.fail_synthesize_text
        return mp3_bytes(300)

    def score_attempt(self, units, audio: bytes):
        self.free_decoder.canonical = [p for u in units for p in u.phonemes]
        return score_chunk(units, audio, self.free_decoder, self.phone_stats)

    @staticmethod
    def slice_reference(reference: ReferenceAudio, span):
        return slice_audio(reference.audio, span[0], span[1], audio_format="mp3")


LETTER_STATS = {c: PhoneStats(mean=0.5, std=0.2, sample_size=1000) for c in "abcdefghijklmnopqrstuvwxyz"}


def make_client(pipeline=None, calibrated=False, warm_up=True, **settings_kw):
    pipeline = pipeline or StubPipeline(phone_stats=dict(LETTER_STATS) if calibrated else {})
    settings = Settings(**settings_kw)
    app = create_app(pipeline, settings, calibrated=calibrated, warm_up=warm_up)
    return TestClient(app), pipeline


@pytest.fixture
def pipeline():
    return StubPipeline()


@pytest.fixture
def client(pipeline):
    with TestClient(create_app(pipeline, Settings(), calibrated=False, warm_up=True)) as c:
        c.app.state.paulou.ready.wait(timeout=5)
        yield c


@pytest.fixture
def prepared(client):
    """A prepared 4-word sentence: chunks 'Bonjour les' / 'petits amis'."""
    body = client.post("/api/sentences", json={"text": "Bonjour les petits amis"}).json()
    return body
