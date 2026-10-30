"""Core models -> API schemas. Pure functions, no I/O (Decision Log D14)."""

import hashlib
import re
import unicodedata

from backend.api.schemas import (
    AttemptResponse,
    ChunkDTO,
    OpDTO,
    OpKind,
    SentenceResponse,
    UnitDTO,
    UnitResultDTO,
)
from core.models import AlignmentOp, PronunciationUnit, Sentence, UnitResult
from stages.speech_assessment.phone_similarity import near_reasons


def normalize_text(text: str) -> str:
    """NFC, whitespace collapsed, ends stripped. The result is what gets
    analyzed, so the same sentence typed with different spacing shares one
    parse-cache entry and one sentence id."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def sentence_id_for(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]


def to_unit_dto(unit: PronunciationUnit) -> UnitDTO:
    return UnitDTO(
        id=unit.id,
        type=unit.type,
        words=list(unit.words),
        phonemes=list(unit.phonemes),
        ipa=unit.ipa,
        liaison_consonant=unit.liaison_consonant,
        scoring_focus=unit.scoring_focus,
    )


def to_sentence_response(sentence_id: str, sentence: Sentence) -> SentenceResponse:
    return SentenceResponse(
        sentence_id=sentence_id,
        text=sentence.text,
        chunks=[
            ChunkDTO(index=i, text=chunk.text, units=[to_unit_dto(u) for u in chunk.units])
            for i, chunk in enumerate(sentence.chunks)
        ],
    )


def classify_op(op: AlignmentOp) -> tuple[OpKind, list[str]]:
    """(kind, near reason codes). Near/far is decided by `phone_similarity` (D64)."""
    if op.op_type == "match":
        return "M", []
    if op.op_type == "deletion":
        return "D", []
    if op.op_type == "insertion":
        return "I", []
    reasons = near_reasons(op.canonical_phoneme, op.decoded_phoneme)
    return ("S", []) if reasons is None else ("S_near", reasons)


def to_op_dto(scored, calibrated: bool) -> OpDTO:
    op = scored.op
    kind, reasons = classify_op(op)
    return OpDTO(
        op_type=op.op_type,
        kind=kind,
        near_reasons=reasons,
        canonical_phoneme=op.canonical_phoneme,
        decoded_phoneme=op.decoded_phoneme,
        start_ms=op.start_ms,
        end_ms=op.end_ms,
        score=scored.accuracy_score if calibrated else None,
    )


def to_unit_result_dto(result: UnitResult, calibrated: bool) -> UnitResultDTO:
    return UnitResultDTO(
        unit_id=result.unit_id,
        score=result.calibrated_score if calibrated else None,
        feedback_text=result.feedback_text,
        ops=[to_op_dto(scored, calibrated) for scored in result.scored_ops],
    )


def to_attempt_response(
    sentence_id: str,
    chunk_index: int | None,
    unit_id: str | None,
    results: list[UnitResult],
    calibrated: bool,
    whole_sentence: bool = False,
) -> AttemptResponse:
    return AttemptResponse(
        sentence_id=sentence_id,
        chunk_index=chunk_index,
        unit_id=unit_id,
        whole_sentence=whole_sentence,
        calibrated=calibrated,
        results=[to_unit_result_dto(r, calibrated) for r in results],
    )
