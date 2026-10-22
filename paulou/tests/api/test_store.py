import threading
import time

import pytest

from backend.api.store import PreparedSentence, SentenceStore
from core.models import Sentence


def _prepared(text="x"):
    return PreparedSentence(sentence=Sentence(text=text, chunks=[]))


def test_get_returns_none_when_missing():
    assert SentenceStore().get("nope") is None


def test_lru_evicts_least_recently_used():
    store = SentenceStore(capacity=2)
    store.get_or_create("a", _prepared)
    store.get_or_create("b", _prepared)
    store.get("a")  # touch a: b is now the oldest
    store.get_or_create("c", _prepared)

    assert store.get("a") is not None
    assert store.get("b") is None
    assert store.get("c") is not None
    assert len(store) == 2


def test_factory_failure_stores_nothing_and_allows_retry():
    store = SentenceStore()

    def boom():
        raise RuntimeError("tts down")

    with pytest.raises(RuntimeError):
        store.get_or_create("a", boom)
    assert store.get("a") is None
    assert store.get_or_create("a", _prepared) is not None


def test_concurrent_requests_share_one_preparation():
    store = SentenceStore()
    calls = []

    def slow_factory():
        calls.append(1)
        time.sleep(0.2)
        return _prepared()

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(store.get_or_create("a", slow_factory)))
        for _ in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1
    assert len({id(r) for r in results}) == 1


def test_reference_and_clip_are_made_once():
    item = _prepared()
    made = []
    for _ in range(3):
        item.reference("slow", lambda: made.append("ref") or "R")
        item.clip(("slow", "chunk", 0), lambda: made.append("clip") or b"c")
    assert made == ["ref", "clip"]


def test_capacity_must_be_positive():
    with pytest.raises(ValueError):
        SentenceStore(capacity=0)
