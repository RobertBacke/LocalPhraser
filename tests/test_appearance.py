from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QColor, QFontInfo, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from localphraser import appearance
from localphraser.config import Config
from localphraser.history import History
from localphraser.home import AppWindow
from localphraser.ui import Indicator, Settings


def test_indicator_stays_on_recording_monitor_and_recovers_if_removed(app, monkeypatch):
    from localphraser.pipeline import State

    left = Mock()
    left.name.return_value = "left"
    left.availableGeometry.return_value = QRect(-1280, 0, 1280, 720)
    right = Mock()
    right.name.return_value = "right"
    right.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
    screens, pointer = [left, right], [left]
    monkeypatch.setattr(QApplication, "screens", lambda: screens)
    monkeypatch.setattr(QApplication, "screenAt", lambda point: pointer[0])
    indicator = Indicator()
    indicator.display(State.RECORDING)
    assert left.availableGeometry().contains(indicator.geometry())
    pointer[0] = right
    indicator.live_preview("Words stay on the recording screen.")
    assert left.availableGeometry().contains(indicator.geometry())
    screens.remove(left)
    indicator.preview("The removed monitor falls back to an available monitor.")
    assert right.availableGeometry().contains(indicator.geometry())
    indicator.display(State.IDLE)
    indicator.display(State.RECORDING)
    assert right.availableGeometry().contains(indicator.geometry())
    indicator.close()
    indicator.deleteLater()


def test_indicator_fits_small_work_area_with_a_long_draft(app, monkeypatch):
    screen = Mock()
    screen.name.return_value = "small"
    screen.availableGeometry.return_value = QRect(-300, 10, 280, 240)
    monkeypatch.setattr(QApplication, "screens", lambda: [screen])
    monkeypatch.setattr(QApplication, "screenAt", lambda point: screen)
    indicator = Indicator()
    indicator.live_preview("a long speech preview " * 30)
    assert screen.availableGeometry().contains(indicator.geometry())
    indicator.close()
    indicator.deleteLater()


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
        assert not widget.grab().isNull()
    assert dialog.native_glass is not native_failure
    assert not indicator.native_glass
    assert indicator.grab().toImage().pixelColor(0, 0).alpha() == 0
    image = indicator.grab().toImage()
    assert image.pixelColor(10, image.height() // 2).alpha() >= 248
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


@pytest.mark.parametrize(
    ("state", "status", "colour"),
    [
        ("WARMING", "Preparing speech model", "muted"),
        ("RECORDING", "Listening", "recording"),
        ("TRANSCRIBING", "Transcribing", "busy"),
        ("POLISHING", "Polishing", "busy"),
        ("INSERTING", "Inserting", "busy"),
        ("ERROR", "Error", "recording"),
    ],
)
def test_capsule_status_line_and_painted_dot_follow_each_state(app, state, status, colour):
    from localphraser.pipeline import State

    indicator = Indicator()
    indicator.expects_words = False  # Live preview off: no invitation to speak.
    try:
        indicator.display(State[state])
        assert indicator.isVisible()
        assert indicator.status.text() == status
        assert "●" not in indicator.status.text()
        assert indicator.dot.tone == colour
        assert not indicator.words.text() and indicator.words.isHidden()
    finally:
        indicator.close()
        indicator.deleteLater()


def test_capsule_invites_speech_then_shows_live_words_and_partial_text(app):
    from localphraser.pipeline import State

    indicator = Indicator()
    try:
        indicator.display(State.RECORDING)
        assert indicator.status.text() == "Listening — speak now"
        assert indicator.words.isHidden()
        indicator.live_preview("these are my words")
        assert indicator.status.text() == "Listening"
        assert indicator.words.text() == "these are my words"
        assert not indicator.words.isHidden()
        assert (
            QFontInfo(indicator.words.font()).pixelSize()
            > QFontInfo(indicator.status.font()).pixelSize()
        )
        indicator.display(State.TRANSCRIBING)
        assert indicator.status.text() == "Transcribing" and indicator.words.isHidden()
        indicator.preview("These are my words.")
        assert indicator.status.text() == "Transcribing · preview"
        assert indicator.words.text() == "These are my words."
        assert indicator.dot.tone == "busy"
        indicator.display(State.IDLE)
        assert not indicator.isVisible()
        assert not indicator.status.text() and not indicator.words.text()
    finally:
        indicator.close()
        indicator.deleteLater()


def test_capsule_dot_is_painted_red_while_listening(app):
    from localphraser.pipeline import State

    indicator = Indicator()
    try:
        indicator.display(State.RECORDING)
        app.processEvents()
        image = indicator.grab().toImage()
        centre = indicator.dot.mapTo(indicator, indicator.dot.rect().center())
        pixel = image.pixelColor(centre)
        assert pixel.red() > pixel.green() + 60 and pixel.red() > pixel.blue() + 60
    finally:
        indicator.close()
        indicator.deleteLater()


def test_capsule_keeps_transcript_text_plain(app):
    from localphraser.pipeline import State

    indicator = Indicator()
    try:
        for show in (indicator.live_preview, indicator.preview):
            show("<b>bold</b> &amp; <i>words</i>")
            assert indicator.words.textFormat() == Qt.TextFormat.PlainText
            assert indicator.status.textFormat() == Qt.TextFormat.PlainText
            assert indicator.words.text() == "<b>bold</b> &amp; <i>words</i>"
        assert indicator.focusPolicy() == Qt.FocusPolicy.NoFocus
        indicator.display(State.IDLE)
    finally:
        indicator.close()
        indicator.deleteLater()


def lightness(image, rect):
    values = [
        image.pixelColor(x, y).lightness()
        for x in range(rect.left(), rect.right() + 1)
        for y in range(rect.top(), rect.bottom() + 1)
    ]
    return sum(values) / len(values)


def test_check_box_shows_an_empty_box_a_ticked_box_and_a_focus_ring(app):
    from PySide6.QtWidgets import QPushButton, QVBoxLayout

    dialog = appearance.GlassDialog()
    layout = QVBoxLayout(dialog)
    other = QPushButton("Elsewhere")
    box = appearance.GlassCheckBox("Keep transcript history on this device")
    layout.addWidget(other)
    layout.addWidget(box)
    dialog.resize(420, 160)
    dialog.show()
    dialog.activateWindow()
    try:
        other.setFocus()
        app.processEvents()

        def capture():
            app.processEvents()
            return dialog.grab().toImage()

        frame = box.indicator_rect().translated(box.mapTo(dialog, box.rect().topLeft()))
        inside = frame.adjusted(4, 4, -4, -4)
        edge = QRect(frame.left() + 5, frame.top() + 1, frame.width() - 10, 1)  # Top border.
        outside = frame.translated(-frame.width() - 6, 0)
        ring = QRect(frame.left(), frame.top() - 2, frame.width(), 2)  # Just above the box.
        box.setChecked(False)
        off = capture()
        # An unticked box is still drawn: its border stands out from the surface around it.
        assert abs(lightness(off, edge) - lightness(off, outside)) > 25
        box.setChecked(True)
        on = capture()
        assert abs(lightness(on, inside) - lightness(off, inside)) > 60
        unfocused_ring = lightness(on, ring)
        box.setFocus(Qt.FocusReason.TabFocusReason)
        assert box.hasFocus()
        focused = capture()
        assert abs(lightness(focused, ring) - unfocused_ring) > 15
    finally:
        dialog.close()
        dialog.deleteLater()


def contrast(first, second):
    def luminance(color):
        channels = []
        for value in (color.redF(), color.greenF(), color.blueF()):
            channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("dark", [False, True])
def test_hint_text_is_muted_smaller_and_readable_on_the_glass(app, monkeypatch, dark):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    monkeypatch.setattr(appearance, "dark_surface", lambda: dark)
    settings = Settings(Config(model="parakeet-tdt-0.6b-v2"), Mock())
    try:
        settings.show()
        app.processEvents()
        hint, label = settings.quality_hint, settings.findChild(QLabel, "fieldLabel")
        assert hint.property("hint") is True
        hint_color = hint.palette().color(QPalette.ColorRole.WindowText)
        label_color = label.palette().color(QPalette.ColorRole.WindowText)
        assert hint_color != label_color
        assert hint.font().pointSizeF() < label.font().pointSizeF()
        surfaces = (
            (QColor(21, 27, 49), QColor(36, 42, 65), QColor(52, 60, 88))
            if dark
            else (QColor(245, 249, 255), QColor(225, 237, 249), QColor(214, 226, 246))
        )
        for surface in surfaces:
            assert contrast(hint_color, surface) >= 4.5, surface.name()
    finally:
        settings.close()
        settings.deleteLater()


def test_settings_rows_are_grouped_under_sections_in_order(app, monkeypatch):
    from PySide6.QtWidgets import QFrame

    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    settings = Settings(Config(mode="polished"), Mock())
    try:
        assert settings.findChild(QLabel, "pageTitle").text() == "Settings"
        sections = [
            frame.accessibleName() for frame in settings.findChildren(QFrame, "settingsSection")
        ]
        assert sections == [
            "General",
            "Shortcut",
            "Microphone",
            "Speech recognition",
            "Text output",
            "Privacy and credits",
        ]

        def section(widget):
            while widget is not None and widget.objectName() != "settingsSection":
                widget = widget.parentWidget()
            return widget.accessibleName() if widget is not None else None

        expected = {
            "General": (settings.theme, settings.start_at_login, settings.keep_history),
            "Shortcut": (settings.hotkey, settings.activation_mode),
            "Microphone": (settings.device, settings.keep_ready),
            "Speech recognition": (
                settings.model,
                settings.recognition_quality,
                settings.quality_hint,
                settings.live_preview,
                settings.duration,
                settings.threads,
                settings.root,
                settings.install,
                settings.progress,
                settings.download_bar,
                settings.cancel_download,
            ),
            "Text output": (
                settings.insert,
                settings.mode,
                settings.refinement_model,
                settings.refinement_prompt,
            ),
            "Privacy and credits": (settings.credits,),
        }
        for name, widgets in expected.items():
            for widget in widgets:
                assert section(widget) == name, widget
    finally:
        settings.close()
        settings.deleteLater()


def test_settings_labels_sit_beside_fields_and_stack_when_narrow(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    settings = Settings(Config(mode="polished"), Mock())
    settings.setMinimumWidth(0)
    try:
        label = settings.findChild(QLabel, "fieldLabel")
        assert label.buddy() is settings.theme
        settings.resize(900, 600)
        settings.show()
        app.processEvents()
        label_box, field_box = label.geometry(), settings.theme.geometry()
        assert label_box.right() < field_box.left()
        assert abs(label_box.center().y() - field_box.center().y()) <= 1  # Centred on the field.
        settings.hide()
        # Embedded in the workspace at its smallest size, nothing is cut off at the side.
        history = History(None)
        window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
        settings.embed(window.pages)
        window.show_settings(settings)
        window.resize(window.minimumSize())
        window.show()
        for _ in range(3):  # Restacking posts follow-up layout requests.
            app.processEvents()
        assert label.geometry().bottom() < settings.theme.geometry().top()
        body = settings.scroll_area.widget()
        assert body.minimumSizeHint().width() <= settings.scroll_area.viewport().width()
        window.hide()
        window.deleteLater()
        history.close()
    finally:
        settings.close()
        settings.deleteLater()


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
