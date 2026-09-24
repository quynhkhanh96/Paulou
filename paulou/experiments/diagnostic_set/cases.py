"""Diagnostic case definitions for the D10 canonicalizer-bias check (D43).

Each `DiagnosticCase` describes ONE native sentence plus the single
controlled perturbation applied to it (deletion / insertion / substitution).
`canonical_phonemes` and `unit_ids` are built by reusing the REAL, already-
implemented G2P provider (`LexiqueEspeakG2P`) and liaison consonant mapping
(`get_liaison_consonant`) rather than hand-typing IPA strings — the fixture
lexicon (`tests/fixtures/g2p_golden.tsv`) is small and already
hand-verified, so word-level phonemes come from there rather than from a
guess. Words not in that fixture (only "héros", for the interdite/insertion
case) are grounded here the same way the codebase's own eSpeak-ng fallback
would produce them (`espeak-ng -v fr --ipa=1 -q héros` -> e/ʁ/o, stress
stripped) rather than typed from memory — see the `_EXTRA_WORDS` comment
below.

Per Decision Log D43, this module belongs to `experiments/diagnostic_set/`,
not `stages/` — it is diagnostic tooling for validating Speech Assessment
(stage 5), not a pipeline stage itself, and produces no `register()`ed
implementation.

Per D3/D38's PronunciationUnit model: a liaison_group's phonemes ALL share
one `unit_id` (the group is scored as one unit), matching the parallel
`unit_ids` array shape that `align_phonemes` (stage 5c') expects.

NOT YET COVERED (flagged, not an oversight): weighting deliberately favors
deletion for the liaison case, per the SLA-literature discussion in D43
(omission is the dominant real liaison error type, not substitution).
Additional cases (more liaison-deletion sentences, a facultative-boundary
case) are expected to be added once Piper is verified locally — this file
is a starting set, not the final one.
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
    )


def build_cases() -> list[DiagnosticCase]:
    """Build the starter diagnostic case list (see module docstring)."""
    g2p = _make_g2p()
    return [
        _liaison_deletion_case(g2p),
        _substitution_case(g2p),
        _liaison_insertion_case(g2p),
    ]


if __name__ == "__main__":
    for case in build_cases():
        print(f"{case.case_id}: {case.canonical_phonemes} ({case.perturbation_type} "
              f"at {case.target_index}, inject={case.injected_phoneme!r})")
        print(f"  unit_ids: {case.unit_ids}")
        print(f"  note: {case.perturbation_note}")
