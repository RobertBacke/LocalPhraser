import queue
import threading
from concurrent.futures import Future
from unittest.mock import Mock

import numpy as np
import pytest

from localphraser.pipeline import QUIET_MESSAGE, TAIL_SECONDS, Dictation, State


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


def test_app_identity_callback_runs_after_audio_starts_without_requiring_insertion(setup):
    pipeline, recorder, _, insertion, _, _, _ = setup
    pipeline.auto_insert = False
    seen = []

    def started(snapshot):
        assert recorder.started == 1
        seen.append(snapshot)

    pipeline.recording_started = started
    pipeline.press()
    assert seen == [insertion.window]
    assert pipeline.target is None


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


def test_start_up_warming_needs_only_warm_on_start_and_leaves_live_preview_off(setup):
    pipeline, recorder, recognizer, _, callbacks, changes, _ = setup
    recognizer.preview_ready = False

    def warm():
        recognizer.preview_ready = True

    recognizer.warm_preview = Mock(side_effect=warm)
    recognizer.transcribe_preview = Mock(return_value="never")
    live = Mock()
    pipeline.live_result = live
    assert not pipeline.warm_live_preview()  # Neither flag is set.
    pipeline.warm_on_start = True
    assert pipeline.warm_live_preview()
    assert pipeline.state == State.WARMING
    pipeline.executor.shutdown(wait=True)
    finish(callbacks)
    assert pipeline.state == State.IDLE
    recognizer.warm_preview.assert_called_once()
    pipeline.press()
    pipeline.preview_after = 0
    recorder.preview_audio = lambda: np.full(16000, 0.05, dtype=np.float32)
    pipeline.request_live_preview()
    assert pipeline.preview_pending is None
    recognizer.transcribe_preview.assert_not_called()
    live.assert_not_called()
    pipeline.cancel()


@pytest.mark.parametrize(
    ("live_preview", "message"),
    [
        (True, "Live preview could not be prepared. Dictation will try after recording."),
        (False, "Speech model could not be prepared. Dictation will try again after recording."),
    ],
)
def test_warm_failure_names_live_preview_only_when_it_is_on(setup, live_preview, message):
    pipeline, _, recognizer, _, callbacks, changes, _ = setup
    recognizer.preview_ready = False
    recognizer.warm_preview = Mock(side_effect=RuntimeError("fixture failure"))
    pipeline.live_preview = live_preview
    pipeline.warm_on_start = not live_preview
    assert pipeline.warm_live_preview()
    pipeline.executor.shutdown(wait=True)
    finish(callbacks)
    assert changes[-1] == (State.IDLE, message)


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


class CountingRecorder(FakeRecorder):
    def __init__(self):
        super().__init__()
        self.stopped = 0

    def stop(self):
        self.stopped += 1
        return super().stop()


@pytest.fixture
def tail_setup():
    recorder, recognizer, insertion = CountingRecorder(), FakeRecognizer(), FakeInsertion()
    callbacks = queue.Queue()
    scheduled, changes, results = [], [], []
    pipeline = Dictation(
        recorder,
        recognizer,
        insertion,
        callbacks.put,
        lambda s, m: changes.append((s, m)),
        lambda t, n: results.append((t, n)),
        tail_seconds=0.25,
        schedule=lambda delay, callback: scheduled.append((delay, callback)),
    )
    pipeline.callbacks, pipeline.results = callbacks, results
    yield pipeline, recorder, scheduled, changes
    pipeline.shutdown()
    pipeline.executor.shutdown(wait=True)


def test_tail_seconds_constant():
    assert TAIL_SECONDS == 0.25


def test_release_keeps_capturing_for_the_tail_then_stops(tail_setup):
    pipeline, recorder, scheduled, changes = tail_setup
    pipeline.press()
    pipeline.release()
    assert recorder.stopped == 0 and pipeline.state == State.TRANSCRIBING
    assert [delay for delay, _ in scheduled] == [0.25]
    scheduled[0][1]()
    assert recorder.stopped == 1
    finish(pipeline.callbacks)
    assert pipeline.results == [("Hello, world.", "Inserted.")]
    assert pipeline.state == State.IDLE
    # The tail does not announce TRANSCRIBING a second time when capture stops.
    assert [state for state, _ in changes].count(State.TRANSCRIBING) == 1


def test_released_at_is_the_moment_of_release_not_the_end_of_the_tail(tail_setup):
    pipeline, _, scheduled, _ = tail_setup
    pipeline.press()
    pipeline.release()
    released_at = pipeline.released_at
    assert released_at is not None
    scheduled[0][1]()
    assert pipeline.released_at == released_at


def test_second_release_during_tail_is_ignored(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    pipeline.press()
    pipeline.release()
    pipeline.release()
    assert len(scheduled) == 1
    scheduled[0][1]()
    scheduled[0][1]()
    assert recorder.stopped == 1


def test_press_during_tail_does_not_start_another_recording(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    pipeline.press()
    pipeline.release()
    pipeline.press()
    assert recorder.started == 1 and pipeline.state == State.TRANSCRIBING
    scheduled[0][1]()
    assert recorder.stopped == 1


def test_cancel_during_tail_stops_capture_and_inserts_nothing(tail_setup):
    pipeline, recorder, scheduled, changes = tail_setup
    pipeline.press()
    pipeline.release()
    pipeline.cancel()
    assert recorder.cancelled == 1 and pipeline.state == State.IDLE
    assert changes[-1] == (State.IDLE, "Recording cancelled.")
    assert pipeline.target is None
    scheduled[0][1]()
    assert recorder.stopped == 0
    assert pipeline.callbacks.empty() and pipeline.results == []


def test_stale_tail_callback_from_an_earlier_recording_does_nothing(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    pipeline.press()
    pipeline.release()
    pipeline.cancel()
    pipeline.press()
    pipeline.release()
    assert len(scheduled) == 2
    scheduled[0][1]()
    assert recorder.stopped == 0 and pipeline.state == State.TRANSCRIBING
    scheduled[1][1]()
    assert recorder.stopped == 1


def test_shutdown_during_tail_does_not_stop_or_submit(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    pipeline.press()
    pipeline.release()
    pipeline.shutdown()
    scheduled[0][1]()
    assert recorder.stopped == 0
    assert pipeline.callbacks.empty() and pipeline.results == []


def test_full_buffer_skips_the_tail(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    recorder.full = threading.Event()
    recorder.full.set()
    pipeline.press()
    pipeline.release()
    assert scheduled == [] and recorder.stopped == 1


def test_silent_recording_after_tail_reports_no_speech(tail_setup):
    pipeline, recorder, scheduled, changes = tail_setup
    recorder.audio = np.zeros(16000, dtype=np.float32)
    pipeline.press()
    pipeline.release()
    scheduled[0][1]()
    assert changes[-1] == (State.IDLE, "No speech captured.")


def test_default_schedule_posts_to_the_owner_thread():
    recorder, recognizer, insertion = CountingRecorder(), FakeRecognizer(), FakeInsertion()
    callbacks = queue.Queue()
    pipeline = Dictation(
        recorder,
        recognizer,
        insertion,
        callbacks.put,
        lambda s, m: None,
        lambda t, n: None,
        tail_seconds=0.01,
    )
    owner = threading.get_ident()
    try:
        pipeline.press()
        pipeline.release()
        assert recorder.stopped == 0
        callback = callbacks.get(timeout=2)
        timer = pipeline.tail_timer
        assert timer is not None and timer.daemon and timer.ident != owner
        assert recorder.stopped == 0  # Queued for the owner thread, not run on the timer.
        callback()
        assert recorder.stopped == 1
        timer.join(2)
        assert not timer.is_alive()
    finally:
        pipeline.shutdown()
        pipeline.executor.shutdown(wait=True)


def test_shutdown_cancels_the_default_tail_timer():
    recorder, recognizer, insertion = CountingRecorder(), FakeRecognizer(), FakeInsertion()
    callbacks = queue.Queue()
    pipeline = Dictation(
        recorder,
        recognizer,
        insertion,
        callbacks.put,
        lambda s, m: None,
        lambda t, n: None,
        tail_seconds=30,
    )
    pipeline.press()
    pipeline.release()
    timer = pipeline.tail_timer
    assert timer is not None
    pipeline.shutdown()
    pipeline.executor.shutdown(wait=True)
    timer.join(2)
    assert not timer.is_alive() and callbacks.empty() and recorder.stopped == 0


def test_tail_that_cannot_be_scheduled_stops_capture_at_once(tail_setup):
    pipeline, recorder, _, changes = tail_setup

    def refuse(delay, callback):
        raise RuntimeError("can't start new thread")

    pipeline.schedule = refuse
    pipeline.press()
    pipeline.release()
    assert recorder.stopped == 1 and not pipeline.tail_pending
    finish(pipeline.callbacks)
    assert pipeline.results == [("Hello, world.", "Inserted.")]
    assert [state for state, _ in changes].count(State.TRANSCRIBING) == 1


def dictate(pipeline, callbacks):
    pipeline.press()
    pipeline.release()
    while pipeline.state not in (State.IDLE, State.ERROR) or callbacks.qsize():
        finish(callbacks)


def test_quiet_input_adds_notice_to_result_but_not_to_state(setup):
    pipeline, recorder, _, _, callbacks, changes, results = setup
    recorder.audio = np.full(16000, 0.005, dtype=np.float32)
    dictate(pipeline, callbacks)
    assert results[-1] == ("Hello, world.", f"Inserted. {QUIET_MESSAGE}")
    assert changes[-1] == (State.IDLE, "Inserted.")


def test_normal_input_adds_no_notice(setup):
    pipeline, _, _, _, callbacks, _, results = setup
    dictate(pipeline, callbacks)
    assert results[-1] == ("Hello, world.", "Inserted.")


def test_quiet_input_with_no_text_replaces_no_speech_message(setup):
    pipeline, recorder, recognizer, _, callbacks, changes, results = setup
    recognizer.transcribe = lambda audio: ""
    recorder.audio = np.full(16000, 0.005, dtype=np.float32)
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert changes[-1] == (State.IDLE, QUIET_MESSAGE)
    assert results == []


def test_no_text_with_normal_input_keeps_no_speech_message(setup):
    pipeline, recorder, recognizer, _, callbacks, changes, _ = setup
    recognizer.transcribe = lambda audio: ""
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert changes[-1] == (State.IDLE, "No speech recognized.")


def test_click_does_not_hide_quiet_input(setup):
    pipeline, recorder, _, _, callbacks, _, results = setup
    recorder.audio = np.full(16000, 0.005, dtype=np.float32)
    recorder.audio[8000:8100] = 0.9
    dictate(pipeline, callbacks)
    assert QUIET_MESSAGE in results[-1][1]


def test_silent_capture_keeps_no_speech_captured_message(setup):
    pipeline, recorder, _, _, _, changes, _ = setup
    recorder.audio = np.zeros(16000, dtype=np.float32)
    pipeline.press()
    pipeline.release()
    assert changes[-1] == (State.IDLE, "No speech captured.")


def test_quiet_input_notice_is_appended_after_polishing_notice(setup):
    pipeline, recorder, _, _, callbacks, changes, results = setup
    pipeline.refiner = Mock()
    pipeline.refiner.refine.return_value = "Hello, world."
    recorder.audio = np.full(16000, 0.005, dtype=np.float32)
    dictate(pipeline, callbacks)
    assert results[-1][1] == f"Polishing checked; no changes needed. Inserted. {QUIET_MESSAGE}"
    assert changes[-1][1] == "Polishing checked; no changes needed. Inserted."


def test_quiet_notice_is_appended_to_insertion_failure_notice(setup):
    pipeline, recorder, _, insertion, callbacks, _, results = setup
    insertion.insert_error = True
    recorder.audio = np.full(16000, 0.005, dtype=np.float32)
    dictate(pipeline, callbacks)
    notice = "Insertion was not confirmed. Check the target before copying the transcript."
    assert results[-1][1] == f"{notice} {QUIET_MESSAGE}"


def test_quiet_recording_does_not_leak_into_the_next_recording(setup):
    pipeline, recorder, _, _, callbacks, _, results = setup
    recorder.audio = np.full(16000, 0.005, dtype=np.float32)
    dictate(pipeline, callbacks)
    assert QUIET_MESSAGE in results[-1][1]
    recorder.audio = np.full(16000, 0.05, dtype=np.float32)
    dictate(pipeline, callbacks)
    assert results[-1] == ("Hello, world.", "Inserted.")


def test_cancelled_quiet_recording_does_not_leak_into_the_next_recording(setup):
    pipeline, recorder, _, _, callbacks, _, results = setup
    recorder.audio = np.full(16000, 0.005, dtype=np.float32)
    dictate(pipeline, callbacks)
    pipeline.press()
    pipeline.cancel()
    recorder.audio = np.full(16000, 0.05, dtype=np.float32)
    dictate(pipeline, callbacks)
    assert results[-1] == ("Hello, world.", "Inserted.")


def test_quiet_input_is_measured_after_the_tail(tail_setup):
    pipeline, recorder, scheduled, changes = tail_setup
    recorder.audio = np.full(16000, 0.005, dtype=np.float32)
    pipeline.press()
    pipeline.release()
    scheduled[0][1]()
    finish(pipeline.callbacks)
    assert pipeline.results[-1] == ("Hello, world.", f"Inserted. {QUIET_MESSAGE}")


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            ValueError("Selection must be a single empty caret."),
            "Selection must be a single empty caret.",
        ),
        (TimeoutError("Target verification timed out."), "Target verification timed out."),
        (ValueError("no full stop"), "no full stop."),
        (TimeoutError(), "TimeoutError."),
        (KeyError("private words"), "KeyError."),
    ],
)
def test_target_failure_notice_says_why_without_foreign_text(setup, error, reason):
    pipeline, _, _, insertion, callbacks, _, results = setup
    target = Future()
    insertion.capture = lambda expected: target
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    target.set_exception(error)
    finish(callbacks)
    assert results[0] == (
        "Hello, world.",
        f"Target could not be verified. {reason} Open Latest transcript to copy.",
    )
    assert "private words" not in results[0][1]


def test_immediate_target_failure_notice_says_why(setup):
    pipeline, _, _, insertion, callbacks, _, results = setup
    insertion.capture_error = True
    pipeline.press()
    pipeline.release()
    finish(callbacks)
    assert results[0][1] == (
        "Target could not be verified. selected text. Open Latest transcript to copy."
    )
