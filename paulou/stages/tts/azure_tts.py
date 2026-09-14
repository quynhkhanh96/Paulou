"""TTS via Azure Neural TTS.

Registered as `register("tts", "azure_neural")` — TTS is a swappable,
model-backed stage per Decision Log D12. Implements the TTSProvider
Protocol (core/interfaces.py) structurally.

SCOPE OF THIS IMPLEMENTATION — deliberately narrower than the full
Architecture Spec stage 3 description:
- Implemented: the core `synthesize(text, rate)` call — one synthesis pass,
  full audio + word-boundary timestamps. This is what the Protocol itself
  specifies.
- NOT implemented here (separate concerns, deferred):
  - Caching by `hash(text + voice + rate)` (Decision Log D7) — belongs as
    a wrapping layer around this provider, not inside it.
  - Slicing chunk/unit-level clips from the full-sentence audio, with
    silence padding + fade-in/out (Decision Log D5, second half) — needs
    an audio-manipulation dependency (e.g. pydub) not yet added, and is a
    downstream concern once raw audio + timings exist.
  - D6 (slow playback via a second pass at rate=0.7) needs no separate
    code path — it falls out of the Protocol's own `rate` parameter:
    calling `synthesize(text, rate=0.7)` a second time IS the second pass.

API — uses the Azure Cognitive Services Speech SDK
(`azure-cognitiveservices-speech`, verified against 1.51.2).
`SpeechSynthesizer.synthesis_word_boundary` fires one event per word during
synthesis; `evt.audio_offset` is in ticks (100ns units, per Microsoft's own
docs) — divide by 10_000 for milliseconds. Structurally verified in this
environment (construction, event wiring, method presence all confirmed
against the real installed SDK) but the actual network round-trip to Azure
could NOT be verified — this environment has no network access to Azure's
endpoints and no real credentials. Please confirm this works with a real
AZURE_SPEECH_KEY / AZURE_SPEECH_REGION before relying on it. Known
community-reported issue (Azure/azure-sdk-for-python#39683): word boundary
events can occasionally fail to fire, especially in multithreaded use —
worth keeping in mind if `word_timings` ever comes back incomplete.

RATE — passed straight through to SSML's `<prosody rate="...">` as the
plain numeric value (e.g. "0.7"), matching the Architecture Spec's literal
example (`<prosody rate="0.7">`), not converted to a percentage string.

API KEY — read from `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` environment
variables inside `__init__` (never hardcoded, never passed through
PipelineConfig, per Codebase Conventions), loaded via the same
`.env`-at-repo-root convention as `GEMINI_API_KEY` (see gemini_parser.py).
"""

import os
from xml.sax.saxutils import escape

import azure.cognitiveservices.speech as speechsdk
from dotenv import find_dotenv, load_dotenv

from core.models import WordTiming
from core.registry import register

load_dotenv(find_dotenv())


@register("tts", "azure_neural")
class AzureTTSProvider:
    """TTSProvider implementation using Azure Neural TTS.

    See module docstring for scope (core synthesize() only) and the
    UNVERIFIED network round-trip caveat.
    """

    def __init__(self, voice: str = "fr-FR-DeniseNeural"):
        api_key = os.environ.get("AZURE_SPEECH_KEY")
        region = os.environ.get("AZURE_SPEECH_REGION")
        if not api_key or not region:
            raise RuntimeError(
                "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must both be set. "
                "Expected in a .env file at the repo root (sibling to the "
                "paulou/ package — see .env.example), or exported directly "
                "in the environment."
            )
        self._speech_config = speechsdk.SpeechConfig(subscription=api_key, region=region)
        self.voice = voice

    def synthesize(self, text: str, rate: float = 1.0) -> tuple[bytes, list[WordTiming]]:
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self._speech_config, audio_config=None
        )

        word_timings: list[WordTiming] = []

        def _on_word_boundary(evt) -> None:
            start_ms = evt.audio_offset / 10_000
            end_ms = start_ms + evt.duration.total_seconds() * 1000
            word_timings.append(
                WordTiming(word=evt.text, start_ms=round(start_ms), end_ms=round(end_ms))
            )

        synthesizer.synthesis_word_boundary.connect(_on_word_boundary)

        ssml = self._build_ssml(text, rate)
        result = synthesizer.speak_ssml_async(ssml).get()

        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            details = getattr(result.cancellation_details, "error_details", None)
            raise RuntimeError(f"Azure TTS synthesis failed: {result.reason} ({details})")

        return result.audio_data, word_timings

    def _build_ssml(self, text: str, rate: float) -> str:
        return (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="fr-FR">'
            f'<voice name="{self.voice}">'
            f'<prosody rate="{rate}">{escape(text)}</prosody>'
            "</voice>"
            "</speak>"
        )