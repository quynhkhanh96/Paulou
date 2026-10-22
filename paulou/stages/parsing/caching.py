"""Caching wrapper for any SentenceParser implementation (Decision Log D52, D55).

Same pattern as `stages/tts/caching.py` (D7): NOT registered via the stage
registry (D12) -- it wraps an already-built SentenceParser instance and
implements the Protocol structurally, so it is usable anywhere a
SentenceParser is expected:

    parser = CachingSentenceParser(build("parser", config.parser), cache_dir="...", namespace=config.parser)

Why: the Gemini parser is stochastic (the same sentence gave 3 chunks on one
run and 2 on another, D50) and is the slowest part of sentence preparation
(D52). Caching the parse by sentence text makes chunking stable for a
sentence once it has been seen, across requests and across restarts, and
skips the LLM call on a repeat.

Cache key: sha256(namespace | text). `namespace` identifies the parser
implementation (the registry key), so switching `PipelineConfig.parser` over
an existing cache directory does not return another parser's chunks.
Changing the parser's prompt or model without changing the namespace does
NOT invalidate the cache: clear the directory when you do that.

STORAGE: one JSON file per sentence (`<hash>.json`, holding the text and the
chunk list). A missing, unreadable or malformed file is treated as a miss and
overwritten, never raised. Only a successful `parse` is stored. Writes are
atomic (temp file + replace), so a crash cannot leave a half-written entry.
No eviction: the cache grows unbounded, like the TTS cache.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from core.interfaces import SentenceParser


class CachingSentenceParser:
    """Wraps any SentenceParser with a filesystem cache keyed by (namespace, text)."""

    def __init__(self, parser: SentenceParser, cache_dir: str | Path, namespace: str = "default"):
        self._parser = parser
        self._namespace = namespace
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, sentence: str) -> Path:
        raw = f"{self._namespace}|{sentence}"
        return self._cache_dir / f"{hashlib.sha256(raw.encode('utf-8')).hexdigest()}.json"

    def _read(self, path: Path) -> list[str] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            chunks = data["chunks"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if isinstance(chunks, list) and chunks and all(isinstance(c, str) for c in chunks):
            return chunks
        return None

    def _write(self, path: Path, sentence: str, chunks: list[str]) -> None:
        payload = json.dumps({"text": sentence, "chunks": chunks}, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(dir=self._cache_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def parse(self, sentence: str) -> list[str]:
        path = self._path(sentence)
        cached = self._read(path)
        if cached is not None:
            return list(cached)

        chunks = self._parser.parse(sentence)
        if chunks:  # never cache an empty parse: it would pin a failure
            self._write(path, sentence, list(chunks))
        return chunks
