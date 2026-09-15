import pytest

from core.models import PhoneScore
from stages.speech_assessment.feedback import generate_feedback


def _phone_score(phone: str, score: int) -> PhoneScore:
    return PhoneScore(phone=phone, raw_gop=0.0, calibrated_score=score, start_ms=0, end_ms=100)


def test_all_good_phones_singular():
    phones = [_phone_score("a", 90)]
    result = generate_feedback(calibrated_score=90, phone_scores=phones)
    assert result == "Overall: great job! Good pronunciation on the a sound!"


def test_all_good_phones_plural():
    phones = [_phone_score("a", 90), _phone_score("m", 95)]
    result = generate_feedback(calibrated_score=92, phone_scores=phones)
    assert result == "Overall: great job! Good pronunciation on these sounds: a, m!"


def test_mixed_brackets_produce_multiple_sentences():
    # One good, one close, one needs-work phone in the same unit.
    phones = [_phone_score("a", 90), _phone_score("ʁ", 70), _phone_score("t", 40)]
    result = generate_feedback(calibrated_score=67, phone_scores=phones)
    assert result == (
        "Overall: pretty good, a little more practice will help. "
        "Good pronunciation on the a sound! "
        "Close, watch the ʁ sound. "
        "The t sound needs work, try the slow sample."
    )


def test_close_bracket_plural():
    phones = [_phone_score("ʁ", 70), _phone_score("ø", 65)]
    result = generate_feedback(calibrated_score=68, phone_scores=phones)
    assert "Close, watch these sounds: ʁ, ø." in result


def test_needs_work_bracket_plural():
    phones = [_phone_score("t", 40), _phone_score("d", 30)]
    result = generate_feedback(calibrated_score=35, phone_scores=phones)
    assert "These sounds need work, try the slow sample: t, d." in result


def test_empty_brackets_are_skipped():
    # All phones "good" -> only the overall + good sentences appear, no
    # empty "Close, watch..." or "These sounds need work..." text at all.
    phones = [_phone_score("a", 95)]
    result = generate_feedback(calibrated_score=95, phone_scores=phones)
    assert "Close" not in result
    assert "needs work" not in result


def test_overall_sentence_boundaries():
    phones = [_phone_score("a", 90)]
    assert generate_feedback(85, phones).startswith("Overall: great job!")
    assert generate_feedback(84, phones).startswith("Overall: pretty good")
    assert generate_feedback(60, phones).startswith("Overall: pretty good")
    assert generate_feedback(59, phones).startswith("Overall: this one needs more practice.")
    assert generate_feedback(0, phones).startswith("Overall: this one needs more practice.")


def test_empty_phone_scores_raises():
    with pytest.raises(ValueError):
        generate_feedback(calibrated_score=90, phone_scores=[])


def test_out_of_range_calibrated_score_raises():
    phones = [_phone_score("a", 90)]
    with pytest.raises(ValueError):
        generate_feedback(calibrated_score=101, phone_scores=phones)
    with pytest.raises(ValueError):
        generate_feedback(calibrated_score=-1, phone_scores=phones)


def test_works_uniformly_regardless_of_unit_type():
    # No unit_type parameter at all anymore (Decision Log D32) — this is
    # the same function used for what would have been a liaison_group's
    # phone_scores, e.g. the phonemes of a merged liaison sequence.
    liaison_phones = [_phone_score("l", 92), _phone_score("e", 88), _phone_score("z", 55)]
    result = generate_feedback(calibrated_score=78, phone_scores=liaison_phones)
    assert "Good pronunciation on these sounds: l, e!" in result
    assert "The z sound needs work, try the slow sample." in result