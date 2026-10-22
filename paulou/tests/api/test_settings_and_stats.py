import json
from pathlib import Path

import pytest

from backend.api.phone_stats import PLACEHOLDER_STATS, fill_placeholder_stats, load_phone_stats
from backend.api.pipeline_factory import build_pipeline
from backend.api.settings import Settings
from core.models import PronunciationUnit
from stages.speech_assessment.calibration import PhoneStats


def _unit(phonemes):
    return PronunciationUnit(
        id="u", type="single", words=["w"], phonemes=phonemes, ipa="".join(phonemes),
        syllables=[], liaison_consonant=None, note="", scoring_focus="phoneme_accuracy",
    )


def test_settings_defaults_match_the_documented_values():
    s = Settings.from_env({})
    assert s.lexique_path == Path("data/Lexique400.tsv")
    assert s.timing_offset_ms == 50  # D49 / pipeline_cli recommended value
    assert s.phone_stats_path is None
    assert s.tts_cache_dir == Path("data/cache/tts")
    assert s.parser_cache_dir == Path("data/cache/parser")


def test_settings_read_the_environment():
    s = Settings.from_env({
        "PAULOU_LEXIQUE_PATH": "/x/lex.tsv", "PAULOU_CACHE_DIR": "/c",
        "PAULOU_PHONE_STATS_PATH": "/s.json", "PAULOU_TIMING_OFFSET_MS": "80",
        "PAULOU_CORS_ORIGINS": "http://a, http://b",
    })
    assert s.lexique_path == Path("/x/lex.tsv")
    assert s.phone_stats_path == Path("/s.json")
    assert s.timing_offset_ms == 80
    assert s.cors_origins == ("http://a", "http://b")


def test_load_phone_stats_reads_the_cli_file_format(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps({"a": {"mean": 0.7, "std": 0.1, "sample_size": 500}}))
    assert load_phone_stats(path) == {"a": PhoneStats(mean=0.7, std=0.1, sample_size=500)}


@pytest.mark.parametrize("content", ["[]", "{}", '{"a": {"mean": 1}}'])
def test_invalid_stats_file_fails_fast(tmp_path, content):
    path = tmp_path / "stats.json"
    path.write_text(content)
    with pytest.raises((ValueError, TypeError)):
        load_phone_stats(path)


def test_placeholder_fill_only_adds_missing_phones():
    real = PhoneStats(mean=0.9, std=0.05, sample_size=9000)
    stats = {"a": real}
    filled = fill_placeholder_stats(stats, [_unit(["a", "b"]), _unit(["b", "c"])])
    assert filled == ["b", "c"]
    assert stats == {"a": real, "b": PLACEHOLDER_STATS, "c": PLACEHOLDER_STATS}


def test_pipeline_factory_names_the_missing_lexicon(tmp_path):
    settings = Settings(lexique_path=tmp_path / "missing.tsv", cache_dir=tmp_path / "cache")
    with pytest.raises(RuntimeError, match="PAULOU_LEXIQUE_PATH"):
        build_pipeline(settings, {})
