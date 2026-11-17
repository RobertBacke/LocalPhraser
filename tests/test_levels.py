import numpy as np
import pytest

from localphraser.levels import BOOST_LIMIT, boost_gain, boost_quiet, speech_level


def test_level_ignores_three_loudest_frames(tone):
    audio = tone(0.02)
    for start in (800, 4000, 9000):  # three clicks, one frame each
        audio[start : start + 100] = 0.9
    assert speech_level(audio) == pytest.approx(0.02, rel=0.05)


def test_level_of_short_or_empty_audio_is_plain_peak(tone):
    assert speech_level(np.empty(0, dtype=np.float32)) == 0.0
    assert speech_level(tone(0.2, seconds=0.1)) == pytest.approx(0.2, rel=0.05)  # 5 frames


def test_level_uses_capture_rate_for_frame_length(tone):
    assert speech_level(tone(0.05, rate=48000), 48000) == pytest.approx(0.05, rel=0.05)


def test_level_counts_negative_peaks_and_short_audio_uses_full_peak():
    audio = np.zeros(16000, dtype=np.float32)
    audio[::2000] = -0.5  # eight frames hold a negative peak: the fourth-largest is 0.5
    assert speech_level(audio) == pytest.approx(0.5)
    assert speech_level(np.array([0.1, -0.7, 0.2], dtype=np.float32)) == pytest.approx(0.7)


def test_boost_raises_quiet_audio_to_target_in_a_new_array(tone):
    audio = tone(0.02)
    boosted = boost_quiet(audio)
    assert boosted is not audio and speech_level(boosted) == pytest.approx(0.3, rel=0.05)
    assert float(np.max(np.abs(audio))) == pytest.approx(0.02, rel=0.05)


def test_boost_is_limited_clipped_and_never_attenuates(tone):
    assert speech_level(boost_quiet(tone(0.001))) == pytest.approx(0.04, rel=0.05)  # 40x
    loud = tone(0.5)
    assert boost_quiet(loud) is loud
    clicked = tone(0.02)
    clicked[100:200] = 0.9
    assert float(np.max(np.abs(boost_quiet(clicked)))) == 1.0
    silent = np.zeros(16000, dtype=np.float32)
    assert boost_quiet(silent) is silent


def test_boost_gain_is_one_without_boost_and_limited_for_very_quiet_audio(tone):
    assert boost_gain(np.zeros(16000, dtype=np.float32)) == 1.0
    assert boost_gain(tone(0.5)) == 1.0
    assert boost_gain(tone(0.02)) == pytest.approx(15.0, rel=0.05)
    assert boost_gain(tone(0.001)) == BOOST_LIMIT
    assert boost_gain(tone(0.05, rate=48000), 48000) == pytest.approx(6.0, rel=0.05)


def decibels(value):
    return 10 ** (value / 20)


def test_display_level_maps_minus_54_to_minus_6_dbfs_onto_the_meter():
    from localphraser.levels import display_level

    assert display_level(decibels(-54)) == pytest.approx(0.0, abs=1e-6)
    assert display_level(decibels(-30)) == pytest.approx(0.5, abs=1e-6)
    assert display_level(decibels(-6)) == pytest.approx(1.0, abs=1e-6)
    # Quiet speech is visible: a peak of 0.01 (-40 dBFS) already shows over a quarter.
    assert display_level(0.01) == pytest.approx(14 / 48, abs=1e-6)


def test_display_level_is_clamped_and_never_decreases_with_level():
    from localphraser.levels import display_level

    assert display_level(0.0) == 0.0 and display_level(-1.0) == 0.0
    assert display_level(1.0) == 1.0 and display_level(4.0) == 1.0
    assert display_level(float("nan")) == 0.0
    steps = [display_level(index / 200) for index in range(201)]
    assert steps == sorted(steps)
