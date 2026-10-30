import queue
import threading
from concurrent.futures import Future
from unittest.mock import Mock

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

    def prepare(self):
        pass

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
    pipeline.executor.shutdown(wait=True)


def finish(callbacks):
    callbacks.get(timeout=5)()


@pytest.mark.parametrize("outcome", ["ready", "failure", "shutdown"])
def test_live_warmup_blocks_capture_and_recovers_without_polishing(setup, outcome):
    pipeline, recorder, recognizer, insertion, callbacks, changes, results = setup
    recognizer.preview_ready = False
    entered, release = threading.Event(), threading.Event()

    def warm():
        entered.set()
        assert release.wait(5)
        if outcome == "failure":
            raise RuntimeError("sensitive details")
        recognizer.preview_ready = True

    recognizer.warm_preview = Mock(side_effect=warm)
    pipeline.refiner = Mock()
    assert not pipeline.warm_live_preview()  # Opt-in only.
    pipeline.live_preview = True
    assert pipeline.warm_live_preview()
    assert entered.wait(5)
    assert pipeline.state == State.WARMING
    assert not pipeline.warm_live_preview()
    pipeline.press()
    pipeline.release()
    assert recorder.started == 0
    insertion.capture = Mock()
    if outcome == "shutdown":
        pipeline.shutdown()
    release.set()
    pipeline.executor.shutdown(wait=True)
    if outcome == "shutdown":
        assert callbacks.empty()
    else:
        finish(callbacks)
        assert pipeline.state == State.IDLE
        assert pipeline.warm_pending is None
        assert "sensitive" not in str(changes)
        if outcome == "ready":
            assert not pipeline.warm_live_preview()
        else:
            assert "could not be prepared" in changes[-1][1]
        pipeline.press()
        assert recorder.started == 1
        pipeline.cancel()
    assert not results
    pipeline.refiner.prepare.assert_not_called()
    pipeline.refiner.refine.assert_not_called()


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
    pipeline.executor.shutdown(wait=True)
    assert callbacks.empty()
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


def test_polishing_runs_off_owner_thread_and_preserves_raw_result(setup):
    pipeline, recorder, _, insertion, callbacks, changes, results = setup
    owner = threading.get_ident()
    raw = []
    pipeline.raw_result = raw.append

    def polish(text):
        assert threading.get_ident() != owner
        assert np.count_nonzero(recorder.audio) == 0
        return "Hello world!"

    backend = Mock()
    backend.refine.side_effect = polish
    pipeline.refiner = backend
    pipeline.press()
    pipeline.release()
    finish(callbacks)  # Polishing state is dispatched to the owner.
    finish(callbacks)
    assert State.POLISHING in [state for state, _ in changes]
    assert insertion.delivered == ["Hello world!"]
    assert raw == ["Hello, world."]
    assert results == [("Hello world!", "Polishing applied. Inserted.")]


@pytest.mark.parametrize("failure", ["timeout", "changed", "empty"])
def test_polishing_failure_inserts_raw_without_exposing_provider_exception(setup, failure):
    pipeline, _, _, insertion, callbacks, changes, results = setup
    backend = Mock()
    if failure == "timeout":
        backend.refine.side_effect = TimeoutError("private transcription in provider exception")
    else:
        backend.refine.return_value = "" if failure == "empty" else "Unrelated new content."
    pipeline.refiner = backend
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    finish(callbacks)
    assert insertion.delivered == ["Hello, world."]
    assert "using raw" in results[0][1]
    assert "private transcription" not in str(changes) + str(results)


def test_shutdown_during_polishing_cannot_deliver_late_result(setup):
    pipeline, _, _, insertion, callbacks, _, results = setup
    gate = threading.Event()
    started = threading.Event()
    backend = Mock()

    def polish(text):
        started.set()
        gate.wait(5)
        return text

    backend.refine.side_effect = polish
    backend.close.side_effect = gate.set
    pipeline.refiner = backend
    pipeline.press()
    pipeline.release()
    assert started.wait(5)
    pipeline.shutdown()
    finish(callbacks)
    pipeline.executor.shutdown(wait=True)
    assert callbacks.empty()
    assert not insertion.delivered and not results
    backend.close.assert_called_once()


def test_polishing_preparation_waits_until_recording_stops(setup):
    pipeline, recorder, _, _, callbacks, _, results = setup
    owner = threading.get_ident()
    started, gate = threading.Event(), threading.Event()
    backend = Mock()

    def prepare():
        assert threading.get_ident() != owner
        assert recorder.started == 1
        assert pipeline.state == State.TRANSCRIBING
        started.set()
        assert gate.wait(5)

    backend.prepare.side_effect = prepare
    backend.refine.side_effect = lambda text: text
    pipeline.refiner = backend
    try:
        pipeline.press()
        pipeline.executor.submit(lambda: None).result(timeout=5)
        assert not started.is_set()
        assert pipeline.state == State.RECORDING
        pipeline.release()
        assert started.wait(5)
        assert pipeline.state == State.TRANSCRIBING
    finally:
        gate.set()
    finish(callbacks)
    finish(callbacks)
    assert results[0][0] == "Hello, world."


def test_preparation_error_does_not_prevent_transcription_or_raw_fallback(setup):
    pipeline, _, _, _, callbacks, _, results = setup
    backend = Mock()
    backend.prepare.side_effect = OSError("private model-loading error")
    backend.refine.side_effect = OSError("private model-loading error")
    pipeline.refiner = backend
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    finish(callbacks)
    assert results[0][0] == "Hello, world."
    assert "using raw" in results[0][1] and "private" not in results[0][1]


def test_minimum_recording_duration_uses_actual_capture_rate(setup):
    pipeline, recorder, _, insertion, _, _, results = setup
    recorder.sample_rate = 48000
    recorder.audio = np.full(4800, 0.05, dtype=np.float32)  # 100 ms, below the 200 ms minimum.
    pipeline.press()
    pipeline.release()
    assert pipeline.state == State.IDLE and not results and not insertion.delivered
    assert not recorder.audio.any()


def test_speech_model_loading_waits_until_recording_stops(setup):
    pipeline, recorder, recognizer, _, callbacks, _, results = setup
    owner = threading.get_ident()
    started, gate = threading.Event(), threading.Event()
    calls = []

    def prepare():
        assert threading.get_ident() != owner
        assert recorder.started == 1
        assert pipeline.state == State.TRANSCRIBING
        calls.append(("prepare", threading.get_ident()))
        started.set()
        assert gate.wait(5)

    def transcribe(audio):
        calls.append(("transcribe", threading.get_ident()))
        return "Hello, world."

    recognizer.prepare = prepare
    recognizer.transcribe = transcribe
    try:
        pipeline.press()
        pipeline.executor.submit(lambda: None).result(timeout=5)
        assert not started.is_set()
        assert pipeline.state == State.RECORDING
        pipeline.release()
        assert started.wait(5)
        assert pipeline.state == State.TRANSCRIBING
        assert len(calls) == 1
    finally:
        gate.set()
    finish(callbacks)
    assert calls[0][1] == calls[1][1]
    assert results[0][0] == "Hello, world."


def test_speech_preparation_failure_defers_to_actual_transcription(setup):
    pipeline, _, recognizer, _, callbacks, changes, results = setup
    recognizer.prepare = Mock(side_effect=OSError("private loading failure"))
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    recognizer.prepare.assert_called_once()
    assert results[0][0] == "Hello, world."
    assert "private" not in str(changes)


def test_shutdown_during_speech_preparation_skips_polishing(setup):
    pipeline, _, recognizer, insertion, callbacks, _, results = setup
    started, gate = threading.Event(), threading.Event()
    backend = Mock()
    pipeline.refiner = backend

    def prepare():
        started.set()
        assert gate.wait(5)

    recognizer.prepare = prepare
    try:
        pipeline.press()
        pipeline.release()
        assert started.wait(5)
        pipeline.shutdown()
    finally:
        gate.set()
    pipeline.executor.shutdown(wait=True)
    backend.prepare.assert_not_called()
    assert callbacks.empty() and not results and not insertion.delivered


def test_release_timing_includes_preparation_and_owner_dispatch_wait(setup, monkeypatch):
    pipeline, _, recognizer, _, callbacks, _, results = setup
    clock = [0.0]
    monkeypatch.setattr("localphraser.pipeline.perf_counter", lambda: clock[0])
    pipeline.timing_result = Mock()

    def prepare():
        clock[0] = 1.0

    def transcribe(audio):
        clock[0] = 3.0
        return "Hello, world."

    recognizer.prepare = prepare
    recognizer.transcribe = transcribe
    # Queue the complete session before preparation can advance the test clock.
    gate = threading.Event()
    pipeline.executor.submit(lambda: gate.wait(5))
    try:
        pipeline.press()
        pipeline.release()
    finally:
        gate.set()
    pipeline.executor.submit(lambda: None).result(timeout=5)
    clock[0] = 5.0
    finish(callbacks)
    assert results[0][0] == "Hello, world."
    pipeline.timing_result.assert_called_once_with(2.0, 0, 5.0)


@pytest.mark.parametrize("fallback", [False, True])
def test_stage_timings_include_polishing_failure_time(setup, monkeypatch, fallback):
    pipeline, recorder, _, _, _, _, _ = setup
    clock = iter((10.0, 12.0, 15.0, 18.0))
    monkeypatch.setattr("localphraser.pipeline.perf_counter", lambda: next(clock))
    pipeline.refiner = Mock()
    if fallback:
        pipeline.refiner.refine.side_effect = TimeoutError()
    else:
        pipeline.refiner.refine.return_value = "Hello world!"
    result = pipeline.executor.submit(pipeline._transcribe, recorder.audio).result(timeout=5)
    assert result.recognition_seconds == 2.0 and result.polishing_seconds == 3.0
    assert ("using raw" in result.notice) == fallback


def test_segment_previews_dispatch_without_inserting_partial_text(setup):
    pipeline, _, recognizer, insertion, callbacks, _, results = setup
    previews = []
    pipeline.partial_result = previews.append

    def stream(audio, partial):
        partial("Hello")
        partial("Hello world")
        assert not insertion.delivered
        return "Hello, world."

    recognizer.transcribe_stream = stream
    pipeline.press()
    pipeline.release()
    pipeline.executor.submit(lambda: None).result(timeout=5)
    assert not previews and not results
    finish(callbacks)
    finish(callbacks)
    assert previews == ["Hello", "Hello world"] and not insertion.delivered
    finish(callbacks)
    assert insertion.delivered == ["Hello, world."]


def test_queued_preview_is_ignored_after_shutdown(setup):
    pipeline, _, _, _, callbacks, _, _ = setup
    pipeline.partial_result = Mock()
    pipeline.state = State.TRANSCRIBING
    pipeline._partial("Hello")
    pipeline.shutdown()
    finish(callbacks)
    pipeline.partial_result.assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_async_delivery_leaves_owner_responsive_until_completion(setup, failure):
    pipeline, _, _, insertion, callbacks, _, results = setup
    delivery = Future()
    insertion.insert_async = Mock(return_value=delivery)
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert pipeline.state == State.INSERTING and not results
    if failure:
        delivery.set_exception(TimeoutError())
    else:
        delivery.set_result(None)
    assert not results
    finish(callbacks)
    assert pipeline.state == State.IDLE and results[0][0] == "Hello, world."
    assert (results[0][1] == "Inserted.") != failure


def test_async_delivery_completion_is_ignored_after_shutdown(setup):
    pipeline, _, _, insertion, callbacks, _, results = setup
    delivery = Future()
    insertion.insert_async = Mock(return_value=delivery)
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert pipeline.state == State.INSERTING
    pipeline.shutdown()
    delivery.set_result(None)
    assert callbacks.empty() and not results


@pytest.mark.parametrize("case", ["changed", "timeout", "unavailable", "applied", "unchanged"])
def test_polishing_notice_reports_actual_outcome(setup, case):
    pipeline, recorder, _, _, _, _, _ = setup
    backend = Mock()
    if case == "timeout":
        backend.refine.side_effect = TimeoutError("private detail")
    elif case == "unavailable":
        backend.refine.side_effect = RuntimeError("private detail")
    else:
        backend.refine.return_value = {
            "changed": "Goodbye world!",
            "applied": "Hello world!",
            "unchanged": "Hello, world.",
        }[case]
    pipeline.refiner = backend
    result = pipeline.executor.submit(pipeline._transcribe, recorder.audio).result(timeout=5)
    expected = {
        "changed": "suggested word changes",
        "timeout": "timed out",
        "unavailable": "unavailable",
        "applied": "applied",
        "unchanged": "no changes needed",
    }[case]
    assert expected in result.notice and "private" not in result.notice
    if case in ("changed", "timeout", "unavailable"):
        assert result.text == result.raw


def enable_live_preview(pipeline, recorder, recognizer):
    pipeline.live_preview = True
    pipeline.live_result = Mock()
    recognizer.preview_ready = True
    recognizer.preview = Mock(return_value="Recent draft words.")
    copies = []

    def snapshot():
        copy = np.full(16000, 0.05, dtype=np.float32)
        copies.append(copy)
        return copy

    recorder.preview_audio = Mock(side_effect=snapshot)
    pipeline.press()
    pipeline.preview_after = 0
    return copies


def test_live_preview_is_draft_only_and_clears_snapshot(setup):
    pipeline, recorder, recognizer, insertion, callbacks, _, results = setup
    copies = enable_live_preview(pipeline, recorder, recognizer)
    pipeline.request_live_preview()
    pipeline.preview_pending.result(timeout=5)
    finish(callbacks)
    pipeline.live_result.assert_called_once_with("Recent draft words.")
    assert not copies[0].any() and not insertion.delivered and not results
    assert pipeline.state == State.RECORDING


@pytest.mark.parametrize("reason", ["off", "cold", "idle", "interval", "silent"])
def test_live_preview_skips_ineligible_capture(setup, reason):
    pipeline, recorder, recognizer, _, callbacks, _, _ = setup
    copies = enable_live_preview(pipeline, recorder, recognizer)
    if reason == "off":
        pipeline.live_preview = False
    elif reason == "cold":
        recognizer.preview_ready = False
    elif reason == "idle":
        pipeline.cancel()
    elif reason == "interval":
        pipeline.preview_after = float("inf")
    else:
        recorder.preview_audio.side_effect = lambda: np.zeros(16000, dtype=np.float32)
    pipeline.request_live_preview()
    assert pipeline.preview_pending is None and callbacks.empty()
    recognizer.preview.assert_not_called()
    assert not copies


def test_live_preview_has_one_request_and_ignores_cancelled_session(setup):
    pipeline, recorder, recognizer, _, callbacks, _, _ = setup
    copies = enable_live_preview(pipeline, recorder, recognizer)
    entered, gate = threading.Event(), threading.Event()

    def preview(audio):
        entered.set()
        assert gate.wait(5)
        return "Stale words."

    recognizer.preview.side_effect = preview
    pipeline.request_live_preview()
    future = pipeline.preview_pending
    try:
        assert entered.wait(5)
        pipeline.preview_after = 0
        pipeline.request_live_preview()
        assert len(copies) == 1
        pipeline.cancel()
        pipeline.press()
    finally:
        gate.set()
    future.result(timeout=5)
    finish(callbacks)
    pipeline.live_result.assert_not_called()
    assert pipeline.preview_pending is None and not copies[0].any()


def test_live_preview_failure_keeps_final_transcription_available(setup):
    pipeline, recorder, recognizer, _, callbacks, _, results = setup
    copies = enable_live_preview(pipeline, recorder, recognizer)
    recognizer.preview.side_effect = RuntimeError("private detail")
    pipeline.request_live_preview()
    future = pipeline.preview_pending
    with pytest.raises(RuntimeError):
        future.result(timeout=5)
    finish(callbacks)
    assert pipeline.preview_disabled and not copies[0].any()
    pipeline.live_result.assert_called_once_with("")
    pipeline.release()
    finish(callbacks)
    assert results[0][0] == "Hello, world."


def test_queued_live_preview_is_skipped_after_release_and_audio_is_cleared(setup):
    pipeline, recorder, recognizer, _, callbacks, _, results = setup
    copies = enable_live_preview(pipeline, recorder, recognizer)
    gate = threading.Event()
    pipeline.executor.submit(lambda: gate.wait(5))
    try:
        pipeline.request_live_preview()
        preview = pipeline.preview_pending
        pipeline.release()
    finally:
        gate.set()
    preview.result(timeout=5)
    finish(callbacks)  # Stale draft must not be displayed during final processing.
    finish(callbacks)
    recognizer.preview.assert_not_called()
    pipeline.live_result.assert_not_called()
    assert not copies[0].any() and results[0][0] == "Hello, world."


def test_live_preview_shutdown_clears_snapshot_and_cannot_display_later(setup):
    pipeline, recorder, recognizer, _, callbacks, _, results = setup
    copies = enable_live_preview(pipeline, recorder, recognizer)
    entered, gate = threading.Event(), threading.Event()

    def preview(audio):
        entered.set()
        assert gate.wait(5)
        return "Late draft."

    recognizer.preview.side_effect = preview
    pipeline.request_live_preview()
    future = pipeline.preview_pending
    try:
        assert entered.wait(5)
        pipeline.shutdown()
    finally:
        gate.set()
    future.result(timeout=5)
    assert not copies[0].any() and callbacks.empty() and not results
    pipeline.live_result.assert_not_called()


def test_live_preview_resamples_off_owner_and_clears_both_buffers(setup, monkeypatch):
    pipeline, recorder, recognizer, _, callbacks, _, _ = setup
    enable_live_preview(pipeline, recorder, recognizer)
    recorder.sample_rate = 48000
    captured = np.full(48000, 0.05, dtype=np.float32)
    converted = np.ones(16000, dtype=np.float32)
    recorder.preview_audio.side_effect = lambda: captured
    owner = threading.get_ident()

    def convert(audio, rate):
        assert threading.get_ident() != owner and audio is captured and rate == 48000
        return converted

    monkeypatch.setattr("localphraser.pipeline.resample_audio", convert)
    pipeline.request_live_preview()
    pipeline.preview_pending.result(timeout=5)
    finish(callbacks)
    assert not captured.any() and not converted.any()
    recognizer.preview.assert_called_once_with(converted)


def test_snapshot_failure_only_disables_preview_for_current_recording(setup):
    pipeline, recorder, recognizer, _, callbacks, _, _ = setup
    enable_live_preview(pipeline, recorder, recognizer)
    recorder.preview_audio.side_effect = RuntimeError("private snapshot error")
    pipeline.request_live_preview()
    assert pipeline.preview_disabled and pipeline.state == State.RECORDING
    assert callbacks.empty()
    pipeline.cancel()
    pipeline.press()
    assert not pipeline.preview_disabled


def test_shutdown_zeroes_preview_cancelled_before_worker_start(setup):
    pipeline, recorder, recognizer, _, callbacks, _, _ = setup
    copies = enable_live_preview(pipeline, recorder, recognizer)
    gate = threading.Event()
    pipeline.executor.submit(lambda: gate.wait(5))
    try:
        pipeline.request_live_preview()
        future = pipeline.preview_pending
        pipeline.shutdown()
        assert future.cancelled() and not copies[0].any()
        assert callbacks.empty()
    finally:
        gate.set()


def test_shutdown_zeroes_final_audio_cancelled_during_model_preparation(setup):
    pipeline, recorder, recognizer, _, callbacks, _, results = setup
    entered, gate = threading.Event(), threading.Event()

    def prepare():
        entered.set()
        assert gate.wait(5)

    recognizer.prepare = prepare
    try:
        pipeline.press()
        pipeline.release()
        assert entered.wait(5)
        pipeline.shutdown()
        assert not recorder.audio.any() and callbacks.empty() and not results
    finally:
        gate.set()
