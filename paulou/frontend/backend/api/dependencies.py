"""Shared application state and FastAPI dependencies."""

import io
import logging
import threading
import wave
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

from backend.api.settings import Settings
from backend.api.store import SentenceStore

if TYPE_CHECKING:  # typing only: importing pipeline pulls spaCy in at import time
    from pipeline import PaulouPipeline

logger = logging.getLogger("paulou.api")


def api_error(status: int, code: str, message: str) -> HTTPException:
    """Error with a machine-readable `code` (the frontend switches on it) and
    a message safe to show. Internal detail goes to the log, not the body."""
    return HTTPException(status_code=status, detail={"code": code, "message": message})


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
