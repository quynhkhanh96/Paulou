import pytest

from core.models import AlignmentOp
from stages.speech_assessment.calibration import PhoneStats
from stages.speech_assessment.feedback import generate_feedback
from stages.speech_assessment.merge import merge_to_unit_result
from stages.speech_assessment.scoring import score_alignment_op

STATS = {"a": PhoneStats(mean=0.0, std=1.0, sample_size=100)}


def _op(op_type, unit_id="unit_0", canonical="a", decoded="a", confidence=0.9):
    return AlignmentOp(
        op_type=op_type,
        unit_id=unit_id,
        canonical_phoneme=canonical,
        decoded_phoneme=decoded,
        confidence=confidence,
        start_ms=None,
        end_ms=None,
    )


def test_mean_aggregation_not_min():
    # substitution scores are 100*(1-confidence): 0.10 -> 90, 0.30 -> 70, 0.60 -> 40
    ops = [
        _op("substitution", confidence=0.10),
        _op("substitution", confidence=0.30),
        _op("substitution", confidence=0.60),
    ]
    result = merge_to_unit_result("unit_0", ops, phone_stats=STATS)
    # (90+70+40)/3 = 66.67 rounds to 67, not 40 (MIN would give 40)
    assert result.calibrated_score == 67


def test_mean_rounds_to_nearest_int():
    # 100*(1-0.20)=80, 100*(1-0.19)=81 -> mean 80.5 -> Python's round-half-
    # to-even ("banker's rounding") gives 80, not 81.
    ops = [_op("substitution", confidence=0.20), _op("substitution", confidence=0.19)]
    result = merge_to_unit_result("unit_0", ops, phone_stats=STATS)
    assert result.calibrated_score == 80


def test_single_op_score_equals_that_op():
    ops = [_op("substitution", confidence=0.10)]
    result = merge_to_unit_result("unit_0", ops, phone_stats=STATS)
    assert result.calibrated_score == 90


def test_unit_id_and_scored_ops_pass_through_unchanged():
    ops = [_op("substitution", confidence=0.10), _op("deletion", confidence=None)]
    result = merge_to_unit_result("unit_0", ops, phone_stats=STATS)
    assert result.unit_id == "unit_0"
    assert len(result.scored_ops) == 2
    assert result.scored_ops[0].op is ops[0]
    assert result.scored_ops[0].accuracy_score == 90
    assert result.scored_ops[1].op is ops[1]
    assert result.scored_ops[1].accuracy_score == 0


def test_raises_on_empty_ops():
    with pytest.raises(ValueError):
        merge_to_unit_result("unit_0", [], phone_stats=STATS)


def test_raises_on_mismatched_unit_id():
    # Guard against a real integration bug: this function must only ever
    # see one unit's ops at a time.
    ops = [_op("substitution", unit_id="unit_0"), _op("substitution", unit_id="unit_1")]
    with pytest.raises(ValueError):
        merge_to_unit_result("unit_0", ops, phone_stats=STATS)


def test_works_uniformly_across_all_four_op_types():
    # No unit-type or op-type special-casing (Decision Log D19/D32's
    # spirit, carried over per D36) — deletion, substitution, insertion,
    # and match all aggregate through the same MEAN, in one unit.
    ops = [
        _op("deletion", confidence=None),  # 0
        _op("substitution", confidence=0.5),  # 50
        _op("insertion", canonical=None, confidence=0.5),  # 50
        _op("match", confidence=1.0),  # 84 (z=1 against mean=0/std=1)
    ]
    result = merge_to_unit_result("unit_0", ops, phone_stats=STATS)
    assert result.calibrated_score == 46
    assert [s.accuracy_score for s in result.scored_ops] == [0, 50, 50, 84]


def test_feedback_text_matches_generate_feedback_output():
    # Verify merge_to_unit_result calls generate_feedback with the right
    # arguments, not a divergent inline copy of the same logic (same
    # reasoning as the pre-D36 version of this test).
    ops = [_op("substitution", confidence=0.10), _op("deletion", confidence=None)]
    result = merge_to_unit_result("unit_0", ops, phone_stats=STATS)

    scored = [
        (op, score_alignment_op(op, phone_stats=STATS))
        for op in ops
    ]
    from core.models import ScoredAlignmentOp

    expected = generate_feedback(
        result.calibrated_score,
        [ScoredAlignmentOp(op=op, accuracy_score=score) for op, score in scored],
    )
    assert result.feedback_text == expected