import pytest

spacy = pytest.importorskip("spacy")

try:
    spacy.load("fr_core_news_sm")
    _MODEL_AVAILABLE = True
except OSError:
    _MODEL_AVAILABLE = False

pytestmark = [
    pytest.mark.model,
    pytest.mark.skipif(not _MODEL_AVAILABLE, reason="fr_core_news_sm model not installed"),
]

from stages.chunk_analyzer.chunk_analyzer import analyze_chunk  # noqa: E402


class _StubG2P:
    """Deterministic stub G2PProvider — isolates analyze_chunk's own
    orchestration logic from real G2P behavior (including eSpeak-ng's
    known quirks, already covered separately by unit_assembler's own
    tests). Matches the G2PProvider Protocol structurally.
    """

    _TABLE = {
        "les": ["l", "e"],
        "amis": ["a", "m", "i"],
        "arrivent": ["a", "ʁ", "i", "v"],
        "demain": ["d", "ə", "m", "ɛ̃"],
        "ami": ["a", "m", "i"],
        "arrive": ["a", "ʁ", "i", "v"],
        "bonjour": ["b", "ɔ̃", "ʒ", "u", "ʁ"],
        # Deliberately "wrong" phonemes for "l'", matching the real
        # confirmed eSpeak-ng bug — re-verifies end-to-end that
        # assemble_units still overrides this correctly (see
        # test_unit_assembler.py::test_elision_overrides_possibly_wrong_g2p_phonemes
        # for the same check at the assembly layer alone).
        "l'": ["ɛ", "l"],
    }

    def phonemize(self, word: str) -> tuple[list[str], str]:
        return self._TABLE.get(word.lower(), ["?"]), "dict"


@pytest.fixture
def g2p():
    return _StubG2P()


def test_les_amis_arrivent_demain(g2p):
    # The worked example from the original design discussion: "les"+"amis"
    # obligatoire liaison; "amis"+"arrivent" blocked (subject noun before
    # verb, D22); "arrivent"+"demain" blocked (demain is consonant-initial
    # anyway) -> 3 units from 4 words.
    units = analyze_chunk("les amis arrivent demain", g2p)

    assert len(units) == 3
    assert units[0].type == "liaison_group"
    assert units[0].words == ["les", "amis"]
    assert units[0].liaison_consonant == "z"
    assert units[1].type == "single"
    assert units[1].words == ["arrivent"]
    assert units[2].type == "single"
    assert units[2].words == ["demain"]


def test_elision_end_to_end(g2p):
    units = analyze_chunk("l'ami arrive", g2p)

    assert len(units) == 2
    assert units[0].type == "elision_group"
    assert units[0].words == ["l'", "ami"]
    assert units[0].ipa == "lami"  # correct, not "ɛlami" — see _StubG2P note
    assert units[1].type == "single"
    assert units[1].words == ["arrive"]


def test_punctuation_is_filtered_out(g2p):
    units = analyze_chunk("Bonjour, les amis", g2p)

    all_words = [w for unit in units for w in unit.words]
    assert "," not in all_words
    assert all(unit.words != [","] for unit in units)


def test_empty_chunk_returns_empty_list(g2p):
    assert analyze_chunk("", g2p) == []


def test_single_word_chunk(g2p):
    units = analyze_chunk("bonjour", g2p)

    assert len(units) == 1
    assert units[0].type == "single"
    assert units[0].words == ["bonjour"]
