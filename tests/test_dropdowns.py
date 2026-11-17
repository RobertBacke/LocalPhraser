from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGroupBox, QListView, QWidget

from localphraser.appearance import GlassComboBox, GlassSpinBox
from localphraser.config import MODEL_NAMES, MODELS, PARAKEET_MODEL, Config
from localphraser.ui import Settings


def test_polished_settings_never_shows_a_detached_group_window(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    shown = []

    class WatchShows(QObject):
        def eventFilter(self, receiver, event):
            if event.type() == QEvent.Type.Show and isinstance(receiver, QGroupBox):
                if receiver.isWindow():
                    shown.append(receiver.title())
            return False

    watcher = WatchShows()
    settings = None
    app.installEventFilter(watcher)
    try:
        settings = Settings(Config(mode="polished"), Mock())
        assert not shown, f"Detached settings panels were shown: {shown}"
    finally:
        app.removeEventFilter(watcher)
        if settings is not None:
            settings.hide()
            settings.deleteLater()


@pytest.mark.parametrize("position", [(10, 10), (10, 275), (260, 155)])
def test_popup_stays_inside_compact_owner_and_all_items_are_reachable(app, position):
    host = QWidget()
    host.setGeometry(60, 70, 520, 340)
    combo = GlassComboBox()
    combo.setParent(host)
    combo.setGeometry(*position, 240, 40)
    combo.addItems([f"Microphone {i}: " + "a long device label " * 5 for i in range(25)])
    host.show()
    app.processEvents()
    bounds = QRect(host.mapToGlobal(QPoint()), host.size())
    try:
        combo.showPopup()
        app.processEvents()
        assert bounds.contains(combo.view().window().geometry())
        QTest.keyClick(combo.view(), Qt.Key.Key_End)
        QTest.keyClick(combo.view(), Qt.Key.Key_Return)
        assert combo.currentIndex() == 24
        combo.showPopup()
        app.processEvents()
        assert bounds.contains(combo.view().window().geometry())
        QTest.keyClick(combo.view(), Qt.Key.Key_Home)
        QTest.keyClick(combo.view(), Qt.Key.Key_Escape)
        assert combo.currentIndex() == 24
        assert not combo.view().isVisible()
    finally:
        combo.hidePopup()
        host.hide()
        host.deleteLater()


def test_model_popup_preserves_keyboard_selection_and_catalog_ids(app, monkeypatch, tmp_path):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    saved = Mock()
    from localphraser.models import model_files

    folder = tmp_path / "distil-small.en"
    folder.mkdir()
    for name in (*model_files("distil-small.en"), "localphraser-manifest.json"):
        (folder / name).touch()
    settings = Settings(Config(model_root=str(tmp_path)), saved)
    settings.show()
    combo = settings.model
    assert isinstance(combo.view(), QListView)
    # Friendly names are shown; the catalog id stays the item's data and the saved value.
    assert [combo.itemData(i) for i in range(combo.count())] == list(MODELS)
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Parakeet — recommended",
        "Whisper tiny.en",
        "Whisper base.en",
        "Whisper small.en",
        "Whisper distil-small.en",
        "Whisper distil-medium.en",
        "Whisper medium.en",
    ]
    assert combo.currentData() == PARAKEET_MODEL
    assert combo.select_data("small.en")
    assert combo.currentText() == "Whisper small.en"
    app.processEvents()  # Let the quality row relayout before the popup opens.
    combo.setFocus()
    combo.showPopup()
    app.processEvents()
    assert combo.view().isVisible()
    QTest.keyClick(combo.view(), Qt.Key.Key_Down)
    QTest.keyClick(combo.view(), Qt.Key.Key_Return)
    assert combo.currentData() == "distil-small.en"
    assert combo.currentText() == "Whisper distil-small.en"
    settings.save()
    assert saved.call_args.args[0].model == "distil-small.en"
    assert settings.isVisible()
    settings.close()
    settings.deleteLater()


def test_parakeet_disables_recognition_quality_and_keeps_the_saved_value(
    app, monkeypatch, tmp_path
):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    saved = Mock()
    from localphraser.models import model_files

    folder = tmp_path / PARAKEET_MODEL
    folder.mkdir()
    for name in (*model_files(PARAKEET_MODEL), "localphraser-manifest.json"):
        (folder / name).touch()
    config = Config(model="small.en", recognition_quality="accurate", model_root=str(tmp_path))
    settings = Settings(config, saved)
    try:
        quality = settings.recognition_quality
        tooltip = quality.toolTip()
        assert quality.isEnabled()
        settings.model.select_data(PARAKEET_MODEL)
        assert not quality.isEnabled()
        assert settings.quality_hint.text() == "Recognition quality applies to Whisper models only."
        assert quality.currentData() == "accurate"
        settings.model.select_data("small.en")
        assert quality.isEnabled() and quality.toolTip() == tooltip
        assert settings.quality_hint.text() == ""
        settings.model.select_data(PARAKEET_MODEL)
        settings.save()
        assert saved.call_args.args[0].recognition_quality == "accurate"
    finally:
        settings.close()
        settings.deleteLater()


def test_settings_credit_line_attributes_parakeet(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    settings = Settings(Config(), Mock())
    try:
        text = settings.credits.text()
        assert "Speech models: Systran" in text
        assert "NVIDIA Parakeet TDT 0.6b v2 (CC-BY-4.0), ONNX conversion by istupakov" in text
        assert "Polishing models: Qwen" in text
    finally:
        settings.close()
        settings.deleteLater()


def wheel_over(widget, delta):
    """A real (spontaneous) wheel turn at the widget's centre, as a mouse would send it."""
    window = widget.window().windowHandle()
    centre = widget.mapTo(widget.window(), widget.rect().center())
    QTest.wheelEvent(window, QPointF(centre), QPoint(0, delta))


def test_wheel_over_a_setting_scrolls_the_page_and_changes_nothing(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    settings = Settings(Config(model="small.en", mode="polished", cpu_threads=1), Mock())
    try:
        settings.resize(560, 420)
        settings.show()
        app.processEvents()
        bar = settings.scroll_area.verticalScrollBar()
        assert bar.maximum() > 0
        before = settings.values()
        for control in (
            settings.theme,
            settings.activation_mode,
            settings.model,
            settings.recognition_quality,
            settings.mode,
            settings.refinement_model,
            settings.threads,
            settings.duration,
            settings.refinement_timeout,
        ):
            settings.scroll_area.ensureWidgetVisible(control)
            app.processEvents()
            control.setFocus()  # Focus must not turn the wheel into a value change.
            position = bar.value()
            down = position < bar.maximum()
            wheel_over(control, -120 if down else 120)
            app.processEvents()
            assert (bar.value() > position) if down else (bar.value() < position), control
            wheel_over(control, 120 if down else -120)
            app.processEvents()
        assert settings.values() == before
    finally:
        settings.hide()
        settings.deleteLater()


def test_keyboard_still_changes_a_focused_list_and_number(app):
    combo = GlassComboBox()
    combo.addItems(["one", "two", "three"])
    QTest.keyClick(combo, Qt.Key.Key_Down)
    assert combo.currentIndex() == 1
    spin = GlassSpinBox()
    spin.setRange(0, 10)
    QTest.keyClick(spin, Qt.Key.Key_Up)
    assert spin.value() == 1


def test_every_catalog_model_has_a_display_name():
    assert set(MODEL_NAMES) == set(MODELS)
    assert MODEL_NAMES[PARAKEET_MODEL] == "Parakeet"
    assert all(MODEL_NAMES[model] == f"Whisper {model}" for model in MODELS[1:])


def test_spin_buttons_still_step_the_value(app):
    from PySide6.QtWidgets import QStyle, QStyleOptionSpinBox

    from localphraser.appearance import GlassDialog

    host = GlassDialog()  # Carries the glass stylesheet that sizes the buttons.
    spin = GlassSpinBox(host)
    spin.setRange(0, 10)
    spin.setGeometry(10, 10, 200, 38)
    host.show()
    app.processEvents()
    try:
        option = QStyleOptionSpinBox()
        spin.initStyleOption(option)
        up = spin.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxUp, spin
        )
        assert up.isValid() and up.width() >= 20
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        assert spin.value() == 1
    finally:
        host.hide()
        host.deleteLater()
