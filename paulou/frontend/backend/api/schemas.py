"""API request/response schemas (Decision Log D14).

Separate from `core/models.py` on purpose: the API contract with the
frontend must not change when core models evolve, and responses must not
leak internal detail. What is NOT exposed: decoder confidence values and
the unit-level / op-level scores while the calibration table is a
placeholder (D24, D50, D53) -- `score` fields exist but are None until a
real `phone_stats` file is loaded, so the frontend needs no change then.
"""

from typing import Literal

from pydantic import BaseModel, Field

UnitType = Literal["single", "liaison_group", "elision_group"]
OpType = Literal["match", "substitution", "insertion", "deletion"]


class SentenceRequest(BaseModel):
    text: str = Field(min_length=1)


class UnitDTO(BaseModel):
    id: str
    type: UnitType
    words: list[str]
    phonemes: list[str]
    ipa: str
    liaison_consonant: str | None
    scoring_focus: str


class ChunkDTO(BaseModel):
    index: int
    text: str
    units: list[UnitDTO]


class SentenceResponse(BaseModel):
    sentence_id: str
    text: str
    chunks: list[ChunkDTO]


class OpDTO(BaseModel):
    op_type: OpType
    canonical_phoneme: str | None
    decoded_phoneme: str | None
    start_ms: int | None
    end_ms: int | None
    score: int | None  # None until calibration stats are real


class UnitResultDTO(BaseModel):
    unit_id: str
    score: int | None  # None until calibration stats are real
    feedback_text: str
    ops: list[OpDTO]  # canonical order; insertions sit between the ops they follow


class AttemptResponse(BaseModel):
    sentence_id: str
    chunk_index: int | None
    unit_id: str | None
    calibrated: bool
    results: list[UnitResultDTO]


class HealthResponse(BaseModel):
    status: Literal["warming_up", "ready", "error"]
    calibrated: bool
    detail: str | None = None


class ApiErrorBody(BaseModel):
    code: str
    message: str
