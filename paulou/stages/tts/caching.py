"""Caching wrapper for any TTSProvider implementation (Decision Log D7).

NOT registered via the stage registry (Decision Log D12) — this wraps an
already-built TTSProvider instance (Azure, edge-tts, or any future
implementation) rather than being a standalone swappable implementation of
the TTS stage itself. It implements the TTSProvider Protocol structurally
(has `voice` and `synthesize`), so it's usable anywhere a TTSProvider is
expected — used compositionally:

    provider = CachingTTSProvider(build("tts", config.tts), cache_dir="...")

Cache key: `hash(text + voice + rate)` per D7. `voice` is read from the
wrapped provider's own `voice` attribute (added to the TTSProvider
Protocol for this reason — see azure_tts.py/edge_tts_provider.py) rather
than passed separately, so the cache can never silently return audio
recorded in the wrong voice.

STORAGE: filesystem-based — no DB exists yet (backend/db/models.py isn't
built). Each cache entry is two files: `<hash>.audio` (the raw bytes
exactly as returned by the wrapped provider — codec/format is whatever
that provider produces, not standardized here) and `<hash>.json` (word
timings, as a plain list of `[word, start_ms, end_ms]` triples).

KNOWN LIMITATION, flagged not fixed: if you swap the underlying provider
(e.g. Azure to edge-tts) on an EXISTING cache directory without clearing
it, old entries stay in whatever codec the old provider produced; nothing
here tracks or validates codec/format consistency across a cache
directory's lifetime. Not a correctness bug for a single provider's own
use, but worth knowing before mixing providers over the same cache_dir.

No cache eviction/size limit — grows unbounded. Not addressed here (no
usage data yet to size this against, same reasoning D11 gives for
deferring supervised calibration).
"""

import hashlib
import json
from pathlib import Path

from core.interfaces import TTSProvider
from core.models import WordTiming


class CachingTTSProvider:
    """Wraps any TTSProvider with a filesystem cache keyed by (text, voice, rate)."""

    def __init__(self, provider: TTSProvider, cache_dir: str | Path):
        self._provider = provider
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def voice(self) -> str:
        return self._provider.voice

    def _cache_key(self, text: str, rate: float) -> str:
        raw = f"{text}|{self._provider.voice}|{rate}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self._cache_dir / f"{key}.audio", self._cache_dir / f"{key}.json"

    def synthesize(self, text: str, rate: float = 1.0) -> tuple[bytes, list[WordTiming]]:
        key = self._cache_key(text, rate)
        audio_path, timings_path = self._paths(key)

        if audio_path.exists() and timings_path.exists():
            audio = audio_path.read_bytes()
            timings_data = json.loads(timings_path.read_text(encoding="utf-8"))
            timings = [WordTiming(word=w, start_ms=s, end_ms=e) for w, s, e in timings_data]
            return audio, timings

        audio, timings = self._provider.synthesize(text, rate=rate)

        audio_path.write_bytes(audio)
        timings_path.write_text(
            json.dumps([[t.word, t.start_ms, t.end_ms] for t in timings]),
            encoding="utf-8",
        )

        return audio, timings