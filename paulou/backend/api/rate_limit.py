"""Per-client rate limits for the endpoints that cost the most (Decision Log D71).

Two buckets, each with a per-minute and a per-hour limit per client IP:
- "tts": `POST /sentences` and `GET /guide/audio` -- every request that can
  make the server call the TTS service. edge-tts is an unofficial protocol
  (D31, D49): the server calls it from ONE IP for every user, so a single
  client sending hundreds of sentences could get that IP blocked for all.
- "attempt": `POST /attempts` -- the wav2vec2 decode, the most CPU per
  request. (Decodes already run one at a time, `AppState.decode_lock`, D52;
  this limit stops one client from filling that queue.)

Every request to a limited endpoint counts, including one answered from a
cache or rejected as invalid: simpler, and abuse is counted either way.
Reference clips (`GET /sentences/{id}/audio`) are not limited: they belong to
a sentence that was already counted, and each prepared sentence synthesizes
at most one extra reference (the slow one).

In-memory sliding window, one process only: limits reset when the server
restarts, and several workers would each keep their own counts. Good enough
for the MVP's single-process deployment (D53, D70).
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

# Above this many tracked clients, idle ones are swept on the next hit, so
# memory stays bounded.
_SWEEP_THRESHOLD = 10_000


class SlidingWindowLimiter:
    """Allows at most `limit` hits per `window_s` seconds per key, for each
    (limit, window_s) pair. A pair with limit <= 0 is ignored; with no
    active pair, every hit is allowed.

    Thread-safe: FastAPI runs the sync endpoints in a thread pool.
    """

    def __init__(
        self,
        limits: list[tuple[int, float]],
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limits = [(limit, window) for limit, window in limits if limit > 0]
        self._longest = max((w for _l, w in self.limits), default=0.0)
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.limits)

    def hit(self, key: str) -> float | None:
        """Record a hit for `key` if allowed and return None; otherwise
        record nothing and return the seconds to wait before retrying."""
        if not self.limits:
            return None
        now = self._clock()
        with self._lock:
            if len(self._hits) > _SWEEP_THRESHOLD:
                self._sweep(now)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self._longest:
                hits.popleft()

            wait = 0.0
            for limit, window in self.limits:
                in_window = [t for t in hits if t > now - window]
                if len(in_window) >= limit:
                    # The oldest hit that has to leave the window first.
                    oldest = in_window[len(in_window) - limit]
                    wait = max(wait, oldest + window - now)
            if wait > 0:
                return wait
            hits.append(now)
            return None

    def _sweep(self, now: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= now - self._longest]:
            del self._hits[key]


def client_key(peer_host: str | None, forwarded_for: str | None, trust_forwarded_for: bool) -> str:
    """The client IP used as the rate-limit key.

    Behind a reverse proxy (needed for HTTPS) every request comes from the
    proxy's IP. With `trust_forwarded_for`, the RIGHTMOST address of
    X-Forwarded-For is used: the one appended by our own proxy. The leftmost
    ones are written by the client and can be forged. Only enable it when the
    backend is reachable through that one proxy and nothing else.
    """
    if trust_forwarded_for and forwarded_for:
        last = forwarded_for.split(",")[-1].strip()
        if last:
            return last
    return peer_host or "unknown"


def retry_after_header(wait_s: float) -> str:
    """Retry-After value: whole seconds, at least 1."""
    return str(max(1, math.ceil(wait_s)))
