import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtGui import QFont, QFontInfo
from PySide6.QtWidgets import QLabel

from localphraser.appearance import GlassDialog
from localphraser.config import Config
from localphraser.history import History
from localphraser.home import AppWindow
from localphraser.typography import interface_family
from localphraser.ui import Settings


def test_bundled_font_loads_with_its_license_and_is_used_by_ui(app):
    assets = Path(__file__).resolve().parents[1] / "src/localphraser/assets/fonts"
    assert (
        hashlib.sha256((assets / "SpaceGrotesk.ttf").read_bytes()).hexdigest()
        == "acad6de1fc93436f5c0f1f4137751ef04f1aea3063e7036535970ffcfbd79f72"
    )
    assert "SIL OPEN FONT LICENSE" in (assets / "OFL.txt").read_text()
    assert interface_family() == "Space Grotesk"
    window = GlassDialog()
    assert QFontInfo(window.font()).family() == "Space Grotesk"
    window.deleteLater()


def test_child_controls_use_bundled_font_even_with_windows_system_font(app):
    previous = app.font()
    app.setFont(QFont("Segoe UI", 9))
    history = History(None)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    with patch("localphraser.ui.microphones", return_value=[]):
        settings = Settings(Config(), Mock())
    try:
        window.show()
        settings.show()
        app.processEvents()
        for widget in (
            window.findChild(QLabel, "pageTitle"),
            window.hint,
            window.result_text,
            window.raw,
            window.home_button,
            settings.model,
        ):
            assert widget.font().family() == "Space Grotesk"
            assert QFontInfo(widget.font()).family() == "Space Grotesk"
        assert window.hint.font().pointSizeF() == 10
    finally:
        window.hide()
        window.deleteLater()
        settings.hide()
        settings.deleteLater()
        history.close()
        app.setFont(previous)
