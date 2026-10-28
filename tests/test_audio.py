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

    module = SimpleNamespace(InputStream=Stream, CallbackStop=CallbackStop)
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
