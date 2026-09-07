"""POS tagging via spaCy `fr_core_news_sm`.

Plain function, NOT wrapped in Protocol/registry — see Decision Log D26:
unlike the GOP scorer (Kaldi vs gop-ft, actively unresolved, D9) or the
free-phone recognizer, there's no live comparison question against an
alternative (e.g. Stanza) driving a need for swap infrastructure. Published
UPOS accuracy for fr_core_news models (~96-97% on UD French Sequoia) is
well above what's needed for the coarse POS categories the liaison rule
engine consumes (DET, NOUN, ADJ, VERB, PRON, ADP, NUM, CCONJ, AUX).

Input: a full sentence (Architecture Spec stage 2b) — NOT individual word
pairs. This matters in practice, not just on paper: empirically, tagging
"enfant arrive" as an isolated 2-word fragment gives ("enfant", NOUN),
("arrive", ADJ) — wrong — while the same words embedded in a real sentence
("Mon enfant arrive demain.") correctly give ("enfant", NOUN), ("arrive",
VERB). Always call `tag_sentence` on the full sentence text, not on
fragments assembled elsewhere.

KNOWN LIMITATION (empirically verified on spaCy 3.8.16 / fr_core_news_sm
3.8.0, not yet checked against fr_core_news_md/lg or Stanza): the model
reproducibly mistags "content" (adjective, "happy") as ADV even in a full,
grammatically correct sentence — "Il est trop content de venir." tags
"content" as ADV, not ADJ. This directly undermines the liaison rule
engine's "très/trop + ADJ" obligatoire pattern for this specific word: real
liaison ("trop content" -> /tʁo.p‿kɔ̃.tɑ̃/) would be missed, since
apply_liaison_rules checks `pos2 == "ADJ"` exactly. Flagged as a known
limitation (same spirit as D4's accepted rule-engine limitations), not
fixed here — see tests/model/test_pos_tagger.py for the regression-locking
test that documents this.

VERSION NOTE (Codebase Conventions — pin model-related dependencies):
verified against spacy==3.8.16, fr_core_news_sm==3.8.0. An unpinned model
update could silently change tagging behavior (including possibly fixing
or changing the "content" limitation above) without any code change to
point to.
"""

import spacy

_NLP = None


def _get_nlp():
    """Lazily load and cache the spaCy pipeline (loading takes ~1-2s)."""
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("fr_core_news_sm")
    return _NLP


def tag_sentence(sentence: str) -> list[tuple[str, str]]:
    """Tag each word in `sentence` with its coarse POS tag (spaCy UPOS).

    Must be called on the full sentence, not isolated word fragments — see
    module docstring.
    """
    doc = _get_nlp()(sentence)
    return [(token.text, token.pos_) for token in doc]
