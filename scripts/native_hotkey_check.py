"""Opt-in actual Qt/Win32 press/release check against an owned input fixture."""

import ctypes as ct
import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer

from localphraser.config import parse_hotkey
from localphraser.hotkey import Hotkey
from localphraser.windows import INPUT, KEYBDINPUT, user32


def main() -> None:
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("native_input_check.py")), "--fixture"],
        stdout=subprocess.PIPE,
        text=True,
    )
    app = QCoreApplication([])
    events = []
    failures = []
    hotkey = Hotkey(lambda: events.append("press"), lambda: events.append("release"))
    api = user32()
    sent = False
    try:
        assert child.stdout is not None
        handles = json.loads(child.stdout.readline())
        app.installNativeEventFilter(hotkey)
        shortcut = sys.argv[1] if len(sys.argv) > 1 else "CapsLock"
        _, _, chord = parse_hotkey(shortcut)
        hotkey.register(shortcut)
        before_caps = api.GetKeyState(0x14) & 1

        def send(down: bool) -> None:
            nonlocal sent
            if down and api.GetForegroundWindow() != handles["window"]:
                failures.append("Owned fixture lost focus. No keys sent.")
                app.quit()
                return
            if not down and not sent:
                return
            keys = (*chord, chord[-1]) if down else tuple(reversed(chord))
            batch = (INPUT * len(keys))(
                *[INPUT(type=1, ki=KEYBDINPUT(wVk=key, dwFlags=0 if down else 2)) for key in keys]
            )
            count = api.SendInput(len(batch), batch, ct.sizeof(INPUT))
            sent = down
            if count != len(batch):
                failures.append("Input blocked or partial.")

        QTimer.singleShot(100, lambda: send(True))
        QTimer.singleShot(300, lambda: send(False))
        QTimer.singleShot(600, app.quit)
        app.exec()
        if sent:
            send(False)
        assert not failures, failures
        assert events == ["press", "release"], events
        assert not hotkey.timer.isActive()
        assert (api.GetKeyState(0x14) & 1) == before_caps, "Caps Lock toggle changed"
        print(
            "Native hotkey: one press/release, repeat suppression and stopped release timer passed."
        )
    finally:
        hotkey.close()
        child.terminate()
        child.wait(timeout=5)


if __name__ == "__main__":
    main()
