"""Chunk Analyzer orchestration.

Composes the Chunk Analyzer's sub-stages (Architecture Spec, stage 2) into
one function. Not itself a Protocol/registry stage (Decision Log D12) —
this is glue/composition code, like `PaulouPipeline` will eventually be,
just scoped to stage 2 rather than the whole pipeline (`pipeline.py` isn't
built yet).

Flow (see the flow diagram discussed when this was designed):
    chunk text
      -> POS tagging (tag_sentence, full chunk for accuracy)
      -> filter out PUNCT tokens
      -> liaison rules (apply_liaison_rules), on the FILTERED word list
      -> G2P each word individually (injected G2PProvider)
      -> assemble_units (checks elision first internally, then liaison)
      -> list[PronunciationUnit]

Known assumptions / flagged gaps, not fully resolved:
- PUNCT tokens are silently dropped, not represented in the output at all.
  If a chunk carries meaningful punctuation (e.g. from how the sentence
  parser draws chunk boundaries), it's lost here with no trace.
- G2P is called for every word, including recognized elided clitics whose
  G2P result gets thrown away by `assemble_units` anyway (it substitutes
  the correct closed-list phoneme instead — see elision.py). This is
  wasted work, not a correctness bug; skipping G2P for elided words is a
  possible future optimization, not done here for simplicity.
- `g2p.phonemize(word)` returns `(phonemes, source)`; only `phonemes` is
  kept. The dict-vs-espeak source is discarded, so there's currently no
  way to know afterward which words used the (less reliable) eSpeak
  fallback. Not a field `PronunciationUnit` has anywhere in the spec.
- `apply_liaison_rules` is run on the PUNCT-filtered word list, not the
  raw tagged output — its result's length is tied 1:1 to that filtered
  list, matching what `assemble_units` expects.
"""

from core.interfaces import G2PProvider
from core.models import PronunciationUnit
from stages.chunk_analyzer.assembly.unit_assembler import assemble_units
from stages.chunk_analyzer.liaison.rule_engine import apply_liaison_rules
from stages.chunk_analyzer.pos.spacy_tagger import tag_sentence


def analyze_chunk(chunk: str, g2p: G2PProvider) -> list[PronunciationUnit]:
    """Analyze one chunk of text into its PronunciationUnits.

    `chunk` should be a single rhythmic-group chunk (Architecture Spec
    stage 1 output) — full-sentence POS tagging accuracy still applies (see
    stages/chunk_analyzer/pos/spacy_tagger.py), so pass the whole chunk
    text, not individual words.

    `g2p` is any G2PProvider implementation (dependency-injected, not
    instantiated here — matches the swappable-stage philosophy even though
    this orchestrator itself isn't a registered stage).
    """
    tagged = tag_sentence(chunk)
    words_with_pos = [(word, pos) for word, pos in tagged if pos != "PUNCT"]

    if not words_with_pos:
        return []

    liaison_decisions = apply_liaison_rules(words_with_pos)

    words_with_phonemes = [
        (word, g2p.phonemize(word)[0]) for word, _pos in words_with_pos
    ]

    return assemble_units(words_with_phonemes, liaison_decisions)
