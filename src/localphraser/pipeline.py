"""Serial lifecycle independent of Qt, Windows, and the selected ASR backend."""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol

import numpy as np

from localphraser.audio import SAMPLE_RATE, Audio, resample_audio
from localphraser.recognition import Recognizer
from localphraser.refinement import RefinementRejected, Refiner, preserve_words


class State(StrEnum):
    IDLE = "Ready"
    WARMING = "Preparing speech model"
    RECORDING = "Listening"
    TRANSCRIBING = "Transcribing"
    POLISHING = "Polishing"
    INSERTING = "Inserting"
    ERROR = "Error"


class Capture(Protocol):
    def start(self) -> None: ...
    def stop(self) -> Audio: ...
    def cancel(self) -> None: ...
    def close(self) -> None: ...


class Insertion(Protocol):
    def snapshot(self) -> Any: ...
    def capture(self, expected: Any) -> Any: ...
    def insert(self, target: Any, text: str) -> None: ...
    def discard(self, target: Any) -> None: ...


@dataclass(frozen=True)
class Transcript:
    raw: str
    text: str
    notice: str = ""
    recognition_seconds: float = 0
    polishing_seconds: float = 0


class Dictation:
    """Public methods run on the UI thread; inference and target verification use workers.

    dispatch must queue a callback onto the owner thread. No UI calls from the worker.
    """

    def __init__(
        self,
        recorder: Capture,
        recognizer: Recognizer,
        insertion: Insertion,
        dispatch: Callable[[Callable[[], None]], None],
        changed: Callable[[State, str], None],
        result: Callable[[str, str], None],
        auto_insert: bool = True,
        refiner: Refiner | None = None,
        raw_result: Callable[[str], None] | None = None,
        timing_result: Callable[[float, float, float], None] | None = None,
        partial_result: Callable[[str], None] | None = None,
        live_preview: bool = False,
        live_result: Callable[[str], None] | None = None,
    ):
        self.recorder = recorder
        self.recognizer = recognizer
        self.insertion = insertion
        self.dispatch = dispatch
        self.changed = changed
        self.result = result
        self.auto_insert = auto_insert
        self.refiner = refiner
        self.raw_result = raw_result
        self.timing_result = timing_result
        self.partial_result = partial_result
        self.live_preview = live_preview
        self.live_result = live_result
        self.preview_pending: Future[str] | None = None
        self.warm_pending: Future[Any] | None = None
        self.preview_after = 0.0
        self.preview_disabled = False
        self.released_at: float | None = None
        self.state = State.IDLE
        self.target: Any = None
        self.target_future: Future[Any] | None = None
        self.pending_transcription: Future[Transcript] | None = None
        self.generation = 0
        self.target_error = ""
        self.closed = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transcription")

    def _state(self, state: State, message: str = "") -> None:
        self.state = state
        self.changed(state, message)

    def _post(self, callback: Callable[[], None]) -> None:
        if self.closed:
            return
        try:
            self.dispatch(callback)
        except RuntimeError:
            if not self.closed:
                raise

    def _audio_done(self, future: Future[Any], audio: Audio, callback: Callable[[], None]) -> None:
        # A cancelled queued task never reaches its worker-side finally block.
        if future.cancelled():
            audio.fill(0)
        self._post(callback)

    def warm_live_preview(self) -> bool:
        warm = getattr(self.recognizer, "warm_preview", None)
        if (
            self.closed
            or not self.live_preview
            or self.state != State.IDLE
            or self.warm_pending is not None
            or getattr(self.recognizer, "preview_ready", False) is True
            or not callable(warm)
        ):
            return False
        self._state(State.WARMING)
        future = self.executor.submit(warm)
        self.warm_pending = future
        future.add_done_callback(lambda f: self._post(lambda: self._warm_finished(f)))
        return True

    def _warm_finished(self, future: Future[Any]) -> None:
        if self.closed:
            return
        self.warm_pending = None
        try:
            future.result()
        except Exception:
            self._state(
                State.IDLE,
                "Live preview could not be prepared. Dictation will try after recording.",
            )
            return
        self._state(State.IDLE)

    def press(self) -> None:
        if self.closed or self.state != State.IDLE:
            return
        self.target = None
        self.target_error = ""
        self.generation += 1
        snapshot = None
        if self.auto_insert:
            try:
                snapshot = self.insertion.snapshot()
            except Exception:
                self.target_error = "Target could not be verified. Open Latest transcript to copy."
        try:
            self.recorder.start()
            self.preview_after = perf_counter() + 2 if self.live_preview else 0
            self.preview_disabled = False
            self._state(State.RECORDING)
        except Exception:
            self.recorder.cancel()
            self._error("Cannot open microphone. Check device and Windows microphone permissions.")
            return
        # Audio is already buffered while potentially slow accessibility checks run.
        if self.auto_insert and snapshot is not None:
            try:
                target = self.insertion.capture(snapshot)
                if isinstance(target, Future):
                    self.target_future = target
                    generation = self.generation
                    target.add_done_callback(lambda f: self._target_completed(f, generation))
                elif self.state == State.RECORDING:
                    self.target = target
            except Exception:
                self.target_error = "Target could not be verified. Open Latest transcript to copy."

    def request_live_preview(self) -> None:
        if (
            self.closed
            or self.state != State.RECORDING
            or not self.live_preview
            or self.live_result is None
            or self.preview_disabled
            or self.preview_pending is not None
            or getattr(self.recognizer, "preview_ready", False) is not True
            or perf_counter() < self.preview_after
        ):
            return
        self.preview_after = perf_counter() + 2
        snapshot = getattr(self.recorder, "preview_audio", None)
        if not callable(snapshot):
            return
        try:
            audio = snapshot()
        except Exception:
            self.preview_disabled = True
            self.live_result("")
            return
        rate = getattr(self.recorder, "sample_rate", SAMPLE_RATE)
        if audio.size < rate or np.max(np.abs(audio), initial=0) < 0.001:
            audio.fill(0)
            return
        generation = self.generation
        future = self.executor.submit(self._live_preview, audio, rate, generation)
        self.preview_pending = future
        future.add_done_callback(
            lambda f: self._audio_done(f, audio, lambda: self._live_finished(f, generation))
        )

    def _live_preview(self, audio: Audio, sample_rate: int, generation: int) -> str:
        captured = audio
        try:
            if self.closed or self.state != State.RECORDING or generation != self.generation:
                return ""
            if sample_rate != SAMPLE_RATE:
                audio = resample_audio(captured, sample_rate)
            preview = getattr(self.recognizer, "preview", None)
            text = preview(audio) if callable(preview) else ""
            return text.strip() if isinstance(text, str) else ""
        finally:
            audio.fill(0)
            if captured is not audio:
                captured.fill(0)

    def _live_finished(self, future: Future[str], generation: int) -> None:
        if self.preview_pending is future:
            self.preview_pending = None
        if self.closed or self.state != State.RECORDING or generation != self.generation:
            return
        try:
            text = future.result()
        except Exception:
            self.preview_disabled = True
            text = ""
        if self.live_result is not None:
            self.live_result(text)

    def _prepare_models(self) -> None:
        if self.closed:
            return
        try:
            self.recognizer.prepare()
        except Exception:
            # Transcription retries and reports loading failures after recording ends.
            pass
        if self.refiner is not None and not self.closed:
            # Model imports/loading can starve microphone callbacks on cold start.
            # Prepare only after capture has stopped; Raw mode never starts it.
            self.refiner.prepare()

    def _target_completed(self, future: Future[Any], generation: int) -> None:
        if self.closed:
            try:
                self.insertion.discard(future.result())
            except Exception:
                pass
            return
        self._post(lambda: self._target_ready(future, generation))

    def _target_ready(self, future: Future[Any], generation: int) -> None:
        if generation != self.generation or self.closed:
            try:
                self.insertion.discard(future.result())
            except Exception:
                pass
            return
        self.target_future = None
        try:
            self.target = future.result()
        except Exception:
            self.target_error = "Target could not be verified. Open Latest transcript to copy."
        if self.pending_transcription is not None:
            pending = self.pending_transcription
            self.pending_transcription = None
            self._finish(pending)

    def _clear_target(self) -> None:
        self.generation += 1
        if self.target is not None:
            self.insertion.discard(self.target)
        self.target = None
        self.target_future = None
        self.pending_transcription = None

    def release(self) -> None:
        if self.closed or self.state != State.RECORDING:
            return
        audio = None
        try:
            audio = self.recorder.stop()
            sample_rate = getattr(self.recorder, "sample_rate", SAMPLE_RATE)
            if audio.size < sample_rate // 5 or np.max(np.abs(audio), initial=0) < 0.001:
                audio.fill(0)
                self._clear_target()
                self._state(State.IDLE, "No speech captured.")
                return
            self._state(State.TRANSCRIBING)
            self.released_at = perf_counter()
            self.executor.submit(self._prepare_models)
            future = self.executor.submit(self._transcribe, audio, sample_rate)
            captured = audio
            future.add_done_callback(
                lambda f: self._audio_done(f, captured, lambda: self._finish(f))
            )
        except Exception:
            if audio is not None:
                audio.fill(0)
            self.recorder.cancel()
            self._error("Recording failed. Check the microphone and try again.")

    def _transcribe(self, audio: Audio, sample_rate: int = SAMPLE_RATE) -> Transcript:
        started = perf_counter()
        captured = audio
        try:
            if sample_rate != SAMPLE_RATE:
                audio = resample_audio(captured, sample_rate)
            if self.partial_result is not None:
                raw = self.recognizer.transcribe_stream(audio, self._partial).strip()
            else:
                raw = self.recognizer.transcribe(audio).strip()
        finally:
            audio.fill(0)
            if captured is not audio:
                captured.fill(0)
        recognition_seconds = perf_counter() - started
        if not raw or self.refiner is None or self.closed:
            return Transcript(raw, raw, recognition_seconds=recognition_seconds)
        self._post(lambda: None if self.closed else self._state(State.POLISHING))
        started = perf_counter()
        notice = ""
        try:
            polished = self.refiner.refine(raw)
            if not preserve_words(raw, polished):
                raise RefinementRejected("Refinement changed words.")
            notice = (
                "Polishing applied." if polished != raw else "Polishing checked; no changes needed."
            )
        except RefinementRejected:
            polished = raw
            notice = "Polishing suggested word changes; using raw transcription."
        except TimeoutError:
            polished = raw
            notice = "Polishing timed out; using raw transcription."
        except Exception:
            polished = raw
            notice = "Polishing skipped or unavailable; using raw transcription."
        return Transcript(raw, polished, notice, recognition_seconds, perf_counter() - started)

    def _partial(self, text: str) -> None:
        self._post(
            lambda: (
                self.partial_result(text)
                if not self.closed and self.state == State.TRANSCRIBING and self.partial_result
                else None
            )
        )

    def _finish(self, future: Future[Transcript]) -> None:
        if self.closed:
            return
        try:
            transcript = future.result()
            text = transcript.text.strip()
        except Exception:
            self._error("Transcription failed. Check the speech model and microphone settings.")
            return
        if not text:
            self._clear_target()
            self._state(State.IDLE, "No speech recognized.")
            return
        if self.target_future is not None:
            self.pending_transcription = future
            return
        notice = self.target_error or "Automatic insertion is disabled. Copy the latest transcript."
        if self.auto_insert and self.target is not None:
            self._state(State.INSERTING)
            try:
                asynchronous = getattr(self.insertion, "insert_async", None)
                if callable(asynchronous):
                    delivery = asynchronous(self.target, text)
                    delivery.add_done_callback(
                        lambda f: self._post(lambda: self._inserted(f, transcript))
                    )
                    return
                self.insertion.insert(self.target, text)
                notice = "Inserted."
            except Exception:
                # Never retry: a partial SendInput may already have inserted some text.
                notice = (
                    "Insertion was not confirmed. Check the target before copying the transcript."
                )
        self._deliver_result(transcript, notice)

    def _inserted(self, future: Future[None], transcript: Transcript) -> None:
        if self.closed:
            return
        try:
            future.result()
            notice = "Inserted."
        except Exception:
            notice = "Insertion was not confirmed. Check the target before copying the transcript."
        self._deliver_result(transcript, notice)

    def _deliver_result(self, transcript: Transcript, notice: str) -> None:
        if self.auto_insert and notice != "Inserted.":
            self._state(State.ERROR, notice)
        self._clear_target()
        if self.raw_result is not None:
            self.raw_result(transcript.raw)
        if transcript.notice:
            notice = f"{transcript.notice} {notice}"
        self.result(transcript.text.strip(), notice)
        if self.timing_result is not None:
            total = (
                perf_counter() - self.released_at
                if self.released_at is not None
                else transcript.recognition_seconds + transcript.polishing_seconds
            )
            self.timing_result(transcript.recognition_seconds, transcript.polishing_seconds, total)
        self._state(State.IDLE, notice)

    def _error(self, message: str) -> None:
        self._clear_target()
        self._state(State.ERROR, message)
        self._state(State.IDLE, message)

    def cancel(self) -> None:
        if self.state == State.RECORDING:
            self.recorder.cancel()
            self._clear_target()
            self._state(State.IDLE, "Recording cancelled.")

    def shutdown(self) -> None:
        self.closed = True
        self.preview_pending = None
        self.recorder.close()
        if self.refiner is not None:
            self.refiner.close()
        self._clear_target()
        self.executor.shutdown(wait=False, cancel_futures=True)
