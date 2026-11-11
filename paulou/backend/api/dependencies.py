"""Shared application state and FastAPI dependencies."""

import io
import logging
import threading
import wave
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request

from backend.api.rate_limit import SlidingWindowLimiter, client_key, retry_after_header
from backend.api.settings import Settings
from backend.api.store import SentenceStore

if TYPE_CHECKING:  # typing only: importing pipeline pulls spaCy in at import time
    from pipeline import PaulouPipeline

logger = logging.getLogger("paulou.api")


def api_error(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> HTTPException:
    """Error with a machine-readable `code` (the frontend switches on it) and
    a message safe to show. Internal detail goes to the log, not the body."""
    return HTTPException(
        status_code=status, detail={"code": code, "message": message}, headers=headers
    )


def silence_wav(duration_s: float = 1.0, sample_rate: int = 16_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * int(duration_s * sample_rate))
    return buf.getvalue()


@dataclass
class AppState:
    pipeline: "PaulouPipeline"
    settings: Settings
    store: SentenceStore
    calibrated: bool
    # Decode is CPU-bound (torch, all threads): one at a time, otherwise
    # concurrent attempts only oversubscribe the cores (D52).
    decode_lock: threading.Lock = field(default_factory=threading.Lock)
    ready: threading.Event = field(default_factory=threading.Event)
    warmup_error: str | None = None
    # D71: "tts" and "attempt" buckets, built from settings by `build_rate_limiters`.
    rate_limiters: dict[str, SlidingWindowLimiter] = field(default_factory=dict)

    def warm_up(self) -> None:
        """Build the free decoder and run one decode (D52): stages are built
        lazily (D48), so without this the first attempt pays ~12 s.

        A failure to BUILD the decoder is fatal (`status: error`). A failure
        of the warm-up decode itself is logged only: the model is loaded, and
        real audio may still work.
        """
        try:
            with self.decode_lock:
                decoder = self.pipeline.free_decoder
                try:
                    decoder.decode(silence_wav())
                except Exception:
                    logger.exception("warm-up decode failed (model is loaded; continuing)")
        except Exception as exc:
            logger.exception("free decoder could not be built")
            self.warmup_error = f"{type(exc).__name__}: {exc}"
            return
        self.ready.set()
        logger.info("free decoder ready")


def get_state(request: Request) -> AppState:
    return request.app.state.paulou


def build_rate_limiters(settings: Settings) -> dict[str, SlidingWindowLimiter]:
    """The two D71 buckets; a limit of 0 turns that window off."""
    return {
        "tts": SlidingWindowLimiter(
            [(settings.tts_limit_per_minute, 60.0), (settings.tts_limit_per_hour, 3600.0)]
        ),
        "attempt": SlidingWindowLimiter(
            [(settings.attempt_limit_per_minute, 60.0), (settings.attempt_limit_per_hour, 3600.0)]
        ),
    }


def rate_limit(bucket: str):
    """FastAPI dependency: count this request in `bucket` for its client, or
    answer 429 with Retry-After (D71). The message does not say which limit
    was hit: the frontend shows one friendly "server is busy" text anyway."""

    def check(request: Request, state: AppState = Depends(get_state)) -> None:
        limiter = state.rate_limiters.get(bucket)
        if limiter is None or not limiter.enabled:
            return
        key = client_key(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
            state.settings.trust_forwarded_for,
        )
        wait = limiter.hit(key)
        if wait is not None:
            logger.warning("rate limit (%s) hit by %s; retry in %.0f s", bucket, key, wait)
            raise api_error(
                429,
                "rate_limited",
                "The server is busy right now. Please try again in a moment.",
                headers={"Retry-After": retry_after_header(wait)},
            )

    return check
