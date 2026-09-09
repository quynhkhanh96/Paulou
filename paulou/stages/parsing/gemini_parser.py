"""LLM-based sentence parser using the Gemini API.

Registered as `register("parser", "gemini")` — the sentence parser is a
swappable, model-backed stage per Decision Log D12. Implements the
SentenceParser Protocol (core/interfaces.py) structurally.

DEVIATION FROM ARCHITECTURE SPEC — see Decision Log D27 (needs your
rationale filled in before it's added): the Architecture Spec names "Claude
API" for this stage, with a sample class name `ClaudeSentenceParser`. This
implementation uses the Gemini API instead (`GeminiSentenceParser`), per
your explicit choice. File/class named after the specific vendor, not
generically, matching the existing `kaldi_gop.py`/`KaldiGOPScorer` naming
convention (Codebase Conventions).

API — uses Google's Interactions API (`client.interactions.create`), the
currently recommended interface for the Gemini API (GA since June 2026),
not the older `generateContent` API the Architecture Spec's general "LLM
call" framing predates. `store=False` is passed since this is a
single-turn, stateless call — no need for `previous_interaction_id`
conversation continuity, and no reason to have Google retain the request.

VERIFIED vs. UNVERIFIED: the keyword arguments used below (`model`,
`input`, `system_instruction`, `response_format` with `type`/`mime_type`/
`schema`, `store`) were structurally verified against the real installed
`google-genai` SDK (no `TypeError` on argument binding — the call reaches
the network dispatch layer). The actual round-trip response shape
(`interaction.output_text` containing the JSON string) is taken from
Google's own documented structured-output examples but could NOT be
verified end-to-end in this environment (no network access to
generativelanguage.googleapis.com, and no real API key). Please confirm
this works with a real GEMINI_API_KEY before relying on it — if
`interaction.output_text` turns out wrong, the likely alternative per the
same docs is `interaction.outputs[-1].text`.

API KEY — read from the `GEMINI_API_KEY` environment variable inside
`__init__` (never hardcoded, never passed through PipelineConfig, per
Codebase Conventions). Loaded via `python-dotenv`'s `find_dotenv()`, which
walks upward from THIS FILE's location looking for a `.env` — per your
setup, `.env` lives at the repo root (sibling to the `paulou/` package),
NOT inside `paulou/`. `find_dotenv()` walking up from
`paulou/stages/parsing/gemini_parser.py` will reach it regardless of the
current working directory the code is run from.

OUTPUT PARSING: requests a JSON array of strings via Gemini's structured
output (`response_format` + JSON Schema) rather than free-text parsing —
avoids an entire class of "the LLM added a preamble/numbered list/markdown
fencing" parsing failures. Still validated as a CONTRACT test, not
exact-match (Testing Conventions) — chunking itself is genuinely
stochastic; only the JSON *shape* is enforced by the API, not which words
end up in which chunk.

VERSION NOTE (Codebase Conventions — pin model-related dependencies):
verified against google-genai==2.22.0 (Interactions API needs >=2.3.0),
model gemini-3.8-flash. An unpinned SDK/model update could change chunking
behavior or the call shape without a code change to point to.
"""

import json
import os

from dotenv import find_dotenv, load_dotenv
from google import genai

from core.registry import register

load_dotenv(find_dotenv())

_CHUNKS_JSON_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}

_SYSTEM_INSTRUCTION = (
    "You split French sentences into rhythmic groups (groupes rythmiques) "
    "for pronunciation practice. A rhythmic group is a natural prosodic "
    "unit — roughly, a phrase pronounced as one breath/rhythm group — NOT "
    "a punctuation-based clause. Return the chunks as a JSON array of "
    "strings, in the original order, covering the entire input sentence "
    "exactly: no words dropped or added, no empty chunks."
)


@register("parser", "gemini")
class GeminiSentenceParser:
    """SentenceParser implementation using the Gemini API.

    See module docstring for the Architecture Spec deviation (D27) and API
    key handling.
    """

    def __init__(self, model: str = "gemini-3.8-flash"):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Expected in a .env file at the "
                "repo root (sibling to the paulou/ package — see "
                ".env.example), or exported directly in the environment."
            )
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def parse(self, sentence: str) -> list[str]:
        interaction = self._client.interactions.create(
            model=self._model,
            input=sentence,
            system_instruction=_SYSTEM_INSTRUCTION,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": _CHUNKS_JSON_SCHEMA,
            },
            store=False,
        )
        return json.loads(interaction.output_text)
