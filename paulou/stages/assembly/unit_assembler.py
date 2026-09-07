"""Unit assembly.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Answers a data-structuring question, distinct from the liaison rule engine's
linguistic question (Architecture Spec, stage 2d, and Codebase Conventions
on why the two are separate): given words (with their phonemes) and the
LiaisonDecisions already computed for each adjacent pair, how do they group
into PronunciationUnits?

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
in practice.
"""

from core.models import LiaisonDecision, PronunciationUnit


def assemble_units(
    words_with_phonemes: list[tuple[str, list[str]]],
    liaison_decisions: list[LiaisonDecision],
) -> list[PronunciationUnit]:
    """Group words into PronunciationUnits using precomputed liaison decisions.

    `words_with_phonemes` and `liaison_decisions` must satisfy
    `len(liaison_decisions) == len(words_with_phonemes) - 1` (one decision
    per adjacent pair), matching what `apply_liaison_rules` returns for the
    same word sequence.
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
        decision = liaison_decisions[i] if i < len(liaison_decisions) else None

        if decision is not None and decision.applies:
            word1, phonemes1 = words_with_phonemes[i]
            word2, phonemes2 = words_with_phonemes[i + 1]
            combined_ipa = "".join(phonemes1) + decision.consonant + "".join(phonemes2)
            units.append(
                PronunciationUnit(
                    id=f"unit_{unit_index}",
                    type="liaison_group",
                    words=[word1, word2],
                    ipa=combined_ipa,
                    syllables=[],  # not yet specced — see module docstring
                    liaison_consonant=decision.consonant,
                    note="",  # not yet specced — see module docstring
                    scoring_focus="liaison_presence_and_continuity",
                )
            )
            i += 2
        else:
            word, phonemes = words_with_phonemes[i]
            units.append(
                PronunciationUnit(
                    id=f"unit_{unit_index}",
                    type="single",
                    words=[word],
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
