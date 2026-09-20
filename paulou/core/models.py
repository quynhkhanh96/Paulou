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
    folded into a neighboring phoneme). Originally needed for stage 5a-2
    (Decision Log D20, count-based phoneme-to-unit grouping) — D20 itself
    is obsolete under D36 (insertions/deletions break count-based grouping),
    but this field is still useful as the source sequence that gets
    concatenated across a chunk's units to build the canonical phoneme
    string for alignment (see AlignmentOp below).

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


# --- Obsolete per Decision Log D36 (single free-decode + 3-way alignment
# pipeline replaces the two-branch GOP/free-decode design). Kept dormant,
# not deleted: `core/interfaces.py`'s GOPScorer Protocol still imports
# RawPhoneScore, and UnitResult.phone_scores still references PhoneScore —
# both need a coordinated edit (GOPScorer Protocol removal, UnitResult
# redesign) that hasn't happened yet. Do not use these in new code;
# AlignmentOp below is the replacement. ---


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


AlignmentOpType = Literal["match", "substitution", "insertion", "deletion"]


@dataclass(frozen=True)
class AlignmentOp:
    """One operation from 3-way (substitution + insertion + deletion)
    alignment between a chunk's canonical phonemes and the free-phone-
    recognizer's decoded output for the same audio span.

    Replaces RawPhoneScore/PhoneScore for Speech Assessment (Decision Log
    D36). Produced by the alignment pure function (Architecture Spec stage
    5c, redesigned) from two flat sequences: canonical phonemes
    (concatenated across a chunk's PronunciationUnits, in order) and the
    FreePhoneRecognizer's decoded phoneme sequence.

    unit_id attribution: match/substitution/deletion attach to the unit
    that owns the canonical phoneme in question (tracked via a parallel
    unit_id array built alongside the canonical phoneme sequence, indexed
    the same way — no separate grouping step needed, unlike D20's
    count-based approach, which breaks once insertions/deletions can shift
    the two sequences out of length-parity). insertion (no canonical
    counterpart) attaches to the PRECEDING unit by convention, not the
    nearest one in time — the goal is surfacing "you added an extra sound
    here," not pinpointing exactly which word it belongs to. An insertion
    with no preceding canonical phoneme (start of the very first unit)
    attaches to that first unit instead.

    start_ms/end_ms require `FreePhoneRecognizer.decode()` to expose
    per-decoded-phone time boundaries — not yet in the Architecture Spec's
    stage 5b signature (`tuple[list[str], list[list[float]]]`); the
    Protocol needs extending to a 3-tuple (phones, posteriors, boundaries)
    before a real implementation is built. No implementation exists yet,
    so this is a free edit, not a breaking change.
    """

    op_type: AlignmentOpType
    unit_id: str
    canonical_phoneme: str | None  # None only for "insertion"
    decoded_phoneme: str | None  # None only for "deletion"
    confidence: float | None  # decoder's posterior for decoded_phoneme;
    # None only for "deletion" (no decoded frame exists)
    start_ms: int | None  # None only for "deletion"
    end_ms: int | None  # None only for "deletion"


@dataclass(frozen=True)
class ScoredAlignmentOp:
    """One AlignmentOp paired with its computed 0-100 accuracy_score.

    Kept separate from AlignmentOp itself (same D34-style separation
    reapplied per D36): AlignmentOp is the structural alignment event;
    accuracy_score is a policy computation over it
    (stages/speech_assessment/scoring.py::score_alignment_op). Built by the
    merge layer (stages/speech_assessment/merge.py), not by alignment or
    scoring themselves — neither of those needs to know the other exists.
    """

    op: AlignmentOp
    accuracy_score: int


@dataclass(frozen=True)
class UnitResult:
    """Scoring result for one PronunciationUnit.

    REPLACED per Decision Log D36: `phone_scores: list[PhoneScore] | None`
    (GOP-based, Branch 1) is replaced by `scored_ops: list[ScoredAlignmentOp]`
    — every unit type is scored the same way now (no more `single` vs
    `liaison_group` asymmetry, no more D19/D32's "low-confidence caveat"
    for liaison_group, since there's only one mechanism for everyone).
    Built by stages/speech_assessment/merge.py::merge_to_unit_result, which
    also aggregates `calibrated_score` as the MEAN of each op's
    accuracy_score (Decision Log D33's choice, carried over unchanged).

    `feedback_text` is not yet populated by anything real — feedback
    templating (Architecture Spec stage 5f) hasn't been redesigned since
    D36 deleted the old feedback.py. See merge.py's module docstring.
    """

    unit_id: str
    calibrated_score: int
    scored_ops: list[ScoredAlignmentOp]
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