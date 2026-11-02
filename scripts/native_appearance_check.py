"""Owned glass UI/theme check; no microphone, shortcut registration, models or insertion."""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QToolButton

from localphraser.appearance import GlassComboBox, dark_surface
from localphraser.audio import Microphone
from localphraser.branding import logo_pixmap
from localphraser.config import Config
from localphraser.ui import Indicator, Latest, Settings, set_appearance


def check(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda *args: errors.append("Qt callback failed")
    try:
        with patch(
            "localphraser.ui.microphones",
            return_value=[
                Microphone(f"Owned test microphone {i} with a long label", "Test API")
                for i in range(25)
            ],
        ):
            settings = Settings(
                Config(model_root=str(output.resolve() / "models"), mode="polished"),
                lambda cfg: None,
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
                screen = next(s for s in app.screens() if s.name() == indicator.anchor_screen)
                assert screen.availableGeometry().contains(indicator.geometry())
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
                latest.hide()
                indicator.hide()
                settings.raise_()
                settings.activateWindow()
                settings.scroll_area.ensureWidgetVisible(settings.model)
                QTest.qWait(150)
                settings.model.setFocus()
                settings.model.setCurrentText("small.en")
                settings.model.showPopup()
                QTest.qWait(500)  # Wait for the native combo roll-open animation.
                popup = settings.model.view().window()
                assert popup.isVisible()
                assert popup.grab().save(str(output / f"{theme}-model-popup.png"))
                QTest.keyClick(settings.model.view(), Qt.Key.Key_Down)
                QTest.keyClick(settings.model.view(), Qt.Key.Key_Return)
                assert settings.model.currentText() == "distil-small.en"
                settings.resize(620, 480)
                for combo in settings.findChildren(GlassComboBox):
                    settings.scroll_area.ensureWidgetVisible(combo)
                    QTest.qWait(50)
                    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
                    QTest.qWait(100)
                    menu = combo.view().window()
                    bounds = QRect(settings.mapToGlobal(QPoint()), settings.size())
                    assert menu.isVisible() and bounds.contains(menu.geometry())
                    assert combo.screen().availableGeometry().contains(menu.geometry())
                    if combo is settings.device:
                        QTest.keyClick(combo.view(), Qt.Key.Key_End)
                        QTest.keyClick(combo.view(), Qt.Key.Key_Return)
                        assert combo.currentIndex() == 25
                    else:
                        previous = combo.currentIndex()
                        QTest.keyClick(combo.view(), Qt.Key.Key_Escape)
                        assert combo.currentIndex() == previous
                    assert not menu.isVisible()
                settings.resize(620, 820)
                indicator.hide()
            assert logo_pixmap(256).save(str(output / "speech-prism.png"))
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
            "Owned glass UI passed: theme changes, opaque model menus, keyboard selection, "
            "focus safety, compact layout and close control."
        )
    finally:
        sys.excepthook = previous_hook


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    check(parser.parse_args().output)
