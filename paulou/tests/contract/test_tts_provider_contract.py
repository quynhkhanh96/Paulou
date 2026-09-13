"""Contract test for AzureTTSProvider.

Per Testing Conventions: TTS output can't be exact-match tested (real audio
bytes, real timing jitter), so this checks invariants that must always
hold. Requires real AZURE_SPEECH_KEY / AZURE_SPEECH_REGION — skipped
otherwise, since it calls the real Azure API and costs quota.

NOT run/verified by the assistant that wrote this — no network access to
Azure's endpoints from that environment, and no real credentials. Please
run this yourself once credentials are set, and report back if anything
fails — see azure_tts.py's docstring for the specific things that
couldn't be verified (the SSML/event-wiring shape was verified
structurally against the real SDK; only the live round-trip is unverified).
"""

import os

import pytest
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

pytestmark = pytest.mark.skipif(
    not (os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION")),
    reason="AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set — see .env.example / SETUP.md",
)

from stages.tts.azure_tts import AzureTTSProvider  # noqa: E402


@pytest.fixture(scope="module")
def tts():
    return AzureTTSProvider()


def test_synthesize_returns_nonempty_audio(tts):
    audio, _ = tts.synthesize("Bonjour tout le monde.")
    assert isinstance(audio, bytes)
    assert len(audio) > 0


def test_synthesize_returns_one_timing_per_word_roughly(tts):
    text = "Les amis sont arrivés hier soir."
    _, timings = tts.synthesize(text)
    word_count = len(text.rstrip(".").split())
    assert len(timings) > 0
    # Not necessarily exact (SSML/tokenization quirks), but in the same
    # ballpark as the number of words in the input.
    assert abs(len(timings) - word_count) <= 2


def test_word_timings_are_in_order_and_non_negative(tts):
    _, timings = tts.synthesize("Bonjour, comment allez-vous aujourd'hui ?")
    assert all(t.start_ms >= 0 and t.end_ms >= t.start_ms for t in timings)
    starts = [t.start_ms for t in timings]
    assert starts == sorted(starts)


def test_slower_rate_produces_longer_or_equal_audio(tts):
    text = "C'est une phrase de test."
    normal_audio, _ = tts.synthesize(text, rate=1.0)
    slow_audio, _ = tts.synthesize(text, rate=0.7)
    # Slower speech -> more audio data for the same text (rough proxy,
    # since exact byte count depends on codec/encoding details too).
    assert len(slow_audio) >= len(normal_audio)