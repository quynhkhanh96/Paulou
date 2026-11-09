"""Rule-based SentenceParser: spaCy POS tags + `chunk_tokens` (Decision Log D67).

Registered as `register("parser", "rule_based")` -- the sentence parser is a
swappable stage (D12) and this is the default since D67 (reverses D27);
`GeminiSentenceParser` stays registered as an alternative.

Deterministic: the same sentence always gives the same chunks (for a fixed
spaCy model version), with no network call and no API key. For that reason
the backend does not wrap it in `CachingSentenceParser` (D55 was for the
stochastic, slow Gemini call): a cache would only keep stale chunks after a
rule change.

Input is expected to be already normalized (`normalize_for_speech`, D68);
`PaulouPipeline.analyze_sentence` does that before calling any parser.

Chunk texts are cut out of the input string itself (each spaCy token is
located in it), so they keep the input's exact spelling and punctuation,
and joined with single spaces they give back the input (the chunking
contract, tests/contract/test_chunking_invariants.py).
"""

from core.registry import register
from stages.chunk_analyzer.pos.spacy_tagger import tag_sentence
from stages.parsing.rule_chunker import chunk_tokens


def _token_offsets(sentence: str, tokens: list[str]) -> list[tuple[int, int]]:
    """(start, end) character offsets of each token, found left to right."""
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for token in tokens:
        start = sentence.find(token, cursor)
        if start < 0:  # spaCy never rewrites token text; guard anyway
            raise ValueError(f"Token {token!r} not found in {sentence!r} after {cursor}")
        offsets.append((start, start + len(token)))
        cursor = start + len(token)
    return offsets


@register("parser", "rule_based")
class RuleBasedSentenceParser:
    """SentenceParser implementation: deterministic, rule-based chunking."""

    def parse(self, sentence: str) -> list[str]:
        tagged = [(text, pos) for text, pos in tag_sentence(sentence) if text.strip()]
        if not tagged:
            return []
        offsets = _token_offsets(sentence, [text for text, _pos in tagged])
        return [
            sentence[offsets[start][0] : offsets[end - 1][1]]
            for start, end in chunk_tokens(tagged)
        ]
