"""POST /sentences (prepare) and GET /sentences/{id}/audio (reference clips).

Preparation is synchronous and slow (analyze ~2.6-13 s + one TTS pass
~1 s, D52); the frontend shows a loading state. The normal-speed pass is
made eagerly, because `locate_spans` (strict, D48) fails on text the TTS
spells differently (e.g. digits) and that must surface at submit time. The
slow pass (rate 0.7, D6) is made on first request and kept.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from backend.api.dependencies import AppState, api_error, get_state
from backend.api.mappers import normalize_text, sentence_id_for, to_sentence_response
from backend.api.schemas import SentenceRequest, SentenceResponse
from backend.api.store import PreparedSentence

logger = logging.getLogger("paulou.api")
router = APIRouter()

Speed = Literal["normal", "slow"]


def _prepare(state: AppState, text: str) -> PreparedSentence:
    pipeline = state.pipeline
    try:
        sentence = pipeline.analyze_sentence(text)
    except Exception:
        logger.exception("analyze_sentence failed")
        raise api_error(
            502,
            "preparation_failed",
            "Could not analyze the sentence. Check the server log (parser API key, "
            "network, Lexique400 file).",
        )
    if not sentence.chunks:
        raise api_error(422, "no_content", "There is nothing to practice in this text.")

    try:
        reference = pipeline.synthesize_reference(sentence, rate=1.0)
    except ValueError:
        # locate_spans: the TTS service spelled something differently (D48)
        logger.exception("reference audio does not match the text")
        raise api_error(
            422,
            "text_not_supported",
            "The voice reads part of this text differently from how it is written "
            "(numbers, symbols and abbreviations are the usual cause). Write them out as words.",
        )
    except Exception:
        logger.exception("synthesize_reference failed")
        raise api_error(
            502,
            "preparation_failed",
            "Could not generate the reference audio. Check the network connection and the server log.",
        )
    return PreparedSentence(sentence=sentence, references={"normal": reference})


@router.post("/sentences", response_model=SentenceResponse)
def create_sentence(body: SentenceRequest, state: AppState = Depends(get_state)) -> SentenceResponse:
    text = normalize_text(body.text)
    if not text:
        raise api_error(422, "empty_text", "Type a sentence first.")
    if len(text) > state.settings.max_text_chars:
        raise api_error(
            422,
            "text_too_long",
            f"Please keep it under {state.settings.max_text_chars} characters.",
        )
    sentence_id = sentence_id_for(text)
    prepared = state.store.get_or_create(sentence_id, lambda: _prepare(state, text))
    return to_sentence_response(sentence_id, prepared.sentence)


@router.get("/sentences/{sentence_id}/audio")
def get_audio(
    sentence_id: str,
    speed: Speed = "normal",
    chunk: int | None = Query(default=None, ge=0),
    unit: str | None = None,
    state: AppState = Depends(get_state),
) -> Response:
    """Whole sentence by default; `chunk=N` or `unit=ID` (not both) for a clip."""
    if chunk is not None and unit is not None:
        raise api_error(422, "invalid_target", "Pass either chunk or unit, not both.")
    prepared = state.store.get(sentence_id)
    if prepared is None:
        raise api_error(404, "sentence_not_found", "This sentence is no longer prepared. Prepare it again.")

    pipeline = state.pipeline

    def make_reference():
        try:
            return pipeline.synthesize_reference(
                prepared.sentence, rate=1.0 if speed == "normal" else state.settings.slow_rate
            )
        except Exception:
            logger.exception("synthesize_reference (%s) failed", speed)
            raise api_error(502, "preparation_failed", "Could not generate the audio.")

    reference = prepared.reference(speed, make_reference)

    if chunk is not None:
        if chunk >= len(reference.chunk_spans):
            raise api_error(404, "chunk_not_found", "No such chunk.")
        span, key = reference.chunk_spans[chunk], (speed, "chunk", chunk)
    elif unit is not None:
        if unit not in reference.unit_spans:
            raise api_error(404, "unit_not_found", "No such unit.")
        span, key = reference.unit_spans[unit], (speed, "unit", unit)
    else:
        return _audio_response(reference.audio)

    data = prepared.clip(key, lambda: pipeline.slice_reference(reference, span))
    return _audio_response(data)


def _audio_response(data: bytes) -> Response:
    return Response(
        content=data,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=600"},
    )
