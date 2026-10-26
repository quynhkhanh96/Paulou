"""Core models -> API schemas. Pure functions, no I/O (Decision Log D14)."""

import hashlib
import re
import unicodedata

from backend.api.schemas import (
    AttemptResponse,
    ChunkDTO,
    OpDTO,
    SentenceResponse,
    UnitDTO,
    UnitResultDTO,
)
from core.models import PronunciationUnit, Sentence, UnitResult


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


def to_unit_result_dto(result: UnitResult, calibrated: bool) -> UnitResultDTO:
    return UnitResultDTO(
        unit_id=result.unit_id,
        score=result.calibrated_score if calibrated else None,
        feedback_text=result.feedback_text,
        ops=[
            OpDTO(
                op_type=scored.op.op_type,
                canonical_phoneme=scored.op.canonical_phoneme,
                decoded_phoneme=scored.op.decoded_phoneme,
                start_ms=scored.op.start_ms,
                end_ms=scored.op.end_ms,
                score=scored.accuracy_score if calibrated else None,
            )
            for scored in result.scored_ops
        ],
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
