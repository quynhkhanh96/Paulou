"""Model tests for RuleBasedSentenceParser (Decision Log D67).

Needs spaCy's fr_core_news_sm (the parser tags with it), hence tests/model.
Checks the chunking contract (same invariants as the Gemini contract test)
and the D67 hard rule against the sentence-level liaison decisions, then
pins the chunks of the hand-checked sentences from the MVP handoff.

The pinned outputs depend on the spaCy model version (VERSION NOTE in
stages/chunk_analyzer/pos/spacy_tagger.py): a model update that moves a tag
can move a cut. They are hand-checked examples, not a regression set (D70).
"""

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

from stages.chunk_analyzer.liaison.rule_engine import apply_liaison_rules  # noqa: E402
from stages.chunk_analyzer.pos.spacy_tagger import tag_sentence  # noqa: E402
from stages.parsing.rule_based_parser import RuleBasedSentenceParser  # noqa: E402
from stages.parsing.text_normalization import normalize_for_speech  # noqa: E402

SENTENCES = [
    "Les enfants ont acheté des pommes.",
    "les anciens amis",
    "J'ai vingt et un ans.",
    "Il est quatorze heures.",
    "Je voudrais un café, s'il vous plaît.",
    "Bonjour, comment allez-vous aujourd'hui ?",
    "Mes amis sont arrivés hier soir.",
    "Nous avons beaucoup travaillé cette semaine pour finir le projet.",
    "Quand il fait beau, nous allons souvent nous promener au bord de la mer avec nos enfants.",
    "Elle n'a jamais vu un aussi grand arbre.",
]


@pytest.fixture(scope="module")
def parser():
    return RuleBasedSentenceParser()


@pytest.mark.parametrize("sentence", SENTENCES)
def test_chunks_join_back_to_the_sentence(parser, sentence):
    chunks = parser.parse(sentence)
    assert chunks and all(c.strip() == c and c for c in chunks)
    assert " ".join(chunks) == sentence


@pytest.mark.parametrize("sentence", SENTENCES)
def test_no_chunk_ends_inside_an_obligatory_liaison_or_an_elision(parser, sentence):
    chunks = parser.parse(sentence)
    words = [(w, p) for w, p in tag_sentence(sentence) if p != "PUNCT"]
    obligatory = {
        d.between for d in apply_liaison_rules(words) if d.rule_type == "obligatoire"
    }
    for left, right in zip(chunks, chunks[1:]):
        last = [w for w, p in tag_sentence(left) if p != "PUNCT"][-1]
        first = [w for w, p in tag_sentence(right) if p != "PUNCT"][0]
        assert (last, first) not in obligatory
        assert not last.endswith("'")


def test_deterministic(parser):
    sentence = SENTENCES[-3]
    assert parser.parse(sentence) == parser.parse(sentence)


def test_empty_sentence(parser):
    assert parser.parse("") == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Les enfants ont acheté des pommes.", ["Les enfants", "ont acheté des pommes."]),
        ("les anciens amis", ["les anciens amis"]),
        ("J’ai 21 ans.", ["J'ai vingt et un ans."]),
        ("Il est 14 h.", ["Il est quatorze heures."]),
        ("Je voudrais un café, s’il vous plaît.", ["Je voudrais un café,", "s'il vous plaît."]),
        ("Mes amis sont arrivés hier soir.", ["Mes amis", "sont arrivés hier soir."]),
        (
            "Nous avons beaucoup travaillé cette semaine pour finir le projet.",
            ["Nous avons beaucoup travaillé", "cette semaine", "pour finir le projet."],
        ),
    ],
)
def test_handoff_sentences(parser, raw, expected):
    assert parser.parse(normalize_for_speech(raw)) == expected
