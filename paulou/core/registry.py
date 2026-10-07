"""Registry for swappable, model-backed stage implementations.

See Decision Log D12: only stages with an external/model dependency likely
to be swapped or compared (sentence parser, G2P source, TTS provider, GOP
scorer, free-phone recognizer) go through this registry + a PipelineConfig
value, rather than being wired up directly. Pure, deterministic logic does
not use this — see D12.
"""

_REGISTRY: dict[str, dict[str, type]] = {}


def register(stage: str, key: str):
    """Class decorator registering an implementation of `stage` under `key`."""

    def wrapper(cls):
        _REGISTRY.setdefault(stage, {})[key] = cls
        return cls

    return wrapper


def is_registered(stage: str, key: str) -> bool:
    """Whether an implementation is registered for `stage` under `key`.

    Lets a caller (PaulouPipeline's lazy stage construction) decide whether
    it still has to import the package whose module-level `@register`
    decorators would register that key -- without building anything.
    Decorators only run when their module is imported, so "not registered
    yet" usually means "package not imported yet", not "doesn't exist".
    """
    return key in _REGISTRY.get(stage, {})


def build(stage: str, key: str, **kwargs):
    """Instantiate the implementation registered for `stage` under `key`.

    Only the registry LOOKUP is guarded. The constructor call sits outside
    the `try`: an earlier version wrapped both, so a KeyError raised inside
    an implementation's own `__init__` (e.g. a vocab lookup in a model
    wrapper) was rewritten into a misleading "No implementation
    registered" message.
    """
    try:
        implementation = _REGISTRY[stage][key]
    except KeyError as exc:
        raise KeyError(
            f"No implementation registered for stage={stage!r}, key={key!r}"
        ) from exc
    return implementation(**kwargs)