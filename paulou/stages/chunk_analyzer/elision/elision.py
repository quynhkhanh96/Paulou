"""Elision detection.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

NEW PHENOMENON, distinct from liaison and enchaînement (see Glossary —
needs an "Elision" entry added, it wasn't there before this): the FINAL
VOWEL of a small closed set of French function words (le/la, de, je, me,
te, se, ne, que, ce) drops when the next word starts with a vowel sound,
marked orthographically with an apostrophe (l', d', j', m', t', s', n',
qu', c'). Unlike liaison:
- It's a CLOSED LIST of specific words, not a POS pattern — no rule engine
  needed, just a lookup.
- It's not a yes/no "decision" the way LiaisonDecision is — seeing the
  elided orthographic form (e.g. "l'" rather than "le") is itself proof
  the fusion already happened in the source text.
- No consonant is added — the elided word's own remaining phoneme (e.g.
  /l/ for "l'") is simply followed directly by the next word's phonemes.
  Confirmed empirically to be mutually exclusive with liaison on the same
  word: elidable words end in a vowel/schwa (nothing for
  get_liaison_consonant to match), so a LiaisonDecision computed for an
  elided word is always a no-op (applies=False) anyway — no conflict when
  both are checked at the same position in unit assembly.

Distinct from enchaînement (also in the Glossary), which is NOT modeled
here or anywhere yet: enchaînement needs to know whether a word's final
consonant is already pronounced, which requires G2P output — unlike
elision and liaison, which are both decidable from orthography/POS alone,
before G2P runs. Modeling enchaînement would need reordering the pipeline
(G2P before the junction decision). Deferred, per the Glossary's existing
note on enchaînement.

Closed list not guaranteed exhaustive — covers the standard set of French
elidable clitics. Apostrophe is assumed to be the straight ASCII quote
(U+0027), matching what spaCy's French tokenizer produces (verified
empirically). A typographic apostrophe (’, U+2019) in raw input would not
match and would fall through to ordinary G2P/liaison handling for that
token instead (almost certainly phonemized wrong, likely via the eSpeak
fallback on an out-of-dictionary fragment).
"""

ELIDED_CLITICS: dict[str, list[str]] = {
    "l'": ["l"],
    "d'": ["d"],
    "j'": ["ʒ"],
    "m'": ["m"],
    "n'": ["n"],
    "qu'": ["k"],
    "s'": ["s"],
    "t'": ["t"],
    "c'": ["s"],
}


def detect_elision(word: str) -> list[str] | None:
    """Return the phoneme(s) for `word` if it's a recognized elided clitic.

    Case-insensitive (matches "L'" as well as "l'"). Returns None if `word`
    is not in the closed list — i.e. not an elided form.
    """
    return ELIDED_CLITICS.get(word.lower())
