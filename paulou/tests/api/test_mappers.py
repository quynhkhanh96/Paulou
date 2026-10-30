from backend.api.mappers import (
    classify_op,
    normalize_text,
    sentence_id_for,
    to_attempt_response,
    to_unit_result_dto,
)
from core.models import AlignmentOp, ScoredAlignmentOp, UnitResult


def _result():
    ops = [
        ScoredAlignmentOp(AlignmentOp("match", "u", "a", "a", 0.9, 0, 50), 99),
        ScoredAlignmentOp(AlignmentOp("deletion", "u", "b", None, None, None, None), 0),
        ScoredAlignmentOp(AlignmentOp("insertion", "u", None, "z", 0.4, 60, 90), 60),
    ]
    return UnitResult(unit_id="u", calibrated_score=53, scored_ops=ops, feedback_text="Overall: x.")


def test_normalize_collapses_whitespace_and_applies_nfc():
    acute = chr(0x301)  # combining acute accent: "e" + acute is the decomposed "\u00e9"
    decomposed = "Les  enfants\n ont ach" + "e" + acute + "t" + "e" + acute + " "
    assert normalize_text(decomposed) == "Les enfants ont ach" + chr(0xE9) + "t" + chr(0xE9)


def test_same_sentence_typed_differently_gets_the_same_id():
    a = sentence_id_for(normalize_text("Les enfants  ont acheté"))
    b = sentence_id_for(normalize_text(" Les enfants ont acheté "))
    assert a == b
    assert a != sentence_id_for(normalize_text("Les enfants ont mangé"))


def test_scores_are_hidden_when_not_calibrated():
    dto = to_unit_result_dto(_result(), calibrated=False)

    assert dto.score is None
    assert [op.score for op in dto.ops] == [None, None, None]
    assert [op.op_type for op in dto.ops] == ["match", "deletion", "insertion"]
    assert dto.feedback_text == "Overall: x."


def test_scores_are_exposed_when_calibrated():
    dto = to_unit_result_dto(_result(), calibrated=True)

    assert dto.score == 53
    assert [op.score for op in dto.ops] == [99, 0, 60]


def test_confidence_is_never_in_the_schema():
    dumped = to_unit_result_dto(_result(), calibrated=True).model_dump()
    assert all("confidence" not in op for op in dumped["ops"])


def test_attempt_response_carries_target_and_flag():
    response = to_attempt_response("sid", 1, None, [_result()], calibrated=False)
    assert (response.sentence_id, response.chunk_index, response.unit_id) == ("sid", 1, None)
    assert response.calibrated is False


def test_ops_are_classified_into_the_five_kinds():
    n = "\u0303"
    cases = [
        (AlignmentOp("match", "u", "a", "a", 0.9, 0, 50), ("M", [])),
        (AlignmentOp("deletion", "u", "a", None, None, None, None), ("D", [])),
        (AlignmentOp("insertion", "u", None, "z", 0.4, 60, 90), ("I", [])),
        (AlignmentOp("substitution", "u", "z", "s", 0.8, 0, 50), ("S_near", ["missing_voicing"])),
        (AlignmentOp("substitution", "u", "ɔ" + n, "o", 0.8, 0, 50), ("S_near", ["missing_nasality", "not_open_enough"])),
        (AlignmentOp("substitution", "u", "ʁ", "l", 0.8, 0, 50), ("S", [])),
        (AlignmentOp("substitution", "u", "a", "t", 0.8, 0, 50), ("S", [])),
    ]
    for op, expected in cases:
        assert classify_op(op) == expected, op


def test_unit_result_dto_exposes_kind_and_reasons_but_never_confidence():
    n = "\u0303"
    ops = [
        ScoredAlignmentOp(AlignmentOp("substitution", "u", "ɔ" + n, "o", 0.8, 0, 50), 20),
        ScoredAlignmentOp(AlignmentOp("match", "u", "b", "b", 0.9, 50, 90), 99),
    ]
    dto = to_unit_result_dto(UnitResult("u", 60, ops, "x"), calibrated=False)
    assert [(o.kind, o.near_reasons) for o in dto.ops] == [("S_near", ["missing_nasality", "not_open_enough"]), ("M", [])]
    assert all("confidence" not in o for o in dto.model_dump()["ops"])
