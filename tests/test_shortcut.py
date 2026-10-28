import gc
import os
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QScrollArea

from localphraser.config import Config
from localphraser.pipeline import State
from localphraser.shortcut import ShortcutRecorder, shortcut_from_key
from localphraser.ui import Desktop, Latest, Settings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application
    application.closeAllWindows()
    for widget in application.topLevelWidgets():
        widget.deleteLater()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    gc.collect()


@pytest.fixture
def chooser(app):
    begin, end = Mock(), Mock()
    widget = ShortcutRecorder("CapsLock", begin, end)
    widget.show()
    app.processEvents()
    yield widget, begin, end
    widget.cancel_capture()
    widget.close()


def test_choose_combination_from_actual_key_events(chooser):
    widget, begin, end = chooser
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    assert widget.capturing
    QTest.keyClick(
        widget,
        Qt.Key.Key_F9,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert widget.shortcut_value == "Ctrl+Shift+F9"
    assert not widget.capturing
    begin.assert_called_once()
    end.assert_called_once()


def test_single_function_key_and_caps_selection(chooser):
    widget, begin, end = chooser
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    QTest.keyClick(widget, Qt.Key.Key_F9)
    assert widget.shortcut_value == "F9"
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    # Native Caps Lock suppression forwards only this explicit chooser callback.
    begin.call_args.args[0]()
    assert widget.shortcut_value == "CapsLock"
    assert not widget.capturing
    assert end.call_count == 2


def test_invalid_plain_letter_does_not_capture_typing_key(chooser):
    widget, _, _ = chooser
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    QTest.keyClick(widget, Qt.Key.Key_A)
    assert widget.capturing and widget.shortcut_value == "CapsLock"
    QTest.keyClick(widget, Qt.Key.Key_Escape)
    assert not widget.capturing and widget.shortcut_value == "CapsLock"


def test_focus_loss_restores_dictation_shortcut(chooser, app):
    widget, _, end = chooser
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    widget.clearFocus()
    app.processEvents()
    assert not widget.capturing
    end.assert_called_once()


def test_modifier_alone_does_not_finish_selection():
    assert shortcut_from_key(Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier) is None
    with pytest.raises(ValueError):
        shortcut_from_key(Qt.Key.Key_F12, Qt.KeyboardModifier.NoModifier)


def test_settings_save_recorded_shortcut_and_microphone_preference(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    applied = Mock()
    settings = Settings(Config(), applied)
    settings.show()
    app.processEvents()
    QTest.mouseClick(settings.hotkey, Qt.MouseButton.LeftButton)
    QTest.keyClick(settings.hotkey, Qt.Key.Key_F9)
    settings.keep_ready.setChecked(False)
    settings.save()
    assert applied.call_args.args[0].hotkey == "F9"
    assert applied.call_args.args[0].keep_microphone_ready is False
    settings.close()


def test_capture_restores_existing_runtime_shortcut():
    desktop = object.__new__(Desktop)
    desktop.pipeline = Mock(state=State.IDLE)
    desktop.config = Config(hotkey="Ctrl+Shift+F9")
    desktop.hotkey = Mock()
    desktop.hotkey._caps_handle = None
    desktop.closing = False
    callback = Mock()
    desktop.begin_shortcut_capture(callback)
    assert desktop.hotkey.capture_callback is callback
    desktop.hotkey.register.assert_called_with("CapsLock")
    desktop.end_shortcut_capture()
    assert desktop.hotkey.capture_callback is None
    desktop.hotkey.register.assert_called_with("Ctrl+Shift+F9")


def test_settings_edit_and_clear_vocabulary_without_changing_model(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    applied = Mock()
    settings = Settings(Config(model="small.en", vocabulary="Codex"), applied)
    assert settings.vocabulary.text() == "Codex"
    settings.vocabulary.setText("  Codex, PySide, NumPy  ")
    settings.save()
    config = applied.call_args.args[0]
    assert config.vocabulary == "Codex, PySide, NumPy"
    assert config.model == "small.en"
    settings.vocabulary.clear()
    assert settings.values().vocabulary == ""
    settings.close()


def test_caps_selection_waits_for_key_up_before_restoring_shortcut():
    desktop = object.__new__(Desktop)
    desktop.hotkey = Mock()
    desktop.hotkey._caps_handle = Mock(down=True)
    desktop.config = Config(hotkey="F9")
    desktop.closing = False
    desktop.end_shortcut_capture()
    desktop.hotkey.close.assert_not_called()
    assert desktop.hotkey.capture_release_callback == desktop.end_shortcut_capture
    desktop.hotkey._caps_handle.down = False
    desktop.hotkey.capture_release_callback()
    desktop.hotkey.close.assert_called_once()
    desktop.hotkey.register.assert_called_once_with("F9")
    assert desktop.hotkey.capture_callback is None


def test_polishing_settings_and_both_transcripts(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    config = Config(mode="polished", refinement_model="qwen2.5-1.5b", refinement_timeout=8)
    settings = Settings(config, Mock())
    assert settings.values() == config
    settings.refinement_prompt.setPlainText("Punctuate only.")
    assert settings.values().refinement_prompt == "Punctuate only."
    settings.mode.setCurrentIndex(0)
    assert settings.values().mode == "raw"
    assert settings.values().refinement_model == "qwen2.5-1.5b"
    settings.close()
    latest = Latest()
    latest.raw.setPlainText("hello world")
    latest.set_transcript("Hello, world.", "Inserted.")
    assert latest.text.toPlainText() == "Hello, world."
    assert latest.raw.toPlainText() == "hello world"
    latest.clear()
    assert not latest.text.toPlainText() and not latest.raw.toPlainText()
    latest.close()


def test_polished_settings_scroll_without_hiding_save(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    settings = Settings(Config(mode="polished"), Mock())
    settings.resize(620, 480)
    settings.show()
    app.processEvents()
    scroll = settings.findChild(QScrollArea)
    buttons = settings.findChild(QDialogButtonBox)
    assert scroll.verticalScrollBar().maximum() > 0
    assert buttons.isVisible()
    assert buttons.geometry().bottom() <= settings.height()
    settings.close()
