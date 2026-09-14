import io
import shutil

import pytest

ffmpeg_installed = pytest.mark.skipif(
    shutil.which("ffmpeg") is None and shutil.which("avconv") is None,
    reason="ffmpeg/avconv is a system dependency, not installed in this environment",
)

pytestmark = ffmpeg_installed

from pydub import AudioSegment  # noqa: E402
from pydub.generators import Sine  # noqa: E402

from stages.tts.audio_slicing import slice_audio  # noqa: E402


@pytest.fixture(scope="module")
def test_tone_mp3() -> bytes:
    # Stand-in for real TTS output — a 2s, 440Hz tone. No real audio was
    # available to test against in the environment this was built in (no
    # network access to Azure/edge-tts's endpoints) — see module docstring
    # in audio_slicing.py.
    tone = Sine(440).to_audio_segment(duration=2000)
    buf = io.BytesIO()
    tone.export(buf, format="mp3")
    return buf.getvalue()


def _decode(audio_bytes: bytes) -> AudioSegment:
    return AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")


def test_slice_duration_matches_expected(test_tone_mp3):
    sliced = slice_audio(test_tone_mp3, start_ms=500, end_ms=1000, padding_ms=50, fade_ms=20)
    result = _decode(sliced)
    # (1000-500) clip + 50ms padding on each side = 600ms
    assert abs(len(result) - 600) <= 5  # small tolerance for encoder framing


def test_slice_start_is_silent(test_tone_mp3):
    # The very beginning of the output falls within the silence padding —
    # should be at or near zero amplitude.
    sliced = slice_audio(test_tone_mp3, start_ms=500, end_ms=1000, padding_ms=50, fade_ms=20)
    result = _decode(sliced)
    samples = result.get_array_of_samples()
    first_5ms_samples = int(0.005 * result.frame_rate)
    assert max(abs(s) for s in samples[:first_5ms_samples]) == 0


def test_slice_middle_has_signal(test_tone_mp3):
    # Well past the padding+fade region, the actual tone should be present
    # at close to full amplitude.
    sliced = slice_audio(test_tone_mp3, start_ms=500, end_ms=1000, padding_ms=50, fade_ms=20)
    result = _decode(sliced)
    samples = result.get_array_of_samples()
    mid = len(samples) // 2
    window = samples[mid - 100 : mid + 100]
    assert max(abs(s) for s in window) > 10_000  # well above silence/fade-region levels


def test_slice_with_default_padding_and_fade(test_tone_mp3):
    # Verify the function works with its documented defaults, not just
    # the explicit values used in the other tests.
    sliced = slice_audio(test_tone_mp3, start_ms=500, end_ms=1000)
    result = _decode(sliced)
    assert len(result) > 500  # at least the raw clip length, plus some padding


def test_slice_produces_valid_decodable_audio(test_tone_mp3):
    # Sanity check: the sliced bytes are a well-formed MP3, not corrupted
    # data — decoding it must not raise.
    sliced = slice_audio(test_tone_mp3, start_ms=0, end_ms=200)
    result = _decode(sliced)
    assert len(result) > 0