"""Contract test for GeminiSentenceParser.

Per Testing Conventions: chunking is stochastic (LLM-based), so this checks
invariants that must always hold, NOT exact expected output. Requires a
real GEMINI_API_KEY (repo-root .env or exported directly) — skipped
otherwise, since it calls the real Gemini API and costs quota.

NOT run/verified by the assistant that wrote this — no network access to
the Gemini API from that environment. Please run this yourself once
GEMINI_API_KEY is set, and report back if `interaction.output_text` in
gemini_parser.py turns out to be the wrong attribute (see that module's
docstring for the documented alternative).
"""

import os

import pytest
from dotenv import find_dotenv, load_dotenv

# Load .env explicitly here, before checking os.environ below — don't rely
# on the side effect of importing gemini_parser.py for this (that was the
# original bug: pytestmark checked os.environ BEFORE the import that
# triggers load_dotenv() ran, so the skip condition always saw an empty
# environment even with a real .env in place).
load_dotenv(find_dotenv())

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set — see .env.example / SETUP.md",
)

from stages.parsing.gemini_parser import GeminiSentenceParser  # noqa: E402


def _normalize(text: str) -> str:
    """Ignore whitespace and case differences; NOT accent/diacritic-insensitive."""
    return "".join(text.split()).lower()


@pytest.fixture(scope="module")
def parser():
    return GeminiSentenceParser()


@pytest.mark.parametrize(
    "sentence",
    [
        "Je voudrais un café, s'il vous plaît.",
        "Les amis sont arrivés hier soir.",
        "Bonjour, comment allez-vous aujourd'hui ?",
        "C'est une petite phrase simple.",
    ],
)
def test_chunking_preserves_all_text(parser, sentence):
    chunks = parser.parse(sentence)

    assert len(chunks) >= 1
    assert all(chunk.strip() for chunk in chunks)  # no empty chunks
    assert _normalize("".join(chunks)) == _normalize(sentence)  # no text lost or added


def test_chunking_returns_a_list_of_strings(parser):
    chunks = parser.parse("Bonjour tout le monde.")
    assert isinstance(chunks, list)
    assert all(isinstance(chunk, str) for chunk in chunks)
