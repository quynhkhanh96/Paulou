"""Calibration.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Converts a raw calibration input value to a 0-100 score via per-phone
z-score against a native-speaker reference distribution, then a normal CDF
(Decision Log D11). Rejected a supervised regressor because no labeled
French mispronunciation dataset exists (unlike English's speechocean762).

RENAMED per Decision Log D36: the parameter/field was originally `raw_gop`,
since this module was built for GOP scores. D36 replaced GOP entirely with
a free-decode + 3-way alignment pipeline; this module's math (z-score
against a native reference distribution) is reused as-is for the new
pipeline's "match" op scoring, but the input is now a free-phone
recognizer's decoder confidence, not a GOP value — so the GOP-specific
naming would now be actively misleading. Only names changed here; the
formula is untouched.

IMPORTANT — data gap, not yet resolved: the per-phone mean/std table this
module needs is supposed to come from running the free-phone recognizer on
a native French corpus offline (e.g. Common Voice fr, per D11, originally
written for a GOP run) — that corpus run hasn't happened yet.
`calibrate_score` therefore takes the stats table as a parameter
(dependency injection) rather than embedding numbers, so nothing here is
mistaken for real calibration data. Tests use synthetic tables.

Also unresolved (flagged, not decided): D11 mentions a fallback to a
"broader phone class" (e.g. grouping nasal vowels) when a phone's sample
size is too small, but doesn't specify the grouping or the size threshold.
`DEFAULT_MIN_SAMPLE_SIZE` below is a placeholder guess, not a validated
value — revisit once real corpus sample sizes are known. The actual
phone-class groupings are left to the caller via `fallback_phone_class`,
since no such closed list exists in the project notes yet.
"""

import math
from dataclasses import dataclass

DEFAULT_MIN_SAMPLE_SIZE = 30  # placeholder — see module docstring


@dataclass(frozen=True)
class PhoneStats:
    """Native-speaker reference distribution for one phone's calibration value.

    Renamed from "raw GOP score" per Decision Log D36 — see module docstring.
    """

    mean: float
    std: float
    sample_size: int


def _normal_cdf(z: float) -> float:
    """Standard normal CDF, via the error function (stdlib only, no scipy)."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def calibrate_score(
    raw_value: float,
    phone: str,
    phone_stats: dict[str, PhoneStats],
    fallback_phone_class: dict[str, str] | None = None,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> int:
    """Convert a raw calibration value for `phone` into a 0-100 score.

    `raw_value` was `raw_gop` before Decision Log D36 — see module
    docstring. Looks up `phone` in `phone_stats`. If its sample_size is
    below `min_sample_size` (unstable mean/std), falls back to the broader
    phone class given by `fallback_phone_class[phone]`, if provided. Raises
    if no usable stats can be found at all.
    """
    stats = phone_stats.get(phone)

    if stats is None or stats.sample_size < min_sample_size:
        fallback_key = (fallback_phone_class or {}).get(phone)
        fallback_stats = phone_stats.get(fallback_key) if fallback_key else None
        if fallback_stats is not None:
            stats = fallback_stats
        elif stats is None:
            raise ValueError(
                f"No calibration stats available for phone {phone!r}, "
                "and no usable fallback phone class was provided."
            )
        # else: stats exists but is under-sampled and no fallback available —
        # use it anyway rather than failing outright; this is a soft
        # degradation, not a validated policy (see module docstring).

    if stats.std == 0:
        z = 0.0
    else:
        z = (raw_value - stats.mean) / stats.std

    score = 100 * _normal_cdf(z)
    return max(0, min(100, round(score)))