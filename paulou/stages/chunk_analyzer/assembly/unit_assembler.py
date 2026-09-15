"""Unit assembly.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Answers a data-structuring question, distinct from the liaison rule engine's
linguistic question (Architecture Spec, stage 2d, and Codebase Conventions
on why the two are separate): given words (with their phonemes), the
LiaisonDecisions already computed for each adjacent pair, and elision
(detected internally per word, see stages/chunk_analyzer/elision/elision.py), how do they
group into PronunciationUnits?

ELISION (added after the original design — not in the Architecture Spec):
checked BEFORE liaison at each position, via `detect_elision(word)`. No new
parameter was needed for this — elision detection depends only on the
word's own spelling, not on any external decision structure, so it's
called directly here. This is safe with respect to the existing liaison
logic: an elided word (e.g. "l'") never has a usable liaison consonant
(`get_liaison_consonant` returns None for it, since it ends in an
apostrophe), so its LiaisonDecision is already a structural no-op
(`applies=False`) — checking elision first never overrides a liaison merge
that would otherwise have happened.

Open design point (not yet resolved in the Architecture Spec — flagged here
rather than silently decided): what happens when two *consecutive*
LiaisonDecisions both apply (e.g. "les anciens amis", where les|anciens and
anciens|amis are both obligatoire)? `PronunciationUnit.liaison_consonant` is
a single value, not a list, which implies each liaison_group spans exactly
one liaison boundary (2 words). This implementation resolves the conflict
greedily, left-to-right: the first applicable pair is merged and both its
words are consumed; if the second word's decision to its right also
applies, it is NOT applied, because that word has already been consumed
into the first group. Revisit if 3+ word liaison chains turn out to matter
in practice. The same greedy left-to-right consumption applies to elision.
"""

from core.models import LiaisonDecision, PronunciationUnit
from stages.chunk_analyzer.elision.elision import detect_elision


def assemble_units(
    words_with_phonemes: list[tuple[str, list[str]]],
    liaison_decisions: list[LiaisonDecision],
) -> list[PronunciationUnit]:
    """Group words into PronunciationUnits using precomputed liaison decisions
    and internally-detected elision.

    `words_with_phonemes` and `liaison_decisions` must satisfy
    `len(liaison_decisions) == len(words_with_phonemes) - 1` (one decision
    per adjacent pair), matching what `apply_liaison_rules` returns for the
    same word sequence.

    Raises ValueError if an elided clitic (e.g. "l'") is the last word in
    the sequence, since elision requires a following word to fuse with —
    this would indicate a malformed chunk (e.g. a chunk boundary drawn
    right after an elided clitic by the sentence parser).
    """
    expected_decisions = max(len(words_with_phonemes) - 1, 0)
    if len(liaison_decisions) != expected_decisions:
        raise ValueError(
            f"Expected {expected_decisions} liaison decisions for "
            f"{len(words_with_phonemes)} words, got {len(liaison_decisions)}."
        )

    units: list[PronunciationUnit] = []
    unit_index = 0
    i = 0
    n = len(words_with_phonemes)

    while i < n:
        word, phonemes = words_with_phonemes[i]
        elided_phonemes = detect_elision(word)

        if elided_phonemes is not None:
            if i + 1 >= n:
                raise ValueError(
                    f"Elided clitic {word!r} has no following word to fuse "
                    f"with — malformed chunk (elision requires a following "
                    f"vowel-initial word)."
                )
            next_word, next_phonemes = words_with_phonemes[i + 1]
            unit_phonemes = list(elided_phonemes) + list(next_phonemes)
            units.append(
                PronunciationUnit(
                    id=f"unit_{unit_index}",
                    type="elision_group",
                    words=[word, next_word],
                    phonemes=unit_phonemes,
                    ipa="".join(unit_phonemes),
                    syllables=[],  # not yet specced — see core/models.py
                    liaison_consonant=None,
                    note="",  # not yet specced — see core/models.py
                    scoring_focus="elision_correctness",
                )
            )
            i += 2
            unit_index += 1
            continue

        decision = liaison_decisions[i] if i < len(liaison_decisions) else None

        if decision is not None and decision.applies:
            word1, phonemes1 = words_with_phonemes[i]
            word2, phonemes2 = words_with_phonemes[i + 1]
            unit_phonemes = list(phonemes1) + [decision.consonant] + list(phonemes2)
            units.append(
                PronunciationUnit(
                    id=f"unit_{unit_index}",
                    type="liaison_group",
                    words=[word1, word2],
                    phonemes=unit_phonemes,
                    ipa="".join(unit_phonemes),
                    syllables=[],  # not yet specced — see module docstring
                    liaison_consonant=decision.consonant,
                    note="",  # not yet specced — see module docstring
                    scoring_focus="liaison_presence_and_continuity",
                )
            )
            i += 2
        else:
            units.append(
                PronunciationUnit(
                    id=f"unit_{unit_index}",
                    type="single",
                    words=[word],
                    phonemes=list(phonemes),
                    ipa="".join(phonemes),
                    syllables=[],
                    liaison_consonant=None,
                    note="",
                    scoring_focus="phoneme_accuracy",
                )
            )
            i += 1

        unit_index += 1

    return units