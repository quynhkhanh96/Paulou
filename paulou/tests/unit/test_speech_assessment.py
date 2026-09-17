import pytest

from core.models import PronunciationUnit, RawPhoneScore
from stages.speech_assessment.calibration import PhoneStats
from stages.speech_assessment.speech_assessment import score_chunk


class _StubGOPScorer:
    """Deterministic stub GOPScorer — isolates the orchestration logic
    from real GOP model behavior (Stage A; real Kaldi/gop-ft is Stage B,
    not built yet). `raw_gop_by_phone` lets each test control exactly
    what raw score each phone gets, so results through calibration are
    fully predictable.
    """

    def __init__(self, raw_gop_by_phone: dict[str, float], default_raw_gop: float = 0.0):
        self._raw_gop_by_phone = raw_gop_by_phone
        self._default_raw_gop = default_raw_gop

    def score(self, audio: bytes, canonical_phonemes: list[str]) -> list[RawPhoneScore]:
        scores = []
        cursor = 0
        for phone in canonical_phonemes:
            raw_gop = self._raw_gop_by_phone.get(phone, self._default_raw_gop)
            scores.append(RawPhoneScore(phone=phone, raw_gop=raw_gop, start_ms=cursor, end_ms=cursor + 100))
            cursor += 100
        return scores


class _WrongCountGOPScorer:
    """Stub that deliberately returns the wrong number of scores, to test
    the integration guard.
    """

    def score(self, audio: bytes, canonical_phonemes: list[str]) -> list[RawPhoneScore]:
        return [RawPhoneScore(phone="x", raw_gop=0.0, start_ms=0, end_ms=100)]


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


# Native-like stats (mean=0, std=1) for every phone used across these
# tests, so raw_gop=0.0 -> calibrated_score=50 (z=0), matching
# test_calibration.py's own baseline case.
STATS = {
    p: PhoneStats(mean=0.0, std=1.0, sample_size=100)
    for p in ["l", "e", "z", "a", "m", "i", "ʁ", "t"]
}


def test_single_unit_scored_correctly():
    units = [_unit("u0", "single", ["l", "e"])]
    gop = _StubGOPScorer(raw_gop_by_phone={"l": 0.0, "e": 0.0})

    results = score_chunk(b"fake-audio", units, gop, STATS)

    assert len(results) == 1
    assert results[0].unit_id == "u0"
    assert results[0].calibrated_score == 50  # mean of two z=0 phones
    assert [p.phone for p in results[0].phone_scores] == ["l", "e"]


def test_multiple_units_each_get_their_own_result():
    units = [
        _unit("u0", "single", ["l", "e"]),
        _unit("u1", "liaison_group", ["z", "a", "m", "i"]),
    ]
    gop = _StubGOPScorer(raw_gop_by_phone={p: 0.0 for p in ["l", "e", "z", "a", "m", "i"]})

    results = score_chunk(b"fake-audio", units, gop, STATS)

    assert len(results) == 2
    assert results[0].unit_id == "u0"
    assert results[1].unit_id == "u1"
    assert [p.phone for p in results[1].phone_scores] == ["z", "a", "m", "i"]


def test_liaison_group_scored_same_way_as_single():
    # No unit_type special-casing anywhere in this flow (D19/D32/D33).
    units = [_unit("u0", "liaison_group", ["z", "a"])]
    gop = _StubGOPScorer(raw_gop_by_phone={"z": -4.0, "a": 4.0})  # one bad, one great

    results = score_chunk(b"fake-audio", units, gop, STATS)

    assert "z" in results[0].feedback_text  # named as needing work
    assert "a" in results[0].feedback_text  # named as good


def test_raw_gop_flows_through_calibration_correctly():
    units = [_unit("u0", "single", ["l"])]
    # Far above the mean -> should calibrate to a high score.
    gop = _StubGOPScorer(raw_gop_by_phone={"l": 4.0})

    results = score_chunk(b"fake-audio", units, gop, STATS)

    assert results[0].calibrated_score > 95


def test_empty_units_returns_empty_list():
    gop = _StubGOPScorer(raw_gop_by_phone={})
    assert score_chunk(b"fake-audio", [], gop, STATS) == []


def test_raises_on_gop_scorer_count_mismatch():
    units = [_unit("u0", "single", ["l", "e"])]  # expects 2 phones
    gop = _WrongCountGOPScorer()  # returns 1

    with pytest.raises(ValueError):
        score_chunk(b"fake-audio", units, gop, STATS)


class _RecordingGOPScorer:
    """Stub that just records what canonical_phonemes it was called with,
    and echoes back a trivial score per phone (raw_gop=0.0) — used to
    verify the SIL-insertion plumbing (Decision Log D35), NOT real
    alignment behavior (a stub has none to get wrong).
    """

    def __init__(self):
        self.received_canonical_phonemes: list[str] | None = None

    def score(self, audio: bytes, canonical_phonemes: list[str]) -> list[RawPhoneScore]:
        self.received_canonical_phonemes = canonical_phonemes
        return [
            RawPhoneScore(phone=p, raw_gop=0.0, start_ms=i * 100, end_ms=i * 100 + 100)
            for i, p in enumerate(canonical_phonemes)
        ]


def test_sil_inserted_between_units_not_within_them():
    # "les_amis" (liaison_group, one merged unit) + "arrivent" (single) +
    # "demain" (single) -> SIL only at the 2 boundaries BETWEEN units, not
    # inside the liaison_group's own merged phoneme sequence.
    units = [
        _unit("u0", "liaison_group", ["l", "e", "z", "a", "m", "i"]),
        _unit("u1", "single", ["a", "ʁ", "i", "v"]),
        _unit("u2", "single", ["d", "ə", "m", "ɛ̃"]),
    ]
    gop = _RecordingGOPScorer()
    stats = {
        **STATS,
        "ʁ": PhoneStats(0.0, 1.0, 100),
        "v": PhoneStats(0.0, 1.0, 100),
        "d": PhoneStats(0.0, 1.0, 100),
        "ə": PhoneStats(0.0, 1.0, 100),
        "ɛ̃": PhoneStats(0.0, 1.0, 100),
    }

    score_chunk(b"fake-audio", units, gop, stats)

    assert gop.received_canonical_phonemes == [
        "l", "e", "z", "a", "m", "i",  # les_amis — no internal SIL
        "SIL",
        "a", "ʁ", "i", "v",  # arrivent
        "SIL",
        "d", "ə", "m", "ɛ̃",  # demain
    ]


def test_sil_scores_are_stripped_before_reaching_unit_results():
    units = [_unit("u0", "single", ["l"]), _unit("u1", "single", ["a"])]
    gop = _RecordingGOPScorer()

    results = score_chunk(b"fake-audio", units, gop, STATS)

    # Neither unit's phone_scores should ever contain a "SIL" entry —
    # it's an alignment-only construct, not something to score/display.
    all_phones = [p.phone for r in results for p in r.phone_scores]
    assert "SIL" not in all_phones
    assert all_phones == ["l", "a"]