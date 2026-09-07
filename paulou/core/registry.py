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


def build(stage: str, key: str, **kwargs):
    """Instantiate the implementation registered for `stage` under `key`."""
    try:
        return _REGISTRY[stage][key](**kwargs)
    except KeyError as exc:
        raise KeyError(
            f"No implementation registered for stage={stage!r}, key={key!r}"
        ) from exc
