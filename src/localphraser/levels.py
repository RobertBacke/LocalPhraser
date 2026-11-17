"""Click-tolerant speech level and the quiet-input boost shared by the recognisers."""

import numpy as np

from localphraser.audio import SAMPLE_RATE, Audio

QUIET_LEVEL = 0.012
BOOST_TARGET = 0.3
BOOST_LIMIT = 40.0
_IGNORED_FRAMES = 3
_MIN_FRAMES = 8


def _peak(values: Audio) -> float:
    return float(max(values.max(), -values.min())) if values.size else 0.0


def speech_level(audio: Audio, sample_rate: int = SAMPLE_RATE) -> float:
    """Fourth-largest 20 ms frame peak, so a few key clicks do not set the level."""
    size = sample_rate // 50
    count = audio.size // size
    if count < _MIN_FRAMES:
        return _peak(audio)
    frames = audio[: count * size].reshape(count, size)  # a view, not a copy
    peaks = np.maximum(frames.max(axis=1), -frames.min(axis=1))
    return float(np.partition(peaks, count - _IGNORED_FRAMES - 1)[count - _IGNORED_FRAMES - 1])


def boost_gain(audio: Audio, sample_rate: int = SAMPLE_RATE) -> float:
    """The factor boost_quiet applies to this audio; 1.0 when it leaves the audio unchanged."""
    level = speech_level(audio, sample_rate)
    if level <= 0.0 or level >= BOOST_TARGET:
        return 1.0
    return min(BOOST_TARGET / level, BOOST_LIMIT)


def boost_quiet(audio: Audio, sample_rate: int = SAMPLE_RATE) -> Audio:
    """Raise quiet speech towards BOOST_TARGET; the input itself is returned when unchanged."""
    gain = boost_gain(audio, sample_rate)
    if gain == 1.0:
        return audio
    boosted = np.multiply(audio, gain, dtype=np.float32)
    np.clip(boosted, -1.0, 1.0, out=boosted)
    return boosted
