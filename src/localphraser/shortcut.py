"""Focused, explicit shortcut selection; no typed shortcut syntax required."""

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import QPushButton

from localphraser.config import parse_hotkey

HINT = "Click to choose, then press Caps Lock, F1–F11, or a modifier combination. Esc cancels."


def shortcut_from_key(key: int, modifiers: Qt.KeyboardModifier) -> str | None:
    if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
        return None
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        raise ValueError("Windows-key shortcuts are not supported.")
    if key == Qt.Key.Key_CapsLock:
        return "CapsLock"
    parts = []
    for flag, name in (
        (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
        (Qt.KeyboardModifier.AltModifier, "Alt"),
        (Qt.KeyboardModifier.ShiftModifier, "Shift"),
    ):
        if modifiers & flag:
            parts.append(name)
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F11:
        parts.append(f"F{key - Qt.Key.Key_F1 + 1}")
    elif key == Qt.Key.Key_Space:
        parts.append("Space")
    elif ord("A") <= key <= ord("Z") or ord("0") <= key <= ord("9"):
        parts.append(chr(key))
    else:
        raise ValueError("Choose Caps Lock, F1–F11, or a supported key combination.")
    value = "+".join(parts)
    parse_hotkey(value)
    return value


class ShortcutRecorder(QPushButton):
    message = Signal(str)

    def __init__(
        self,
        value: str,
        begin: Callable[[Callable[[], None]], None] | None = None,
        end: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.shortcut_value = value
        self.capturing = False
        self.begin = begin
        self.end = end
        self.setCheckable(True)
        self.setAccessibleName("Choose global push-to-talk shortcut")
        self.setToolTip(HINT)
        self._label()
        self.clicked.connect(self.start_capture)

    def _label(self) -> None:
        self.setText(
            "Press your shortcut…" if self.capturing else f"{self.shortcut_value} · Change…"
        )

    def start_capture(self) -> None:
        if self.capturing:
            self.cancel_capture()
            return
        try:
            if self.begin:
                self.begin(lambda: self.choose("CapsLock"))
        except Exception as exc:
            self.setChecked(False)
            self.message.emit(str(exc))
            return
        self.capturing = True
        self.setChecked(True)
        self.setFocus()
        self._label()
        self.message.emit("Press the desired key or combination. Esc cancels.")

    def choose(self, value: str) -> None:
        if not self.capturing:
            return
        self.shortcut_value = value
        self.cancel_capture()
        self.message.emit(f"Selected {value}. Save to apply.")

    def cancel_capture(self) -> None:
        if self.capturing:
            self.capturing = False
            self.setChecked(False)
            self._label()
            if self.end:
                self.end()
            self.message.emit(HINT)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.capturing:
            super().keyPressEvent(event)
            return
        event.accept()
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_capture()
            return
        try:
            value = shortcut_from_key(event.key(), event.modifiers())
            if value:
                self.choose(value)
        except ValueError as exc:
            self.message.emit(str(exc))

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.cancel_capture()
        super().focusOutEvent(event)
