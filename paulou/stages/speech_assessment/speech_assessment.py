"""Speech Assessment orchestration (Architecture Spec stage 5).

Composes the stage's sub-steps into one function, analogous to
stages/chunk_analyzer/chunk_analyzer.py for stage 2. Not itself Protocol/
registered (Decision Log D12) — glue/composition code, like `analyze_chunk`.

Flow:
    audio + units
      -> build canonical_phonemes by concatenating each unit's `.phonemes`,
         in order (one GOP call for the whole chunk, per D20 — NOT one
         call per unit, to preserve coarticulation context)
      -> gop_scorer.score(audio, canonical_phonemes) -> list[RawPhoneScore]
         (UNCALIBRATED — see Decision Log D34)
      -> calibrate_score() on each entry -> list[PhoneScore]
      -> group_phone_scores_by_unit() (5a-2, D20) -> per-unit PhoneScores
      -> merge_to_unit_result() (5e, D33 — MEAN aggregation) -> UnitResult
         per unit

STAGE A SCOPE: `gop_scorer` is dependency-injected (matches `analyze_chunk`'s
`g2p` parameter) — this function doesn't know or care whether it's a real
GOPScorer (Kaldi/gop-ft, not built yet — Stage B) or a test stub. Tested
here only with a simulated stub; see tests/unit/test_speech_assessment.py.

No unit_type special-casing anywhere in this flow (Decision Log D19/D32/
D33) — `liaison_group` units go through exactly the same GOP scoring,
calibration, grouping, and merge as `single`/`elision_group` units. Per
D19's second option, attaching a "may be unreliable for liaison" caveat
in the UI is the CALLER's responsibility (using `PronunciationUnit.type`),
not this function's.
"""

from core.interfaces import GOPScorer
from core.models import PhoneScore, PronunciationUnit, UnitResult
from stages.speech_assessment.calibration import (
    DEFAULT_MIN_SAMPLE_SIZE,
    PhoneStats,
    calibrate_score,
)
from stages.speech_assessment.merge import merge_to_unit_result
from stages.speech_assessment.phoneme_grouping import group_phone_scores_by_unit


def score_chunk(
    audio: bytes,
    units: list[PronunciationUnit],
    gop_scorer: GOPScorer,
    phone_stats: dict[str, PhoneStats],
    fallback_phone_class: dict[str, str] | None = None,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> list[UnitResult]:
    """Score every PronunciationUnit in a chunk against one audio recording.

    `phone_stats`/`fallback_phone_class`/`min_sample_size` are forwarded
    straight to `calibrate_score` for each phone — see calibration.py for
    what these mean (no real corpus-derived stats exist yet, D11/D24).

    Raises ValueError if `gop_scorer` returns a different number of scores
    than canonical phonemes were requested for.
    """
    if not units:
        return []

    canonical_phonemes = [phone for unit in units for phone in unit.phonemes]

    raw_scores = gop_scorer.score(audio, canonical_phonemes)
    if len(raw_scores) != len(canonical_phonemes):
        raise ValueError(
            f"GOPScorer returned {len(raw_scores)} scores for "
            f"{len(canonical_phonemes)} canonical phonemes."
        )

    phone_scores = [
        PhoneScore(
            phone=r.phone,
            raw_gop=r.raw_gop,
            calibrated_score=calibrate_score(
                r.raw_gop, r.phone, phone_stats, fallback_phone_class, min_sample_size
            ),
            start_ms=r.start_ms,
            end_ms=r.end_ms,
        )
        for r in raw_scores
    ]

    grouped = group_phone_scores_by_unit(phone_scores, units)

    return [merge_to_unit_result(unit.id, grouped[unit.id]) for unit in units]