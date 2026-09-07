import pytest

from stages.speech_assessment.calibration import PhoneStats, calibrate_score


def test_raw_gop_equal_to_mean_gives_score_50():
    stats = {"a": PhoneStats(mean=0.0, std=1.0, sample_size=100)}
    assert calibrate_score(raw_gop=0.0, phone="a", phone_stats=stats) == 50


def test_raw_gop_far_below_mean_gives_low_score():
    stats = {"a": PhoneStats(mean=0.0, std=1.0, sample_size=100)}
    score = calibrate_score(raw_gop=-4.0, phone="a", phone_stats=stats)
    assert score < 5


def test_raw_gop_far_above_mean_gives_high_score():
    stats = {"a": PhoneStats(mean=0.0, std=1.0, sample_size=100)}
    score = calibrate_score(raw_gop=4.0, phone="a", phone_stats=stats)
    assert score > 95


def test_score_is_clamped_to_0_100_range():
    stats = {"a": PhoneStats(mean=0.0, std=0.01, sample_size=100)}
    high = calibrate_score(raw_gop=100.0, phone="a", phone_stats=stats)
    low = calibrate_score(raw_gop=-100.0, phone="a", phone_stats=stats)
    assert high == 100
    assert low == 0


def test_missing_phone_with_no_fallback_raises():
    stats = {"a": PhoneStats(mean=0.0, std=1.0, sample_size=100)}
    with pytest.raises(ValueError):
        calibrate_score(raw_gop=0.0, phone="ɑ̃", phone_stats=stats)


def test_undersampled_phone_falls_back_to_broader_class():
    stats = {
        "ɑ̃": PhoneStats(mean=-5.0, std=1.0, sample_size=2),  # too few samples
        "nasal_vowel": PhoneStats(mean=0.0, std=1.0, sample_size=200),
    }
    score = calibrate_score(
        raw_gop=0.0,
        phone="ɑ̃",
        phone_stats=stats,
        fallback_phone_class={"ɑ̃": "nasal_vowel"},
        min_sample_size=30,
    )
    # Should use the fallback's mean (0.0), not the undersampled phone's (-5.0).
    assert score == 50


def test_undersampled_phone_without_fallback_uses_its_own_stats_anyway():
    stats = {"ɑ̃": PhoneStats(mean=0.0, std=1.0, sample_size=2)}
    # No fallback provided — soft-degrades to using the phone's own
    # under-sampled stats rather than raising (see calibration.py docstring).
    score = calibrate_score(raw_gop=0.0, phone="ɑ̃", phone_stats=stats, min_sample_size=30)
    assert score == 50


def test_zero_std_does_not_crash():
    stats = {"a": PhoneStats(mean=0.0, std=0.0, sample_size=100)}
    score = calibrate_score(raw_gop=5.0, phone="a", phone_stats=stats)
    assert score == 50  # z forced to 0.0 when std == 0, per implementation
