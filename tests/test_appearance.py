from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QToolButton

from localphraser import appearance
from localphraser.config import Config
from localphraser.ui import Indicator, Settings


def test_palette_notifications_do_not_reapply_stylesheet_recursively(app, capsys):
    dialog = appearance.GlassDialog()
    dialog.show()
    app.processEvents()
    style = dialog.styleSheet()
    for _ in range(5):
        QApplication.sendEvent(dialog, QEvent(QEvent.Type.PaletteChange))
    assert dialog.styleSheet() == style
    assert "Error calling Python override" not in capsys.readouterr().err
    dialog.close()
    dialog.deleteLater()


def test_high_contrast_retains_native_palette_and_disables_glass(app, monkeypatch):
    monkeypatch.setattr(appearance, "high_contrast", lambda: True)
    dialog = appearance.GlassDialog()
    assert not appearance.enable_backdrop(dialog)
    assert not dialog.styleSheet()
    dialog.show()
    assert not dialog.native_glass
    assert not dialog.grab().isNull()
    dialog.close()
    dialog.deleteLater()


@pytest.mark.parametrize("native_failure", [False, True])
def test_dialog_and_indicator_render_with_or_without_native_backdrop(
    app, monkeypatch, native_failure
):
    monkeypatch.setattr(appearance, "enable_backdrop", lambda widget: not native_failure)
    dialog = appearance.GlassDialog()
    from PySide6.QtWidgets import QVBoxLayout

    layout = QVBoxLayout(dialog)
    layout.addLayout(dialog.header("Owned test window"))
    dialog.show()
    indicator = Indicator()
    indicator.live_preview("Words stay readable on the glass surface.")
    app.processEvents()
    for widget in (dialog, indicator):
        assert widget.native_glass is not native_failure
        assert not widget.grab().isNull()
    assert indicator.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert indicator.windowFlags() & Qt.WindowType.WindowTransparentForInput
    close = dialog.findChild(QToolButton)
    assert close.accessibleName() == "Close window"
    close.click()
    assert not dialog.isVisible()
    indicator.close()
    dialog.deleteLater()
    indicator.deleteLater()


def test_unsupported_qt_surface_does_not_load_windows_effects(app, monkeypatch):
    native = Mock()
    monkeypatch.setattr(QApplication, "platformName", lambda: "offscreen")
    monkeypatch.setattr(appearance.ctypes, "WinDLL", native)
    dialog = appearance.GlassDialog()
    assert not appearance.enable_backdrop(dialog)
    native.assert_not_called()
    dialog.close()
    dialog.deleteLater()


def test_existing_windows_follow_application_palette_changes(app, capsys):
    original = QPalette(app.palette())
    dialog, indicator = appearance.GlassDialog(), Indicator()
    dialog.show()
    indicator.live_preview("A readable preview.")
    try:
        for color, dark in (("#f4f8f8", False), ("#18272b", True), ("#f4f8f8", False)):
            palette = QPalette(original)
            palette.setColor(QPalette.ColorRole.Window, QColor(color))
            app.setPalette(palette)
            app.processEvents()
            assert dialog.surface_mode[0] is dark
            assert indicator.surface_mode[0] is dark
            assert ("#edf8f7" if dark else "#163c42") in indicator.styleSheet()
        assert "Error calling Python override" not in capsys.readouterr().err
    finally:
        app.setPalette(original)
        dialog.close()
        indicator.close()
        dialog.deleteLater()
        indicator.deleteLater()


def test_glass_close_button_preserves_active_download_guard(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    settings = Settings(Config(), Mock())
    settings.show()
    settings.downloader.phase = "download"
    close = settings.findChild(QToolButton)
    close.click()
    assert settings.isVisible()
    assert "Cancel the download" in settings.progress.text()
    settings.downloader.phase = "idle"
    close.click()
    assert not settings.isVisible()
    settings.deleteLater()
