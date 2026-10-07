"""Unit tests for core/registry.py.

`_REGISTRY` is module-level global state, and importing real stage modules
elsewhere in a pytest session registers real implementations into it. Each
test therefore swaps in its own empty registry (monkeypatch) so nothing
leaks in or out. `register`/`build`/`is_registered` look `_REGISTRY` up by
module-global name at call time, so patching the module attribute works.
"""

import pytest

from core import registry


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(registry, "_REGISTRY", {})


def test_register_then_build_passes_kwargs_to_constructor():
    @registry.register("stage_a", "impl")
    class Impl:
        def __init__(self, value=0):
            self.value = value

    built = registry.build("stage_a", "impl", value=7)

    assert isinstance(built, Impl)
    assert built.value == 7


def test_register_returns_the_class_unchanged():
    class Impl:
        pass

    assert registry.register("stage_a", "impl")(Impl) is Impl


def test_is_registered_true_after_register():
    @registry.register("stage_a", "impl")
    class Impl:
        pass

    assert registry.is_registered("stage_a", "impl") is True


def test_is_registered_false_for_unknown_key_and_unknown_stage():
    @registry.register("stage_a", "impl")
    class Impl:
        pass

    assert registry.is_registered("stage_a", "other") is False
    assert registry.is_registered("no_such_stage", "impl") is False


def test_is_registered_is_scoped_per_stage():
    @registry.register("stage_a", "shared_key")
    class Impl:
        pass

    assert registry.is_registered("stage_a", "shared_key") is True
    assert registry.is_registered("stage_b", "shared_key") is False


def test_is_registered_does_not_instantiate():
    constructed = []

    @registry.register("stage_a", "impl")
    class Impl:
        def __init__(self):
            constructed.append(True)

    registry.is_registered("stage_a", "impl")

    assert constructed == []


@pytest.mark.parametrize("stage, key", [("stage_a", "missing"), ("no_such_stage", "impl")])
def test_build_unregistered_raises_keyerror_naming_stage_and_key(stage, key):
    @registry.register("stage_a", "impl")
    class Impl:
        pass

    with pytest.raises(KeyError, match="No implementation registered") as excinfo:
        registry.build(stage, key)

    assert repr(stage) in str(excinfo.value)
    assert repr(key) in str(excinfo.value)


def test_keyerror_raised_inside_constructor_is_not_reported_as_unregistered():
    """Regression: build() used to wrap the constructor call in the same
    try/except as the lookup, so a KeyError from inside an implementation's
    own __init__ (e.g. `vocab[token]` in a model wrapper) surfaced as
    "No implementation registered" even though it WAS registered.
    """

    @registry.register("stage_a", "broken")
    class Broken:
        def __init__(self):
            {}["some_missing_vocab_token"]

    with pytest.raises(KeyError) as excinfo:
        registry.build("stage_a", "broken")

    assert "No implementation registered" not in str(excinfo.value)
    assert "some_missing_vocab_token" in str(excinfo.value)
    assert registry.is_registered("stage_a", "broken") is True