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
- `Communicate.stream_sync()` returns a plain synchronous generator — no
  asyncio needed here, even though the library is asyncio-based internally.
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

RATE — edge-tts takes a percentage-delta STRING (e.g. "-30%"), unlike
Azure's SSML which takes the Architecture Spec's literal "0.7" multiplier
string. Converted here from the Protocol's `rate: float` (1.0 = normal, no
change) via `(rate - 1.0) * 100`, formatted with an explicit sign.
"""

import edge_tts

from core.models import WordTiming
from core.registry import register


@register("tts", "edge_tts")
class EdgeTTSProvider:
    """TTSProvider implementation using edge-tts.

    See module docstring for the "unofficial API" reliability caveat
    (Decision Log D31) before relying on this in production.
    """

    def __init__(self, voice: str = "fr-FR-DeniseNeural"):
        self._voice = voice

    def synthesize(self, text: str, rate: float = 1.0) -> tuple[bytes, list[WordTiming]]:
        rate_str = f"{(rate - 1.0) * 100:+.0f}%"
        communicate = edge_tts.Communicate(
            text, self._voice, rate=rate_str, boundary="WordBoundary"
        )

        audio_chunks: list[bytes] = []
        word_timings: list[WordTiming] = []

        for chunk in communicate.stream_sync():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_ms = chunk["offset"] / 10_000
                end_ms = start_ms + chunk["duration"] / 10_000
                word_timings.append(
                    WordTiming(
                        word=chunk["text"],
                        start_ms=round(start_ms),
                        end_ms=round(end_ms),
                    )
                )

        return b"".join(audio_chunks), word_timings