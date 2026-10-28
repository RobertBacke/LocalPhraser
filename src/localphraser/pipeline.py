"""Serial lifecycle independent of Qt, Windows, and the selected ASR backend."""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from enum import StrEnum
from typing import Any, Protocol

import numpy as np

from localphraser.audio import SAMPLE_RATE, Audio
from localphraser.recognition import Recognizer


class State(StrEnum):
    IDLE = "Ready"
    RECORDING = "Listening"
    TRANSCRIBING = "Transcribing"
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
    ):
        self.recorder = recorder
        self.recognizer = recognizer
        self.insertion = insertion
        self.dispatch = dispatch
        self.changed = changed
        self.result = result
        self.auto_insert = auto_insert
        self.state = State.IDLE
        self.target: Any = None
        self.target_future: Future[Any] | None = None
        self.pending_transcription: Future[str] | None = None
        self.generation = 0
        self.target_error = ""
        self.closed = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transcription")

    def _state(self, state: State, message: str = "") -> None:
        self.state = state
        self.changed(state, message)

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

    def _target_completed(self, future: Future[Any], generation: int) -> None:
        if self.closed:
            try:
                self.insertion.discard(future.result())
            except Exception:
                pass
            return
        self.dispatch(lambda: self._target_ready(future, generation))

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
        try:
            audio = self.recorder.stop()
            if audio.size < SAMPLE_RATE // 5 or np.max(np.abs(audio), initial=0) < 0.001:
                audio.fill(0)
                self._clear_target()
                self._state(State.IDLE, "No speech captured.")
                return
            self._state(State.TRANSCRIBING)
            future = self.executor.submit(self._transcribe, audio)
            future.add_done_callback(lambda f: self.dispatch(lambda: self._finish(f)))
        except Exception:
            self.recorder.cancel()
            self._error("Recording failed. Check the microphone and try again.")

    def _transcribe(self, audio: Audio) -> str:
        try:
            return self.recognizer.transcribe(audio)
        finally:
            audio.fill(0)

    def _finish(self, future: Future[str]) -> None:
        if self.closed:
            return
        try:
            text = future.result().strip()
        except Exception:
            self._error("Transcription failed. Verify the installed model or reinstall it.")
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
                self.insertion.insert(self.target, text)
                notice = "Inserted."
            except Exception:
                # Never retry: a partial SendInput may already have inserted some text.
                notice = (
                    "Insertion was not confirmed. Check the target before copying the transcript."
                )
        self._clear_target()
        self.result(text, notice)
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
        self.recorder.close()
        self._clear_target()
        self.executor.shutdown(wait=False, cancel_futures=True)
