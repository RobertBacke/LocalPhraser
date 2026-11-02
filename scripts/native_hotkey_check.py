"""Opt-in actual Qt/Win32 press/release check against an owned input fixture."""

import ctypes as ct
import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer

from localphraser.activation import ShortcutActivation
from localphraser.config import parse_hotkey
from localphraser.hotkey import Hotkey
from localphraser.windows import INPUT, KEYBDINPUT, user32


def main() -> None:
    gestures = "--gestures" in sys.argv
    if gestures:
        import psutil

        assert not any(
            (process.info["name"] or "").casefold() == "localphraser.exe"
            for process in psutil.process_iter(["name"])
        ), "Quit LocalPhraser before testing real global shortcut gestures."
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("native_input_check.py")), "--fixture"],
        stdout=subprocess.PIPE,
        text=True,
    )
    app = QCoreApplication([])
    events = []
    failures = []
    recording = [False]

    def record(event: str, active: bool) -> None:
        events.append(event)
        recording[0] = active

    activation = ShortcutActivation(
        lambda: record("press", True),
        lambda: record("release", False),
        lambda: record("release" if recording[0] else "press", not recording[0]),
        lambda: record("cancel", False),
        lambda: recording[0],
    )
    hotkey = Hotkey(
        activation.key_down if gestures else lambda: events.append("press"),
        activation.key_up if gestures else lambda: events.append("release"),
    )
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

        if gestures:
            timeline = [
                (100, True),
                (450, False),
                (1400, True),
                (1440, False),
                (1510, True),
                (1550, False),
                (2500, True),
                (2540, False),
                (2610, True),
                (2650, False),
                (3400, True),
                (3440, False),
            ]
            for delay, down in timeline:
                QTimer.singleShot(delay, lambda down=down: send(down))
            QTimer.singleShot(4200, app.quit)
        else:
            QTimer.singleShot(100, lambda: send(True))
            QTimer.singleShot(300, lambda: send(False))
            QTimer.singleShot(600, app.quit)
        app.exec()
        if sent:
            send(False)
        assert not failures, failures
        expected = (
            ["press", "release", "press", "release", "press", "cancel"]
            if gestures
            else ["press", "release"]
        )
        assert events == expected, events
        assert not hotkey.timer.isActive()
        assert (api.GetKeyState(0x14) & 1) == before_caps, "Caps Lock toggle changed"
        print(
            "Native hotkey passed: "
            + (
                "combined hold, double-tap latch/stop, lone-tap cancellation; "
                if gestures
                else "one press/release; "
            )
            + "repeat suppression, released keys and unchanged Caps Lock state."
        )
    finally:
        hotkey.close()
        child.terminate()
        child.wait(timeout=5)


if __name__ == "__main__":
    main()
