"""Contract test for EdgeTTSProvider.

Unlike the Gemini/Azure contract tests, there's no credential to check for
here — edge-tts needs no API key. Instead, a fast (3s) raw-socket
connectivity pre-check to edge-tts's actual host
(`speech.platform.bing.com`, read from edge-tts's own `constants.py`)
skips the whole module immediately if unreachable — deliberately NOT
relying on catching an exception from the full synthesis call, since that
was confirmed to HANG (not fail cleanly) for 20+ seconds in the sandboxed
environment this was built in, unlike the fast, clear rejections
Gemini/Azure gave. Without this pre-check, an unreachable network could
make each of the 4 tests below hang for up to `receive_timeout` (60s
default) instead of skipping in ~3s.

NOT run/verified by the assistant that wrote this — see above; that
environment's egress proxy doesn't appear to reject the WebSocket
connection edge-tts uses the way it cleanly rejects Gemini/Azure's plain
HTTPS calls, so even the pre-check couldn't be confirmed to correctly
detect the sandboxed block. The code was verified structurally against
the real installed edge-tts 7.2.8 package by reading its source (see
edge_tts_provider.py's docstring). Please run this yourself and report
back, especially if anything still hangs rather than completing or
skipping quickly.
"""

import socket

import pytest

from stages.tts.edge_tts_provider import EdgeTTSProvider

EDGE_TTS_HOST = "speech.platform.bing.com"  # from edge_tts.constants.BASE_URL


def _edge_tts_host_reachable(timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((EDGE_TTS_HOST, 443), timeout=timeout):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _edge_tts_host_reachable(),
    reason=f"{EDGE_TTS_HOST} not reachable (network/firewall) — see module docstring",
)


@pytest.fixture
def tts():
    return EdgeTTSProvider()


def test_synthesize_returns_nonempty_audio(tts):
    audio, _ = tts.synthesize("Bonjour tout le monde.")
    assert isinstance(audio, bytes)
    assert len(audio) > 0


def test_synthesize_returns_one_timing_per_word_roughly(tts):
    text = "Les amis sont arrivés hier soir."
    _, timings = tts.synthesize(text)
    word_count = len(text.rstrip(".").split())
    assert len(timings) > 0
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
    assert len(slow_audio) >= len(normal_audio)