import pytest

from stages.speech_assessment.phone_similarity import near_reasons

N = "̃"


@pytest.mark.parametrize(
    "canonical, decoded, expected",
    [
        # the prototype's headline example: nasal vowel said as its oral cousin
        ("ɔ" + N, "o", ["missing_nasality", "not_open_enough"]),
        ("ɔ" + N, "ɔ", ["missing_nasality"]),
        ("ɑ" + N, "a", ["missing_nasality", "too_far_forward"]),
        ("ɔ", "ɔ" + N, ["extra_nasality"]),
        ("y", "u", ["too_far_back"]),
        ("u", "y", ["too_far_forward"]),
        ("y", "i", ["not_rounded"]),
        ("i", "y", ["over_rounded"]),
        ("ø", "e", ["not_rounded"]),
        ("e", "ɛ", ["too_open"]),
        ("ɛ", "e", ["not_open_enough"]),
    ],
)
def test_near_vowels_name_the_features_that_differ(canonical, decoded, expected):
    assert near_reasons(canonical, decoded) == expected


@pytest.mark.parametrize(
    "canonical, decoded, expected",
    [
        ("z", "s", ["missing_voicing"]),
        ("s", "z", ["extra_voicing"]),
        ("ʒ", "ʃ", ["missing_voicing"]),
        ("ʃ", "s", ["wrong_place"]),
        ("t", "k", ["wrong_place"]),
        ("d", "z", ["wrong_manner"]),
    ],
)
def test_near_consonants_name_the_features_that_differ(canonical, decoded, expected):
    assert near_reasons(canonical, decoded) == expected


@pytest.mark.parametrize(
    "canonical, decoded",
    [
        ("y", "a"),  # too many features apart
        ("ɔ" + N, "i"),
        ("ʁ", "l"),  # place and manner both differ
        ("p", "z"),
        ("a", "t"),  # vowel against consonant
        ("t", "a"),
        ("ɔ", "ɨ"),  # a phone the tables do not know
        ("ɨ", "ɔ"),
    ],
)
def test_far_substitutions_are_none(canonical, decoded):
    assert near_reasons(canonical, decoded) is None


def test_two_spellings_of_the_same_sound_are_near_without_reasons():
    assert near_reasons("g", "ɡ") == []
    assert near_reasons("ɡ", "g") == []


def test_vowel_threshold_is_two_points_inclusive():
    # /ɔ̃/ -> /o/: 0.5 * 2 (height) + 1 (nasality) = 2.0 -> still near
    assert near_reasons("ɔ" + N, "o") is not None
    # /ɔ̃/ -> /i/: height 1.5 + backness 1 + rounding 1 + nasality 1 = 4.5 -> far
    assert near_reasons("ɔ" + N, "i") is None


def test_nasal_vowels_given_decomposed_or_typed_the_same_way():
    assert near_reasons("ɛ" + N, "ɛ") == ["missing_nasality"]
