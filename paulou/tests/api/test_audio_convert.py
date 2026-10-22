import io

import pytest
import soundfile as sf

from backend.api.audio_convert import AudioDecodeError, convert_to_wav
from tests.api.conftest import FIXTURES, wav_bytes


def test_real_browser_recording_cannot_be_read_by_soundfile_directly():
    """Documents why conversion exists: the bytes below are real MediaRecorder
    output (Chromium, audio/webm;codecs=opus)."""
    data = (FIXTURES / "browser_recording.webm").read_bytes()
    with pytest.raises(sf.LibsndfileError):
        sf.read(io.BytesIO(data))


def test_real_browser_recording_converts_to_a_wav_soundfile_reads():
    data = (FIXTURES / "browser_recording.webm").read_bytes()

    converted = convert_to_wav(data)

    samples, rate = sf.read(io.BytesIO(converted.wav))
    assert rate == 48_000
    assert len(samples) / rate == pytest.approx(converted.duration_ms / 1000, abs=0.05)
    assert 1300 < converted.duration_ms < 1700


def test_wav_input_passes_through_with_its_duration():
    converted = convert_to_wav(wav_bytes(800))
    assert converted.duration_ms == 800
    assert sf.read(io.BytesIO(converted.wav))[1] == 16_000


def test_garbage_is_rejected():
    with pytest.raises(AudioDecodeError):
        convert_to_wav(b"this is not audio at all" * 20)


def test_empty_is_rejected():
    with pytest.raises(AudioDecodeError):
        convert_to_wav(b"")
