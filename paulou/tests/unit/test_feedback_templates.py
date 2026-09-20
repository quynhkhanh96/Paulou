import pytest

from core.models import AlignmentOp, ScoredAlignmentOp
from stages.speech_assessment.feedback import generate_feedback


def _scored(op_type, accuracy_score, canonical="a", decoded="a"):
    op = AlignmentOp(
        op_type=op_type,
        unit_id="unit_0",
        canonical_phoneme=canonical,
        decoded_phoneme=decoded,
        confidence=0.5 if op_type != "deletion" else None,
        start_ms=None,
        end_ms=None,
    )
    return ScoredAlignmentOp(op=op, accuracy_score=accuracy_score)


def test_all_match_good_bracket_singular():
    ops = [_scored("match", 90, canonical="a")]
    result = generate_feedback(90, ops)
    assert result == "Overall: great job! Good pronunciation on the a sound!"


def test_all_match_good_bracket_plural():
    ops = [_scored("match", 90, canonical="a"), _scored("match", 95, canonical="m")]
    result = generate_feedback(92, ops)
    assert result == "Overall: great job! Good pronunciation on these sounds: a, m!"


def test_match_mixed_brackets_order_is_good_close_needs_work():
    ops = [
        _scored("match", 90, canonical="a"),
        _scored("match", 70, canonical="ʁ"),
        _scored("match", 70, canonical="ø"),
        _scored("match", 30, canonical="t"),
        _scored("match", 30, canonical="d"),
    ]
    result = generate_feedback(58, ops)
    assert result == (
        "Overall: this one needs more practice. "
        "Good pronunciation on the a sound! "
        "Close, watch these sounds: ʁ, ø. "
        "These sounds need work, try the slow sample: t, d."
    )


def test_overall_sentence_boundaries():
    ops = [_scored("match", 50, canonical="a")]
    assert generate_feedback(85, ops).startswith("Overall: great job!")
    assert generate_feedback(84, ops).startswith("Overall: good effort")
    assert generate_feedback(60, ops).startswith("Overall: good effort")
    assert generate_feedback(59, ops).startswith("Overall: this one needs more practice.")
    assert generate_feedback(0, ops).startswith("Overall: this one needs more practice.")


def test_deletion_sentence_singular():
    ops = [_scored("deletion", 0, canonical="z", decoded=None)]
    result = generate_feedback(0, ops)
    assert result == "Overall: this one needs more practice. Missing the z sound."


def test_deletion_sentence_plural():
    ops = [
        _scored("deletion", 0, canonical="z", decoded=None),
        _scored("deletion", 0, canonical="t", decoded=None),
    ]
    result = generate_feedback(0, ops)
    assert "Missing these sounds: z, t." in result


def test_insertion_sentence_singular():
    ops = [_scored("insertion", 20, canonical=None, decoded="ə")]
    result = generate_feedback(20, ops)
    assert "Extra sound heard: ə." in result


def test_insertion_sentence_plural():
    ops = [
        _scored("insertion", 20, canonical=None, decoded="ə"),
        _scored("insertion", 20, canonical=None, decoded="s"),
    ]
    result = generate_feedback(20, ops)
    assert "Extra sounds heard: ə, s." in result


def test_substitution_sentence_singular():
    ops = [_scored("substitution", 10, canonical="s", decoded="ʃ")]
    result = generate_feedback(10, ops)
    assert "You substituted a sound: s→ʃ." in result


def test_substitution_sentence_plural():
    ops = [
        _scored("substitution", 10, canonical="s", decoded="ʃ"),
        _scored("substitution", 10, canonical="m", decoded="n"),
    ]
    result = generate_feedback(10, ops)
    assert "You substituted these sounds: s→ʃ, m→n." in result


def test_sentence_order_with_all_four_op_types():
    ops = [
        _scored("deletion", 0, canonical="z", decoded=None),
        _scored("insertion", 20, canonical=None, decoded="ə"),
        _scored("substitution", 10, canonical="s", decoded="ʃ"),
        _scored("match", 90, canonical="a"),
    ]
    result = generate_feedback(30, ops)
    assert result == (
        "Overall: this one needs more practice. "
        "Missing the z sound. "
        "Extra sound heard: ə. "
        "You substituted a sound: s→ʃ. "
        "Good pronunciation on the a sound!"
    )


def test_overview_sentence_appears_even_with_a_single_structural_error():
    # A single-phone unit that was dropped entirely still gets the overall
    # sentence, even though it's the only op and there's nothing to
    # bracket — product decision: the overview and the specific-error
    # sentence are not considered redundant.
    ops = [_scored("deletion", 0, canonical="z", decoded=None)]
    result = generate_feedback(0, ops)
    assert result == "Overall: this one needs more practice. Missing the z sound."


def test_empty_scored_ops_raises():
    with pytest.raises(ValueError):
        generate_feedback(50, [])


def test_out_of_range_calibrated_score_raises():
    ops = [_scored("match", 50, canonical="a")]
    with pytest.raises(ValueError):
        generate_feedback(101, ops)
    with pytest.raises(ValueError):
        generate_feedback(-1, ops)