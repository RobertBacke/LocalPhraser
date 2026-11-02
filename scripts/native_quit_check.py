"""Owned visible-window Quit check; no microphone, keyboard input or model inference."""

import argparse
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton

from localphraser.config import Config
from localphraser.hotkey import Hotkey
from localphraser.ui import Desktop


def check(case: str, temporary: Path) -> None:
    temporary.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    failures = []
    with tempfile.TemporaryDirectory(dir=temporary) as folder:
        with (
            patch.object(Hotkey, "register"),
            patch("localphraser.ui.microphones", return_value=[]),
        ):
            desktop = Desktop(
                app,
                Config(keep_microphone_ready=False),
                Path(folder) / "config.json",
                persist_history=False,
            )
            desktop.tray.hide()
            desktop.show_settings() if case == "settings" else desktop.show_home()

            def quit_once():
                if case == "tray":
                    desktop.menu.actions()[-1].trigger()
                else:
                    button = next(
                        b
                        for b in desktop.window.findChildren(QPushButton)
                        if b.text() == "Quit LocalPhraser"
                    )
                    button.click()

            def deadline():
                failures.append("Explicit Quit did not end the event loop")
                desktop.shutdown()
                app.exit(1)

            QTimer.singleShot(150, quit_once)
            QTimer.singleShot(5000, deadline)
            code = app.exec()
            desktop.pipeline.executor.shutdown(wait=True)
            desktop.insertion.executor.shutdown(wait=True)
            assert code == 0 and not failures and desktop.closing
            assert not desktop.window.isVisible()
    print(f"Owned explicit Quit passed: visible {case}; clean event-loop exit.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("home", "settings", "tray"), required=True)
    parser.add_argument("--temp-dir", type=Path, required=True)
    args = parser.parse_args()
    check(args.case, args.temp_dir.resolve())
