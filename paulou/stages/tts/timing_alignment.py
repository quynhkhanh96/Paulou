"""Locate chunk/unit time spans inside one full-sentence TTS pass.

Pure function -- no Protocol/registry (Decision Log D12): deterministic
post-processing of already-synthesized timestamps, the same category as
`audio_slicing.py`.

The problem: `analyze_sentence` produces `PronunciationUnit`s whose `words`
come from the Chunk Analyzer (e.g. an elision unit holds ["l'", "ami"]),
while the TTS provider returns its OWN word tokenization in `WordTiming`
(both edge-tts and Azure emit one token per whitespace-delimited word, so
"l'ami" is typically ONE token, and "est-ce" may be one token where the
analyzer sees two words). The two tokenizations cannot be compared
word-by-word.

The approach: compare them as sequences of NORMALIZED CHARACTERS instead
(lowercase, letters and digits only -- apostrophes, hyphens, punctuation and
whitespace are dropped). Both sides spell out the same sentence, so the two
character streams must be identical; each unit then owns a character range,
and each TTS word owns a character range, and a unit's span runs from the
start of the first TTS word touching its range to the end of the last one.

STRICT: if the two streams differ at all (a word the provider dropped,
re-spelled, or expanded -- e.g. digits read out as words), a ValueError is
raised rather than guessing a partial alignment, because a mis-placed span
would silently slice the wrong audio for the learner to imitate.

KNOWN LIMIT: spans are word-granular, the finest the providers give. When a
TTS token straddles a unit boundary (one token "est-ce" vs units "est" and
"ce" in separate units), both units get that token's full span, so their
spans overlap.
"""

import unicodedata

from core.models import Sentence, WordTiming


def _normalize(text: str) -> str:
    """Lowercase, NFC, keep only alphanumeric characters."""
    folded = unicodedata.normalize("NFC", text).lower()
    return "".join(ch for ch in folded if ch.isalnum())


def _ranges(pieces: list[str]) -> tuple[list[tuple[int, int]], str]:
    """Half-open character range of each piece within the concatenation of
    the normalized pieces, plus that concatenation."""
    ranges: list[tuple[int, int]] = []
    parts: list[str] = []
    cursor = 0
    for piece in pieces:
        normalized = _normalize(piece)
        ranges.append((cursor, cursor + len(normalized)))
        parts.append(normalized)
        cursor += len(normalized)
    return ranges, "".join(parts)


def locate_spans(
    sentence: Sentence, word_timings: list[WordTiming]
) -> tuple[list[tuple[int, int]], dict[str, tuple[int, int]]]:
    """Return (chunk_spans, unit_spans) in the TTS audio's own timeline.

    `chunk_spans[i]` is (start_ms, end_ms) of `sentence.chunks[i]`;
    `unit_spans` maps each unit id to its (start_ms, end_ms). Unit ids must
    already be unique across the sentence (`analyze_sentence` guarantees it).

    Raises ValueError if the sentence's words and the timings' words do not
    spell the same normalized text, if a chunk has no units, or if unit ids
    repeat.
    """
    units = [unit for chunk in sentence.chunks for unit in chunk.units]
    unit_ids = [unit.id for unit in units]
    if len(set(unit_ids)) != len(unit_ids):
        raise ValueError("Unit ids must be unique across the sentence.")
    for index, chunk in enumerate(sentence.chunks):
        if not chunk.units:
            raise ValueError(f"Chunk {index} has no units; cannot locate a span.")

    unit_ranges, unit_text = _ranges(["".join(unit.words) for unit in units])
    timing_ranges, timing_text = _ranges([t.word for t in word_timings])

    if unit_text != timing_text:
        raise ValueError(
            "Sentence units and TTS word timings do not spell the same text: "
            f"units={unit_text!r}, timings={timing_text!r}."
        )

    def span_of(char_start: int, char_end: int) -> tuple[int, int]:
        touching = [
            timing
            for timing, (t_start, t_end) in zip(word_timings, timing_ranges)
            if t_end > t_start and t_start < char_end and t_end > char_start
        ]
        return touching[0].start_ms, touching[-1].end_ms

    unit_spans: dict[str, tuple[int, int]] = {}
    for unit, (start, end) in zip(units, unit_ranges):
        if end == start:
            raise ValueError(f"Unit {unit.id!r} has no letters; cannot locate a span.")
        unit_spans[unit.id] = span_of(start, end)

    chunk_spans: list[tuple[int, int]] = []
    for chunk in sentence.chunks:
        first, last = unit_spans[chunk.units[0].id], unit_spans[chunk.units[-1].id]
        chunk_spans.append((first[0], last[1]))

    return chunk_spans, unit_spans