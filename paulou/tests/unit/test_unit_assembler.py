import pytest

from core.models import LiaisonDecision
from stages.chunk_analyzer.assembly.unit_assembler import assemble_units


def _no_liaison(word1: str, word2: str) -> LiaisonDecision:
    return LiaisonDecision(between=(word1, word2), applies=False, consonant=None, rule_type="interdite")


def _liaison(word1: str, word2: str, consonant: str) -> LiaisonDecision:
    return LiaisonDecision(between=(word1, word2), applies=True, consonant=consonant, rule_type="obligatoire")


def test_all_single_words_when_no_liaison_applies():
    words = [("le", ["l", "ə"]), ("chat", ["ʃ", "a"])]
    decisions = [_no_liaison("le", "chat")]

    units = assemble_units(words, decisions)

    assert len(units) == 2
    assert all(u.type == "single" for u in units)
    assert all(u.scoring_focus == "phoneme_accuracy" for u in units)
    assert all(u.liaison_consonant is None for u in units)
    assert units[0].words == ["le"]
    assert units[0].phonemes == ["l", "ə"]
    assert units[0].ipa == "lə"
    assert units[1].words == ["chat"]


def test_single_liaison_group_formed():
    words = [("les", ["l", "e"]), ("amis", ["a", "m", "i"])]
    decisions = [_liaison("les", "amis", "z")]

    units = assemble_units(words, decisions)

    assert len(units) == 1
    unit = units[0]
    assert unit.type == "liaison_group"
    assert unit.words == ["les", "amis"]
    assert unit.liaison_consonant == "z"
    assert unit.phonemes == ["l", "e", "z", "a", "m", "i"]  # consonant is its own element
    assert unit.ipa == "lezami"
    assert unit.scoring_focus == "liaison_presence_and_continuity"


def test_mixed_single_and_liaison_group_in_one_chunk():
    # "le petit_ami dort" -> le (single), petit+ami (liaison_group), dort (single)
    words = [
        ("le", ["l", "ə"]),
        ("petit", ["p", "ə", "t", "i"]),
        ("ami", ["a", "m", "i"]),
        ("dort", ["d", "ɔ", "ʁ"]),
    ]
    decisions = [
        _no_liaison("le", "petit"),
        _liaison("petit", "ami", "t"),
        _no_liaison("ami", "dort"),
    ]

    units = assemble_units(words, decisions)

    assert [u.type for u in units] == ["single", "liaison_group", "single"]
    assert units[1].words == ["petit", "ami"]
    assert units[1].liaison_consonant == "t"
    assert units[2].words == ["dort"]


def test_consecutive_applicable_decisions_only_merge_first_pair():
    # Documents the greedy left-to-right resolution described in the
    # unit_assembler module docstring: "les anciens amis" where both
    # les|anciens and anciens|amis are obligatoire. "anciens" gets consumed
    # into the first group; the second decision is not applied.
    words = [
        ("les", ["l", "e"]),
        ("anciens", ["ɑ̃", "s", "j", "ɛ̃"]),
        ("amis", ["a", "m", "i"]),
    ]
    decisions = [
        _liaison("les", "anciens", "z"),
        _liaison("anciens", "amis", "z"),
    ]

    units = assemble_units(words, decisions)

    assert len(units) == 2
    assert units[0].type == "liaison_group"
    assert units[0].words == ["les", "anciens"]
    assert units[1].type == "single"
    assert units[1].words == ["amis"]


def test_single_word_input_with_no_decisions():
    units = assemble_units([("bonjour", ["b", "ɔ̃", "ʒ", "u", "ʁ"])], [])

    assert len(units) == 1
    assert units[0].type == "single"
    assert units[0].words == ["bonjour"]


def test_unit_ids_are_sequential():
    words = [("le", ["l", "ə"]), ("chat", ["ʃ", "a"]), ("dort", ["d", "ɔ", "ʁ"])]
    decisions = [_no_liaison("le", "chat"), _no_liaison("chat", "dort")]

    units = assemble_units(words, decisions)

    assert [u.id for u in units] == ["unit_0", "unit_1", "unit_2"]


def test_raises_on_mismatched_decision_count():
    words = [("le", ["l", "ə"]), ("chat", ["ʃ", "a"])]
    wrong_decisions = []  # should have exactly 1 decision for 2 words

    with pytest.raises(ValueError):
        assemble_units(words, wrong_decisions)


# --- Elision (added after the original design — see elision.py) -----------

def test_elision_group_formed():
    words = [("l'", ["l"]), ("ami", ["a", "m", "i"])]
    decisions = [_no_liaison("l'", "ami")]

    units = assemble_units(words, decisions)

    assert len(units) == 1
    unit = units[0]
    assert unit.type == "elision_group"
    assert unit.words == ["l'", "ami"]
    assert unit.phonemes == ["l", "a", "m", "i"]
    assert unit.ipa == "lami"
    assert unit.liaison_consonant is None
    assert unit.scoring_focus == "elision_correctness"


def test_elision_overrides_possibly_wrong_g2p_phonemes():
    # words_with_phonemes carries whatever G2P produced for "l'" — which,
    # per the confirmed eSpeak-ng bug (isolated "l'" mispronounced as the
    # letter name "elle" -> /ɛl/), would be wrong. assemble_units ignores
    # this and substitutes the correct closed-list phoneme (/l/) instead —
    # this is a real, practical side benefit of the elision fix, not just a
    # theoretical one.
    words = [("l'", ["ɛ", "l"]), ("ami", ["a", "m", "i"])]  # ["ɛ","l"] = the wrong eSpeak output
    decisions = [_no_liaison("l'", "ami")]

    units = assemble_units(words, decisions)

    assert units[0].ipa == "lami"  # correct — NOT "ɛlami"


def test_elision_takes_priority_over_liaison_decision_at_same_position():
    # Synthetic/unrealistic LiaisonDecision — real apply_liaison_rules would
    # never produce applies=True here, since get_liaison_consonant("l'") is
    # None. This defensively locks in the documented priority: elision is
    # checked first, regardless of what the liaison decision says.
    words = [("l'", ["l"]), ("ami", ["a", "m", "i"])]
    decisions = [_liaison("l'", "ami", "z")]  # should be ignored

    units = assemble_units(words, decisions)

    assert len(units) == 1
    assert units[0].type == "elision_group"
    assert units[0].liaison_consonant is None


def test_mixed_elision_single_and_liaison_group():
    # "j'ai un ami" -> j'+ai (elision_group), un+ami (liaison_group)
    words = [
        ("j'", ["ʒ"]),
        ("ai", ["ɛ"]),
        ("un", ["œ̃"]),
        ("ami", ["a", "m", "i"]),
    ]
    decisions = [
        _no_liaison("j'", "ai"),
        _no_liaison("ai", "un"),
        _liaison("un", "ami", "n"),
    ]

    units = assemble_units(words, decisions)

    assert len(units) == 2
    assert units[0].type == "elision_group"
    assert units[0].words == ["j'", "ai"]
    assert units[1].type == "liaison_group"
    assert units[1].words == ["un", "ami"]
    assert units[1].liaison_consonant == "n"


def test_elision_as_last_word_raises():
    # Malformed input: an elided clitic with nothing after it to fuse with.
    words = [("amis", ["a", "m", "i"]), ("l'", ["l"])]
    decisions = [_no_liaison("amis", "l'")]

    with pytest.raises(ValueError):
        assemble_units(words, decisions)