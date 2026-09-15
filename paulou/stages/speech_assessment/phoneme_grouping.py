"""Phoneme-to-unit grouping (Architecture Spec stage 5a-2, Decision Log D20).

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Not a replacement for merge (stage 5e) — a preparatory step that turns one
flat GOP call's output (for a whole chunk/sentence, per D20's granularity-
agnostic design) into the per-unit shape 5e expects.

Relies on `PronunciationUnit.phonemes` (a field the Architecture Spec's
original data model didn't have — added specifically to make this
grouping possible; see core/models.py's docstring). Groups by ORDER and
COUNT only: walks `phone_scores` sequentially, consuming
`len(unit.phonemes)` entries for each unit in turn. This assumes
`phone_scores` came from a GOP call whose canonical_phonemes argument was
built by concatenating each unit's `phonemes` in the same order as
`units` — if that assumption doesn't hold (e.g. phone_scores from a
different phoneme sequence, or units out of order), the grouping will be
silently wrong rather than obviously wrong, since nothing here can verify
WHICH phoneme each score belongs to, only how many. The length check below
catches a COUNT mismatch, but not a correctly-counted-yet-misaligned one.
"""

from core.models import PhoneScore, PronunciationUnit


def group_phone_scores_by_unit(
    phone_scores: list[PhoneScore],
    units: list[PronunciationUnit],
) -> dict[str, list[PhoneScore]]:
    """Slice a flat, chunk-level `phone_scores` list into per-unit groups.

    Returns `{unit.id: [that unit's PhoneScores]}`, in the same order as
    `units`. Raises ValueError if the total phoneme count across `units`
    doesn't match `len(phone_scores)`.
    """
    expected_total = sum(len(unit.phonemes) for unit in units)
    if expected_total != len(phone_scores):
        raise ValueError(
            f"Expected {expected_total} phone scores (sum of phoneme counts "
            f"across {len(units)} units), got {len(phone_scores)}."
        )

    grouped: dict[str, list[PhoneScore]] = {}
    cursor = 0
    for unit in units:
        count = len(unit.phonemes)
        grouped[unit.id] = phone_scores[cursor : cursor + count]
        cursor += count

    return grouped