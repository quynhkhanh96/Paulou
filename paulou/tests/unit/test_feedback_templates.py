import pytest

from core.models import PhoneScore
from stages.speech_assessment.feedback import generate_feedback


def _phone_score(phone: str, score: int) -> PhoneScore:
    return PhoneScore(phone=phone, raw_gop=0.0, calibrated_score=score, start_ms=0, end_ms=100)


def test_high_score_gives_good_pronunciation_template():
    phones = [_phone_score("a", 90), _phone_score("m", 88)]
    result = generate_feedback("single", calibrated_score=90, phone_scores=phones)
    assert result == "Good pronunciation!"


def test_mid_score_names_the_weakest_phone():
    phones = [_phone_score("a", 90), _phone_score("ʁ", 65)]
    result = generate_feedback("single", calibrated_score=70, phone_scores=phones)
    assert result == "Close, watch the ʁ sound"


def test_low_score_names_the_weakest_phone():
    phones = [_phone_score("a", 90), _phone_score("ʁ", 30)]
    result = generate_feedback("single", calibrated_score=45, phone_scores=phones)
    assert result == "The ʁ sound needs work, try the slow sample"


def test_boundary_score_85_is_good_pronunciation():
    phones = [_phone_score("a", 85)]
    result = generate_feedback("single", calibrated_score=85, phone_scores=phones)
    assert result == "Good pronunciation!"


def test_boundary_score_59_is_low_tier():
    phones = [_phone_score("a", 59)]
    result = generate_feedback("single", calibrated_score=59, phone_scores=phones)
    assert "needs work" in result


def test_liaison_group_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        generate_feedback("liaison_group", calibrated_score=90, phone_scores=None)


def test_single_unit_without_phone_scores_raises():
    with pytest.raises(ValueError):
        generate_feedback("single", calibrated_score=90, phone_scores=[])


def test_unknown_unit_type_raises():
    with pytest.raises(ValueError):
        generate_feedback("paragraph", calibrated_score=90, phone_scores=[_phone_score("a", 90)])
