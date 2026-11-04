import unicodedata

import pytest

from stages.speech_assessment import phone_similarity
from stages.speech_assessment.phone_similarity import CONFUSION_REASONS, near_reasons

N = "̃"


@pytest.mark.parametrize(
    "target, produced, expected",
    [
        # the prototype's headline example: bonjour said [boʒuʁ]
        ("ɔ" + N, "o", ["missing_nasality"]),
        ("o", "ɔ" + N, ["extra_nasality"]),
        ("ɔ" + N, "ɔ", ["missing_nasality"]),
        ("ɑ" + N, "a", ["missing_nasality"]),
        ("ɑ" + N, "ɔ" + N, ["over_rounded", "not_open_enough"]),
        ("y", "u", ["too_far_back"]),
        ("u", "y", ["too_far_forward"]),
        ("ə", "e", ["not_rounded"]),
        ("e", "ɛ", ["too_open"]),
        ("ɥ", "w", ["too_far_back"]),
    ],
)
def test_vowel_confusions_give_their_reasons(target, produced, expected):
    assert near_reasons(target, produced) == expected


@pytest.mark.parametrize(
    "target, produced, expected",
    [
        ("z", "s", ["missing_voicing"]),
        ("s", "z", ["extra_voicing"]),
        ("ʃ", "s", ["wrong_place", "not_rounded"]),
        ("ʁ", "z", ["wrong_place"]),
        ("ʁ", "r", ["wrong_place"]),
        ("r", "ʁ", ["wrong_place"]),
    ],
)
def test_consonant_confusions_give_their_reasons(target, produced, expected):
    assert near_reasons(target, produced) == expected


@pytest.mark.parametrize(
    "target, produced",
    [
        ("i", "a"),  # was near under the D64 formula
        ("ʁ", "l"),  # common but distant: left out on purpose
        ("ʁ", "ɡ"),
        ("ʁ", "g"),
        ("y", "a"),
        ("ɔ" + N, "i"),
        ("p", "z"),
        ("a", "t"),  # vowel against consonant
        ("ɔ", "ɨ"),  # a phone the table does not know
    ],
)
def test_pairs_not_in_the_table_are_far(target, produced):
    assert near_reasons(target, produced) is None


def test_g_and_script_g_are_the_same_sound():
    assert near_reasons("g", "ɡ") == []
    assert near_reasons("k", "g") == ["extra_voicing"]


def test_nasal_vowels_given_precomposed_or_decomposed_match():
    # no precomposed nasal IPA vowel exists, but NFC/NFD input must not matter
    assert near_reasons(unicodedata.normalize("NFC", "ɛ" + N), "ɛ") == ["missing_nasality"]


def test_every_pair_is_listed_in_both_directions():
    missing = [(a, b) for (a, b) in CONFUSION_REASONS if (b, a) not in CONFUSION_REASONS]
    assert missing == []


def test_every_reason_is_a_known_code():
    codes = {v for k, v in vars(phone_similarity).items() if k.isupper() and isinstance(v, str)}
    used = {r for reasons in CONFUSION_REASONS.values() for r in reasons}
    assert used <= codes
    assert all(CONFUSION_REASONS.values())  # no near pair without a reason


def test_returned_list_is_a_copy():
    near_reasons("y", "u").append("x")
    assert near_reasons("y", "u") == ["too_far_back"]
