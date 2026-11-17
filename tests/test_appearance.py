from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontInfo, QImage, QPainter, QPalette
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
            assert appearance.theme(dark).text in dialog.styleSheet()
            assert appearance.theme(not dark).text not in dialog.styleSheet()
            # The capsule floats over other apps: one dark, legible look in both themes.
            assert appearance.theme(True).text in indicator.styleSheet()
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


def test_capsule_shows_the_live_meter_while_listening_and_a_painted_dot_otherwise(app):
    from localphraser.pipeline import State

    indicator = Indicator()
    try:
        indicator.display(State.RECORDING)
        app.processEvents()
        # Listening: the level meter takes the dot's place, left of the status line.
        assert indicator.meter.isVisible() and not indicator.dot.isVisible()
        assert indicator.meter.width() >= 48 and indicator.meter.height() <= 28
        assert indicator.meter.geometry().right() < indicator.status.geometry().left()
        indicator.live_preview("words while speaking")
        assert indicator.meter.isVisible() and not indicator.dot.isVisible()
        quiet = indicator.grab().toImage()
        for _ in range(6):
            indicator.set_level(0.9)
        app.processEvents()
        assert indicator.grab().toImage() != quiet  # The level is drawn, not only stored.
        for state, channel in ((State.ERROR, "red"), (State.TRANSCRIBING, "amber")):
            indicator.display(state)
            app.processEvents()
            assert indicator.dot.isVisible() and not indicator.meter.isVisible()
            assert not any(indicator.meter.levels)  # Left flat for the next recording.
            image = indicator.grab().toImage()
            centre = indicator.dot.mapTo(indicator, indicator.dot.rect().center())
            pixel = image.pixelColor(centre)
            assert pixel.red() > pixel.blue() + 60
            if channel == "red":
                assert pixel.red() > pixel.green() + 60
            else:
                assert pixel.green() > pixel.blue() + 60
        indicator.preview("Partial words.")
        assert indicator.dot.isVisible() and not indicator.meter.isVisible()
    finally:
        indicator.close()
        indicator.deleteLater()


def test_capsule_is_the_same_dark_pill_in_both_themes_with_a_gradient_rim(app, monkeypatch):
    from localphraser.pipeline import State

    images = {}
    for dark in (False, True):
        monkeypatch.setattr(appearance, "dark_surface", lambda dark=dark: dark)
        indicator = Indicator()
        try:
            indicator.display(State.TRANSCRIBING)
            app.processEvents()
            image = indicator.grab().toImage()
            images[dark] = image
            middle = image.height() // 2
            body = image.pixelColor(image.width() // 2, image.height() - 6)
            assert body.alpha() >= 235 and body.lightness() < 40  # Deep, nearly opaque.
            words = QColor(appearance.theme(True).text)
            assert contrast(words, body) >= 12
            left, right = image.pixelColor(0, middle), image.pixelColor(image.width() - 1, middle)
            assert left.green() > left.red() + 40  # Cyan at one end of the rim...
            assert right.blue() > right.green() + 40  # ...violet at the other.
        finally:
            indicator.close()
            indicator.deleteLater()
    assert images[False] == images[True]


def meter_image(meter, app):
    app.processEvents()
    return meter.grab().toImage()


def test_level_meter_draws_levels_scrolls_them_left_and_flattens_on_reset(app):
    meter = appearance.LevelMeter(bars=12)
    meter.resize(96, 32)
    meter.show()
    try:
        idle = meter_image(meter, app)
        assert len(meter.levels) == 12 and not any(meter.levels) and not meter.active

        def ink(image, columns):
            background = image.pixelColor(0, 0)
            return sum(
                image.pixelColor(x, y) != background for x in columns for y in range(image.height())
            )

        right, left = range(64, 96), range(0, 32)
        assert ink(idle, range(96)) > 0  # Idle still shows short flat bars.
        meter.set_level(0.3)
        low = meter_image(meter, app)
        meter.reset()
        meter.set_level(1.0)
        high = meter_image(meter, app)
        assert meter.active and meter.levels[-1] == 1.0 and len(meter.levels) == 12
        # Different levels paint differently: louder means taller bars.
        assert ink(high, right) > ink(low, right) > ink(idle, right)
        assert ink(high, left) == ink(idle, left)  # The newest level is on the right.
        for _ in range(11):
            meter.set_level(0.0)
        scrolled = meter_image(meter, app)
        assert meter.levels[0] == 1.0 and len(meter.levels) == 12  # A fixed-length history.
        assert ink(scrolled, left) > ink(idle, left) and ink(scrolled, right) < ink(high, right)
        meter.set_level(7.0)
        meter.set_level(-3.0)
        assert list(meter.levels)[-2:] == [1.0, 0.0]  # Clamped to the meter's range.
        meter.reset()
        assert not meter.active and not any(meter.levels)
        assert meter_image(meter, app) == idle
    finally:
        meter.close()
        meter.deleteLater()


def test_level_meter_uses_the_palette_text_colour_in_high_contrast(app, monkeypatch):
    monkeypatch.setattr(appearance, "high_contrast", lambda: True)
    meter = appearance.LevelMeter(bars=8)
    meter.resize(64, 24)
    meter.show()
    try:
        for _ in range(8):
            meter.set_level(1.0)
        image = meter_image(meter, app)
        text = meter.palette().color(QPalette.ColorRole.WindowText)
        assert image.pixelColor(image.width() - 5, image.height() // 2) == text
    finally:
        meter.close()
        meter.deleteLater()


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


def colour_gap(image, first, second, other=None):
    """Mean colour distance between two regions (of one image, or of two images)."""

    def mean(source, rect):
        totals = [0, 0, 0]
        count = 0
        for x in range(rect.left(), rect.right() + 1):
            for y in range(rect.top(), rect.bottom() + 1):
                pixel = source.pixelColor(x, y)
                totals[0] += pixel.red()
                totals[1] += pixel.green()
                totals[2] += pixel.blue()
                count += 1
        return [total / count for total in totals]

    a, b = mean(image, first), mean(other or image, second)
    return sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) ** 0.5


@pytest.mark.parametrize("dark", [False, True])
def test_switch_shows_off_on_and_focus_states(app, monkeypatch, dark):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QCheckBox, QPushButton, QVBoxLayout

    monkeypatch.setattr(appearance, "dark_surface", lambda: dark)
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
        assert isinstance(box, QCheckBox)  # Same role and keyboard handling as a check box.

        def capture():
            app.processEvents()
            return dialog.grab().toImage()

        frame = box.indicator_rect().translated(box.mapTo(dialog, box.rect().topLeft()))
        assert frame.width() >= frame.height() * 1.6  # A track, not a square box.
        inset = frame.height() // 2 - 3
        centre = frame.center().y()
        left = QRect(frame.left() + inset, centre - 2, 5, 5)  # The thumb when off.
        right = QRect(frame.right() - inset - 4, centre - 2, 5, 5)  # The thumb when on.
        ring = QRect(frame.left() + 8, frame.top() - 2, frame.width() - 16, 2)  # Above it.
        box.setChecked(False)
        off = capture()
        # Off is still drawn: a thumb resting at the left end of a visible track.
        assert colour_gap(off, left, right) > 40
        assert lightness(off, left) > lightness(off, right)
        box.setChecked(True)
        on = capture()
        # On moves the thumb to the right (position, not only colour) and fills the track.
        assert colour_gap(on, left, right) > 60
        assert lightness(on, right) > lightness(on, left)
        assert colour_gap(off, left, left, on) > 60
        unfocused_ring = lightness(on, ring)
        box.setFocus(Qt.FocusReason.TabFocusReason)
        assert box.hasFocus()
        focused = capture()
        assert abs(lightness(focused, ring) - unfocused_ring) > 15
        QTest.keyClick(box, Qt.Key.Key_Space)
        assert not box.isChecked()  # Space still toggles it.
    finally:
        dialog.close()
        dialog.deleteLater()


def test_switch_is_a_native_check_box_in_high_contrast(app, monkeypatch):
    monkeypatch.setattr(appearance, "high_contrast", lambda: True)
    dialog = appearance.GlassDialog()
    box = appearance.GlassCheckBox("Keep transcript history on this device")
    box.setParent(dialog)
    try:
        assert not dialog.styleSheet()
        frame = box.indicator_rect()
        assert frame.width() < frame.height() * 1.6  # The system's own square indicator.
        assert not box.grab().isNull()
    finally:
        dialog.deleteLater()


def contrast(first, second):
    def luminance(color):
        channels = []
        for value in (color.redF(), color.greenF(), color.blueF()):
            channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_theme_tokens_are_frozen_and_carry_the_design_colours():
    from dataclasses import FrozenInstanceError

    dark, light = appearance.theme(True), appearance.theme(False)
    assert (dark.text, dark.muted, dark.glow, dark.focus) == (
        "#F3F6FF",
        "#A7B3D1",
        "#22D3EE",
        "#22D3EE",
    )
    assert (light.text, light.muted, light.glow, light.focus) == (
        "#0B1433",
        "#46527A",
        "#0891B2",
        "#4F46E5",
    )
    assert dark.accent == light.accent == ("#4F46E5", "#7C3AED", "#C026D3")
    assert dark.backdrop == ("#060913", "#0B1024", "#120B2A")
    assert light.backdrop == ("#F4F7FF", "#E9EEFF", "#F3E9FF")
    assert appearance.theme(True) is dark and dark.dark and not light.dark
    with pytest.raises(FrozenInstanceError):
        dark.text = "#000000"


@pytest.mark.parametrize("dark", [False, True])
def test_white_text_reaches_aa_on_every_primary_gradient_stop(dark):
    tokens = appearance.theme(dark)
    for stop in (*tokens.accent, *tokens.accent_pressed):
        assert contrast(QColor("white"), QColor(stop)) >= 4.5, stop


@pytest.mark.parametrize("size", [(1040, 740), (600, 480), (1920, 1040)])
@pytest.mark.parametrize("dark", [False, True])
def test_text_muted_and_danger_reach_aa_on_every_painted_surface(app, dark, size):
    tokens = appearance.theme(dark)
    area = QRectF(0, 0, *size)
    stacks = {
        "backdrop": (),
        "panel": ({},),
        "nested card": ({}, {"nested": True}),
        "selected card": ({"selected": True},),
    }
    for name, layers in stacks.items():
        image = QImage(*size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        appearance.paint_backdrop(painter, area, tokens, False, 22)
        for layer in layers:
            appearance.paint_panel(painter, area, tokens, 18, **layer)
        painter.end()
        # Every part of the surface, including the brightest and darkest aurora light.
        pixels = [
            image.pixelColor(x, y)
            for x in range(24, size[0] - 24, 9)
            for y in range(24, size[1] - 24, 9)
        ]
        for role in ("text", "muted", "danger"):
            colour = QColor(getattr(tokens, role))
            worst = min(pixels, key=lambda pixel: contrast(colour, pixel))
            assert contrast(colour, worst) >= 4.5, (name, role, worst.name())


def test_segmented_control_fills_the_selected_segment_and_keeps_tab_keys(app):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QTabBar, QTabWidget, QTextEdit, QVBoxLayout

    dialog = appearance.GlassDialog()
    layout = QVBoxLayout(dialog)
    tabs = appearance.SegmentedTabs()
    tabs.addTab(QTextEdit(), "Result")
    tabs.addTab(QTextEdit(), "Original")
    layout.addWidget(tabs)
    dialog.resize(420, 240)
    dialog.show()
    try:
        bar = tabs.tabBar()
        assert isinstance(tabs, QTabWidget) and isinstance(bar, QTabBar)
        assert [bar.tabText(index) for index in range(bar.count())] == ["Result", "Original"]

        def fill(index):
            app.processEvents()
            rect = bar.tabRect(index)
            point = bar.mapTo(dialog, QPoint(rect.left() + 8, rect.center().y()))
            return dialog.grab().toImage().pixelColor(point)

        accent = QColor(appearance.theme(False).accent[0])
        assert contrast(fill(0), accent) < 1.6 < contrast(fill(1), accent)
        bar.setFocus()
        QTest.keyClick(bar, Qt.Key.Key_Right)  # Still a tab bar: arrow keys change the tab.
        assert tabs.currentIndex() == 1
        assert contrast(fill(1), accent) < 1.6 < contrast(fill(0), accent)
    finally:
        dialog.close()
        dialog.deleteLater()


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
        assert hint_color == QColor(appearance.theme(dark).muted)
        assert label_color == QColor(appearance.theme(dark).text)
        # Readable on what is actually painted around the hint, not on an assumed colour.
        settings.scroll_area.ensureWidgetVisible(hint)
        app.processEvents()
        image = settings.grab().toImage()
        for offset in (QPoint(-3, hint.height() // 2), QPoint(hint.width() + 2, 2)):
            point = hint.mapTo(settings, offset)
            assert image.rect().contains(point)
            surface = image.pixelColor(point)
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
