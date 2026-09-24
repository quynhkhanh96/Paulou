"""Convert Lexique400-style phoneme units into Piper's phoneme-id input shape.

Per Decision Log D43: Lexique400 (`LexiqueEspeakG2P._segment_ipa`, D30)
groups a base IPA character with any trailing Unicode combining marks into
ONE phoneme (e.g. "ɛ̃" is one phoneme). Piper's `phoneme_ids.py` (installed
package, read directly — not assumed) keys each NFD codepoint SEPARATELY
(the combining tilde "̃" has its own id, distinct from base vowels). This
module does the mechanical NFD decomposition to go from one shape to the
other — NOT a hand-built symbol mapping table (see D43's rationale for why
this is simpler than the espeak-ng CLI mnemonic-code route that was
rejected).

Word-boundary spaces: Piper's own phonemizer inserts " " (id [3] in
DEFAULT_PHONEME_ID_MAP) between words. Our cases are built per-sentence as
a single flat phoneme list with no word-boundary markers (liaison_group
phonemes are meant to be pronounced with no gap, per D35), so this module
takes an explicit `word_boundary_indices` set instead of guessing word
boundaries from the phoneme list itself.
"""

import unicodedata


def to_piper_phonemes(
    phonemes: list[str],
    word_boundary_before: set[int] | None = None,
) -> list[str]:
    """Decompose each phoneme into Piper-compatible individual codepoints.

    :param phonemes: Lexique400-style phoneme list (combining marks grouped
        with their base character, e.g. "ɛ̃" as one entry).
    :param word_boundary_before: Indices (into `phonemes`) before which a
        literal " " should be inserted — i.e. index 2 means a space goes
        between phonemes[1] and phonemes[2]. Omit for a single-word case.
    :return: Flat list of individual codepoints/spaces, in Piper's own
        phoneme-id-map vocabulary (verify against a specific voice's
        `config.json` before assuming full coverage — see D43 Tradeoffs).
    """
    word_boundary_before = word_boundary_before or set()
    piper_phonemes: list[str] = []

    for i, phoneme in enumerate(phonemes):
        if i in word_boundary_before:
            piper_phonemes.append(" ")
        # NFD: split a base character from any combining diacritics it
        # carries (e.g. "ɛ̃" -> "ɛ", "̃") into separate list entries.
        piper_phonemes.extend(unicodedata.normalize("NFD", phoneme))

    return piper_phonemes


if __name__ == "__main__":
    # Sanity-check against Piper's real DEFAULT_PHONEME_ID_MAP (installed
    # package) rather than assuming every symbol is covered.
    from piper.phoneme_ids import DEFAULT_PHONEME_ID_MAP

    from experiments.diagnostic_set.cases import build_cases
    from experiments.diagnostic_set.perturbation import apply_perturbation

    for case in build_cases():
        for label, phonemes in [
            ("native", case.canonical_phonemes),
            ("perturbed", apply_perturbation(case)),
        ]:
            piper_phonemes = to_piper_phonemes(phonemes)
            missing = [p for p in piper_phonemes if p not in DEFAULT_PHONEME_ID_MAP]
            status = "OK" if not missing else f"MISSING FROM MAP: {missing}"
            print(f"{case.case_id} [{label}]: {piper_phonemes}  -> {status}")
