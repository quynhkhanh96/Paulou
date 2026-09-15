"""Feedback templating.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

REDESIGNED from the original single-template-per-unit approach (Decision
Log D32, supersedes part of the original D25/D19 implementation): instead
of picking ONE template based on the unit's overall `calibrated_score` and
naming only the single weakest phone, this groups ALL phones in
`phone_scores` by score bracket (same 85-100 / 60-84 / 0-59 thresholds as
the Architecture Spec's stage 5f table) and produces one sentence per
non-empty bracket, plus one overall sentence for `calibrated_score` itself.
This surfaces what was done well AND what needs work in the same unit,
rather than only the weakest point — and, per the design discussion, is
what makes MEAN (rather than MIN) a reasonable choice for the stage 5e
phone-to-unit score aggregation: a MIN-only summary would silently hide
good phones in the same unit, but this per-bracket breakdown surfaces them
regardless of which aggregation the unit-level score uses.

APPLIES UNIFORMLY TO ALL UNIT TYPES now — no `unit_type` parameter, no
special-casing. Per Decision Log D19, this exercises the SECOND of the two
options D19 explicitly allowed for `liaison_group`: "raw GOP is shown with
an explicit low-confidence caveat" (rather than the first option, "no
auto-score is shown", which the original NotImplementedError enforced).
Branch 1 GOP can score individual phones within a liaison_group's combined
sequence for substitution-style accuracy — what it can't reliably do is
confirm the liaison sound wasn't entirely missing or added (an
insertion/deletion question, Branch 2's job). This function has no way to
know or express that caveat itself (it only sees phone_scores + a
calibrated_score) — attaching a "this score may be unreliable for
liaison" caveat in the UI is the CALLER's responsibility, using
`PronunciationUnit.type` which this function doesn't take as input at all.

FLAGGED, not specced anywhere (this function's own design choices):
- Exact wording of the per-bracket and overall sentences — invented here,
  not given anywhere in the notes. Easy to revise; the bracket boundaries
  and grouping logic are the part that matters more than the copy.
- Singular vs. plural phrasing: a bracket with exactly one phone gets
  singular wording ("the [X] sound"), 2+ gets plural ("these sounds:
  [X, Y]") — reads oddly otherwise, especially for short `single` units
  that often have only 1-3 phones total.
- Concatenation order: overall sentence first, then good / close / needs-
  work brackets in that order, skipping empty brackets. Joined with a
  single space into one `feedback_text` string.

Deviation from the literal Architecture Spec table, unchanged from before:
the spec lists "Input: UnitResult" for this stage, but UnitResult.
feedback_text is the very thing this function produces — taking a full
UnitResult as input would be circular. This function takes the specific
fields it needs directly; the caller (merge, stage 5e) builds the final
UnitResult afterward, feedback_text included.
"""

from core.models import PhoneScore

_GOOD = (85, 100)
_CLOSE = (60, 84)
_NEEDS_WORK = (0, 59)


def _in_range(score: int, bounds: tuple[int, int]) -> bool:
    low, high = bounds
    return low <= score <= high


def _join_phones(phones: list[str]) -> str:
    return ", ".join(phones)


def _good_sentence(phones: list[str]) -> str:
    if len(phones) == 1:
        return f"Good pronunciation on the {phones[0]} sound!"
    return f"Good pronunciation on these sounds: {_join_phones(phones)}!"


def _close_sentence(phones: list[str]) -> str:
    if len(phones) == 1:
        return f"Close, watch the {phones[0]} sound."
    return f"Close, watch these sounds: {_join_phones(phones)}."


def _needs_work_sentence(phones: list[str]) -> str:
    if len(phones) == 1:
        return f"The {phones[0]} sound needs work, try the slow sample."
    return f"These sounds need work, try the slow sample: {_join_phones(phones)}."


def _overall_sentence(calibrated_score: int) -> str:
    if _in_range(calibrated_score, _GOOD):
        return "Overall: great job!"
    if _in_range(calibrated_score, _CLOSE):
        return "Overall: pretty good, a little more practice will help."
    if _in_range(calibrated_score, _NEEDS_WORK):
        return "Overall: this one needs more practice."
    raise ValueError(
        f"calibrated_score {calibrated_score} is outside the expected 0-100 range."
    )


def generate_feedback(calibrated_score: int, phone_scores: list[PhoneScore]) -> str:
    """Generate feedback text for a scored PronunciationUnit.

    Applies uniformly to any unit type — see module docstring for the
    Decision Log D19/D32 implications of using this for `liaison_group`
    units too. Raises ValueError if `phone_scores` is empty, or if
    `calibrated_score` is outside the expected 0-100 range.
    """
    if not phone_scores:
        raise ValueError("At least one PhoneScore is required to generate feedback.")

    good = [p.phone for p in phone_scores if _in_range(p.calibrated_score, _GOOD)]
    close = [p.phone for p in phone_scores if _in_range(p.calibrated_score, _CLOSE)]
    needs_work = [p.phone for p in phone_scores if _in_range(p.calibrated_score, _NEEDS_WORK)]

    sentences = [_overall_sentence(calibrated_score)]
    if good:
        sentences.append(_good_sentence(good))
    if close:
        sentences.append(_close_sentence(close))
    if needs_work:
        sentences.append(_needs_work_sentence(needs_work))

    return " ".join(sentences)