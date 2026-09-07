import shutil
from pathlib import Path

import pytest

from stages.g2p.lexique_espeak import LexiqueEspeakG2P, _load_lexicon, _parse_espeak_ipa

FIXTURE_LEXICON = Path(__file__).parent.parent / "fixtures" / "g2p_golden.tsv"

espeak_installed = pytest.mark.skipif(
    shutil.which("espeak-ng") is None,
    reason="espeak-ng is a system dependency, not installed in this environment",
)


# --- Dictionary lookup path (fast, no external dependency) ------------------

def test_dict_lookup_returns_source_dict():
    g2p = LexiqueEspeakG2P(FIXTURE_LEXICON)
    phonemes, source = g2p.phonemize("bonjour")
    assert phonemes == ["b", "ɔ̃", "ʒ", "u", "ʁ"]
    assert source == "dict"


def test_dict_lookup_is_case_insensitive():
    g2p = LexiqueEspeakG2P(FIXTURE_LEXICON)
    phonemes, source = g2p.phonemize("Bonjour")
    assert source == "dict"
    assert phonemes == ["b", "ɔ̃", "ʒ", "u", "ʁ"]


def test_load_lexicon_raises_on_malformed_line(tmp_path):
    bad_file = tmp_path / "bad_lexicon.tsv"
    bad_file.write_text("this line has no tab\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_lexicon(bad_file)


def test_missing_lexicon_file_raises():
    with pytest.raises(FileNotFoundError):
        LexiqueEspeakG2P("/nonexistent/path/lexicon.tsv")


# --- _parse_espeak_ipa (pure function, tested on canned strings — no ------
# --- binary needed; strings taken from real `espeak-ng --ipa=1` output) ----

def test_parse_espeak_ipa_simple_word():
    # "bonjour" -> b_ɔ̃_ʒ_ˈu_ʁ
    assert _parse_espeak_ipa("b_ɔ̃_ʒ_ˈu_ʁ") == ["b", "ɔ̃", "ʒ", "u", "ʁ"]


def test_parse_espeak_ipa_strips_leading_empty_token():
    # "onze" -> _ˈɔ̃_z (leading underscore produces an empty first token)
    assert _parse_espeak_ipa("_ˈɔ̃_z") == ["ɔ̃", "z"]


def test_parse_espeak_ipa_strips_trailing_hyphen():
    # "les" -> l_ˈe- (trailing hyphen is a liaison hint, not a phoneme)
    assert _parse_espeak_ipa("l_ˈe-") == ["l", "e"]


def test_parse_espeak_ipa_single_phoneme_word():
    # "un" -> ˈœ̃ (no underscores at all — single phoneme)
    assert _parse_espeak_ipa("ˈœ̃") == ["œ̃"]


# --- eSpeak-ng fallback path (requires the real binary) ---------------------

@espeak_installed
def test_fallback_to_espeak_for_unknown_word():
    g2p = LexiqueEspeakG2P(FIXTURE_LEXICON)
    phonemes, source = g2p.phonemize("xylophone")  # not in the fixture lexicon
    assert source == "espeak"
    assert len(phonemes) > 0


@espeak_installed
def test_espeak_fallback_output_has_no_stress_marks():
    g2p = LexiqueEspeakG2P(FIXTURE_LEXICON)
    phonemes, _ = g2p.phonemize("xylophone")
    assert all("ˈ" not in p and "ˌ" not in p for p in phonemes)


@espeak_installed
def test_espeak_fallback_never_raises_for_unknown_word():
    # Codebase Conventions: phonemize() must never raise for "word not
    # found" — falling back to eSpeak is the designed behavior.
    g2p = LexiqueEspeakG2P(FIXTURE_LEXICON)
    phonemes, source = g2p.phonemize("anticonstitutionnellement")
    assert source == "espeak"
    assert len(phonemes) > 0
