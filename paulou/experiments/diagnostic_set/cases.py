"""Diagnostic case definitions for the D10 canonicalizer-bias check (D43).

Each `DiagnosticCase` describes ONE native sentence plus the single
controlled perturbation applied to it (deletion / insertion / substitution).
`canonical_phonemes` and `unit_ids` are built by reusing the REAL, already-
implemented G2P provider (`LexiqueEspeakG2P`) and liaison consonant mapping
(`get_liaison_consonant`) rather than hand-typing IPA strings — the fixture
lexicon (`tests/fixtures/g2p_golden.tsv`) is small and already
hand-verified, so word-level phonemes come from there rather than from a
guess. Words not in that fixture ("héros", "anciens", "et") are grounded
here the same way the codebase's own eSpeak-ng fallback would produce them
(`espeak-ng -v fr --ipa=1 -q <word>`, stress stripped) rather than typed
from memory — see the `_EXTRA_WORDS` comment below.

Per Decision Log D43, this module belongs to `experiments/diagnostic_set/`,
not `stages/` — it is diagnostic tooling for validating Speech Assessment
(stage 5), not a pipeline stage itself, and produces no `register()`ed
implementation.

Per D3/D38's PronunciationUnit model: a liaison_group's phonemes ALL share
one `unit_id` (the group is scored as one unit), matching the parallel
`unit_ids` array shape that `align_phonemes` (stage 5c') expects.

TRANCHE 1 (this revision) vs. TRANCHE 2 (not yet built): per the
conversation reviewing an external (Grok-authored) ~48-case proposal, cases
here are scoped to Paulou's actual liaison focus (D3/D9) first. Broader
categories that proposal raised — generic final-consonant deletion,
weak/cluster deletion, wider substitution coverage (nasal vowels, /y/-/u/)
— are deliberately deferred to a later Tranche 2, not forgotten; see the
chat discussion for the full external proposal and which parts were
accepted vs. corrected (notably: its "un petit ami" case was mislabeled as
a liaison "chain" — verified via espeak-ng that "un"+"petit" has no liaison
at all, since "petit" is consonant-initial — the real chain example is
"les anciens amis", already documented as D23's own worked example, used
below instead).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from stages.chunk_analyzer.g2p.lexique_espeak import LexiqueEspeakG2P
from stages.chunk_analyzer.liaison.rule_engine import get_liaison_consonant

PerturbationType = Literal["native", "substitution", "deletion", "insertion"]

_GOLDEN_LEXICON_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "g2p_golden.tsv"
)

# Words needed for cases below that are NOT in the golden fixture.
# Grounded via `espeak-ng -v fr --ipa=1 -q <word>` (same method the real
# eSpeak-ng fallback uses, see lexique_espeak.py docstring), stress marks
# stripped — NOT typed from memory.
_EXTRA_WORDS: dict[str, list[str]] = {
    "héros": ["e", "ʁ", "o"],
    "anciens": ["ɑ̃", "s", "j", "ɛ̃"],
    "et": ["e"],
    "table": ["t", "a", "b", "l"],
    "porte": ["p", "ɔ", "ʁ", "t"],
    "spectacle": ["s", "p", "ɛ", "k", "t", "a", "k", "l"],
    "lune": ["l", "y", "n"],
}


@dataclass(frozen=True)
class DiagnosticCase:
    """One diagnostic audio case: a sentence plus its single perturbation."""

    case_id: str
    sentence_text: str
    canonical_phonemes: list[str]
    """The NATIVE (correct) phoneme sequence, in order."""
    unit_ids: list[str]
    """Parallel to canonical_phonemes — see align_phonemes' expected shape."""
    perturbation_type: PerturbationType
    target_index: int | None
    """Index into canonical_phonemes the perturbation applies at/before.
    None only for perturbation_type == "native" (no change)."""
    injected_phoneme: str | None
    """Phoneme substituted in, or inserted. None for deletion and native."""
    perturbation_note: str
    """Human-readable note on WHY this case — liaison rule type, or which
    real-world error pattern it's modeling (see module docstring)."""
    native_word_boundary_index: int | None = None
    """Index into canonical_phonemes where a word-boundary pause belongs
    when rendering the NATIVE audio -- None (the default) for a real
    liaison_group, single word, or anywhere words are meant to be
    pronounced connected with no gap (D35). Only meaningfully set for a
    case type where the NATIVE form has no liaison connecting two words
    (not yet used by any Tranche 1/2 case; see chat discussion re:
    insertion-case symmetry, left unset pending a decision)."""
    perturbed_word_boundary_index: int | None = None
    """Index into the PERTURBED phoneme list (not canonical_phonemes) where
    a word-boundary pause belongs when rendering the perturbed audio --
    set for deletion-type liaison cases: once the liaison consonant is
    removed, the two words are no longer acoustically one connected unit
    (a learner unaware of the liaison would say them as two separate
    words, with a natural pause) -- see chat discussion. None (default)
    for cases where this doesn't apply (substitution, word-internal
    deletion, and insertion cases for now)."""


def _make_g2p() -> LexiqueEspeakG2P:
    """Build a G2P provider covering the golden fixture plus _EXTRA_WORDS.

    Uses the real LexiqueEspeakG2P class (not a reimplementation) with an
    in-memory lexicon dict, per its documented `lexicon=` constructor path.
    """
    golden = LexiqueEspeakG2P(lexicon_path=_GOLDEN_LEXICON_PATH)
    combined = dict(golden._lexicon)
    combined.update(_EXTRA_WORDS)
    return LexiqueEspeakG2P(lexicon=combined)


def _liaison_deletion_case(g2p: LexiqueEspeakG2P) -> DiagnosticCase:
    """"Les amis" — obligatoire liaison (determiner+noun, D21-D23) -> /z/.

    Perturbation: DELETE the /z/. Chosen as the primary case per D43's
    SLA-literature finding that omission is the dominant real liaison
    error type — this is the single most important failure mode D10 must
    catch (an undetected dropped liaison is exactly what D9/D19/D36 exist
    to guard against).
    """
    les_phonemes, _ = g2p.phonemize("les")
    amis_phonemes, _ = g2p.phonemize("amis")
    consonant = get_liaison_consonant("les")
    assert consonant == "z", f"expected liaison consonant z, got {consonant!r}"

    canonical = [*les_phonemes, consonant, *amis_phonemes]
    unit_id = "u_les_amis"  # liaison_group: ALL phonemes share one unit_id
    unit_ids = [unit_id] * len(canonical)
    z_index = len(les_phonemes)  # position of the liaison consonant

    return DiagnosticCase(
        case_id="liaison_deletion_les_amis",
        sentence_text="les amis",
        canonical_phonemes=canonical,
        unit_ids=unit_ids,
        perturbation_type="deletion",
        target_index=z_index,
        injected_phoneme=None,
        perturbation_note=(
            "Obligatoire liaison (determiner+noun) between 'les' and "
            "'amis'; deleting the /z/ models the dominant real liaison "
            "error type (omission) per D43's SLA-literature review."
        ),
        # Once /z/ is gone, "les" and "amis" are no longer one connected
        # liaison_group -- a learner unaware of the liaison would say them
        # as two separate words with a natural pause between them.
        perturbed_word_boundary_index=len(les_phonemes),
    )


def _substitution_case(g2p: LexiqueEspeakG2P) -> DiagnosticCase:
    """"Chat" — single-word substitution, unrelated to liaison.

    Perturbation: substitute /ʃ/ -> /s/. Not liaison-related; represents
    the general phoneme_accuracy scoring_focus (single units), informed by
    general MDD-corpus literature (L2-ARCTIC) where substitution is the
    dominant error type for ordinary phoneme mispronunciation.
    """
    chat_phonemes, _ = g2p.phonemize("chat")
    unit_id = "u_chat"

    return DiagnosticCase(
        case_id="substitution_chat",
        sentence_text="chat",
        canonical_phonemes=list(chat_phonemes),
        unit_ids=[unit_id] * len(chat_phonemes),
        perturbation_type="substitution",
        target_index=0,
        injected_phoneme="s",
        perturbation_note=(
            "Single-word substitution /ʃ/->/s/, no liaison involved — "
            "general phoneme_accuracy case, informed by L2-ARCTIC's "
            "substitution-dominant error distribution for ordinary "
            "(non-liaison) phoneme errors."
        ),
    )


def _liaison_insertion_case(g2p: LexiqueEspeakG2P) -> DiagnosticCase:
    """"Un héros" — INTERDITE liaison (h-aspiré, D21-D22) -> no liaison.

    Perturbation: INSERT the /n/ liaison consonant anyway (wrongly applying
    liaison where it's forbidden). Modeled as inserting the real liaison
    consonant rather than a glottal stop/l-insertion (the SLA-literature-
    attested realistic forms, see D43) — a deliberate MVP simplification,
    flagged as a candidate addition once more cases are added.
    """
    un_phonemes, _ = g2p.phonemize("un")
    heros_phonemes, _ = g2p.phonemize("héros")
    consonant = get_liaison_consonant("un")
    assert consonant == "n", f"expected liaison consonant n, got {consonant!r}"

    canonical = [*un_phonemes, *heros_phonemes]  # NO liaison in the native form
    unit_ids = ["u_un"] * len(un_phonemes) + ["u_heros"] * len(heros_phonemes)
    insertion_index = len(un_phonemes)  # insert right after "un"'s phonemes

    return DiagnosticCase(
        case_id="liaison_insertion_un_heros",
        sentence_text="un héros",
        canonical_phonemes=canonical,
        unit_ids=unit_ids,
        perturbation_type="insertion",
        target_index=insertion_index,
        injected_phoneme=consonant,
        perturbation_note=(
            "Interdite liaison (h-aspiré closed list, D21-D22) between "
            "'un' and 'héros'; inserting /n/ anyway models a learner "
            "wrongly applying liaison in a forbidden context."
        ),
        # NOT given a native_word_boundary_index, unlike et_amis -- confirmed
        # by listening (chat discussion) that a pause right after "un"'s
        # nasal vowel (œ̃) produces a nasal-release artifact that is easily
        # mistaken for /n/, which is exactly backwards from what this case
        # needs to demonstrate (no consonant in native, a real /n/ only in
        # perturbed). et_amis ends in an oral vowel (/e/) and doesn't have
        # this problem, so it keeps its boundary. This only affects manual
        # listening verification -- the underlying phoneme data (no /n/ in
        # canonical_phonemes, /n/ only in the perturbed list) is unchanged
        # and is what actually reaches FreePhoneRecognizer later.
    )


def _petit_ami_deletion_case(g2p: LexiqueEspeakG2P) -> DiagnosticCase:
    """"Petit ami" — obligatoire liaison (adjective before noun, D-spec 2c) -> /t/.

    Second liaison-deletion case, using a DIFFERENT consonant (/t/, not
    /z/) than the "les amis" case — Tranche 1 diversification per the
    Grok-proposal review.
    """
    petit_phonemes, _ = g2p.phonemize("petit")
    ami_phonemes, _ = g2p.phonemize("ami")
    consonant = get_liaison_consonant("petit")
    assert consonant == "t", f"expected liaison consonant t, got {consonant!r}"

    canonical = [*petit_phonemes, consonant, *ami_phonemes]
    unit_id = "u_petit_ami"
    t_index = len(petit_phonemes)

    return DiagnosticCase(
        case_id="liaison_deletion_petit_ami",
        sentence_text="petit ami",
        canonical_phonemes=canonical,
        unit_ids=[unit_id] * len(canonical),
        perturbation_type="deletion",
        target_index=t_index,
        injected_phoneme=None,
        perturbation_note=(
            "Obligatoire liaison (adjective before noun) between 'petit' "
            "and 'ami'; deleting the /t/ diversifies the liaison-consonant "
            "coverage beyond the /z/ case (les amis)."
        ),
        perturbed_word_boundary_index=len(petit_phonemes),
    )


def _les_anciens_amis_chain_case(g2p: LexiqueEspeakG2P) -> DiagnosticCase:
    """"Les anciens amis" — a genuine liaison CHAIN (D23's own worked example).

    NOTE on unit_ids (flagged simplification, not a D23 fix): D23 documents
    that the real `assemble_units` greedily consumes "anciens" into the
    les+anciens liaison_group and DROPS the second (anciens-amis) liaison
    boundary entirely -- it would not produce a unit for it. This function
    does NOT reproduce that dropping behavior; it assigns "anciens"'s
    phonemes to one unit and the second liaison consonant + "amis" to a
    SEPARATE unit, so this diagnostic can exercise a real two-liaison
    acoustic sequence through align_phonemes/FreePhoneRecognizer. This
    sidesteps D23's actual ambiguity (which unit legitimately "owns" a
    word sitting between two liaison boundaries) rather than resolving it
    -- that remains open, tracked at D23, not by this test-only script.

    Perturbation: delete ONLY the FIRST liaison (les-anciens /z/), keep the
    second (anciens-amis /z/) intact in both native and perturbed audio --
    tests whether a correct liaison immediately after a deleted one still
    gets read correctly (coarticulation/context robustness, D20's
    rationale for chunk-level rather than per-unit analysis).
    """
    les_phonemes, _ = g2p.phonemize("les")
    anciens_phonemes, _ = g2p.phonemize("anciens")
    amis_phonemes, _ = g2p.phonemize("amis")
    consonant1 = get_liaison_consonant("les")
    consonant2 = get_liaison_consonant("anciens")
    assert consonant1 == "z", f"expected liaison consonant z, got {consonant1!r}"
    assert consonant2 == "z", f"expected liaison consonant z, got {consonant2!r}"

    canonical = [
        *les_phonemes, consonant1, *anciens_phonemes, consonant2, *amis_phonemes,
    ]
    unit_les_anciens = "u_les_anciens"
    unit_anciens_amis = "u_anciens_amis"
    unit_ids = (
        [unit_les_anciens] * (len(les_phonemes) + 1 + len(anciens_phonemes))
        + [unit_anciens_amis] * (1 + len(amis_phonemes))
    )
    first_z_index = len(les_phonemes)  # position of the FIRST liaison /z/

    return DiagnosticCase(
        case_id="liaison_deletion_les_anciens_amis_chain",
        sentence_text="les anciens amis",
        canonical_phonemes=canonical,
        unit_ids=unit_ids,
        perturbation_type="deletion",
        target_index=first_z_index,
        injected_phoneme=None,
        perturbation_note=(
            "Genuine liaison chain (D23's own worked example): les|anciens "
            "and anciens|amis are BOTH obligatoire. Deletes only the FIRST "
            "/z/, keeping the second /z/ intact, to test whether a correct "
            "liaison right next to a deleted one is still read correctly. "
            "unit_id assignment is a flagged simplification -- see "
            "docstring, does not resolve D23's own open ambiguity."
        ),
        # Only the les|anciens junction loses its liaison here -- that's
        # the one that becomes two disconnected words needing a pause.
        # anciens|amis keeps its /z/ in both native and perturbed, so it
        # stays connected and gets no boundary (index unchanged from the
        # native position since nothing before it was removed... except
        # the deleted /z/ shifts everything after it left by 1, which is
        # exactly what makes this index equal len(les_phonemes) too).
        perturbed_word_boundary_index=len(les_phonemes),
    )


def _et_amis_insertion_case(g2p: LexiqueEspeakG2P) -> DiagnosticCase:
    """"Et amis" — INTERDITE liaison (after "et", D9/Glossary) -> no liaison.

    Second insertion case, using a DIFFERENT interdite rule (after "et")
    than the existing "un héros" case (h-aspiré) -- Tranche 1
    diversification per the Grok-proposal review.
    """
    et_phonemes, _ = g2p.phonemize("et")
    amis_phonemes, _ = g2p.phonemize("amis")
    # "et" itself ends in a vowel sound and has no liaison-capable final
    # consonant of its own (get_liaison_consonant("et") would return None,
    # same as any vowel-final word) -- but the rule is interdite regardless
    # of what consonant a learner might mistakenly insert. /z/ is used here
    # as the prototypical liaison consonant a learner would default to
    # (the most frequent one, per get_liaison_consonant's s/x/z mapping),
    # not because "et" itself maps to it.
    false_consonant = "z"

    canonical = [*et_phonemes, *amis_phonemes]  # NO liaison in the native form
    unit_ids = ["u_et"] * len(et_phonemes) + ["u_amis"] * len(amis_phonemes)
    insertion_index = len(et_phonemes)

    return DiagnosticCase(
        case_id="liaison_insertion_et_amis",
        sentence_text="et amis",
        canonical_phonemes=canonical,
        unit_ids=unit_ids,
        perturbation_type="insertion",
        target_index=insertion_index,
        injected_phoneme=false_consonant,
        perturbation_note=(
            "Interdite liaison (after 'et', always blocked) between 'et' "
            "and 'amis'; inserting /z/ anyway models a learner wrongly "
            "applying liaison after 'et' -- a DIFFERENT interdite rule "
            "than the existing h-aspiré case (un héros)."
        ),
        native_word_boundary_index=insertion_index,
    )


def _final_consonant_deletion_case(
    g2p: LexiqueEspeakG2P, word: str, note: str
) -> DiagnosticCase:
    """Generic single-word, final-consonant-deletion case (Tranche 2).

    NOT liaison-related -- tests general (non-liaison) deletion robustness,
    in scope per D36's expanded framing (one free-decode model responsible
    for ALL error types, not just liaison). No word_boundary fields: this
    is one word, not two words that could become "disconnected".
    """
    phonemes, _ = g2p.phonemize(word)
    unit_id = f"u_{word}"
    last_index = len(phonemes) - 1

    return DiagnosticCase(
        case_id=f"final_consonant_deletion_{word}",
        sentence_text=word,
        canonical_phonemes=list(phonemes),
        unit_ids=[unit_id] * len(phonemes),
        perturbation_type="deletion",
        target_index=last_index,
        injected_phoneme=None,
        perturbation_note=note,
    )


def _weak_cluster_deletion_case(
    g2p: LexiqueEspeakG2P, word: str, target_index: int, note: str
) -> DiagnosticCase:
    """Generic single-word, internal-consonant-cluster-deletion case (Tranche 2).

    Same rationale as _final_consonant_deletion_case, but the deleted
    phoneme is INSIDE a consonant cluster rather than word-final.
    """
    phonemes, _ = g2p.phonemize(word)
    unit_id = f"u_{word}"

    return DiagnosticCase(
        case_id=f"weak_cluster_deletion_{word}",
        sentence_text=word,
        canonical_phonemes=list(phonemes),
        unit_ids=[unit_id] * len(phonemes),
        perturbation_type="deletion",
        target_index=target_index,
        injected_phoneme=None,
        perturbation_note=note,
    )


def _substitution_generic_case(
    g2p: LexiqueEspeakG2P,
    word: str,
    target_index: int,
    injected_phoneme: str,
    note: str,
) -> DiagnosticCase:
    """Generic single-word substitution case (Tranche 2) -- broader vowel
    coverage than the existing "chat" (consonant) case.
    """
    phonemes, _ = g2p.phonemize(word)
    unit_id = f"u_{word}"

    return DiagnosticCase(
        case_id=f"substitution_{word}",
        sentence_text=word,
        canonical_phonemes=list(phonemes),
        unit_ids=[unit_id] * len(phonemes),
        perturbation_type="substitution",
        target_index=target_index,
        injected_phoneme=injected_phoneme,
        perturbation_note=note,
    )


def build_cases() -> list[DiagnosticCase]:
    """Build the Tranche 1 + Tranche 2 diagnostic case list (module docstring)."""
    g2p = _make_g2p()
    return [
        # Tranche 1 -- liaison-focused (D3/D9's core concern)
        _liaison_deletion_case(g2p),
        _substitution_case(g2p),
        _liaison_insertion_case(g2p),
        _petit_ami_deletion_case(g2p),
        _les_anciens_amis_chain_case(g2p),
        _et_amis_insertion_case(g2p),
        # Tranche 2 -- broader, non-liaison-specific (D36's expanded scope)
        _final_consonant_deletion_case(
            g2p, "table",
            "Final-consonant deletion (non-liaison): 'table' -> 'tab', "
            "deleting the word-final /l/.",
        ),
        _final_consonant_deletion_case(
            g2p, "porte",
            "Final-consonant deletion (non-liaison): 'porte' -> 'pɔʁ', "
            "deleting the word-final /t/.",
        ),
        _weak_cluster_deletion_case(
            g2p, "spectacle", 3,
            "Weak-cluster deletion (non-liaison): 'spectacle' -> 'spɛtakl', "
            "deleting the first /k/ inside the k-t-a-k-l cluster.",
        ),
        _substitution_generic_case(
            g2p, "bonjour", 1, "ɑ̃",
            "Nasal-vowel substitution /ɔ̃/->/ɑ̃/ in 'bonjour' -- a "
            "classic learner confusion pair (Glossary: nasal vowels).",
        ),
        _substitution_generic_case(
            g2p, "lune", 1, "u",
            "Oral-vowel substitution /y/->/u/ in 'lune' -- a well-known "
            "confusable pair for anglophone/many L2 learners.",
        ),
        _substitution_generic_case(
            g2p, "deux", 1, "e",
            "Oral-vowel substitution /ø/->/e/ in 'deux' -- vowel-height "
            "merger, another common learner confusion.",
        ),
    ]


if __name__ == "__main__":
    for case in build_cases():
        print(f"{case.case_id}: {case.canonical_phonemes} ({case.perturbation_type} "
              f"at {case.target_index}, inject={case.injected_phoneme!r})")
        print(f"  unit_ids: {case.unit_ids}")
        print(f"  note: {case.perturbation_note}")