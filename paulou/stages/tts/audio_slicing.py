"""Audio slicing: extract chunk/unit-level clips from a full-sentence pass.

Pure function — no Protocol/registry (Decision Log D12): slicing isn't a
swappable "implementation" the way Kaldi vs gop-ft is; it's deterministic
post-processing on already-synthesized audio + timestamps.

Per Decision Log D5: "Add short silence padding + fade-in/out at slice
boundaries, since natural continuous speech has no pause where a slice cut
is made."

ORDER OF OPERATIONS MATTERS, and is easy to get backwards: fade is applied
to the RAW sliced clip FIRST (this is the actual click-prevention D5 asks
for — smoothing the edges where we cut into continuous speech), and pure
silence is added AROUND that already-faded clip AFTERWARD. Doing it the
other way — fading the combined silence+speech+silence clip as one unit —
wastes the fade window on silence (already 0 amplitude) whenever
`padding_ms >= fade_ms`, leaving the actual cut edge unsmoothed, which
defeats the point.

SYSTEM DEPENDENCY — `pydub` shells out to `ffmpeg` (or `libav`) to decode/
encode compressed formats (MP3, the format both TTS providers produce).
NOT a pip package; must be installed separately (e.g. `apt install
ffmpeg`). Verified in this environment against ffmpeg 6.1.1 and a
synthetically-generated test tone (pydub's own sine-wave generator) — NOT
against real TTS output, since no real audio was available to test with
here (no network access to Azure/edge-tts's endpoints in this
environment). Please verify against real synthesized audio once you can.
"""

import io

from pydub import AudioSegment


def slice_audio(
    audio_bytes: bytes,
    start_ms: int,
    end_ms: int,
    audio_format: str = "mp3",
    padding_ms: int = 50,
    fade_ms: int = 20,
) -> bytes:
    """Extract [start_ms, end_ms) from `audio_bytes`, with silence padding
    and fade-in/out at the cut edges (Decision Log D5).

    `audio_format` must match the format `audio_bytes` was encoded in
    (both TTSProvider implementations currently produce MP3, but this
    isn't enforced here — pass the right value for whatever you're
    slicing).
    """
    full_audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=audio_format)

    clip = full_audio[start_ms:end_ms]
    clip = clip.fade_in(fade_ms).fade_out(fade_ms)

    silence = AudioSegment.silent(duration=padding_ms, frame_rate=clip.frame_rate)
    clip = silence + clip + silence

    buf = io.BytesIO()
    clip.export(buf, format=audio_format)
    return buf.getvalue()