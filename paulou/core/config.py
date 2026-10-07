"""PipelineConfig -- selects the active implementation per stage.

Per Codebase Conventions: "PipelineConfig (in core/config.py) holds *which
implementation* is active per stage -- not secrets, not environment-
specific paths... should be safe to log or commit as a default file."

Differs from the Architecture Spec's original illustrative example in two
ways, both discussed in chat:
- No `gop_scorer` field. `GOPScorer` has been dormant/obsolete since D36
  (the single free-decode pipeline replaced the two-branch GOP design) --
  including it here would wrongly imply it's still wired into anything.
- `free_decoder` defaults to "wav2vec2_cnam", not a placeholder -- chosen
  from real data (D47's canonicalizer-bias comparison against
  "wav2vec2_bofenghuang"), not arbitrarily.

`tts` defaults to "edge_tts" (D31), not "azure_neural" as the Architecture
Spec's original example showed -- no Azure Speech API key is currently
provisioned (same reasoning as D43's TTS-for-diagnostics decision), and
edge_tts needs no API key to run.
"""

from dataclasses import dataclass


@dataclass
class PipelineConfig:
    parser: str = "gemini"  # D27 -- only implementation; needs GEMINI_API_KEY
    g2p: str = "lexique_espeak"  # D30 -- only implementation
    tts: str = "edge_tts"  # D31 -- 2 registered ("edge_tts", "azure_neural");
    # edge_tts needs no API key, azure_neural needs AZURE_SPEECH_KEY/REGION
    free_decoder: str = "wav2vec2_cnam"  # D47 -- chosen over "wav2vec2_bofenghuang"
    # via the real canonicalizer-bias comparison, not a placeholder