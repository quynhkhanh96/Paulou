"""Core data models for the Paulou pipeline.

No ORM or web-framework inheritance here (Decision Log D14) — these must be
importable and usable with zero DB connection, zero API framework.

Models are added incrementally as the pipeline stages that need them are
implemented (per the build order in the Roadmap), not all at once up front.
"""

from dataclasses import dataclass
from typing import Literal

LiaisonRuleType = Literal["obligatoire", "interdite", "facultative"]

# s/x/z -> /z/, t/d -> /t/, n -> /n/, r -> /ʁ/ (rare), p -> /p/ (rare),
# f -> /v/ (rare, irregular) — see Architecture Spec, stage 2c.
LiaisonConsonant = Literal["z", "t", "n", "ʁ", "p", "v"]


@dataclass(frozen=True)
class LiaisonDecision:
    """Result of evaluating whether liaison applies between two adjacent words.

    See Architecture Spec, Data model section, and Decision Log D3/D4.
    """

    between: tuple[str, str]
    applies: bool
    consonant: LiaisonConsonant | None
    rule_type: LiaisonRuleType


PronunciationUnitType = Literal["single", "liaison_group", "elision_group"]
ScoringFocus = Literal[
    "phoneme_accuracy",
    "liaison_presence_and_continuity",
    "elision_correctness",
]


@dataclass(frozen=True)
class PronunciationUnit:
    """The atomic unit of practice and scoring in Paulou.

    See Architecture Spec, Data model section, and Decision Log D3. Extended
    with `type="elision_group"` beyond what the Architecture Spec originally
    specced — elision (see stages/chunk_analyzer/elision/elision.py) is a distinct
    phenomenon from liaison, added when the gap was noticed during Chunk
    Analyzer implementation. `liaison_consonant` is None for elision_group
    (no consonant is added in elision — see elision.py).

    ALSO EXTENDED (not in the Architecture Spec's original field list):
    `phonemes: list[str]` — the unit's actual phoneme sequence (for
    liaison_group, includes the liaison consonant as its own element, not
    folded into a neighboring phoneme). Needed for stage 5a-2 (phoneme-to-
    unit grouping, Decision Log D20) to know how many phone_scores from a
    flat per-chunk GOP call belong to this unit — recovering that count
    from `ipa` alone isn't reliable, since multi-codepoint phonemes (e.g.
    nasal vowels) make character-counting ambiguous. `ipa` is derived from
    `phonemes` (`"".join(phonemes)`), so the two can never drift apart.

    NOTE (gap, not yet specced anywhere): `syllables` and `note` have no
    owning stage in the Architecture Spec — no syllabifier, no pedagogical
    note generator. Left as empty placeholders (`[]`, `""`) by
    stages/chunk_analyzer/assembly/unit_assembler.py until that's designed.
    """

    id: str
    type: PronunciationUnitType
    words: list[str]
    phonemes: list[str]
    ipa: str
    syllables: list[str]
    liaison_consonant: LiaisonConsonant | None
    note: str
    scoring_focus: ScoringFocus


@dataclass(frozen=True)
class RawPhoneScore:
    """Per-phone GOP score, NOT yet calibrated (Decision Log D34).

    Architecture Spec stage 5a originally has `GOPScorer.score()` return
    `list[PhoneScore]` directly (calibrated_score included). Per D12 (GOP-
    scorer implementations shouldn't call calibration's pure-function
    logic themselves — the same reasoning D25 already applied to feedback
    templating), `GOPScorer.score()` returns this uncalibrated type
    instead; an orchestration layer (stages/speech_assessment/
    speech_assessment.py) calls `calibrate_score` on each entry to build
    real `PhoneScore`s. Same fields as `PhoneScore` minus
    `calibrated_score`.
    """

    phone: str
    raw_gop: float
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class PhoneScore:
    """Per-phone GOP score, calibrated to a 0-100 scale.

    See Architecture Spec, Data model section, and Decision Log D11 (why
    calibration is unsupervised percentile/z-score, not a regressor) and
    D20 (why start_ms/end_ms exist — grouping a flat per-sentence/chunk GOP
    call's output back onto individual PronunciationUnits).
    """

    phone: str
    raw_gop: float
    calibrated_score: int
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class UnitResult:
    """Scoring result for one PronunciationUnit.

    NOTE (Decision Log D19, D32): `alignment_ops` (Branch 2 output,
    DEL/INS/match) is intentionally omitted here — the AlignmentOp schema
    isn't designed yet, and MVP excludes Branch 2 entirely. `phone_scores`
    (Branch 1 / GOP) IS populated for `liaison_group` units too, not just
    `single` — D19's second option ("raw GOP shown with an explicit
    low-confidence caveat"), not its first ("no auto-score shown"). GOP can
    still score individual phones within a liaison_group's combined
    sequence for substitution-style accuracy; it just can't reliably
    confirm the liaison sound wasn't entirely missing or added
    (insertion/deletion, Branch 2's job). This module has no way to
    express that caveat itself — attaching a "may be unreliable for
    liaison" note in the UI is the caller's responsibility, using
    `PronunciationUnit.type`.
    """

    unit_id: str
    calibrated_score: int
    phone_scores: list[PhoneScore] | None
    feedback_text: str


@dataclass(frozen=True)
class WordTiming:
    """Word-boundary timestamp from TTS synthesis.

    See Architecture Spec, Data model section, and Decision Log D5 (why
    synthesis is sentence-level, sliced afterward via these timestamps).
    """

    word: str
    start_ms: int
    end_ms: int