"""Merge: combines one PronunciationUnit's AlignmentOps into a UnitResult.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Replaces the old GOP-based merge_to_unit_result (Architecture Spec stage
5e, Decision Log D33) under D36's single free-decode + 3-way alignment
pipeline. D33's choice of MEAN (not MIN) is kept unchanged — only the
input changed, from a unit's PhoneScores to its ScoredAlignmentOps
(stages/speech_assessment/scoring.py::score_alignment_op applied to each
op). MEAN naturally extends to the new op types: a deletion's accuracy_score
is 0, so one dropped sound pulls a unit's average down without a single
harsh phone dominating the way MIN would.

`feedback_text` now calls the redesigned `generate_feedback`
(stages/speech_assessment/feedback.py) — previously left as a placeholder
empty string until feedback templating was redesigned; that redesign is
done, see that module's docstring.
"""

from core.models import AlignmentOp, ScoredAlignmentOp, UnitResult
from stages.speech_assessment.calibration import PhoneStats
from stages.speech_assessment.feedback import generate_feedback
from stages.speech_assessment.scoring import score_alignment_op


def merge_to_unit_result(
    unit_id: str,
    ops: list[AlignmentOp],
    phone_stats: dict[str, PhoneStats],
    fallback_phone_class: dict[str, str] | None = None,
) -> UnitResult:
    """Score each op, aggregate via MEAN (Decision Log D33), build a UnitResult.

    Raises ValueError if `ops` is empty (nothing to aggregate) or if any
    op's `unit_id` doesn't match the `unit_id` argument (a real integration
    bug — this function must only ever see one unit's ops at a time).
    """
    if not ops:
        raise ValueError(f"Unit {unit_id!r}: at least one AlignmentOp is required to merge.")

    mismatched = [op for op in ops if op.unit_id != unit_id]
    if mismatched:
        raise ValueError(
            f"Unit {unit_id!r}: received {len(mismatched)} op(s) belonging "
            f"to a different unit_id ({mismatched[0].unit_id!r})."
        )

    scored_ops = [
        ScoredAlignmentOp(
            op=op,
            accuracy_score=score_alignment_op(op, phone_stats, fallback_phone_class),
        )
        for op in ops
    ]

    mean_score = round(sum(s.accuracy_score for s in scored_ops) / len(scored_ops))

    return UnitResult(
        unit_id=unit_id,
        calibrated_score=mean_score,
        scored_ops=scored_ops,
        feedback_text=generate_feedback(mean_score, scored_ops),
    )