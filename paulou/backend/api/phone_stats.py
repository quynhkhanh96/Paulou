"""Calibration table loading (Decision Log D24, D50, D53).

`phone_stats` is a parameter of the pipeline, so a real native-corpus table
is swapped in by pointing PAULOU_PHONE_STATS_PATH at a JSON file
`{"a": {"mean": .., "std": .., "sample_size": ..}, ...}` -- no code change.
Same file format as `experiments/runners/pipeline_cli.py --phone-stats`
(duplicated here because the backend must not import from experiments/).

Without a file, every phone used gets PLACEHOLDER_STATS and the API reports
`calibrated=false` with all scores None.
"""

import json
from pathlib import Path

from core.models import PronunciationUnit
from stages.speech_assessment.calibration import PhoneStats

PLACEHOLDER_STATS = PhoneStats(mean=0.5, std=0.2, sample_size=1000)


def load_phone_stats(path: Path) -> dict[str, PhoneStats]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"{path}: expected a non-empty JSON object keyed by phone")
    return {phone: PhoneStats(**fields) for phone, fields in raw.items()}


def fill_placeholder_stats(
    stats: dict[str, PhoneStats], units: list[PronunciationUnit]
) -> list[str]:
    """Add PLACEHOLDER_STATS for canonical phones missing from `stats`
    (mutating it) and return the phones filled. Only used when no real
    table is loaded."""
    filled = sorted({p for unit in units for p in unit.phonemes} - stats.keys())
    for phone in filled:
        stats[phone] = PLACEHOLDER_STATS
    return filled
