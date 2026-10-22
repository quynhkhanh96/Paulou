from stages.parsing.caching import CachingSentenceParser


class _CountingParser:
    def __init__(self, results=None):
        self.calls = 0
        self._results = results

    def parse(self, sentence: str) -> list[str]:
        self.calls += 1
        if self._results is not None:
            return list(self._results[(self.calls - 1) % len(self._results)])
        return sentence.split(" ", 1)


def test_miss_calls_underlying_parser(tmp_path):
    inner = _CountingParser()
    cache = CachingSentenceParser(inner, tmp_path)

    assert cache.parse("Bonjour le monde") == ["Bonjour", "le monde"]
    assert inner.calls == 1


def test_hit_skips_underlying_parser(tmp_path):
    inner = _CountingParser()
    cache = CachingSentenceParser(inner, tmp_path)

    cache.parse("Bonjour le monde")
    assert cache.parse("Bonjour le monde") == ["Bonjour", "le monde"]
    assert inner.calls == 1


def test_stable_chunking_despite_nondeterministic_parser(tmp_path):
    inner = _CountingParser(results=[["a b", "c"], ["a", "b c"]])
    cache = CachingSentenceParser(inner, tmp_path)

    first = cache.parse("a b c")
    again = [cache.parse("a b c") for _ in range(3)]

    assert again == [first] * 3


def test_cache_survives_a_new_instance_on_the_same_directory(tmp_path):
    CachingSentenceParser(_CountingParser(), tmp_path).parse("Bonjour le monde")

    second_inner = _CountingParser()
    result = CachingSentenceParser(second_inner, tmp_path).parse("Bonjour le monde")

    assert result == ["Bonjour", "le monde"]
    assert second_inner.calls == 0


def test_different_text_is_a_different_entry(tmp_path):
    inner = _CountingParser()
    cache = CachingSentenceParser(inner, tmp_path)

    cache.parse("Bonjour le monde")
    cache.parse("Salut les amis")

    assert inner.calls == 2


def test_namespace_separates_parsers(tmp_path):
    first = _CountingParser(results=[["x"]])
    second = _CountingParser(results=[["y"]])

    assert CachingSentenceParser(first, tmp_path, namespace="gemini").parse("t") == ["x"]
    assert CachingSentenceParser(second, tmp_path, namespace="other").parse("t") == ["y"]


def test_corrupt_entry_is_a_miss_and_is_overwritten(tmp_path):
    inner = _CountingParser()
    cache = CachingSentenceParser(inner, tmp_path)
    cache.parse("Bonjour le monde")
    for entry in tmp_path.glob("*.json"):
        entry.write_text("{not json", encoding="utf-8")

    assert cache.parse("Bonjour le monde") == ["Bonjour", "le monde"]
    assert inner.calls == 2
    assert cache.parse("Bonjour le monde") == ["Bonjour", "le monde"]
    assert inner.calls == 2


def test_empty_parse_is_not_cached(tmp_path):
    inner = _CountingParser(results=[[], ["ok"]])
    cache = CachingSentenceParser(inner, tmp_path)

    assert cache.parse("x") == []
    assert cache.parse("x") == ["ok"]
    assert inner.calls == 2


def test_underlying_error_propagates_and_nothing_is_cached(tmp_path):
    class Failing:
        def parse(self, sentence):
            raise RuntimeError("api down")

    cache = CachingSentenceParser(Failing(), tmp_path)
    try:
        cache.parse("x")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")
    assert list(tmp_path.glob("*.json")) == []
    assert list(tmp_path.glob("*.tmp")) == []


def test_unicode_text_round_trips(tmp_path):
    inner = _CountingParser(results=[["Les enfants", "ont acheté des pommes"]])
    cache = CachingSentenceParser(inner, tmp_path)

    cache.parse("Les enfants ont acheté des pommes")
    assert cache.parse("Les enfants ont acheté des pommes") == ["Les enfants", "ont acheté des pommes"]
    assert inner.calls == 1
