"""G2P (grapheme-to-phoneme): Lexique383 dictionary lookup, eSpeak-ng fallback.

Registered as `register("g2p", "lexique_espeak")` — G2P is a swappable,
data/model-backed stage per Decision Log D12. Implements the G2PProvider
Protocol (core/interfaces.py) structurally (no inheritance needed).

DATA GAP — the real Lexique383 database (lexique.org) isn't reachable from
this environment's network allowlist, so it can't be downloaded and wired
in here. `LexiqueEspeakG2P` loads its dictionary from a `lexicon_path` TSV
file supplied at construction time, in a SIMPLIFIED two-column format
(`word<TAB>phoneme phoneme phoneme...`) — this is NOT the real Lexique383
column layout (which has many columns: lemma, multiple transcription
variants, POS, frequency, etc.). Whoever wires in the real corpus will need
to adapt `_load_lexicon` to that format. Tests use a small hand-written
fixture lexicon (tests/fixtures/g2p_golden.tsv), not the real database.

SYSTEM DEPENDENCY — the eSpeak-ng fallback shells out to the `espeak-ng`
CLI, which must be installed as a system package (e.g. `apt install
espeak-ng`), NOT a pip dependency. Per Codebase Conventions, this should be
documented in `.env.example`/setup docs, not used silently.

Output parsing (`_parse_espeak_ipa`) is derived EMPIRICALLY by probing
`espeak-ng -v fr --ipa=1 -q <word>` output on a range of words (numbers,
nasal vowels, liaison-prone words, apostrophes) — not from a formal spec of
espeak-ng's IPA output, which isn't documented in enough detail anywhere
accessible. Observed behavior: `--ipa=1` separates phonemes with `_`, the
stressed phoneme is prefixed with `ˈ`, and some words emit a leading or
trailing empty token or stray `-` (e.g. "onze" -> `_ˈɔ̃_z`, "les" -> `l_ˈe-`).
Stress marks are stripped here (not just cosmetic — French lexical items
don't carry word-level stress; only the rhythmic-group-final syllable does,
per the glossary's "accent tonique" entry, so a stress mark from eSpeak's
isolated-word synthesis would be actively wrong information at the chunk
level). This parsing should be re-verified if the espeak-ng version changes.
"""

import subprocess
from pathlib import Path

from core.registry import register


def _load_lexicon(lexicon_path: str | Path) -> dict[str, list[str]]:
    """Load a simplified word -> phonemes TSV fixture.

    Format: one entry per line, `word<TAB>phoneme phoneme phoneme...`.
    NOT the real Lexique383 column layout — see module docstring.
    """
    lexicon: dict[str, list[str]] = {}
    with open(lexicon_path, encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 2:
                raise ValueError(
                    f"{lexicon_path}:{line_number}: expected "
                    f"'word<TAB>phonemes', got: {line!r}"
                )
            word, phonemes_str = parts
            lexicon[word.lower()] = phonemes_str.split()
    return lexicon


def _parse_espeak_ipa(raw_output: str) -> list[str]:
    """Parse `espeak-ng --ipa=1` output into a list of individual phonemes.

    Empirically derived — see module docstring. Strips stress marks (ˈ, ˌ)
    and stray liaison-hint hyphens; drops empty tokens from leading/
    trailing separators.
    """
    phonemes = []
    for token in raw_output.strip().split("_"):
        token = token.strip("-")
        token = token.lstrip("ˈˌ")
        if token:
            phonemes.append(token)
    return phonemes


@register("g2p", "lexique_espeak")
class LexiqueEspeakG2P:
    """G2PProvider implementation: Lexique383 lookup, eSpeak-ng fallback.

    Per Codebase Conventions: `phonemize()` never raises for a word not
    found in the dictionary — it falls back to eSpeak-ng and returns
    `source="espeak"` so the caller can decide how much to trust it.
    """

    def __init__(self, lexicon_path: str | Path):
        self._lexicon = _load_lexicon(lexicon_path)

    def phonemize(self, word: str) -> tuple[list[str], str]:
        key = word.lower()
        if key in self._lexicon:
            return self._lexicon[key], "dict"
        return self._phonemize_with_espeak(word), "espeak"

    @staticmethod
    def _phonemize_with_espeak(word: str) -> list[str]:
        result = subprocess.run(
            ["espeak-ng", "-v", "fr", "--ipa=1", "-q", word],
            capture_output=True,
            text=True,
            check=True,
        )
        return _parse_espeak_ipa(result.stdout)
