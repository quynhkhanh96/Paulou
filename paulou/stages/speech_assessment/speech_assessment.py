"""Speech Assessment orchestration: scores a whole chunk in one call.

This is the top-level entry point for the redesigned pipeline (Decision
Log D36-D41): given a chunk's PronunciationUnits and its audio, wires a
real FreePhoneRecognizer through align_phonemes and merge_chunk_results to
produce one UnitResult per unit.

NOT a pure function — score_chunk calls FreePhoneRecognizer.decode(), an
external/model-backed dependency (Decision Log D12). Kept swappable via a
Protocol parameter (not yet wired through a config/registry, since
pipeline.py doesn't exist yet — same situation D31 already noted for TTS).
This module has no import-time dependency on any real FreePhoneRecognizer
implementation, so it's fully testable with a stub — see test_speech_
assessment.py — without needing Stage B (a real model) to exist. Stage B
now consists of exactly two things: a real FreePhoneRecognizer
implementation, and the diagnostic audio set to validate it (Decision Log
D10/D36, MVP-blocking).
"""

from core.interfaces import FreePhoneRecognizer
from core.models import PronunciationUnit, UnitResult
from stages.speech_assessment.align import align_phonemes
from stages.speech_assessment.calibration import PhoneStats
from stages.speech_assessment.merge import merge_chunk_results


def _build_canonical_sequence(units: list[PronunciationUnit]) -> tuple[list[str], list[str]]:
    """Flatten a chunk's units into one canonical phoneme sequence, plus a
    parallel array of which unit_id owns each phoneme.

    Pure, and deliberately separate from align_phonemes (Decision Log
    D38's design discussion) — align_phonemes only knows about flat
    sequences, not PronunciationUnit; this is the one place that bridges
    the two.
    """
    canonical_phonemes: list[str] = []
    unit_ids: list[str] = []
    for unit in units:
        canonical_phonemes.extend(unit.phonemes)
        unit_ids.extend([unit.id] * len(unit.phonemes))
    return canonical_phonemes, unit_ids


def score_chunk(
    units: list[PronunciationUnit],
    audio: bytes,
    free_phone_recognizer: FreePhoneRecognizer,
    phone_stats: dict[str, PhoneStats],
    fallback_phone_class: dict[str, str] | None = None,
) -> list[UnitResult]:
    """Score every PronunciationUnit in a chunk against one audio recording.

    Raises ValueError if `units` is empty. Any error from
    `align_phonemes` (e.g. empty canonical phonemes, mismatched lengths
    from a malformed FreePhoneRecognizer) propagates unchanged — this
    function adds no additional validation of its own beyond the empty
    check, since align_phonemes and merge_chunk_results already validate
    their own inputs.
    """
    if not units:
        raise ValueError("At least one PronunciationUnit is required to score a chunk.")

    canonical_phonemes, unit_ids = _build_canonical_sequence(units)
    decoded_phonemes, decoded_confidences, decoded_boundaries = free_phone_recognizer.decode(audio)

    ops = align_phonemes(
        canonical_phonemes, unit_ids, decoded_phonemes, decoded_confidences, decoded_boundaries
    )
    return merge_chunk_results(ops, phone_stats, fallback_phone_class)