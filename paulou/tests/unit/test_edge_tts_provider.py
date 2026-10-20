"""Offline tests for EdgeTTSProvider (network replaced by a fake stream).

Regression: edge-tts 7.3.1's `stream_sync()` hangs forever when `stream()`
raises, so the provider must surface errors instead of blocking.
"""

import concurrent.futures

import edge_tts
import pytest

from core.models import WordTiming
from stages.tts.edge_tts_provider import EdgeTTSProvider


def _patch_stream(monkeypatch, make_chunks):
    async def fake_stream(self):
        for chunk in make_chunks():
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    monkeypatch.setattr(edge_tts.Communicate, "stream", fake_stream)


def test_synthesize_joins_audio_and_converts_ticks_to_ms(monkeypatch):
    _patch_stream(monkeypatch, lambda: [
        {"type": "audio", "data": b"ab"},
        {"type": "WordBoundary", "text": "Bonjour", "offset": 1_000_000, "duration": 5_000_000},
        {"type": "audio", "data": b"cd"},
    ])

    audio, timings = EdgeTTSProvider().synthesize("Bonjour")

    assert audio == b"abcd"
    assert timings == [WordTiming("Bonjour", 100, 600)]


def test_stream_error_propagates_instead_of_hanging(monkeypatch):
    _patch_stream(monkeypatch, lambda: [{"type": "audio", "data": b"a"}, RuntimeError("403")])
    tts = EdgeTTSProvider()

    with concurrent.futures.ThreadPoolExecutor(1) as executor:
        future = executor.submit(tts.synthesize, "Bonjour")
        with pytest.raises(RuntimeError, match="403"):
            future.result(timeout=10)  # a hang would raise TimeoutError here


def test_rate_is_sent_as_signed_percentage(monkeypatch):
    seen = {}
    original_init = edge_tts.Communicate.__init__

    def spy(self, text, voice, **kwargs):
        seen.update(kwargs)
        original_init(self, text, voice, **kwargs)

    monkeypatch.setattr(edge_tts.Communicate, "__init__", spy)
    _patch_stream(monkeypatch, lambda: [])

    EdgeTTSProvider().synthesize("x", rate=0.7)

    assert seen["rate"] == "-30%" and seen["boundary"] == "WordBoundary"


def test_timing_offset_shifts_start_and_end_later(monkeypatch):
    _patch_stream(monkeypatch, lambda: [
        {"type": "WordBoundary", "text": "a", "offset": 1_000_000, "duration": 1_000_000},
    ])

    _, timings = EdgeTTSProvider(timing_offset_ms=50).synthesize("a")

    assert timings == [WordTiming("a", 150, 250)]


def test_negative_timing_offset_is_clamped_at_zero(monkeypatch):
    _patch_stream(monkeypatch, lambda: [
        {"type": "WordBoundary", "text": "a", "offset": 100_000, "duration": 100_000},
    ])

    _, timings = EdgeTTSProvider(timing_offset_ms=-50).synthesize("a")

    assert timings == [WordTiming("a", 0, 0)]