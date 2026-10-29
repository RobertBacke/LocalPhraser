import threading

import numpy as np
import pytest

from localphraser.audio import resample_audio


@pytest.mark.parametrize("rate", [8000, 32000, 44100, 48000, 96000])
def test_real_resampler_preserves_duration_and_voice_band_tone(rate):
    audio = np.sin(2 * np.pi * 440 * np.arange(rate) / rate).astype(np.float32)
    original = audio.copy()
    result = resample_audio(audio, rate)
    assert result.dtype == np.float32 and result.shape == (16000,)
    spectrum = np.abs(np.fft.rfft(result))
    assert np.argmax(spectrum) == 440
    assert np.sqrt(np.mean(result**2)) > 0.65
    assert np.array_equal(audio, original)
    result.fill(0)
    audio.fill(0)


def test_downsampling_filters_above_output_nyquist():
    audio = np.sin(2 * np.pi * 12000 * np.arange(48000) / 48000).astype(np.float32)
    result = resample_audio(audio, 48000)
    assert np.sqrt(np.mean(result[100:-100] ** 2)) < 0.01


def test_chunk_boundaries_preserve_continuous_audio():
    rate = 44100
    audio = np.sin(2 * np.pi * 440 * np.arange(rate * 3 // 2) / rate).astype(np.float32)
    result = resample_audio(audio, rate)
    expected = np.sin(2 * np.pi * 440 * np.arange(24000) / 16000)
    assert result.shape == (24000,)
    assert np.sqrt(np.mean((result[100:-100] - expected[100:-100]) ** 2)) < 0.01


def test_passthrough_and_empty_do_not_allocate_recording_copies():
    audio = np.ones(100, dtype=np.float32)
    assert resample_audio(audio, 16000) is audio
    empty = np.empty(0, dtype=np.float32)
    assert resample_audio(empty, 48000) is empty


def test_pipeline_resamples_off_owner_thread_and_clears_both_buffers(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import Mock

    from localphraser.pipeline import Dictation

    pipeline = object.__new__(Dictation)
    pipeline.refiner = None
    pipeline.closed = False
    pipeline.recognizer = Mock()
    owner = threading.get_ident()
    captured = np.ones(48000, dtype=np.float32)
    observed = []

    def transcribe(audio):
        assert threading.get_ident() != owner
        assert audio.size == 16000 and audio.any()
        observed.append(audio)
        return "synthetic words"

    pipeline.recognizer.transcribe.side_effect = transcribe
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert (
            executor.submit(pipeline._transcribe, captured, 48000).result().text
            == "synthetic words"
        )
    assert not captured.any() and not observed[0].any()


def test_conversion_failure_also_clears_original_buffer(monkeypatch):
    from unittest.mock import Mock

    from localphraser.pipeline import Dictation

    pipeline = object.__new__(Dictation)
    captured = np.ones(48000, dtype=np.float32)
    monkeypatch.setattr("localphraser.pipeline.resample_audio", Mock(side_effect=RuntimeError()))
    with pytest.raises(RuntimeError):
        pipeline._transcribe(captured, 48000)
    assert not captured.any()


def test_recognizer_failure_clears_native_and_converted_buffers():
    from unittest.mock import Mock

    from localphraser.pipeline import Dictation

    pipeline = object.__new__(Dictation)
    captured = np.ones(48000, dtype=np.float32)
    observed = []

    def failed(audio):
        observed.append(audio)
        raise RuntimeError("owned failure fixture")

    pipeline.recognizer = Mock(transcribe=failed)
    with pytest.raises(RuntimeError):
        pipeline._transcribe(captured, 48000)
    assert not captured.any() and not observed[0].any()
