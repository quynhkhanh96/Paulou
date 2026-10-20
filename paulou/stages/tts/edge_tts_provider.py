"""TTS via edge-tts (Microsoft Edge's unofficial Read Aloud service).

Registered as `register("tts", "edge_tts")` — a SECOND implementation
alongside `stages/tts/azure_tts.py` (`register("tts", "azure_neural")`),
per Decision Log D12/D31 — TTS is exactly the kind of stage meant to have
swappable candidate implementations (same spirit as Kaldi vs gop-ft for
the GOP scorer). Implements the TTSProvider Protocol (core/interfaces.py)
structurally.

DEVIATION FROM ARCHITECTURE SPEC (Decision Log D31): the Architecture Spec
names Azure Neural TTS specifically. This adds edge-tts as an alternative,
chosen for setup convenience (no Azure account/API key needed).

IMPORTANT — edge-tts is UNOFFICIAL: it reverse-engineers the WebSocket
protocol behind Microsoft Edge browser's "Read Aloud" feature; it is NOT a
published/supported Microsoft API. No API key is needed (the reason for
adding it here), but there's no SLA, and Microsoft could change or block
the underlying protocol at any time without notice — a materially
different reliability posture than the official Azure SDK. It happens to
use the SAME neural voices as Azure (Edge's Read Aloud runs on Azure
Cognitive Services under the hood), so voice names like
"fr-FR-DeniseNeural" work identically in both implementations.

API — verified against edge-tts 7.2.8 (structural only, by reading the
installed package's own source and inspecting real signatures — the
actual network round-trip to Microsoft's endpoint could NOT be verified in
this environment, no network access to it here):
- DO NOT USE `Communicate.stream_sync()` (what this file used originally):
  verified on edge-tts 7.3.1 that it HANGS FOREVER, silently, whenever the
  underlying async `stream()` raises (HTTP 403, blocked/closed WebSocket,
  `NoAudioReceived`, timeout...). Its worker thread dies with the exception
  before it can enqueue the end-of-stream sentinel, and the caller blocks on
  `queue.get()` for good -- the error is never shown. This is what made
  `pipeline_cli reference` hang with no output. `synthesize` below instead
  drives the async `stream()` itself (`asyncio.run` in a worker thread, so
  it also works when called from inside a running event loop) and lets any
  exception propagate to the caller.
- CRITICAL, easy to miss: `Communicate`'s `boundary` parameter defaults to
  `"SentenceBoundary"`, NOT `"WordBoundary"` — must be passed explicitly
  here, or `word_timings` would silently end up with one (wrong-grained)
  entry per sentence instead of one per word.
- Each yielded chunk is a dict with `"type"` of `"audio"` (has `"data"`:
  bytes) or `"WordBoundary"` (has `"text"`, `"offset"`, `"duration"`).
- `offset`/`duration` are in ticks (100ns units) — confirmed by reading
  edge-tts's own source (`communicate.py`, which does cross-chunk offset
  compensation arithmetic directly in tick units) — same unit and
  conversion (`/10_000` for ms) as Azure's SDK.

TIMING (measured on edge-tts 7.3.1 with the wav2vec2 recognizer, one sentence,
one voice -- a small sample, so treat as a lead, not a result): the word
windows do not line up with the audio they describe. (1) Every gap between
consecutive windows was 12-13 ms ("Les enfants ont acheté des pommes."), so
window ENDS look derived from the next word's start rather than measured.
(2) Word-final vowels sit at or past their window's end -- /e/ of "acheté"
decoded at 1231-1251 ms against a window ending at 1212 -- so cutting at the
window truncates it, and the next clip starts with the tail of the previous
word. Needed shifts at the five word boundaries ranged ~15-70 ms (mean ~50).
A possible, UNVERIFIED contributor: MP3 decoder delay without a LAME header
is ~1105 samples (~46 ms at 24 kHz). `timing_offset_ms` is the knob.

RATE — edge-tts takes a percentage-delta STRING (e.g. "-30%"), unlike
Azure's SSML which takes the Architecture Spec's literal "0.7" multiplier
string. Converted here from the Protocol's `rate: float` (1.0 = normal, no
change) via `(rate - 1.0) * 100`, formatted with an explicit sign.
"""

import asyncio
import concurrent.futures

import edge_tts

from core.models import WordTiming
from core.registry import register


@register("tts", "edge_tts")
class EdgeTTSProvider:
    """TTSProvider implementation using edge-tts.

    See module docstring for the "unofficial API" reliability caveat
    (Decision Log D31) before relying on this in production.
    """

    def __init__(self, voice: str = "fr-FR-DeniseNeural", timing_offset_ms: int = 0):
        """`timing_offset_ms` shifts every returned WordTiming LATER by that
        many ms (clamped at 0). Default 0 = timings exactly as the service
        reports them. Exists because measured word windows lead the decoded
        audio by tens of ms and their ends are not real measurements -- see
        the module docstring's TIMING note; tune by ear/decoder, don't trust
        any nonzero default until validated on more sentences.
        """
        self.voice = voice
        self.timing_offset_ms = timing_offset_ms

    def synthesize(self, text: str, rate: float = 1.0) -> tuple[bytes, list[WordTiming]]:
        rate_str = f"{(rate - 1.0) * 100:+.0f}%"
        communicate = edge_tts.Communicate(
            text, self.voice, rate=rate_str, boundary="WordBoundary"
        )

        async def collect() -> list[dict]:
            return [chunk async for chunk in communicate.stream()]

        # Worker thread: asyncio.run would fail inside an already-running
        # loop (e.g. a future async backend). .result() re-raises any error.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            chunks = executor.submit(asyncio.run, collect()).result()

        audio_chunks: list[bytes] = []
        word_timings: list[WordTiming] = []

        for chunk in chunks:
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_ms = chunk["offset"] / 10_000 + self.timing_offset_ms
                end_ms = start_ms + chunk["duration"] / 10_000
                start_ms, end_ms = max(start_ms, 0), max(end_ms, 0)
                word_timings.append(
                    WordTiming(
                        word=chunk["text"],
                        start_ms=round(start_ms),
                        end_ms=round(end_ms),
                    )
                )

        return b"".join(audio_chunks), word_timings