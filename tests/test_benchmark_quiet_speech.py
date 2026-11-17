import importlib.util
from pathlib import Path

import numpy as np
import pytest

_spec = importlib.util.spec_from_file_location(
    "benchmark_quiet_speech",
    Path(__file__).resolve().parents[1] / "scripts" / "benchmark_quiet_speech.py",
)
assert _spec and _spec.loader
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def test_word_errors_counts_edits_over_reference_words():
    assert bench.word_errors("the cat sat down", "The cat sat down.") == (0, 4)
    assert bench.word_errors("the cat sat down", "the cat down") == (1, 4)
    assert bench.word_errors("the cat", "the the the the cat") == (3, 2)


def test_paused_markup_is_one_utterance_with_700_ms_between_words():
    assert bench.paused_markup("a b c") == (
        '<rate speed="-3">a <silence msec="700"/> b <silence msec="700"/> c</rate>'
    )


def test_degrade_sets_peak_pads_half_a_second_and_adds_noise():
    out = bench.degrade(np.ones(16000, dtype=np.float32), 0.02, seed=0)
    assert out.size == 32000 and out.dtype == np.float32
    assert float(np.std(out[:8000])) == pytest.approx(0.002, rel=0.1)
    assert float(np.mean(out[8000:24000])) == pytest.approx(0.02, rel=0.05)


def test_click_adds_two_bursts_of_peak_0_35_at_fixed_offsets():
    out = bench.click(np.zeros(32000, dtype=np.float32), seed=0)
    burst = int(0.008 * 16000)
    for start in (int(0.05 * 16000), 32000 - int(0.12 * 16000)):
        assert float(np.max(np.abs(out[start : start + burst]))) == pytest.approx(0.35)
    assert not out[: int(0.05 * 16000)].any()


def test_noise_clips_are_the_four_fixed_lengths():
    assert [clip.size // 16000 for clip in bench.noise_clips()] == [3, 8, 5, 5]


def test_sentences_total_88_words():
    assert sum(len(s.split()) for s in bench.SENTENCES) == 88


def test_levels_and_models_option():
    assert bench.LEVELS == (0.25, 0.02, 0.014, 0.011, 0.008)
    args = bench.parse_args(["--root", "r", "--models", "base.en", "small.en", "--temp-dir", "t"])
    assert args.models == ["base.en", "small.en"] and not args.retry and not args.long
