"""Feedback templating.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Threshold-based template lookup (Architecture Spec, stage 5f table), not raw
score display.

MVP SCOPE (Decision Log D19): only `single` units (`phoneme_accuracy`,
Branch 1 / GOP) get automated feedback. `liaison_group` units have no
trustworthy automated score in MVP — calling `generate_feedback` with
unit_type="liaison_group" raises NotImplementedError rather than silently
returning a templated string with no real score behind it.

Deviation from the literal Architecture Spec table worth flagging: the spec
lists "Input: UnitResult" for this stage, but UnitResult.feedback_text is
the very thing this function produces — taking a full UnitResult as input
would be circular. This function instead takes the specific fields it
needs (calibrated_score, phone_scores) directly; the caller (merge, stage
5e) is expected to build the final UnitResult afterward, feedback_text
included.

Also flagged, not specced anywhere: which phone gets named as "[X]" when a
unit has multiple phones. This implementation picks the single
lowest-`calibrated_score` phone — the most natural reading, but a choice
made here, not one dictated by the notes.
"""

from typing import Literal

from core.models import PhoneScore

SINGLE_FEEDBACK_TEMPLATES: tuple[tuple[int, int, str], ...] = (
    (85, 100, "Good pronunciation!"),
    (60, 84, "Close, watch the [X] sound"),
    (0, 59, "The [X] sound needs work, try the slow sample"),
)


def _fill_placeholder(template: str, weakest_phone: str) -> str:
    return template.replace("[X]", weakest_phone)


def generate_feedback(
    unit_type: Literal["single", "liaison_group"],
    calibrated_score: int,
    phone_scores: list[PhoneScore] | None = None,
) -> str:
    """Generate feedback text for a scored PronunciationUnit.

    Raises NotImplementedError for `liaison_group` (out of MVP scope, D19).
    Raises ValueError if `single` units are missing phone_scores, or if
    calibrated_score is outside the expected 0-100 range.
    """
    if unit_type == "liaison_group":
        raise NotImplementedError(
            "Liaison feedback templating is out of MVP scope (Decision Log "
            "D19) — liaison_group units don't get a trustworthy automated "
            "score to template against yet."
        )
    if unit_type != "single":
        raise ValueError(f"Unknown unit type: {unit_type!r}")

    if not phone_scores:
        raise ValueError(
            "Single units require at least one PhoneScore to generate feedback."
        )

    weakest_phone = min(phone_scores, key=lambda p: p.calibrated_score).phone

    for low, high, template in SINGLE_FEEDBACK_TEMPLATES:
        if low <= calibrated_score <= high:
            return _fill_placeholder(template, weakest_phone)

    raise ValueError(
        f"calibrated_score {calibrated_score} is outside the expected 0-100 range."
    )
