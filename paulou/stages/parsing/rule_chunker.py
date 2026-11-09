"""Rule-based chunking of a POS-tagged sentence into rhythmic groups (D67).

Pure, deterministic logic -- no Protocol/registry wrapper (Decision Log D12).
The registered `SentenceParser` that tags the sentence with spaCy and calls
this is `stages/parsing/rule_based_parser.py`; this module takes the tags as
input so it can be tested without loading a model.

Order of work (D67):
1. Split the sentence at punctuation (, ; : . ! ? … and the like). No
   liaison is made across punctuation, and a chunk always ends there.
2. Compute liaison decisions per punctuation segment, over the WHOLE segment
   (`apply_liaison_rules`), before any chunk exists. Elision is detected
   from the spelling (a word ending in an apostrophe).
3. Cut each segment into groups, left to right.

HARD RULES -- a cut is never made:
- inside a liaison: an obligatory one, or an optional one in /z/, /t/ or
  /n/ (`_RARE_OPTIONAL_CONSONANTS` excepted). Cutting inside an optional
  liaison would forbid it, and a learner who makes it would be marked with
  an extra sound (the D51 problem). Optional liaisons in /ʁ/, /p/, /v/
  ("promener‿au") are rare in speech and the rule engine allows them
  broadly, so they do not block a cut;
- after an elided word ("l'", "qu'", "jusqu'"...): it fuses with the next
  word (and `assemble_units` raises on a chunk ending in one);
- across a hyphen ("allez" + "-vous"; "quarante", "-", "cinq" when spaCy
  splits a hyphenated number), whether the hyphen is its own token or not;
- after a word that leans on the next one (`_leans_forward`): determiners,
  prepositions, conjunctions, auxiliaries, "ne"/"n'", a pronoun before its
  verb, an adverb before an adjective or adverb ("très grand").

SOFT RULES -- where a cut is made, among the allowed places:
- at a STRONG boundary (`_boundary`: before a preposition or conjunction;
  between a noun phrase and a following verb, pronoun or adverb) once the
  group has `MIN_SYLLABLES`;
- at a WEAK boundary (before a determiner, or a numeral after a verb: the
  start of an object noun phrase; between a verb and a following adverb)
  once the group has `MIN_SYLLABLES_WEAK`;
- never before "de"/"d'"/"du"/"des" after a noun: a noun complement
  ("l'université de Toulon") stays in its noun phrase;
- anywhere allowed, if the next word would take the group past
  `MAX_SYLLABLES`.
A last group shorter than `MIN_SYLLABLES` in its segment is merged into the
previous one when the result stays within `MAX_SYLLABLES` (avoids a lone
"des pommes" or "pas" at the end).

Group length is counted in ESTIMATED syllables, from the spelling
(`estimate_syllables`): G2P has not run yet at this point.

KNOWN LIMITS (D67, accepted for MVP; checked by hand, no regression set,
D70):
- Groups follow syntax, not measured prosody: they approximate D2's
  "groupe rythmique".
- Depends on spaCy's tags; known mistags (e.g. "habite" as ADJ, "des" as
  ADP) move cuts.
- A sentence with no allowed cut (e.g. a long chain of liaisons) gives one
  long chunk: the hard rules win over `MAX_SYLLABLES`.
"""

import re

from core.models import LiaisonDecision
from stages.chunk_analyzer.liaison.rule_engine import apply_liaison_rules, get_liaison_consonant

MIN_SYLLABLES = 3
MIN_SYLLABLES_WEAK = 5
MAX_SYLLABLES = 10

# Punctuation that belongs to the FOLLOWING word; every other punctuation
# token belongs to the preceding word and ends a segment.
_OPENING_PUNCT = frozenset({"«", "(", "[", "“", "‘", '"', "„", "‹"})
_PUNCT_POS = frozenset({"PUNCT", "SYM", "SPACE"})
_HYPHENS = ("-", "\u2010", "\u2011")

_FUNCTION_POS = frozenset({"DET", "ADP", "CCONJ", "SCONJ", "AUX"})
_NOMINAL_POS = frozenset({"NOUN", "PROPN", "ADJ"})
_NEGATION_START = frozenset({"ne", "n'"})
_NOUN_COMPLEMENT_ADP = frozenset({"de", "d'", "du", "des"})
_RARE_OPTIONAL_CONSONANTS = frozenset({"ʁ", "p", "v"})
# Second part of a negation: not the start of a new group ("Je ne sais pas").
_NEGATION_END = frozenset({"pas", "plus", "jamais", "rien", "point", "guère", "personne"})

_VOWEL_GROUP_RE = re.compile(r"[aeiouyàâäéèêëîïôöùûüœæ]+")
_MUTE_E_RE = re.compile(r"[^aeiouyàâäéèêëîïôöùûüœæ]es?$")


def estimate_syllables(word: str, pos: str = "") -> int:
    """Rough syllable count from the spelling: vowel-letter groups, minus a
    final mute e ("pommes" -> 1) or a verb's "-ent" ("mangent" -> 1).

    An elided clitic ("l'") counts 0. Good enough to size groups; not a
    syllabifier (the `syllables` field of PronunciationUnit is still unset).
    """
    w = word.lower().strip("'-")
    groups = len(_VOWEL_GROUP_RE.findall(w))
    if groups > 1 and (_MUTE_E_RE.search(w) or (pos in ("VERB", "AUX") and w.endswith("ent"))):
        groups -= 1
    return groups


def _is_elided(word: str) -> bool:
    return word.endswith("'")


def _leans_forward(word: str, pos: str, next_word: str, next_pos: str) -> bool:
    """Whether `word` belongs with the word after it (no cut after it)."""
    lower = word.lower()
    if _is_elided(word) or lower in _NEGATION_START:
        return True
    if pos in _FUNCTION_POS:
        return True
    if pos == "PRON" and (
        next_pos in ("VERB", "AUX", "PRON") or next_word.lower() in _NEGATION_START
    ):
        return True
    if pos == "ADV" and next_pos in ("ADJ", "ADV") and next_word.lower() not in _NEGATION_END:
        return True
    return False


def _boundary(pos: str, next_word: str, next_pos: str) -> str | None:
    """Strength of the boundary between a word and the next one: "strong",
    "weak", or None when the next word does not start a new group."""
    next_lower = next_word.lower()
    if next_pos == "ADP" and pos in ("NOUN", "PROPN") and next_lower in _NOUN_COMPLEMENT_ADP:
        return None
    if next_pos in ("ADP", "SCONJ", "CCONJ") or next_lower in _NEGATION_START:
        return "strong"
    if pos in _NOMINAL_POS and next_pos in ("VERB", "AUX", "PRON"):
        return "strong"
    if next_pos == "ADV" and next_lower not in _NEGATION_END:
        if pos in _NOMINAL_POS:
            return "strong"
        if pos == "VERB":
            return "weak"
    if next_pos == "DET" or (next_pos == "NUM" and pos in ("VERB", "AUX")):
        return "weak"
    return None


def _cut_blocked(
    words: list[tuple[str, str]], decisions: list[LiaisonDecision], glued: list[bool], i: int
) -> bool:
    """Whether a cut between words[i] and words[i + 1] is forbidden."""
    word, pos = words[i]
    next_word, next_pos = words[i + 1]
    liaison = decisions[i].rule_type == "obligatoire" or (
        decisions[i].rule_type == "facultative"
        and get_liaison_consonant(word) not in _RARE_OPTIONAL_CONSONANTS
    )
    return (
        liaison
        or glued[i]
        or word.endswith(_HYPHENS)
        or next_word.startswith(_HYPHENS)
        or _leans_forward(word, pos, next_word, next_pos)
    )


def _group_segment(words: list[tuple[str, str]], glued: list[bool]) -> list[list[int]]:
    """Cut one punctuation segment (a list of (word, pos)) into groups of
    word indices. `glued[i]` is True when a hyphen token sits between word i
    and word i + 1."""
    decisions = apply_liaison_rules(words)
    syllables = [estimate_syllables(w, p) for w, p in words]

    groups: list[list[int]] = [[0]]
    size = syllables[0]
    for i in range(len(words) - 1):
        cut = False
        if not _cut_blocked(words, decisions, glued, i):
            strength = _boundary(words[i][1], *words[i + 1])
            cut = (
                (strength == "strong" and size >= MIN_SYLLABLES)
                or (strength == "weak" and size >= MIN_SYLLABLES_WEAK)
                or size + syllables[i + 1] > MAX_SYLLABLES
            )
        if cut:
            groups.append([i + 1])
            size = syllables[i + 1]
        else:
            groups[-1].append(i + 1)
            size += syllables[i + 1]

    if len(groups) > 1:
        last = sum(syllables[j] for j in groups[-1])
        previous = sum(syllables[j] for j in groups[-2])
        if last < MIN_SYLLABLES and last + previous <= MAX_SYLLABLES:
            groups[-2].extend(groups.pop())
    return groups


def chunk_tokens(tokens: list[tuple[str, str]]) -> list[tuple[int, int]]:
    """Cut a tagged sentence into chunks.

    `tokens` is the WHOLE sentence as tagged (text, UPOS), punctuation
    included, in order. Returns half-open token index ranges, one per chunk:
    contiguous, in order, covering every token. Punctuation stays with the
    preceding word (opening quotes and brackets with the following one).
    A sentence with no word gives one chunk holding everything (or [] for
    no tokens).
    """
    if not tokens:
        return []

    word_positions = [k for k, (_t, pos) in enumerate(tokens) if pos not in _PUNCT_POS]
    if not word_positions:
        return [(0, len(tokens))]

    # 1. Punctuation segments, as lists of token positions of words. A
    # hyphen tagged as punctuation does not end a segment: it glues the
    # words on both sides.
    segments: list[list[int]] = [[]]
    glued_after: set[int] = set()
    for k, (text, pos) in enumerate(tokens):
        if pos in _PUNCT_POS:
            if text in _HYPHENS:
                if segments[-1]:
                    glued_after.add(segments[-1][-1])
            elif text not in _OPENING_PUNCT and pos != "SPACE" and segments[-1]:
                segments.append([])
        else:
            segments[-1].append(k)
    segments = [s for s in segments if s]

    # 2-3. Groups per segment; record the token position each group starts at.
    group_starts: list[int] = []
    for segment in segments:
        words = [tokens[k] for k in segment]
        glued = [k in glued_after for k in segment]
        for group in _group_segment(words, glued):
            group_starts.append(segment[group[0]])

    # Attach punctuation: an opening mark directly before a group's first
    # word moves into that group; the first group also takes anything before
    # it.
    starts: list[int] = []
    for start in group_starts:
        while start > 0 and tokens[start - 1][0] in _OPENING_PUNCT:
            start -= 1
        starts.append(start)
    starts[0] = 0

    ends = starts[1:] + [len(tokens)]
    return list(zip(starts, ends))
