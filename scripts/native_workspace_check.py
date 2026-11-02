"""Owned desktop/history/taskbar/activation check. No microphone or keyboard input."""

import argparse
import ctypes
import subprocess
import sys
import time
import uuid
from concurrent.futures import Future
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
            assert api.GetWindowLongPtrW(hwnd, -16) & 0x00040000, "Snap sizing style missing"
            from ctypes import wintypes

            from PySide6.QtCore import QPoint
            from PySide6.QtWidgets import QPushButton

            maximize = next(
                button
                for button in desktop.window.findChildren(QPushButton)
                if button.property("systemMaximizeButton")
            )
            center = maximize.mapTo(desktop.window, maximize.rect().center())
            scale = desktop.window.devicePixelRatioF()
            point = wintypes.POINT(round(center.x() * scale), round(center.y() * scale))
            api.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
            api.ClientToScreen(hwnd, ctypes.byref(point))
            api.SendMessageW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            api.SendMessageW.restype = ctypes.c_ssize_t
            assert (
                api.SendMessageW(hwnd, 0x84, 0, (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16))
                == 9
            )
            for maximized in (True, False):
                api.SendMessageW(hwnd, 0xA1, 9, 0)
                api.SendMessageW(hwnd, 0xA2, 9, 0)
                QTest.qWait(100)
                assert desktop.window.isMaximized() == maximized
                if maximized:
                    for navigate in (
                        desktop.show_settings,
                        desktop.show_vocabulary,
                        desktop.show_home,
                    ):
                        navigate()
                        QTest.qWait(50)
                        assert desktop.window.isMaximized(), (
                            "Navigation restored a maximized window"
                        )
                    desktop.window.showMinimized()
                    desktop.show_home()
                    assert desktop.window.isMaximized() and not desktop.window.isMinimized()
            desktop.pipeline.audio_seconds = 2
            origin = Future()
            origin.set_result("Codex")
            desktop.recording_app = origin
            desktop.latest.raw.setPlainText("hello from the local workspace")
            desktop.complete_transcript("Hello from the local workspace.", "Inserted.")
            assert desktop.window.entries.count() == 1
            assert desktop.window.metric_labels[2].text() == "150 wpm"
            desktop.window.analytics_button.click()
            assert desktop.window.pages.currentWidget() is desktop.window.analytics
            assert desktop.window.analytics.table.item(0, 0).text() == "Codex"
            assert [desktop.window.analytics.table.item(0, i).text() for i in (1, 2, 3)] == [
                "1",
                "1",
                "1",
            ]
            desktop.window.grab().save(str(folder / "analytics.png"))
            desktop.window.vocabulary_button.click()
            vocabulary = desktop.vocabulary_page
            assert vocabulary is not None
            vocabulary.entry.setText("Codex")
            vocabulary.add_button.click()
            assert load_config(config_path).vocabulary == "Codex"
            assert desktop.pipeline.recognizer.vocabulary == "Codex"
            desktop.window.grab().save(str(folder / "vocabulary.png"))
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
            for nav_button in desktop.window.sidebar.findChildren(QPushButton):
                assert nav_button.width() >= nav_button.minimumSizeHint().width(), nav_button.text()
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
            desktop.history.connection.execute("PRAGMA query_only=ON")
            desktop.window.delete_button.click()
            QTest.qWait(50)
            assert desktop.window.history_notice.isVisible()
            assert desktop.window.result_text.toPlainText() == "Hello from the local workspace."
            assert not desktop.window.delete_button.isEnabled()
            assert desktop.window.copy_button.isEnabled()
            assert (
                desktop.window.copy_button.mapTo(
                    desktop.window, QPoint(0, desktop.window.copy_button.height())
                ).y()
                <= desktop.window.height()
            )
            desktop.window.grab().save(str(folder / "history-readonly.png"))
            desktop.history.connection.execute("PRAGMA query_only=OFF")
            desktop.window.show_home()
            assert desktop.window.history_notice.isHidden()
            assert desktop.window.delete_button.isEnabled()
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
            "persistent history, read-only recovery, WPM, compact layout and second-launch restore."
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
