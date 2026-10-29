import sys
from types import SimpleNamespace

import numpy as np
import pytest

from localphraser.audio import Recorder


@pytest.fixture
def device(monkeypatch):
    class Stream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
            self.active = False
            self.closed = False

        def start(self):
            self.active = True

        def stop(self):
            self.active = False

        abort = stop

        def close(self):
            self.closed = True

    class CallbackStop(Exception):
        pass

    module = SimpleNamespace(
        InputStream=Stream,
        CallbackStop=CallbackStop,
        PortAudioError=type("PortAudioError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", module)
    return module


def test_capture_is_bounded_and_zeroed(device):
    recorder = Recorder(None, 1)
    recorder.start()
    stream = recorder.stream
    buffer = recorder.buffer
    with pytest.raises(device.CallbackStop):
        stream.callback(np.ones((17000, 1), dtype=np.float32), 17000, None, False)
    assert recorder.full.is_set()
    audio = recorder.stop()
    assert len(audio) == 16000
    assert np.all(audio == 1)
    assert np.all(buffer == 0)
    assert stream.closed
    assert recorder.buffer.size == 0


def test_audio_overflow_fails_and_cleans(device):
    recorder = Recorder(None, 1)
    recorder.start()
    stream = recorder.stream
    stream.callback(np.ones((100, 1), dtype=np.float32), 100, None, True)
    assert not recorder.healthy()
    with pytest.raises(RuntimeError):
        recorder.stop()
    assert stream.closed
    assert recorder.buffer.size == 0


def test_cancel_closes_stream_and_clears_buffer(device):
    recorder = Recorder(None, 1)
    recorder.start()
    buffer = recorder.buffer
    buffer.fill(1)
    stream = recorder.stream
    recorder.cancel()
    assert not np.any(buffer)
    assert stream.closed
    assert recorder.stream is None


def test_cancel_survives_disconnected_device(device):
    recorder = Recorder(None, 1)
    recorder.start()
    buffer = recorder.buffer
    buffer.fill(1)

    def failed():
        raise OSError("Device disconnected")

    recorder.stream.abort = failed
    recorder.stream.close = failed
    recorder.cancel()
    assert not np.any(buffer)
    assert recorder.stream is None


def test_preparation_does_not_start_capture_and_stream_is_reused(device):
    recorder = Recorder(None, 1, keep_ready=True)
    recorder.prepare()
    stream = recorder.stream
    assert not stream.active
    assert not recorder.first_frame.is_set()
    recorder.start()
    stream.callback(np.ones((100, 1), dtype=np.float32), 100, None, False)
    audio = recorder.stop()
    assert len(audio) == 100 and np.all(audio == 1)
    assert not stream.active and not stream.closed
    assert not np.any(recorder.buffer)
    recorder.start()
    assert recorder.stream is stream
    assert recorder.position == 0
    assert not recorder.first_frame.is_set()
    recorder.close()
    assert stream.closed
    assert recorder.buffer.size == 0


def test_prepare_cannot_reopen_after_shutdown(device):
    recorder = Recorder(None, 1, keep_ready=True)
    recorder.close()
    recorder.prepare()
    assert recorder.stream is None
    with pytest.raises(RuntimeError, match="closed"):
        recorder.start()


@pytest.mark.parametrize("has_frames", [False, True])
def test_active_stream_without_recent_frames_is_unhealthy(device, monkeypatch, has_frames):
    clock = [100.0]
    monkeypatch.setattr("localphraser.audio.monotonic", lambda: clock[0], raising=False)
    recorder = Recorder(None, 120)
    recorder.start()
    stream = recorder.stream
    assert recorder.healthy()
    if has_frames:
        clock[0] = 101.0
        stream.callback(np.ones((100, 1), dtype=np.float32), 100, None, False)
        clock[0] = 103.0
        assert recorder.healthy()
    clock[0] += 3.1
    assert stream.active
    assert not recorder.healthy()
    recorder.cancel()
    assert stream.closed and not recorder.buffer.size


def test_release_after_callback_stall_refuses_partial_audio(device, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("localphraser.audio.monotonic", lambda: clock[0], raising=False)
    recorder = Recorder(None, 120, keep_ready=True)
    recorder.start()
    stream, buffer = recorder.stream, recorder.buffer
    stream.callback(np.ones((5000, 1), dtype=np.float32), 5000, None, False)
    clock[0] = 104.0
    with pytest.raises(RuntimeError, match="interrupted"):
        recorder.stop()
    assert stream.closed and recorder.stream is None
    assert not buffer.any() and not recorder.buffer.size


def test_silent_frames_keep_stream_healthy_and_reuse_resets_clock(device, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("localphraser.audio.monotonic", lambda: clock[0])
    recorder = Recorder(None, 120, keep_ready=True)
    recorder.start()
    stream = recorder.stream
    for _ in range(10):
        clock[0] += 1
        stream.callback(np.zeros((100, 1), dtype=np.float32), 100, None, False)
        assert recorder.healthy()
    recorder.stop().fill(0)
    clock[0] += 60
    recorder.start()
    assert recorder.stream is stream and recorder.healthy()
    recorder.cancel()


def test_complete_capture_is_not_treated_as_stalled(device, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("localphraser.audio.monotonic", lambda: clock[0])
    recorder = Recorder(None, 1)
    recorder.start()
    with pytest.raises(device.CallbackStop):
        recorder.stream.callback(np.ones((16000, 1), dtype=np.float32), 16000, None, False)
    clock[0] += 10
    assert recorder.healthy()
    audio = recorder.stop()
    assert audio.size == 16000
    audio.fill(0)


def test_stall_latches_failure_until_cancel_and_new_recording(device, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("localphraser.audio.monotonic", lambda: clock[0])
    recorder = Recorder(None, 120)
    recorder.start()
    clock[0] += 4
    assert not recorder.healthy()
    recorder.stream.callback(np.ones((100, 1), dtype=np.float32), 100, None, False)
    assert not recorder.healthy()
    recorder.cancel()
    recorder.start()
    assert recorder.healthy()
    recorder.cancel()


def test_default_rate_fallback_is_inactive_bounded_and_reused(device):
    original = device.InputStream
    attempts = []

    def open_stream(**kwargs):
        attempts.append(kwargs["samplerate"])
        if kwargs["samplerate"] == 16000:
            raise device.PortAudioError("unsupported rate", -9997)
        return original(**kwargs)

    device.InputStream = open_stream
    device.query_devices = lambda *args: {"default_samplerate": 48000.0}
    recorder = Recorder(None, 1, keep_ready=True)
    recorder.prepare()
    assert attempts == [16000, 48000]
    assert recorder.sample_rate == 48000 and recorder.buffer.size == 48000
    assert not recorder.stream.active
    recorder.start()
    with pytest.raises(device.CallbackStop):
        recorder.stream.callback(np.ones((49000, 1), dtype=np.float32), 49000, None, False)
    audio = recorder.stop()
    assert audio.size == 48000 and not recorder.buffer.any()
    recorder.start()
    assert attempts == [16000, 48000]
    recorder.close()


def test_unrelated_open_error_never_retries_a_different_rate(device):
    from unittest.mock import Mock

    device.InputStream = Mock(side_effect=device.PortAudioError("device unavailable", -9985))
    device.query_devices = Mock(side_effect=AssertionError("Unexpected fallback"))
    recorder = Recorder(None, 1)
    with pytest.raises(device.PortAudioError):
        recorder.prepare()
    device.InputStream.assert_called_once()
    assert recorder.stream is None and recorder.buffer.size == 0


@pytest.mark.parametrize("rate", [0, 192000, float("nan"), 44100.5, 16000])
def test_invalid_or_unchanged_fallback_rate_is_refused(device, rate):
    from unittest.mock import Mock

    device.InputStream = Mock(side_effect=device.PortAudioError("unsupported rate", -9997))
    device.query_devices = lambda *args: {"default_samplerate": rate}
    recorder = Recorder(None, 1)
    with pytest.raises(ValueError):
        recorder.prepare()
    device.InputStream.assert_called_once()
    assert recorder.stream is None and recorder.buffer.size == 0
