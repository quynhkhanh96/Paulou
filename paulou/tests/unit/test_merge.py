import pytest

from core.models import PhoneScore
from stages.speech_assessment.feedback import generate_feedback
from stages.speech_assessment.merge import merge_to_unit_result


def _phone_score(phone: str, score: int) -> PhoneScore:
    return PhoneScore(phone=phone, raw_gop=0.0, calibrated_score=score, start_ms=0, end_ms=100)


def test_mean_aggregation_not_min():
    # MIN would give 40; MEAN gives (90+70+40)/3 = 66.67 -> round to 67.
    phones = [_phone_score("a", 90), _phone_score("ʁ", 70), _phone_score("t", 40)]
    result = merge_to_unit_result("u0", phones)
    assert result.calibrated_score == 67


def test_mean_rounds_to_nearest_int():
    phones = [_phone_score("a", 80), _phone_score("b", 81)]  # mean = 80.5
    result = merge_to_unit_result("u0", phones)
    # Python's round() uses banker's rounding (round-half-to-even) — 80.5
    # rounds to 80, not 81. Flagging this since it's an easy gotcha: this
    # is NOT "always rounds up", it depends on which side is even.
    assert result.calibrated_score == 80


def test_single_phone_unit_score_equals_that_phone():
    phones = [_phone_score("a", 73)]
    result = merge_to_unit_result("u0", phones)
    assert result.calibrated_score == 73


def test_feedback_text_matches_generate_feedback_output():
    phones = [_phone_score("a", 90), _phone_score("t", 40)]
    result = merge_to_unit_result("u0", phones)
    expected = generate_feedback(calibrated_score=result.calibrated_score, phone_scores=phones)
    assert result.feedback_text == expected


def test_unit_id_and_phone_scores_pass_through_unchanged():
    phones = [_phone_score("a", 90), _phone_score("t", 85)]
    result = merge_to_unit_result("chunk3_unit1", phones)
    assert result.unit_id == "chunk3_unit1"
    assert result.phone_scores == phones


def test_raises_on_empty_phone_scores():
    with pytest.raises(ValueError):
        merge_to_unit_result("u0", [])


def test_works_for_liaison_group_phone_scores_too():
    # No unit_type distinction anywhere in this module (Decision Log D19/
    # D32) — a liaison_group's phone_scores merge exactly the same way.
    phones = [_phone_score("l", 92), _phone_score("e", 88), _phone_score("z", 55)]
    result = merge_to_unit_result("liaison_unit_0", phones)
    assert result.calibrated_score == round((92 + 88 + 55) / 3)
    assert "z" in result.feedback_text