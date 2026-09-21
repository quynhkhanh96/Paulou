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

Also provides `merge_chunk_results`, which groups a whole chunk's flat
`align_phonemes` output by `unit_id` and calls `merge_to_unit_result` once
per unit — the missing link between align_phonemes (chunk-level) and
merge_to_unit_result (deliberately unit-level only). Still a pure
function, no model involved.

`feedback_text` now calls the redesigned `generate_feedback`
(stages/speech_assessment/feedback.py) — previously left as a placeholder
empty string until feedback templating was redesigned; that redesign is
done, see that module's docstring.
"""

from core.models import AlignmentOp, ScoredAlignmentOp, UnitResult
from stages.speech_assessment.calibration import PhoneStats
from stages.speech_assessment.feedback import generate_feedback
from stages.speech_assessment.scoring import score_alignment_op


def merge_chunk_results(
    ops: list[AlignmentOp],
    phone_stats: dict[str, PhoneStats],
    fallback_phone_class: dict[str, str] | None = None,
) -> list[UnitResult]:
    """Group a whole chunk's flat AlignmentOps by unit_id, then merge each
    group into its own UnitResult via merge_to_unit_result.

    This is the piece align_phonemes and merge_to_unit_result don't cover
    between them: align_phonemes operates across a whole chunk (multiple
    units' canonical phonemes concatenated together) and returns one flat
    list; merge_to_unit_result deliberately only accepts one unit's ops at
    a time (guarded — see its mismatched-unit_id check). Grouping by
    unit_id here is the missing link, and — unlike a real
    FreePhoneRecognizer — needs no model at all: it's a pure function over
    data align_phonemes has already produced.

    Groups are built with a dict keyed by unit_id (not, say,
    itertools.groupby), so units are returned in first-seen order without
    requiring each unit's ops to already be contiguous in `ops` — true in
    practice given how align_phonemes constructs its output, but not
    relied on here as an assumption.

    Raises ValueError if `ops` is empty.
    """
    if not ops:
        raise ValueError("At least one AlignmentOp is required to merge a chunk's results.")

    ops_by_unit: dict[str, list[AlignmentOp]] = {}
    for op in ops:
        ops_by_unit.setdefault(op.unit_id, []).append(op)

    return [
        merge_to_unit_result(unit_id, unit_ops, phone_stats, fallback_phone_class)
        for unit_id, unit_ops in ops_by_unit.items()
    ]


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