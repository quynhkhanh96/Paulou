"""Liaison rule engine.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12):
there is no real expectation of swapping this rule algorithm for another
implementation.

Answers a single linguistic question per adjacent word pair: "does liaison
happen here, and if so, with which consonant?" (Architecture Spec, stage 2c).
Grouping words into PronunciationUnits from this output is a separate
concern (stage 2d, unit assembly) — kept separate on purpose so each can be
tested independently (see Codebase Conventions).

Known limitation (accepted, not an oversight — Decision Log D4): purely
rule-based liaison detection is expected to be incomplete on unconstrained
free-form input containing rare vocabulary, proper nouns, or unusual syntax.
"""

from core.models import LiaisonConsonant, LiaisonDecision

# --- Closed lists -----------------------------------------------------------
# Deliberately small starter sets for MVP. Genuinely closed in principle
# (a fixed set of French words), but these lists are not exhaustive yet —
# extending them is a data task, not a rule-engine design change.

H_ASPIRE_WORDS: frozenset[str] = frozenset(
    {
        "héros", "haricot", "hibou", "hamac", "hasard", "honte", "houle",
        "hache", "hall", "handicap", "hanche", "harpe", "hauteur", "hérisson",
        "hockey", "homard",
    }
)

# Words that are spelled vowel-initial (or semivowel) but behave as
# consonant-initial for liaison purposes.
SEMIVOWEL_BLOCKING_WORDS: frozenset[str] = frozenset(
    {"onze", "oui", "uhlan", "yaourt", "ouistiti", "yacht", "yoga"}
)

MONOSYLLABIC_PREPOSITIONS: frozenset[str] = frozenset(
    {"dans", "en", "sans", "chez", "sous", "dès"}
)

TRES_TROP_WORDS: frozenset[str] = frozenset({"très", "trop"})

_VOWEL_LETTERS = "aeiouyàâäéèêëîïôöùûü"


def get_liaison_consonant(word: str) -> LiaisonConsonant | None:
    """Return the liaison consonant a word's final letter would produce, if any.

    Mapping per Architecture Spec, stage 2c: s/x/z -> z, t/d -> t, n -> n,
    r -> ʁ (rare), p -> p (rare), f -> v (rare, irregular). Words not ending
    in one of these letters cannot take part in liaison.
    """
    if not word:
        return None
    last = word[-1].lower()
    return {
        "s": "z", "x": "z", "z": "z",
        "t": "t", "d": "t",
        "n": "n",
        "r": "ʁ",
        "p": "p",
        "f": "v",
    }.get(last)


def _liaison_allowed_before(word: str) -> bool:
    """Whether the following word's initial sound can host a liaison at all.

    True for vowel-initial words and h-muet words; False for ordinary
    consonant-initial words, h-aspiré words (closed list), and the small set
    of semivowel words that behave as consonant-initial despite their
    spelling (e.g. "onze", "oui").
    """
    word_lower = word.lower()
    if not word_lower:
        return False

    first_letter = word_lower[0]

    if first_letter == "h":
        return word_lower not in H_ASPIRE_WORDS

    if first_letter in _VOWEL_LETTERS:
        return word_lower not in SEMIVOWEL_BLOCKING_WORDS

    return False


def _is_obligatoire(word1: str, pos1: str, word2: str, pos2: str) -> bool:
    """Check the POS-pattern obligatoire rules from Architecture Spec 2c."""
    pos1, pos2 = pos1.upper(), pos2.upper()
    word1_lower = word1.lower()

    if pos1 == "DET" and pos2 in {"NOUN", "ADJ"}:
        return True
    if pos1 == "PRON" and pos2 in {"VERB", "AUX"}:
        return True
    if pos1 == "ADJ" and pos2 == "NOUN":
        return True
    if pos1 == "ADP" and word1_lower in MONOSYLLABIC_PREPOSITIONS:
        return True
    if pos1 == "NUM" and pos2 == "NOUN":
        return True
    if word1_lower in TRES_TROP_WORDS and pos2 == "ADJ":
        return True
    return False


def _is_interdite_by_grammar(word1: str, pos1: str, word2: str, pos2: str) -> bool:
    """Check the closed-list / grammar-pattern interdite rules.

    Note on the "after a singular noun subject" rule: number (singular vs.
    plural) isn't available from POS tags alone. This is simplified to
    "NOUN directly followed by VERB/AUX" for MVP — a known simplification
    of the rule as specced, not a full implementation of number agreement.
    """
    if word1.lower() == "et":
        return True
    if pos1.upper() == "NOUN" and pos2.upper() in {"VERB", "AUX"}:
        return True
    return False


def apply_liaison_rules(
    words_with_pos: list[tuple[str, str]]
) -> list[LiaisonDecision]:
    """Evaluate liaison between each pair of adjacent words in a chunk.

    Returns one LiaisonDecision per adjacent pair (len(words_with_pos) - 1
    decisions total). Order of checks, most to least specific:

    1. Structurally impossible (next word doesn't allow liaison at all, or
       current word has no liaison-capable final consonant) -> interdite.
    2. Grammar/closed-list interdite rules (after "et", subject noun before
       verb) -> interdite, even if the next word would otherwise allow it.
    3. POS-pattern obligatoire rules -> obligatoire.
    4. Otherwise (liaison is phonetically possible but not covered by 2 or
       3) -> facultative. Per Architecture Spec, this is deliberately NOT
       predicted as True or False — Paulou accepts either variant. `applies`
       is set to False here as a placeholder value only; `rule_type` is what
       downstream code (unit assembly) should actually branch on.
    """
    decisions: list[LiaisonDecision] = []

    for (word1, pos1), (word2, pos2) in zip(words_with_pos, words_with_pos[1:]):
        consonant = get_liaison_consonant(word1)
        next_allows_liaison = _liaison_allowed_before(word2)

        if consonant is None or not next_allows_liaison:
            decisions.append(
                LiaisonDecision(
                    between=(word1, word2),
                    applies=False,
                    consonant=None,
                    rule_type="interdite",
                )
            )
            continue

        if _is_interdite_by_grammar(word1, pos1, word2, pos2):
            decisions.append(
                LiaisonDecision(
                    between=(word1, word2),
                    applies=False,
                    consonant=None,
                    rule_type="interdite",
                )
            )
            continue

        if _is_obligatoire(word1, pos1, word2, pos2):
            decisions.append(
                LiaisonDecision(
                    between=(word1, word2),
                    applies=True,
                    consonant=consonant,
                    rule_type="obligatoire",
                )
            )
            continue

        decisions.append(
            LiaisonDecision(
                between=(word1, word2),
                applies=False,
                consonant=None,
                rule_type="facultative",
            )
        )

    return decisions
