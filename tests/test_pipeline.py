import queue
import threading
from concurrent.futures import Future

import numpy as np
import pytest

from localphraser.pipeline import Dictation, State


class FakeRecorder:
    def __init__(self):
        self.started = 0
        self.cancelled = 0
        self.audio = np.full(16000, 0.05, dtype=np.float32)

    def start(self):
        self.started += 1

    def stop(self):
        return self.audio

    def cancel(self):
        self.cancelled += 1

    def close(self):
        self.cancel()


class FakeRecognizer:
    def __init__(self):
        self.error = False
        self.gate = threading.Event()
        self.gate.set()

    def transcribe(self, audio):
        self.gate.wait(3)
        if self.error:
            raise ValueError("sensitive exception must not reach UI")
        return "Hello, world."


class FakeInsertion:
    def __init__(self):
        self.delivered = []
        self.capture_error = False
        self.insert_error = False
        self.window = object()
        self.discarded = []

    def snapshot(self):
        return self.window

    def capture(self, expected=None):
        if expected is not None and expected != self.window:
            raise ValueError("changed window")
        if self.capture_error:
            raise ValueError("selected text")
        return object()

    def insert(self, target, text):
        if self.insert_error:
            raise ValueError("changed target")
        self.delivered.append(text)

    def discard(self, target):
        self.discarded.append(target)


@pytest.fixture
def setup():
    recorder, recognizer, insertion = FakeRecorder(), FakeRecognizer(), FakeInsertion()
    callbacks = queue.Queue()
    changes, results = [], []
    pipeline = Dictation(
        recorder,
        recognizer,
        insertion,
        callbacks.put,
        lambda s, m: changes.append((s, m)),
        lambda t, n: results.append((t, n)),
    )
    yield pipeline, recorder, recognizer, insertion, callbacks, changes, results
    recognizer.gate.set()
    pipeline.shutdown()


def finish(callbacks):
    callbacks.get(timeout=5)()


def test_end_to_end_with_injected_ports(setup):
    pipeline, recorder, _, insertion, callbacks, changes, results = setup
    pipeline.press()
    pipeline.press()
    assert recorder.started == 1
    pipeline.release()
    pipeline.release()
    finish(callbacks)
    assert insertion.delivered == ["Hello, world."]
    assert results == [("Hello, world.", "Inserted.")]
    assert [s for s, _ in changes] == [
        State.RECORDING,
        State.TRANSCRIBING,
        State.INSERTING,
        State.IDLE,
    ]
    assert np.count_nonzero(recorder.audio) == 0


@pytest.mark.parametrize("failure", ["capture_error", "insert_error"])
def test_insertion_failure_preserves_transcript_without_retry(setup, failure):
    pipeline, _, _, insertion, callbacks, _, results = setup
    setattr(insertion, failure, True)
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert results[0][0] == "Hello, world."
    assert insertion.delivered == []
    assert pipeline.state == State.IDLE


def test_failed_inference_recovers_without_exposing_exception(setup):
    pipeline, _, recognizer, _, callbacks, changes, results = setup
    recognizer.error = True
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert not results
    assert pipeline.state == State.IDLE
    assert "sensitive" not in str(changes)
    recognizer.error = False
    pipeline.press()
    # Refill fake buffer (the real recorder allocates a new buffer).
    pipeline.recorder.audio[:] = 0.05
    pipeline.release()
    finish(callbacks)
    assert results[0][0] == "Hello, world."


def test_silence_skips_model(setup):
    pipeline, recorder, _, _, callbacks, _, results = setup
    recorder.audio[:] = 0
    pipeline.press()
    pipeline.release()
    assert pipeline.state == State.IDLE
    assert callbacks.empty()
    assert not results


def test_shutdown_during_inference_never_inserts(setup):
    pipeline, recorder, recognizer, insertion, callbacks, _, results = setup
    recognizer.gate.clear()
    pipeline.press()
    pipeline.release()
    pipeline.press()
    assert recorder.started == 1
    pipeline.shutdown()
    recognizer.gate.set()
    finish(callbacks)
    assert not results and not insertion.delivered


def test_cancel_and_manual_copy_mode(setup):
    pipeline, _, _, insertion, callbacks, _, results = setup
    pipeline.press()
    pipeline.cancel()
    pipeline.release()
    assert callbacks.empty()
    pipeline.auto_insert = False
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert results and not insertion.delivered


def test_microphone_failure_returns_to_idle(setup):
    pipeline, recorder, _, insertion, callbacks, changes, results = setup

    def denied():
        raise OSError("Permission denied")

    recorder.start = denied
    pipeline.press()
    assert pipeline.state == State.IDLE
    assert recorder.cancelled == 1
    assert State.ERROR in [state for state, _ in changes]
    assert not results and not insertion.delivered and callbacks.empty()


def test_audio_is_running_before_slow_target_verification(setup):
    pipeline, recorder, _, insertion, callbacks, _, results = setup
    original = insertion.capture

    def slow_capture(expected=None):
        assert recorder.started == 1
        assert pipeline.state == State.RECORDING
        # Simulate samples arriving while accessibility verification is in progress.
        recorder.audio[:100] = 0.75
        return original(expected)

    insertion.capture = slow_capture
    pipeline.press()
    assert np.all(recorder.audio[:100] == 0.75)
    pipeline.release()
    finish(callbacks)
    assert results[0][1] == "Inserted."


def test_window_change_during_microphone_start_keeps_manual_recovery(setup):
    pipeline, recorder, _, insertion, callbacks, _, results = setup
    original = recorder.start

    def changed_window():
        original()
        insertion.window = object()

    recorder.start = changed_window
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert not insertion.delivered
    assert results[0][0] == "Hello, world."


def test_release_and_transcription_do_not_wait_for_accessibility(setup):
    pipeline, _, _, insertion, callbacks, _, results = setup
    target = Future()
    insertion.capture = lambda expected: target
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert pipeline.state == State.TRANSCRIBING and not results
    target.set_result(123)
    finish(callbacks)
    assert results == [("Hello, world.", "Inserted.")]


def test_cancelled_session_discards_late_target(setup):
    pipeline, _, _, insertion, callbacks, _, results = setup
    target = Future()
    insertion.capture = lambda expected: target
    pipeline.press()
    pipeline.cancel()
    target.set_result(123)
    finish(callbacks)
    assert insertion.discarded == [123]
    assert pipeline.target is None and not results


def test_target_timeout_preserves_raw_transcript(setup):
    pipeline, _, _, insertion, callbacks, _, results = setup
    target = Future()
    insertion.capture = lambda expected: target
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    target.set_exception(TimeoutError())
    finish(callbacks)
    assert results[0][0] == "Hello, world."
    assert not insertion.delivered
