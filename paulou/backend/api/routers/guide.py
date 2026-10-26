"""GET /guide/audio: a short word or phrase read aloud, for the pronunciation
guide's example buttons (Decision Log D62).

Not tied to a prepared sentence. The text is restricted (letters, spaces,
apostrophes and hyphens, at most `max_guide_text_chars`) so the endpoint
cannot be used to read arbitrary text through the TTS service. Audio is
cached on disk by the pipeline's TTS cache (D7), so a word is synthesized once.
"""

import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from backend.api.dependencies import AppState, api_error, get_state
from backend.api.mappers import normalize_text

logger = logging.getLogger("paulou.api")
router = APIRouter()

# Unicode letters, joined by single spaces, apostrophes or hyphens.
_ALLOWED = re.compile(r"[^\W\d_]+(?:[ '’\-][^\W\d_]+)*")


@router.get("/guide/audio")
def get_guide_audio(
    text: str = Query(...),
    speed: Literal["normal", "slow"] = "normal",
    state: AppState = Depends(get_state),
) -> Response:
    text = normalize_text(text)
    if not text or len(text) > state.settings.max_guide_text_chars or not _ALLOWED.fullmatch(text):
        raise api_error(422, "invalid_guide_text", "Only a short word or phrase can be played here.")
    rate = 1.0 if speed == "normal" else state.settings.slow_rate
    try:
        data = state.pipeline.synthesize_text(text, rate=rate)
    except Exception:
        logger.exception("synthesize_text failed")
        raise api_error(502, "audio_unavailable", "Could not generate the audio.")
    return Response(content=data, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})
