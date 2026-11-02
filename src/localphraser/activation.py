"""Shortcut gestures shared by Caps Lock and registered key chords."""

from collections.abc import Callable
from time import monotonic

from PySide6.QtCore import QTimer

TAP_WINDOW = 0.35
HOLD_THRESHOLD = 0.2


class ShortcutActivation:
    def __init__(
        self,
        press: Callable[[], None],
        release: Callable[[], None],
        toggle: Callable[[], None],
        cancel: Callable[[], None],
        recording: Callable[[], bool],
        mode: str = "both",
        clock: Callable[[], float] = monotonic,
        schedule: Callable = QTimer.singleShot,
    ):
        self.press, self.release, self.toggle = press, release, toggle
        self.cancel, self.recording, self.schedule = cancel, recording, schedule
        self.mode, self.clock = mode, clock
        self.epoch = 0
        self.reset()

    def reset(self) -> None:
        self.down_at: float | None = None
        self.tap_at: float | None = None
        self.pair = False
        self.owns_recording = False
        self.was_recording = False
        self.epoch += 1

    def key_down(self) -> None:
        if self.down_at is not None:
            return
        now = self.clock()
        if self.mode != "hold" and self.tap_at is not None:
            if now - self.tap_at <= TAP_WINDOW:
                self.epoch += 1
                self.pair = True
                self.tap_at = None
                self.down_at = now
                return
            self._expire(self.epoch)
        self.down_at = now
        if self.mode == "hold":
            self.press()
        elif self.mode == "both":
            self.was_recording = self.recording()
            if not self.was_recording:
                self.press()  # Buffer opening words before the hold threshold.
            self.owns_recording = not self.was_recording and self.recording()

    def key_up(self) -> None:
        if self.down_at is None:
            return
        now, started = self.clock(), self.down_at
        self.down_at = None
        if self.mode == "hold":
            self.release()
        elif now - started >= HOLD_THRESHOLD:
            if self.mode == "both" and self.recording():
                self.release()
            self.reset()
        elif self.pair:
            was_recording = self.was_recording
            self.reset()
            if self.mode == "double_tap":
                self.toggle()
            elif was_recording and self.recording():
                self.release()
        else:
            self.tap_at = now
            epoch = self.epoch
            self.schedule(round(TAP_WINDOW * 1000), lambda: self._expire(epoch))

    def _expire(self, epoch: int) -> None:
        if epoch != self.epoch:
            return
        cancel = self.owns_recording and self.recording()
        self.reset()
        if cancel:
            self.cancel()  # A lone quick tap never transcribes or inserts its buffer.
