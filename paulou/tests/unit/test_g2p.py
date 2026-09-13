import shutil
from pathlib import Path

import pytest

from stages.chunk_analyzer.g2p.lexique_espeak import LexiqueEspeakG2P, _load_lexicon, _parse_espeak_ipa

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


def test_espeak_not_found_gives_actionable_error(monkeypatch):
    # Confirmed real failure mode: on a machine without espeak-ng on PATH
    # (e.g. a fresh Windows install), subprocess.run raised a bare
    # FileNotFoundError ("[WinError 2] The system cannot find the file
    # specified") with no indication of what was actually missing. This
    # locks in the fix: a clear, actionable RuntimeError instead.
    import subprocess as subprocess_module

    def _raise_not_found(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess_module, "run", _raise_not_found)

    g2p = LexiqueEspeakG2P(FIXTURE_LEXICON)
    with pytest.raises(RuntimeError, match="espeak-ng executable not found"):
        g2p.phonemize("xylophone")


# --- Real Lexique400 database (Decision Log D30) ---------------------------
# 33MB, not committed to the repo (.gitignore) — skipped automatically if
# the file isn't present at the expected path. Download separately.

LEXIQUE400_PATH = Path(__file__).parent.parent.parent / "data" / "Lexique400.tsv"

lexique400_available = pytest.mark.skipif(
    not LEXIQUE400_PATH.exists(),
    reason="Lexique400.tsv not present (git-ignored, download separately — see SETUP.md)",
)


@lexique400_available
def test_from_lexique400_loads_known_words():
    g2p = LexiqueEspeakG2P.from_lexique400(LEXIQUE400_PATH)
    phonemes, source = g2p.phonemize("bonjour")
    assert phonemes == ["b", "ɔ̃", "ʒ", "u", "ʁ"]
    assert source == "dict"


@lexique400_available
def test_from_lexique400_nasal_vowel_is_one_phoneme():
    # Verifies the combining-mark segmentation: "ɔ̃" (base + combining
    # tilde) must be ONE phoneme, not two.
    g2p = LexiqueEspeakG2P.from_lexique400(LEXIQUE400_PATH)
    phonemes, _ = g2p.phonemize("avons")
    assert phonemes == ["a", "v", "ɔ̃"]
    assert len(phonemes[-1]) == 2  # base char + combining tilde, one phoneme


@lexique400_available
def test_from_lexique400_has_substantial_coverage():
    g2p = LexiqueEspeakG2P.from_lexique400(LEXIQUE400_PATH)
    assert len(g2p._lexicon) > 100_000


@lexique400_available
def test_from_lexique400_elided_clitics_are_real_dictionary_entries():
    # If Lexique400 has its own entries for elided forms, dict lookup
    # returns them directly — the eSpeak fallback (confirmed to mishandle
    # "l'" as the letter name "elle", see elision.py) is never reached.
    g2p = LexiqueEspeakG2P.from_lexique400(LEXIQUE400_PATH)
    phonemes, source = g2p.phonemize("l'")
    assert source == "dict"
    assert phonemes == ["l"]