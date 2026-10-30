"""Owned desktop/history/taskbar/activation check. No microphone or keyboard input."""

import argparse
import ctypes
import subprocess
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QLockFile
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from localphraser.appearance import dark_surface
from localphraser.config import Config, load_config
from localphraser.history import History
from localphraser.hotkey import Hotkey
from localphraser.instance import listen
from localphraser.ui import Desktop


def check(output: Path, models: Path) -> None:
    folder = output / uuid.uuid4().hex
    folder.mkdir(parents=True)
    config_path = folder / "config.json"
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    lock = QLockFile(str(folder / "localphraser.lock"))
    assert lock.tryLock(0)
    errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda *args: errors.append("Qt callback failed")
    try:
        with (
            patch.object(Hotkey, "register"),
            patch("localphraser.ui.microphones", return_value=[]),
        ):
            desktop = Desktop(
                app, Config(model_root=str(models), keep_microphone_ready=False), config_path
            )
            desktop.tray.hide()
            desktop.show_home()
            QTest.qWait(100)
            hwnd = int(desktop.window.winId())
            api = ctypes.WinDLL("user32")
            api.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            api.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            api.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            api.GetWindow.restype = ctypes.c_void_p
            assert not api.GetWindowLongPtrW(hwnd, -20) & 0x80, "Workspace is a tool window"
            assert not api.GetWindow(hwnd, 4), "Workspace has a hidden owner"
            desktop.pipeline.audio_seconds = 2
            desktop.latest.raw.setPlainText("hello from the local workspace")
            desktop.complete_transcript("Hello from the local workspace.", "Inserted.")
            assert desktop.window.entries.count() == 1
            assert desktop.window.metric_labels[2].text() == "150 wpm"
            desktop.show_settings()
            settings = desktop.settings
            assert settings is not None
            settings.duration.setValue(180)
            for theme in ("dark", "light"):
                settings.theme.setCurrentIndex(settings.theme.findData(theme))
                QTest.qWait(150)
                assert dark_surface() == (theme == "dark")
                assert load_config(config_path).theme == theme
                assert load_config(config_path).max_seconds == 120
                desktop.window.grab().save(str(folder / f"{theme}-settings.png"))
                desktop.window.show_home()
                QTest.qWait(100)
                assert not settings.isVisible()
                desktop.window.grab().save(str(folder / f"{theme}-home.png"))
                desktop.window.show_settings(settings)
            settings.save()
            assert desktop.settings is None and desktop.window.isVisible()
            assert desktop.window.pages.currentWidget() is desktop.window.home
            assert load_config(config_path).max_seconds == 180
            desktop.show_settings()
            settings = desktop.settings
            assert settings is not None
            desktop.window.resize(740, 480)
            QTest.qWait(50)
            from PySide6.QtCore import QPoint
            from PySide6.QtWidgets import QDialogButtonBox

            buttons = settings.findChild(QDialogButtonBox)
            assert (
                buttons.mapTo(desktop.window, QPoint(0, buttons.height())).y()
                <= desktop.window.height()
            )
            desktop.window.show_home()
            assert (
                desktop.window.copy_button.mapTo(
                    desktop.window, QPoint(0, desktop.window.copy_button.height())
                ).y()
                <= desktop.window.height()
            )
            server = listen(config_path, desktop.show_home)
            try:
                desktop.window.showMinimized()
                child = subprocess.Popen(
                    [sys.executable, "-m", "localphraser", "--config", str(config_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                deadline = time.monotonic() + 10
                while child.poll() is None and time.monotonic() < deadline:
                    QTest.qWait(50)
                if child.poll() is None:
                    child.terminate()  # Only the owned second-launch fixture.
                    child.wait(timeout=5)
                    raise AssertionError("Second launch did not finish")
                assert child.returncode == 0
                QTest.qWait(100)
                assert desktop.window.isVisible() and not desktop.window.isMinimized()
                assert desktop.window.pages.currentWidget() is desktop.window.home
            finally:
                server.close()
            app.aboutToQuit.disconnect(desktop.shutdown)
            app.removeNativeEventFilter(desktop.hotkey)
            desktop.shutdown()
            desktop.pipeline.executor.shutdown(wait=True)
            desktop.insertion.executor.shutdown(wait=True)
            reopened = History(folder / "history.sqlite3")
            assert reopened.stats() == (1, 5, 150)
            reopened.close()
            for widget in (desktop.window, desktop.indicator, desktop.latest):
                widget.deleteLater()
            app.processEvents()
        assert not errors
        print(
            "Owned workspace passed: taskbar, instant theme, settings, "
            "persistent history, WPM, compact layout and second-launch restore."
        )
    finally:
        sys.excepthook = previous_hook
        lock.unlock()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    check(args.output.resolve(), args.models.resolve())
