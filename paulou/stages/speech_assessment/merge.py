"""Merge: combine a unit's per-phone calibrated scores into a UnitResult.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Architecture Spec stage 5e originally specs `Input: gop_scores:
list[PhoneScore], alignment_ops: list[AlignmentOp]` (combining Branch 1 +
Branch 2 per unit). Branch 2 doesn't exist yet (D19), so this MVP version
only handles Branch 1's `phone_scores` — no `alignment_ops` parameter at
all, matching `UnitResult`'s own current field set (core/models.py).

AGGREGATION (Decision Log D33): unit-level `calibrated_score` is the MEAN
of its phone_scores' calibrated_score, rounded to the nearest int — not
MIN. MIN was the original instinct (kept score and feedback text
consistent when feedback could only name one weakest phone), but D32's
feedback redesign (grouping ALL phones by bracket, not just the weakest)
removed that constraint: a mean score paired with a per-bracket feedback
breakdown already surfaces both strong and weak phones, without a harsh
single low phone dragging the whole unit's displayed score down
disproportionately.

Expects `phone_scores` to already be calibrated (each PhoneScore's
`calibrated_score` populated) — this function does not call
`calibrate_score` itself (Decision Log D12/D25 precedent: pure functions
don't call each other's stage boundaries; an orchestration layer, not yet
built, is responsible for calibrating raw GOP output before this runs).
"""

from core.models import PhoneScore, UnitResult
from stages.speech_assessment.feedback import generate_feedback


def merge_to_unit_result(unit_id: str, phone_scores: list[PhoneScore]) -> UnitResult:
    """Merge one unit's calibrated phone_scores into a UnitResult.

    Raises ValueError if `phone_scores` is empty.
    """
    if not phone_scores:
        raise ValueError(f"Unit {unit_id!r}: at least one PhoneScore is required to merge.")

    calibrated_score = round(
        sum(p.calibrated_score for p in phone_scores) / len(phone_scores)
    )
    feedback_text = generate_feedback(calibrated_score, phone_scores)

    return UnitResult(
        unit_id=unit_id,
        calibrated_score=calibrated_score,
        phone_scores=phone_scores,
        feedback_text=feedback_text,
    )