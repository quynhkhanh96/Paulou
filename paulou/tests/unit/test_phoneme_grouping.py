import pytest

from core.models import PhoneScore, PronunciationUnit
from stages.speech_assessment.phoneme_grouping import group_phone_scores_by_unit


def _unit(unit_id: str, unit_type: str, phonemes: list[str]) -> PronunciationUnit:
    return PronunciationUnit(
        id=unit_id,
        type=unit_type,
        words=["dummy"],
        phonemes=phonemes,
        ipa="".join(phonemes),
        syllables=[],
        liaison_consonant=None,
        note="",
        scoring_focus="phoneme_accuracy",
    )


def _phone_score(phone: str, score: int = 80) -> PhoneScore:
    return PhoneScore(phone=phone, raw_gop=0.0, calibrated_score=score, start_ms=0, end_ms=100)


def test_groups_single_units_correctly():
    units = [_unit("u0", "single", ["l", "e"]), _unit("u1", "single", ["ʃ", "a"])]
    scores = [_phone_score("l"), _phone_score("e"), _phone_score("ʃ"), _phone_score("a")]

    grouped = group_phone_scores_by_unit(scores, units)

    assert [s.phone for s in grouped["u0"]] == ["l", "e"]
    assert [s.phone for s in grouped["u1"]] == ["ʃ", "a"]


def test_groups_liaison_unit_including_consonant():
    # "les amis" -> phonemes = ["l","e","z","a","m","i"], consonant "z"
    # included as its own element (per core/models.py's docstring note).
    units = [_unit("u0", "liaison_group", ["l", "e", "z", "a", "m", "i"])]
    scores = [_phone_score(p) for p in ["l", "e", "z", "a", "m", "i"]]

    grouped = group_phone_scores_by_unit(scores, units)

    assert [s.phone for s in grouped["u0"]] == ["l", "e", "z", "a", "m", "i"]
    assert len(grouped["u0"]) == 6


def test_multiple_units_various_types_preserve_order():
    units = [
        _unit("u0", "elision_group", ["l", "a", "m", "i"]),
        _unit("u1", "single", ["a", "ʁ", "i", "v"]),
    ]
    scores = [_phone_score(p) for p in ["l", "a", "m", "i", "a", "ʁ", "i", "v"]]

    grouped = group_phone_scores_by_unit(scores, units)

    assert [s.phone for s in grouped["u0"]] == ["l", "a", "m", "i"]
    assert [s.phone for s in grouped["u1"]] == ["a", "ʁ", "i", "v"]


def test_raises_on_count_mismatch():
    units = [_unit("u0", "single", ["l", "e"])]  # expects 2 phone scores
    scores = [_phone_score("l")]  # only 1 given

    with pytest.raises(ValueError):
        group_phone_scores_by_unit(scores, units)


def test_empty_units_and_scores():
    assert group_phone_scores_by_unit([], []) == {}