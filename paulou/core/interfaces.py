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


# Obsolete per Decision Log D36 (single free-decode + 3-way alignment
# pipeline replaces the two-branch GOP/free-decode design). Kept dormant,
# not deleted: still imports RawPhoneScore (core/models.py), which is
# itself kept dormant for the same reason. FreePhoneRecognizer below is
# the replacement — the sole model-backed interface for Speech Assessment
# going forward.
class GOPScorer(Protocol):
    def score(self, audio: bytes, canonical_phonemes: list[str]) -> list[RawPhoneScore]: ...


class FreePhoneRecognizer(Protocol):
    """Unconstrained phone recognition — no reference-sequence constraint,
    unlike GOPScorer's forced-alignment. See Architecture Spec stage 5b'
    and Decision Log D36/D37.

    Returns, all the same length: the decoded phone sequence; each
    position's confidence (the decoder's own top-1 probability there —
    since the decoded phone at position j is itself the argmax of that
    position's distribution, this already equals the max of the full
    posterior, so there's no need to also return the full distribution);
    and each position's (start_ms, end_ms) time boundary in the source
    audio. Simplified from the Architecture Spec's original stage 5b
    signature (which returned the full posterior per position) once
    nothing downstream needed more than one float per position — see
    Decision Log D37.
    """

    def decode(self, audio: bytes) -> tuple[list[str], list[float], list[tuple[int, int]]]: ...