import pytest

from core.models import AlignmentOp
from stages.speech_assessment.calibration import PhoneStats, calibrate_score
from stages.speech_assessment.scoring import score_alignment_op


def _op(
    op_type,
    unit_id="unit_0",
    canonical_phoneme="a",
    decoded_phoneme="a",
    confidence=0.9,
):
    return AlignmentOp(
        op_type=op_type,
        unit_id=unit_id,
        canonical_phoneme=canonical_phoneme,
        decoded_phoneme=decoded_phoneme,
        confidence=confidence,
        start_ms=None,
        end_ms=None,
    )


def test_deletion_scores_zero():
    op = _op("deletion", canonical_phoneme="z", decoded_phoneme=None, confidence=None)
    stats = {"z": PhoneStats(mean=0.0, std=1.0, sample_size=100)}
    assert score_alignment_op(op, phone_stats=stats) == 0


def test_deletion_ignores_missing_confidence():
    # Deletion is the one op_type allowed to have confidence=None (no
    # decoded frame exists) — must not raise on that account.
    op = _op("deletion", confidence=None)
    assert score_alignment_op(op, phone_stats={}) == 0


def test_match_delegates_to_calibrate_score():
    stats = {"a": PhoneStats(mean=0.0, std=1.0, sample_size=100)}
    op = _op("match", canonical_phoneme="a", decoded_phoneme="a", confidence=0.0)
    expected = calibrate_score(raw_value=0.0, phone="a", phone_stats=stats)
    assert score_alignment_op(op, phone_stats=stats) == expected


def test_match_uses_canonical_phoneme_to_look_up_stats():
    # For a match, canonical_phoneme == decoded_phoneme, but the lookup
    # must explicitly key off canonical_phoneme, not decoded_phoneme —
    # this test would still pass if the implementation used either field
    # for a match, but documents the intended contract for future edits.
    stats = {"a": PhoneStats(mean=2.0, std=1.0, sample_size=100)}
    op = _op("match", canonical_phoneme="a", decoded_phoneme="a", confidence=2.0)
    assert score_alignment_op(op, phone_stats=stats) == 50


def test_match_without_confidence_raises():
    op = _op("match", confidence=None)
    with pytest.raises(ValueError):
        score_alignment_op(op, phone_stats={})


def test_substitution_high_confidence_gives_low_score():
    op = _op("substitution", canonical_phoneme="s", decoded_phoneme="ʃ", confidence=0.9)
    assert score_alignment_op(op, phone_stats={}) == 10


def test_substitution_low_confidence_gives_high_score():
    op = _op("substitution", canonical_phoneme="s", decoded_phoneme="ʃ", confidence=0.1)
    assert score_alignment_op(op, phone_stats={}) == 90


def test_substitution_without_confidence_raises():
    op = _op("substitution", confidence=None)
    with pytest.raises(ValueError):
        score_alignment_op(op, phone_stats={})


def test_insertion_uses_same_formula_as_substitution():
    ins = _op("insertion", canonical_phoneme=None, decoded_phoneme="ə", confidence=0.7)
    sub = _op("substitution", canonical_phoneme="s", decoded_phoneme="ə", confidence=0.7)
    assert score_alignment_op(ins, phone_stats={}) == score_alignment_op(sub, phone_stats={})


def test_insertion_without_confidence_raises():
    op = _op("insertion", canonical_phoneme=None, confidence=None)
    with pytest.raises(ValueError):
        score_alignment_op(op, phone_stats={})


def test_unknown_op_type_raises():
    # AlignmentOpType is a Literal, not enforced at runtime by a plain
    # dataclass — guard against a typo'd/invalid op_type reaching here.
    op = _op("bogus_type")
    with pytest.raises(ValueError):
        score_alignment_op(op, phone_stats={})