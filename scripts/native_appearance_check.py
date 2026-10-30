"""Owned glass UI/theme check; no microphone, shortcut registration, models or insertion."""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QToolButton

from localphraser.appearance import dark_surface
from localphraser.config import Config
from localphraser.ui import Indicator, Latest, Settings, set_appearance


def check(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda *args: errors.append("Qt callback failed")
    try:
        with patch("localphraser.ui.microphones", return_value=[]):
            settings = Settings(
                Config(model_root=str(output.resolve() / "models")), lambda cfg: None
            )
            latest = Latest()
            latest.set_transcript("Your words stay on this device.", "Inserted.")
            indicator = Indicator()
            for theme in ("light", "dark", "system"):
                set_appearance(theme)
                settings.show()
                latest.show()
                QTest.qWait(150)
                active = app.activeWindow()
                indicator.live_preview("Your words stay on this device.")
                QTest.qWait(150)
                assert app.activeWindow() is active
                assert indicator.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
                assert indicator.windowFlags() & Qt.WindowType.WindowTransparentForInput
                for label, widget in (
                    ("settings", settings),
                    ("latest", latest),
                    ("indicator", indicator),
                ):
                    if theme != "system":
                        assert dark_surface() == (theme == "dark")
                        assert widget.surface_mode[0] == (theme == "dark")
                    assert widget.grab().save(str(output / f"{theme}-{label}.png"))
                settings.resize(620, 480)
                app.processEvents()
                buttons = settings.findChild(QDialogButtonBox)
                assert buttons.isVisible() and buttons.geometry().bottom() <= settings.height()
                settings.resize(620, 820)
                indicator.hide()
            close = latest.findChild(QToolButton)
            assert close.accessibleName() == "Close window"
            close.click()
            assert not latest.isVisible()
            for widget in (settings, latest, indicator):
                widget.close()
                widget.deleteLater()
            app.processEvents()
        assert not errors
        print(
            "Owned glass UI passed: theme changes, focus safety, compact layout and close control."
        )
    finally:
        sys.excepthook = previous_hook


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    check(parser.parse_args().output)
