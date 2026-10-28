"""Verify native Caps Lock selection in an owned Settings window; no audio capture."""

import ctypes as ct
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from localphraser.config import Config
from localphraser.hotkey import Hotkey
from localphraser.pipeline import State
from localphraser.ui import Desktop, Settings
from localphraser.windows import INPUT, KEYBDINPUT, user32


def main() -> None:
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    events = []
    desktop = object.__new__(Desktop)
    desktop.pipeline = type("Idle", (), {"state": State.IDLE})()
    desktop.config = Config(hotkey="CapsLock" if "--caps-default" in sys.argv else "Ctrl+Shift+F9")
    desktop.closing = False
    desktop.notify = lambda message: events.append("notification")
    desktop.hotkey = Hotkey(lambda: events.append("dictation"), lambda: events.append("dictation"))
    app.installNativeEventFilter(desktop.hotkey)
    desktop.hotkey.register(desktop.config.hotkey)
    settings = Settings(
        desktop.config,
        lambda config: None,
        desktop.begin_shortcut_capture,
        desktop.end_shortcut_capture,
    )
    settings.show()
    api = user32()
    failures = []

    def choose() -> None:
        settings.hotkey.start_capture()
        assert settings.hotkey.capturing
        assert desktop.hotkey.capture_callback is not None

    sent = False

    def press_caps(down: bool) -> None:
        nonlocal sent
        if down and api.GetForegroundWindow() != int(settings.winId()):
            failures.append("Owned Settings window was not foreground; no input sent.")
            return
        batch = (INPUT * 1)(
            INPUT(type=1, ki=KEYBDINPUT(wVk=0x14, dwFlags=0 if down else 2)),
        )
        sent = down
        if api.SendInput(1, batch, ct.sizeof(INPUT)) != 1:
            failures.append("Native input blocked.")

    QTimer.singleShot(100, choose)
    QTimer.singleShot(250, lambda: press_caps(True))
    QTimer.singleShot(400, lambda: press_caps(True))  # Held-key repeat after accepting selection.
    QTimer.singleShot(500, lambda: press_caps(False))
    QTimer.singleShot(800, app.quit)
    try:
        app.exec()
        assert not failures, failures
        assert settings.hotkey.shortcut_value == "CapsLock"
        assert not settings.hotkey.capturing
        assert desktop.hotkey.capture_callback is None
        assert desktop.hotkey.registered
        assert bool(desktop.hotkey._caps_handle) == (desktop.config.hotkey == "CapsLock")
        assert not events, events
        print("Native Caps Lock selection and restoration passed without starting dictation.")
    finally:
        desktop.closing = True
        if sent:
            press_caps(False)
        settings.hotkey.cancel_capture()
        desktop.hotkey.close()
        settings.close()


if __name__ == "__main__":
    main()
