"""POST /attempts: score one recording, synchronously (Decision Log D52)."""

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile

from backend.api.audio_convert import AudioDecodeError, convert_to_wav
from backend.api.dependencies import AppState, api_error, get_state
from backend.api.mappers import to_attempt_response
from backend.api.phone_stats import fill_placeholder_stats
from backend.api.schemas import AttemptResponse

logger = logging.getLogger("paulou.api")
router = APIRouter()


@router.post("/attempts", response_model=AttemptResponse)
def create_attempt(
    sentence_id: str = Form(...),
    chunk_index: int | None = Form(default=None, ge=0),
    unit_id: str | None = Form(default=None),
    whole_sentence: bool = Form(default=False),
    audio: UploadFile = File(...),
    state: AppState = Depends(get_state),
) -> AttemptResponse:
    """Target is a whole chunk (`chunk_index`), a single unit (`unit_id`) or
    the whole sentence (`whole_sentence=true`, every chunk's units in order,
    D59). The client never sends phonemes: units are looked up server-side
    from the prepared sentence."""
    if (chunk_index is not None) + (unit_id is not None) + whole_sentence != 1:
        raise api_error(
            422, "invalid_target", "Pass exactly one of chunk_index, unit_id or whole_sentence."
        )
    if not state.ready.is_set():
        raise api_error(
            503, "model_not_ready", "The speech model is still loading. Try again in a few seconds."
        )

    prepared = state.store.get(sentence_id)
    if prepared is None:
        raise api_error(404, "sentence_not_found", "This sentence is no longer prepared. Prepare it again.")

    if whole_sentence:
        units = [u for chunk in prepared.sentence.chunks for u in chunk.units]
    elif chunk_index is not None:
        if chunk_index >= len(prepared.sentence.chunks):
            raise api_error(404, "chunk_not_found", "No such chunk.")
        units = prepared.sentence.chunks[chunk_index].units
    else:
        unit = prepared.find_unit(unit_id)
        if unit is None:
            raise api_error(404, "unit_not_found", "No such unit.")
        units = [unit]

    settings = state.settings
    data = audio.file.read(settings.max_audio_bytes + 1)
    if len(data) > settings.max_audio_bytes:
        raise api_error(413, "audio_too_large", "The recording is too large.")
    try:
        converted = convert_to_wav(data)
    except AudioDecodeError:
        logger.exception("could not decode the uploaded recording")
        raise api_error(422, "bad_audio", "The recording could not be read as audio.")
    if converted.duration_ms < settings.min_audio_ms:
        raise api_error(422, "audio_too_short", "The recording is too short. Press record, speak, then press stop.")
    if converted.duration_ms > settings.max_audio_ms:
        raise api_error(422, "audio_too_long", "The recording is too long.")

    try:
        with state.decode_lock:
            if not state.calibrated:
                fill_placeholder_stats(state.pipeline.phone_stats, units)
            results = state.pipeline.score_attempt(units, converted.wav)
    except Exception:
        logger.exception("score_attempt failed")
        raise api_error(500, "scoring_failed", "Scoring failed. Check the server log.")

    return to_attempt_response(
        sentence_id, chunk_index, unit_id, results, state.calibrated, whole_sentence=whole_sentence
    )
