"""G2P (grapheme-to-phoneme): Lexique dictionary lookup, eSpeak-ng fallback.

Registered as `register("g2p", "lexique_espeak")` — G2P is a swappable,
data/model-backed stage per Decision Log D12. Implements the G2PProvider
Protocol (core/interfaces.py) structurally (no inheritance needed).

REAL DATA (Decision Log D30): uses Lexique400 (lexique.org), not
Lexique383 as originally named in the Architecture Spec — Lexique400 is a
"major upgrade" per its 2026 publication (New et al.), and provides real
IPA transcriptions directly (column `3_Phono_IPA`), unlike the ASCII
phonetic code Lexique383 used. The 33MB TSV file is NOT committed to the
repo (see `.gitignore`) — expected at `paulou/data/Lexique400.tsv`,
downloaded separately by whoever runs this. `LexiqueEspeakG2P.from_lexique400`
loads it; the plain `__init__(lexicon_path)` path still loads the
SIMPLIFIED two-column fixture format (`word<TAB>phoneme phoneme...`) used
by tests/fixtures/g2p_golden.tsv, kept for fast, hand-verified unit tests
that shouldn't depend on the real 170k-word file.

Lexique400 phoneme segmentation (`_segment_ipa`): groups each base IPA
character in `3_Phono_IPA` with any following Unicode combining marks
(e.g. combining tilde U+0303 for nasal vowels) into one phoneme unit.
EMPIRICALLY VERIFIED against Lexique400's own ASCII phonetic column
(`2_Phono`, a reliable one-ASCII-character-per-phoneme encoding): 0
mismatches in phoneme count across all 189,863 rows of the real file.

KNOWN LIMITATION (Lexique400 data, not a code bug): ~719 words (0.4%)
have more than one distinct pronunciation across different entries in the
file (sampled cases were minor phonetic variants — schwa presence, vowel
openness — not meaning-changing heteronyms, e.g. "maintenant"). Loading
keeps whichever pronunciation appears LAST for such words; no
disambiguation by grammatical category, frequency, or context is
attempted.

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

import csv
import subprocess
import unicodedata
from pathlib import Path

from core.registry import register


def _load_lexicon(lexicon_path: str | Path) -> dict[str, list[str]]:
    """Load a simplified word -> phonemes TSV fixture.

    Format: one entry per line, `word<TAB>phoneme phoneme phoneme...`.
    Used only for the small hand-written test fixture — see
    `from_lexique400` for the real Lexique400 loader.
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


def _segment_ipa(ipa: str) -> list[str]:
    """Group each base IPA character with any trailing combining marks.

    E.g. "ɛ̃" (U+025B + combining tilde U+0303) becomes one phoneme, not
    two. See module docstring — empirically verified against Lexique400's
    own ASCII phonetic column across all 189,863 rows (0 mismatches).
    """
    phonemes: list[str] = []
    for ch in ipa:
        if unicodedata.combining(ch) and phonemes:
            phonemes[-1] += ch
        else:
            phonemes.append(ch)
    return phonemes


def _load_lexique400(lexicon_path: str | Path) -> dict[str, list[str]]:
    """Load the real Lexique400 database (37-column TSV, tab-separated).

    Uses columns `1_Mot` (word) and `3_Phono_IPA` (IPA transcription). See
    module docstring for the phoneme segmentation approach and the
    known ~719-word multiple-pronunciation limitation (last-wins policy).
    """
    lexicon: dict[str, list[str]] = {}
    with open(lexicon_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            ipa = row["3_Phono_IPA"]
            if not ipa:
                continue
            lexicon[row["1_Mot"].lower()] = _segment_ipa(ipa)
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
    """G2PProvider implementation: Lexique lookup, eSpeak-ng fallback.

    Per Codebase Conventions: `phonemize()` never raises for a word not
    found in the dictionary — it falls back to eSpeak-ng and returns
    `source="espeak"` so the caller can decide how much to trust it.
    """

    def __init__(
        self,
        lexicon_path: str | Path | None = None,
        *,
        lexicon: dict[str, list[str]] | None = None,
    ):
        if lexicon is not None:
            self._lexicon = lexicon
        elif lexicon_path is not None:
            self._lexicon = _load_lexicon(lexicon_path)
        else:
            raise ValueError("Must provide either lexicon_path or lexicon.")

    @classmethod
    def from_lexique400(cls, lexicon_path: str | Path) -> "LexiqueEspeakG2P":
        """Build an instance backed by the real Lexique400 database."""
        return cls(lexicon=_load_lexique400(lexicon_path))

    def phonemize(self, word: str) -> tuple[list[str], str]:
        key = word.lower()
        if key in self._lexicon:
            return self._lexicon[key], "dict"
        return self._phonemize_with_espeak(word), "espeak"

    @staticmethod
    def _phonemize_with_espeak(word: str) -> list[str]:
        try:
            result = subprocess.run(
                ["espeak-ng", "-v", "fr", "--ipa=1", "-q", word],
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "espeak-ng executable not found on PATH. It's a system "
                "package, not a pip dependency — see SETUP.md. On Windows: "
                "download an installer from "
                "https://github.com/espeak-ng/espeak-ng/releases and make "
                "sure the folder containing espeak-ng.exe is added to PATH."
            ) from exc
        return _parse_espeak_ipa(result.stdout)