"""Browser recording -> WAV for the free-phone recognizer.

Verified (headless Chromium, fake microphone): `MediaRecorder` produces
`audio/webm;codecs=opus`, which `soundfile` cannot open ("Format not
recognised"), while pydub/ffmpeg decodes it and `soundfile` reads the
resulting WAV. Safari records `audio/mp4` and Firefox `audio/ogg`; ffmpeg
detects the container itself, so no format hint is passed -- but those two
browsers have not been tried.

The WAV keeps the source sample rate and channel count: the recognizer
downmixes and resamples by itself (`_wav2vec2_ctc_common.decode`), the same
as for the CLI path, so scores do not depend on which entry point was used.
"""

import io
from dataclasses import dataclass

from pydub import AudioSegment


class AudioDecodeError(Exception):
    """The uploaded bytes are not audio ffmpeg can decode."""


@dataclass(frozen=True)
class ConvertedAudio:
    wav: bytes
    duration_ms: int


def convert_to_wav(data: bytes) -> ConvertedAudio:
    if not data:
        raise AudioDecodeError("empty upload")
    try:
        segment = AudioSegment.from_file(io.BytesIO(data))
        buf = io.BytesIO()
        segment.export(buf, format="wav")
    except Exception as exc:  # pydub raises CouldntDecodeError, IndexError, ...
        raise AudioDecodeError(f"cannot decode audio: {type(exc).__name__}") from exc
    return ConvertedAudio(wav=buf.getvalue(), duration_ms=len(segment))
