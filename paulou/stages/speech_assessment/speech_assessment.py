"""Speech Assessment orchestration (Architecture Spec stage 5).

Composes the stage's sub-steps into one function, analogous to
stages/chunk_analyzer/chunk_analyzer.py for stage 2. Not itself Protocol/
registered (Decision Log D12) — glue/composition code, like `analyze_chunk`.

Flow:
    audio + units
      -> build canonical_phonemes by concatenating each unit's `.phonemes`,
         in order, WITH an optional-silence marker (SIL_PHONE) inserted
         BETWEEN units — see "OPTIONAL SILENCE" below. One GOP call for
         the whole chunk (per D20 — NOT one call per unit, to preserve
         coarticulation context).
      -> gop_scorer.score(audio, canonical_phonemes) -> list[RawPhoneScore]
         (UNCALIBRATED — see Decision Log D34)
      -> strip out the SIL_PHONE entries from the result
      -> calibrate_score() on each remaining entry -> list[PhoneScore]
      -> group_phone_scores_by_unit() (5a-2, D20) -> per-unit PhoneScores
      -> merge_to_unit_result() (5e, D33 — MEAN aggregation) -> UnitResult
         per unit

OPTIONAL SILENCE (Decision Log D35) — found during review, not in the
Architecture Spec: without a silence marker between units, a real forced
aligner has no way to account for any pause/breath a LEARNER (not a
native speaker) might take between words — it would be forced to fold
that silence into the timing/scoring of whichever real phone is adjacent,
corrupting both. `SIL_PHONE = "SIL"` is inserted between every pair of
adjacent units (NOT within a liaison_group/elision_group's own merged
phonemes — those are specifically meant to be pronounced with no gap, so
inserting SIL there would work against the very thing being taught).

CRITICAL CAVEAT, genuinely unverified: inserting the literal string "SIL"
into canonical_phonemes only WORKS if the GOPScorer implementation itself
specifically treats a phone named "SIL" as OPTIONAL (zero-duration
allowed) during alignment — this is normally a property of the alignment
FST/lexicon construction (e.g. Kaldi's optional-silence handling), not
something a plain "align this reference sequence, every phone mandatory"
implementation gets for free just because one of the strings happens to
be "SIL". Whether a real GOPScorer implementation (Stage B: Kaldi/gop-ft)
actually honors this is NOT verified here — a simulated stub has no real
alignment behavior to get wrong. This is a contract/convention this
function establishes for any real GOPScorer to honor, not something
proven correct yet. Also unverified: whether "SIL" (this exact casing) is
the token the actual `fr_kaldi-rhasspy` acoustic model's phone set uses —
must be confirmed against that model's real phone symbol table before
Stage B is wired in.
"""

from core.interfaces import GOPScorer
from core.models import PhoneScore, PronunciationUnit, RawPhoneScore, UnitResult
from stages.speech_assessment.calibration import (
    DEFAULT_MIN_SAMPLE_SIZE,
    PhoneStats,
    calibrate_score,
)
from stages.speech_assessment.merge import merge_to_unit_result
from stages.speech_assessment.phoneme_grouping import group_phone_scores_by_unit

SIL_PHONE = "SIL"


def _build_canonical_phonemes_with_sil(units: list[PronunciationUnit]) -> list[str]:
    """Concatenate units' phonemes, with SIL_PHONE between adjacent units
    (not within a unit's own merged phonemes — see module docstring).
    """
    canonical_phonemes: list[str] = []
    for i, unit in enumerate(units):
        if i > 0:
            canonical_phonemes.append(SIL_PHONE)
        canonical_phonemes.extend(unit.phonemes)
    return canonical_phonemes


def score_chunk(
    audio: bytes,
    units: list[PronunciationUnit],
    gop_scorer: GOPScorer,
    phone_stats: dict[str, PhoneStats],
    fallback_phone_class: dict[str, str] | None = None,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> list[UnitResult]:
    """Score every PronunciationUnit in a chunk against one audio recording.

    `phone_stats`/`fallback_phone_class`/`min_sample_size` are forwarded
    straight to `calibrate_score` for each phone — see calibration.py for
    what these mean (no real corpus-derived stats exist yet, D11/D24).

    Raises ValueError if `gop_scorer` returns a different number of scores
    than canonical phonemes (including SIL) were requested for.
    """
    if not units:
        return []

    canonical_phonemes = _build_canonical_phonemes_with_sil(units)

    raw_scores = gop_scorer.score(audio, canonical_phonemes)
    if len(raw_scores) != len(canonical_phonemes):
        raise ValueError(
            f"GOPScorer returned {len(raw_scores)} scores for "
            f"{len(canonical_phonemes)} canonical phonemes (incl. SIL)."
        )

    real_scores: list[RawPhoneScore] = [r for r in raw_scores if r.phone != SIL_PHONE]

    phone_scores = [
        PhoneScore(
            phone=r.phone,
            raw_gop=r.raw_gop,
            calibrated_score=calibrate_score(
                r.raw_gop, r.phone, phone_stats, fallback_phone_class, min_sample_size
            ),
            start_ms=r.start_ms,
            end_ms=r.end_ms,
        )
        for r in real_scores
    ]

    grouped = group_phone_scores_by_unit(phone_scores, units)

    return [merge_to_unit_result(unit.id, grouped[unit.id]) for unit in units]