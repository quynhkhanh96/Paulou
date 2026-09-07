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

from stages.pos.spacy_tagger import tag_sentence  # noqa: E402


def test_determiner_noun():
    assert tag_sentence("les amis") == [("les", "DET"), ("amis", "NOUN")]


def test_pronoun_verb():
    assert tag_sentence("nous avons") == [("nous", "PRON"), ("avons", "VERB")]


def test_adjective_noun():
    assert tag_sentence("petit ami") == [("petit", "ADJ"), ("ami", "NOUN")]


def test_liaison_chain_sentence():
    assert tag_sentence("les anciens amis") == [
        ("les", "DET"),
        ("anciens", "ADJ"),
        ("amis", "NOUN"),
    ]


def test_facultative_example_sentence():
    assert tag_sentence("pas encore") == [("pas", "ADV"), ("encore", "ADV")]


def test_subject_noun_verb_requires_full_sentence_context():
    # Documents an empirically verified difference: the same words tagged
    # as an isolated 2-word fragment vs. embedded in a real sentence give
    # different (and differently correct) results. See module docstring
    # in stages/pos/spacy_tagger.py.
    fragment_result = tag_sentence("enfant arrive")
    sentence_result = tag_sentence("Mon enfant arrive demain.")

    # Isolated fragment: known to mistag "arrive" as ADJ, not VERB.
    assert fragment_result == [("enfant", "NOUN"), ("arrive", "ADJ")]

    # Full sentence: correctly tagged as NOUN + VERB.
    tagged_words = {word: pos for word, pos in sentence_result}
    assert tagged_words["enfant"] == "NOUN"
    assert tagged_words["arrive"] == "VERB"


def test_known_limitation_content_mistagged_as_adverb():
    # Regression-locking test for the known limitation documented in
    # stages/pos/spacy_tagger.py: "content" (adjective) is reproducibly
    # mistagged as ADV even in a full, correct sentence. If this test ever
    # FAILS (i.e. "content" gets tagged ADJ), that's good news — it means
    # the model improved — but the docstring/decision log note about this
    # limitation and the "très/trop + ADJ" rule should be updated too.
    result = tag_sentence("Il est trop content de venir.")
    tagged_words = {word: pos for word, pos in result}
    assert tagged_words["content"] == "ADV"
