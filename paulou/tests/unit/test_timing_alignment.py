"""Unit tests for stages/tts/timing_alignment.py (fake timings, no TTS)."""

import pytest

from core.models import Chunk, PronunciationUnit, Sentence, WordTiming
from stages.tts.timing_alignment import locate_spans


def _unit(uid, words, type_="single"):
    return PronunciationUnit(
        id=uid, type=type_, words=words, phonemes=["a"], ipa="a",
        syllables=[], liaison_consonant=None, note="",
        scoring_focus="phoneme_accuracy",
    )


def _wt(word, start, end):
    return WordTiming(word=word, start_ms=start, end_ms=end)


def test_one_unit_per_timing_word():
    sentence = Sentence("Bonjour le monde", [
        Chunk("Bonjour", [_unit("c0_unit_0", ["Bonjour"])]),
        Chunk("le monde", [_unit("c1_unit_0", ["le"]), _unit("c1_unit_1", ["monde"])]),
    ])
    timings = [_wt("Bonjour", 0, 500), _wt("le", 600, 700), _wt("monde", 700, 1000)]

    chunk_spans, unit_spans = locate_spans(sentence, timings)

    assert unit_spans == {
        "c0_unit_0": (0, 500), "c1_unit_0": (600, 700), "c1_unit_1": (700, 1000),
    }
    assert chunk_spans == [(0, 500), (600, 1000)]


def test_elision_unit_matches_single_tts_token():
    """Provider emits "l'ami" as one token; the unit holds ["l'", "ami"]."""
    sentence = Sentence("l'ami part", [
        Chunk("l'ami part", [
            _unit("c0_unit_0", ["l'", "ami"], "elision_group"),
            _unit("c0_unit_1", ["part"]),
        ]),
    ])
    timings = [_wt("l'ami", 0, 400), _wt("part", 450, 800)]

    _, unit_spans = locate_spans(sentence, timings)

    assert unit_spans == {"c0_unit_0": (0, 400), "c0_unit_1": (450, 800)}


def test_liaison_group_spans_two_timing_words():
    sentence = Sentence("les amis", [
        Chunk("les amis", [_unit("c0_unit_0", ["les", "amis"], "liaison_group")]),
    ])
    timings = [_wt("les", 0, 200), _wt("amis", 220, 600)]

    chunk_spans, unit_spans = locate_spans(sentence, timings)

    assert unit_spans["c0_unit_0"] == (0, 600)
    assert chunk_spans == [(0, 600)]


def test_case_accents_and_punctuation_are_ignored():
    sentence = Sentence("Où est-il ?", [
        Chunk("Où est-il ?", [_unit("u0", ["Où"]), _unit("u1", ["est-il"])]),
    ])
    timings = [_wt("où", 0, 300), _wt("est-il", 320, 700), _wt("?", 700, 710)]

    _, unit_spans = locate_spans(sentence, timings)

    assert unit_spans == {"u0": (0, 300), "u1": (320, 700)}


def test_token_straddling_two_units_gives_both_the_full_token_span():
    sentence = Sentence("est-ce", [
        Chunk("est-ce", [_unit("u0", ["est"]), _unit("u1", ["ce"])]),
    ])

    _, unit_spans = locate_spans(sentence, [_wt("est-ce", 0, 500)])

    assert unit_spans == {"u0": (0, 500), "u1": (0, 500)}


def test_text_mismatch_raises():
    sentence = Sentence("j'ai 3 chats", [
        Chunk("j'ai 3 chats", [_unit("u0", ["j'ai", "3", "chats"])]),
    ])
    timings = [_wt("j'ai", 0, 200), _wt("trois", 200, 400), _wt("chats", 400, 800)]

    with pytest.raises(ValueError, match="do not spell the same text"):
        locate_spans(sentence, timings)


def test_missing_timing_word_raises():
    sentence = Sentence("a b", [Chunk("a b", [_unit("u0", ["a"]), _unit("u1", ["b"])])])

    with pytest.raises(ValueError):
        locate_spans(sentence, [_wt("a", 0, 100)])


def test_duplicate_unit_ids_raise():
    sentence = Sentence("a b", [
        Chunk("a", [_unit("unit_0", ["a"])]),
        Chunk("b", [_unit("unit_0", ["b"])]),
    ])

    with pytest.raises(ValueError, match="unique"):
        locate_spans(sentence, [_wt("a", 0, 100), _wt("b", 100, 200)])


def test_empty_chunk_raises():
    sentence = Sentence("a", [Chunk("a", [_unit("u0", ["a"])]), Chunk("", [])])

    with pytest.raises(ValueError, match="no units"):
        locate_spans(sentence, [_wt("a", 0, 100)])


def test_repeated_words_are_located_by_position_not_by_text():
    sentence = Sentence("la la", [
        Chunk("la la", [_unit("u0", ["la"]), _unit("u1", ["la"])]),
    ])

    _, unit_spans = locate_spans(sentence, [_wt("la", 0, 100), _wt("la", 200, 300)])

    assert unit_spans == {"u0": (0, 100), "u1": (200, 300)}