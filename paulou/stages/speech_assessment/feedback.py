"""Feedback templating: turns a unit's ScoredAlignmentOps into human-
readable feedback text.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Replaces the old feedback.py (Architecture Spec stage 5f, Decision Log
D32) under D36's single free-decode + 3-way alignment pipeline. D32's core
idea — group phones by outcome, one sentence per group, instead of naming
only the single weakest phone (D25) — is kept for `match` ops, which still
carry a continuous 0-100 score suited to bracketing. `substitution`/
`insertion`/`deletion` are different in kind: alignment already tells us
exactly what happened (which sound was missing, extra, or wrong), so
bucketing them into score brackets would throw away the most useful,
specific information alignment provides. These three always get their own
explicit sentence instead, regardless of their accuracy_score.

Design discussion (not yet in the Decision Log — pending write-up):
sentence order is overview -> deletion -> insertion -> substitution ->
match brackets (good/close/needs-work) — structural errors surfaced before
the finer-grained match feedback. The overview sentence (from
calibrated_score, i.e. the unit's MEAN) always appears, even when the unit
has only one op and that op is a structural error (e.g. a single-phone
`single` unit with just a deletion) — it's the one sentence guaranteed to
always say something, even when there's nothing to bracket.
"""

from core.models import ScoredAlignmentOp


def generate_feedback(calibrated_score: int, scored_ops: list[ScoredAlignmentOp]) -> str:
    """Build the full feedback string for one unit.

    Raises ValueError if `scored_ops` is empty (nothing to describe) or if
    `calibrated_score` is outside 0-100 (defensive — should never happen
    if merge_to_unit_result computed it).
    """
    if not scored_ops:
        raise ValueError("At least one ScoredAlignmentOp is required to generate feedback.")
    if not (0 <= calibrated_score <= 100):
        raise ValueError(f"calibrated_score must be in [0, 100], got {calibrated_score}.")

    deletions = [s for s in scored_ops if s.op.op_type == "deletion"]
    insertions = [s for s in scored_ops if s.op.op_type == "insertion"]
    substitutions = [s for s in scored_ops if s.op.op_type == "substitution"]
    matches = [s for s in scored_ops if s.op.op_type == "match"]

    sentences = [_overall_sentence(calibrated_score)]
    if deletions:
        sentences.append(_deletion_sentence(deletions))
    if insertions:
        sentences.append(_insertion_sentence(insertions))
    if substitutions:
        sentences.append(_substitution_sentence(substitutions))
    sentences.extend(_match_bracket_sentences(matches))

    return " ".join(sentences)


def _join(phones: list[str]) -> str:
    return ", ".join(phones)


def _overall_sentence(score: int) -> str:
    if score >= 85:
        return "Overall: great job!"
    if score >= 60:
        return "Overall: good effort, a few things to work on."
    return "Overall: this one needs more practice."


def _deletion_sentence(deletions: list[ScoredAlignmentOp]) -> str:
    phones = [s.op.canonical_phoneme for s in deletions]
    if len(phones) == 1:
        return f"Missing the {phones[0]} sound."
    return f"Missing these sounds: {_join(phones)}."


def _insertion_sentence(insertions: list[ScoredAlignmentOp]) -> str:
    phones = [s.op.decoded_phoneme for s in insertions]
    if len(phones) == 1:
        return f"Extra sound heard: {phones[0]}."
    return f"Extra sounds heard: {_join(phones)}."


def _substitution_sentence(substitutions: list[ScoredAlignmentOp]) -> str:
    pairs = [f"{s.op.canonical_phoneme}→{s.op.decoded_phoneme}" for s in substitutions]
    if len(pairs) == 1:
        return f"You substituted a sound: {pairs[0]}."
    return f"You substituted these sounds: {_join(pairs)}."


def _match_bracket_sentences(matches: list[ScoredAlignmentOp]) -> list[str]:
    good = [s.op.canonical_phoneme for s in matches if s.accuracy_score >= 85]
    close = [s.op.canonical_phoneme for s in matches if 60 <= s.accuracy_score < 85]
    needs_work = [s.op.canonical_phoneme for s in matches if s.accuracy_score < 60]

    sentences = []
    if good:
        if len(good) == 1:
            sentences.append(f"Good pronunciation on the {good[0]} sound!")
        else:
            sentences.append(f"Good pronunciation on these sounds: {_join(good)}!")
    if close:
        if len(close) == 1:
            sentences.append(f"Close, watch the {close[0]} sound.")
        else:
            sentences.append(f"Close, watch these sounds: {_join(close)}.")
    if needs_work:
        if len(needs_work) == 1:
            sentences.append(f"The {needs_work[0]} sound needs work, try the slow sample.")
        else:
            sentences.append(f"These sounds need work, try the slow sample: {_join(needs_work)}.")
    return sentences