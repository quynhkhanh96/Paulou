import pytest

from core.models import PronunciationUnit
from stages.speech_assessment.calibration import PhoneStats
from stages.speech_assessment.speech_assessment import _build_canonical_sequence, score_chunk


class _StubFreePhoneRecognizer:
    """Ignores the `audio` argument entirely and returns a fixed decode
    result — same test-double style as the pre-D36 _StubGOPScorer.
    """

    def __init__(self, decoded, confidences, boundaries):
        self._decoded = decoded
        self._confidences = confidences
        self._boundaries = boundaries
        self.received_audio = None

    def decode(self, audio: bytes):
        self.received_audio = audio
        return self._decoded, self._confidences, self._boundaries


def _chat_les_amis_units():
    chat = PronunciationUnit(
        id="u0",
        type="single",
        words=["chat"],
        phonemes=["ʃ", "a"],
        ipa="ʃa",
        syllables=[],
        liaison_consonant=None,
        note="",
        scoring_focus="phoneme_accuracy",
    )
    les_amis = PronunciationUnit(
        id="u1",
        type="liaison_group",
        words=["les", "amis"],
        phonemes=["l", "e", "z", "a", "m", "i"],
        ipa="lezami",
        syllables=[],
        liaison_consonant="z",
        note="",
        scoring_focus="liaison_presence_and_continuity",
    )
    return [chat, les_amis]


def _reference_phone_stats():
    return {
        p: PhoneStats(mean=0.85, std=0.08, sample_size=200)
        for p in ["ʃ", "a", "l", "e", "i", "z", "m"]
    }


def test_build_canonical_sequence_flattens_units_in_order():
    units = _chat_les_amis_units()
    canonical_phonemes, unit_ids = _build_canonical_sequence(units)
    assert canonical_phonemes == ["ʃ", "a", "l", "e", "z", "a", "m", "i"]
    assert unit_ids == ["u0", "u0", "u1", "u1", "u1", "u1", "u1", "u1"]


def test_score_chunk_full_worked_example_dropped_liaison_and_substitution():
    # Same worked example verified by direct execution during design
    # discussion: "chat" pronounced correctly; "les amis" loses its
    # liaison (deletion), m->n (substitution), plus a trailing stray
    # schwa (insertion).
    units = _chat_les_amis_units()
    recognizer = _StubFreePhoneRecognizer(
        decoded=["ʃ", "a", "l", "e", "a", "n", "i", "ə"],
        confidences=[0.95, 0.92, 0.93, 0.90, 0.85, 0.75, 0.88, 0.55],
        boundaries=[
            (0, 80), (80, 150), (150, 220), (220, 290),
            (290, 360), (360, 430), (430, 500), (500, 540),
        ],
    )

    results = score_chunk(units, b"fake-audio-bytes", recognizer, _reference_phone_stats())

    assert [r.unit_id for r in results] == ["u0", "u1"]

    u0_result, u1_result = results
    assert u0_result.calibrated_score == 85
    assert u0_result.feedback_text == (
        "Overall: great job! Good pronunciation on the ʃ sound! "
        "Close, watch the a sound."
    )

    assert u1_result.calibrated_score == 49
    assert u1_result.feedback_text == (
        "Overall: this one needs more practice. Missing the z sound. "
        "Extra sound heard: ə. You substituted a sound: m→n. "
        "Close, watch these sounds: l, e, i. "
        "The a sound needs work, try the slow sample."
    )


def test_score_chunk_passes_audio_through_to_recognizer_unchanged():
    units = _chat_les_amis_units()
    recognizer = _StubFreePhoneRecognizer(
        decoded=["ʃ", "a", "l", "e", "z", "a", "m", "i"],
        confidences=[0.9] * 8,
        boundaries=[(i * 70, i * 70 + 70) for i in range(8)],
    )
    audio = b"some-specific-audio-bytes"

    score_chunk(units, audio, recognizer, _reference_phone_stats())

    assert recognizer.received_audio is audio


def test_score_chunk_raises_on_empty_units():
    recognizer = _StubFreePhoneRecognizer(decoded=[], confidences=[], boundaries=[])
    with pytest.raises(ValueError):
        score_chunk([], b"audio", recognizer, _reference_phone_stats())