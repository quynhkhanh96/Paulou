import pytest

from stages.speech_assessment.align import align_phonemes


def test_all_match_when_sequences_are_identical():
    ops = align_phonemes(["a", "b"], ["u0", "u0"], ["a", "b"], [0.5, 0.6], [(0, 10), (10, 20)])
    assert [op.op_type for op in ops] == ["match", "match"]
    assert ops[0].confidence == 0.5
    assert ops[1].confidence == 0.6


def test_single_deletion_detected_for_dropped_liaison():
    # The "les amis" -> /leami/ worked example (liaison consonant dropped).
    canonical = ["l", "e", "z", "a", "m", "i"]
    unit_ids = ["u0"] * 6
    decoded = ["l", "e", "a", "m", "i"]
    confidences = [0.9] * 5
    boundaries = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50)]

    ops = align_phonemes(canonical, unit_ids, decoded, confidences, boundaries)

    assert [op.op_type for op in ops] == ["match", "match", "deletion", "match", "match", "match"]
    deletion = ops[2]
    assert deletion.canonical_phoneme == "z"
    assert deletion.decoded_phoneme is None
    assert deletion.confidence is None
    assert deletion.start_ms is None and deletion.end_ms is None
    assert deletion.unit_id == "u0"


def test_single_real_error_resolves_as_substitution_not_delete_plus_insert():
    # Equal edit weights (1,1,1) must prefer ONE substitution (cost 1) over
    # a deletion+insertion pair for the same event (cost 2) — the more
    # useful pedagogical reading, and a direct consequence of the DP, not
    # something special-cased.
    ops = align_phonemes(["m"], ["u0"], ["n"], [0.8], [(0, 10)])
    assert [op.op_type for op in ops] == ["substitution"]
    assert ops[0].canonical_phoneme == "m"
    assert ops[0].decoded_phoneme == "n"
    assert ops[0].confidence == 0.8


def test_substitution_and_trailing_insertion_together():
    canonical = ["l", "e", "z", "a", "m", "i"]
    unit_ids = ["u0"] * 6
    decoded = ["l", "e", "a", "n", "i", "s"]  # m->n substitution, trailing "s" inserted
    confidences = [0.9, 0.9, 0.9, 0.8, 0.9, 0.6]
    boundaries = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 60)]

    ops = align_phonemes(canonical, unit_ids, decoded, confidences, boundaries)

    assert [op.op_type for op in ops] == [
        "match", "match", "deletion", "match", "substitution", "match", "insertion",
    ]
    substitution = ops[4]
    assert (substitution.canonical_phoneme, substitution.decoded_phoneme) == ("m", "n")
    insertion = ops[6]
    assert insertion.canonical_phoneme is None
    assert insertion.decoded_phoneme == "s"
    assert insertion.confidence == 0.6
    assert insertion.unit_id == "u0"  # attaches to the preceding unit


def test_insertion_attaches_to_preceding_unit_across_a_unit_boundary():
    canonical = ["a", "b", "c", "d"]
    unit_ids = ["u0", "u0", "u1", "u1"]
    decoded = ["a", "b", "x", "c", "d"]  # extra "x" between the two units
    confidences = [0.9] * 5
    boundaries = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50)]

    ops = align_phonemes(canonical, unit_ids, decoded, confidences, boundaries)

    insertion = next(op for op in ops if op.op_type == "insertion")
    assert insertion.decoded_phoneme == "x"
    assert insertion.unit_id == "u0"  # the unit ending in "b", not "u1"


def test_insertion_with_nothing_preceding_attaches_to_first_unit():
    ops = align_phonemes(
        ["a", "b"], ["u0", "u0"], ["x", "a", "b"], [0.9, 0.9, 0.9], [(0, 10), (10, 20), (20, 30)]
    )
    insertion = ops[0]
    assert insertion.op_type == "insertion"
    assert insertion.unit_id == "u0"


def test_deletions_across_two_units_each_keep_their_own_unit_id():
    canonical = ["a", "b", "c", "d"]
    unit_ids = ["u0", "u0", "u1", "u1"]
    ops = align_phonemes(canonical, unit_ids, [], [], [])
    assert [op.op_type for op in ops] == ["deletion"] * 4
    assert [op.unit_id for op in ops] == ["u0", "u0", "u1", "u1"]


def test_raises_on_empty_canonical_phonemes():
    with pytest.raises(ValueError):
        align_phonemes([], [], ["a"], [0.5], [(0, 10)])


def test_raises_on_unit_ids_length_mismatch():
    with pytest.raises(ValueError):
        align_phonemes(["a", "b"], ["u0"], ["a", "b"], [0.5, 0.5], [(0, 10), (10, 20)])


def test_raises_on_decoded_lists_length_mismatch():
    with pytest.raises(ValueError):
        align_phonemes(["a"], ["u0"], ["a", "b"], [0.5], [(0, 10)])