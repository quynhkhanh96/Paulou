"""In-memory store of prepared sentences (single-process, single-user MVP).

NOT a database (Decision Log D53: no persistence of sentences or attempts).
Holds, per sentence id, the analyzed `Sentence` plus the reference audio
passes and the clips cut from them, so the audio endpoint can serve a clip
without re-running TTS or re-slicing. Bounded LRU. The parse cache
(`CachingSentenceParser`) and the TTS cache are on disk, so a restart
loses only this store -- the next request for the same sentence is fast.

Concurrency: FastAPI runs the sync endpoints in a thread pool. Two requests
for the same sentence id (e.g. a double click) share ONE preparation
(`get_or_create`), and one slow-pass TTS call (`PreparedSentence.reference`).
"""

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from core.models import PronunciationUnit, ReferenceAudio, Sentence


@dataclass
class PreparedSentence:
    sentence: Sentence
    references: dict[str, ReferenceAudio] = field(default_factory=dict)
    clips: dict[tuple, bytes] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def find_unit(self, unit_id: str) -> PronunciationUnit | None:
        for chunk in self.sentence.chunks:
            for unit in chunk.units:
                if unit.id == unit_id:
                    return unit
        return None

    def reference(self, speed: str, make: Callable[[], ReferenceAudio]) -> ReferenceAudio:
        with self._lock:
            if speed not in self.references:
                self.references[speed] = make()
            return self.references[speed]

    def clip(self, key: tuple, make: Callable[[], bytes]) -> bytes:
        with self._lock:
            if key not in self.clips:
                self.clips[key] = make()
            return self.clips[key]


class SentenceStore:
    def __init__(self, capacity: int = 32):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._items: OrderedDict[str, PreparedSentence] = OrderedDict()
        self._lock = threading.Lock()
        self._creating: dict[str, threading.Lock] = {}

    def get(self, sentence_id: str) -> PreparedSentence | None:
        with self._lock:
            item = self._items.get(sentence_id)
            if item is not None:
                self._items.move_to_end(sentence_id)
            return item

    def _put(self, sentence_id: str, item: PreparedSentence) -> None:
        with self._lock:
            self._items[sentence_id] = item
            self._items.move_to_end(sentence_id)
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)

    def get_or_create(
        self, sentence_id: str, factory: Callable[[], PreparedSentence]
    ) -> PreparedSentence:
        existing = self.get(sentence_id)
        if existing is not None:
            return existing
        with self._lock:
            creation_lock = self._creating.setdefault(sentence_id, threading.Lock())
        with creation_lock:
            try:
                existing = self.get(sentence_id)
                if existing is not None:
                    return existing
                created = factory()  # may raise: nothing is stored then
                self._put(sentence_id, created)
                return created
            finally:
                with self._lock:
                    self._creating.pop(sentence_id, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
