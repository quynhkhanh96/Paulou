"""Protocol definitions for swappable, model-backed pipeline stages.

Structural typing only (typing.Protocol) — implementations don't need to
import or subclass these; matching the method signature is enough
(Codebase Conventions). Kept here as a single source of truth for each
stage's expected interface.

Per Decision Log D12, only stages with an external/model dependency likely
to be swapped or compared get a Protocol here: sentence parser, G2P source,
TTS provider, GOP scorer, free-phone recognizer. POS tagging is deliberately
NOT here — see Decision Log D26 (plain class, not registry-swappable).
Pure, deterministic logic (liaison rules, unit assembly, calibration,
feedback, etc.) is also not here — see D12.

Added incrementally as each stage is actually built, not all at once
up front (same convention as core/models.py).
"""

from typing import Protocol

from core.models import RawPhoneScore, WordTiming


class SentenceParser(Protocol):
    def parse(self, sentence: str) -> list[str]: ...


class G2PProvider(Protocol):
    def phonemize(self, word: str) -> tuple[list[str], str]: ...


class TTSProvider(Protocol):
    voice: str
    def synthesize(self, text: str, rate: float = 1.0) -> tuple[bytes, list[WordTiming]]: ...


class GOPScorer(Protocol):
    def score(self, audio: bytes, canonical_phonemes: list[str]) -> list[RawPhoneScore]: ...