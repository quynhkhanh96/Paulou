"""Converts one AlignmentOp into a 0-100 accuracy score.

Kept separate from the alignment algorithm itself (same reasoning as D34's
GOPScorer/calibration split, reapplied here per D36): alignment is a
structural, purely mechanical computation (what happened at each position);
scoring is a policy decision about how much each kind of op should count.
Two independent design surfaces, two independently testable functions.
"""

from core.models import AlignmentOp
from stages.speech_assessment.calibration import PhoneStats, calibrate_score


def score_alignment_op(
    op: AlignmentOp,
    phone_stats: dict[str, PhoneStats],
    fallback_phone_class: dict[str, str] | None = None,
) -> int:
    """Convert one AlignmentOp into a 0-100 accuracy score.

    - match: calibrated against the native-speaker confidence distribution
      for that phone — same z-score/CDF mechanism as D11, reused verbatim;
      only the underlying quantity changed (decoder confidence, not raw GOP).
    - substitution / insertion: NOT calibrated — there is no "native
      distribution of confidence-when-wrong" to compare against (native
      speech has no substitutions/insertions by definition). Uses a direct
      heuristic instead: `100 * (1 - confidence)`. A confident wrong guess
      is unambiguous evidence of an error (low score); a hesitant one may
      be an honest near-miss (higher score).
    - deletion: always 0 — no decoded frame exists to reason about at all.
    """
    if op.op_type == "deletion":
        return 0

    if op.confidence is None:
        raise ValueError(
            f"AlignmentOp of type {op.op_type!r} must have a confidence "
            "value to be scored."
        )

    if op.op_type == "match":
        return calibrate_score(
            raw_value=op.confidence,
            phone=op.canonical_phoneme,
            phone_stats=phone_stats,
            fallback_phone_class=fallback_phone_class,
        )

    if op.op_type in ("substitution", "insertion"):
        return round(100 * (1 - op.confidence))

    raise ValueError(f"Unknown AlignmentOp.op_type: {op.op_type!r}")