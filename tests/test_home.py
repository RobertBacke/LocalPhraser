import sqlite3
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox, QPushButton

from localphraser import appearance
from localphraser.history import History
from localphraser.home import AppWindow


def test_workspace_browses_deletes_and_clears_persistent_history(app, tmp_path, monkeypatch):
    history = History(tmp_path / "history.sqlite3")
    history.add("hello world", "Hello, world.", "Inserted.", 2)
    history.add("another three words", "Another three words.", "Inserted.", 3)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    window.show()
    assert window.windowFlags() & Qt.WindowType.Window
    assert window.entries.count() == 2
    assert window.result_text.toPlainText() == "Another three words."
    assert window.metric_labels[2].text() == "60 wpm"
    window.delete_button.click()
    assert window.entries.count() == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    window.clear_history()
    assert history.stats()[0] == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.clear_history()
    assert history.stats() == (0, 0, None)
    assert not window.result_text.toPlainText()
    assert not window.delete_button.isEnabled()
    window.close()
    assert not window.isVisible()
    window.deleteLater()
    history.close()


@pytest.fixture
def saved_workspace(app, tmp_path):
    history = History(tmp_path / "history.sqlite3")
    history.add("recover these words", "Recover these words.", "Inserted.", 2)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    yield window, history
    window.hide()
    window.deleteLater()
    history.close()


@pytest.mark.parametrize("operation", ["stats", "recent", "get"])
def test_history_read_failure_preserves_display_and_recovers(
    saved_workspace, monkeypatch, operation
):
    window, history = saved_workspace
    original = getattr(history, operation)
    monkeypatch.setattr(history, operation, Mock(side_effect=sqlite3.DatabaseError("private path")))
    window.refresh_history()
    assert window.result_text.toPlainText() == "Recover these words."
    assert window.entries.count() == 1
    assert window.history_notice.text() and not window.history_notice.isHidden()
    assert "private" not in window.history_notice.text()
    monkeypatch.setattr(history, operation, original)
    window.show_home()
    assert window.history_notice.isHidden()
    assert window.result_text.toPlainText() == "Recover these words."


def test_history_selection_read_failure_keeps_copyable_text(saved_workspace, monkeypatch):
    window, history = saved_workspace
    monkeypatch.setattr(
        history, "get", Mock(side_effect=sqlite3.DatabaseError("fixture read error"))
    )
    window.select_entry(window.entries.currentItem())
    assert window.result_text.toPlainText() == "Recover these words."
    assert window.copy_button.isEnabled()
    assert not window.delete_button.isEnabled()
    assert not window.history_notice.isHidden()


@pytest.mark.parametrize("operation", ["delete_entry", "clear_history"])
def test_readonly_history_reports_failed_deletion_without_losing_text(
    saved_workspace, monkeypatch, operation
):
    window, history = saved_workspace
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    history.connection.execute("PRAGMA query_only=ON")
    getattr(window, operation)()
    assert history.stats()[0] == 1
    assert window.result_text.toPlainText() == "Recover these words."
    assert not window.history_notice.isHidden()
    history.connection.execute("PRAGMA query_only=OFF")
    getattr(window, operation)()
    assert history.stats()[0] == 0
    assert window.history_notice.isHidden()


def text_bands(image):
    """Count separate horizontal runs of dark (text) pixels in a light row."""
    bands, inside = 0, False
    for y in range(image.height()):
        ink = any(image.pixelColor(x, y).lightness() < 128 for x in range(image.width()))
        if ink and not inside:
            bands += 1
        inside = ink
    return bands


def test_selected_and_unselected_history_rows_show_date_and_preview_lines(app):
    history = History(None)
    history.add("first words", "Hello there, everyone.", "Inserted.", 2)
    history.add("second words", "Thanks again for coming.", "Inserted.", 3)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    window.resize(1040, 740)
    window.show()
    app.processEvents()
    try:
        assert window.entries.currentRow() == 0
        for row in (0, 1):
            item = window.entries.item(row)
            assert item.isSelected() is (row == 0)
            rect = window.entries.visualItemRect(item)
            image = window.entries.viewport().grab(rect).toImage()
            assert text_bands(image) == 2, f"row {row} shows {text_bands(image)} line(s)"
    finally:
        window.hide()
        window.deleteLater()
        history.close()


def test_empty_history_shows_a_first_use_message_naming_the_shortcut(app):
    history = History(None)
    window = AppWindow(history, Mock(), Mock(), Mock(), "F9")
    window.show()
    app.processEvents()
    try:
        assert window.empty_history.isVisible()
        assert not window.entries.isVisible()
        message = window.empty_message.text()
        assert "F9" in message and "first dictation will appear here" in message
        window.set_hint("Double-tap F8 to start or stop recording.")
        assert "Double-tap F8" in window.empty_message.text()
        assert window.hint.text() == "Double-tap F8 to start or stop recording."
        history.add("first words", "First words.", "Inserted.", 2)
        window.refresh_history()
        app.processEvents()
        assert not window.empty_history.isVisible()
        assert window.entries.isVisible() and window.entries.count() == 1
    finally:
        window.hide()
        window.deleteLater()
        history.close()


def test_entry_notice_is_a_separate_wrapped_hint(app):
    history = History(None)
    notice = "Target could not be verified. Open Latest transcript to copy. " * 3
    history.add("words here", "Words here.", notice, 2)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    try:
        assert window.entry_info.text() == "2 words · 2.0s recorded"
        assert window.entry_notice.text() == notice
        assert window.entry_notice.wordWrap() and window.entry_notice.property("hint") is True
    finally:
        window.deleteLater()
        history.close()


def colour_distance(first, second):
    return (
        (first.red() - second.red()) ** 2
        + (first.green() - second.green()) ** 2
        + (first.blue() - second.blue()) ** 2
    ) ** 0.5


def test_sidebar_separates_navigation_from_actions_and_shows_a_state_chip(app):
    history = History(None)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    try:
        for button in (
            window.home_button,
            window.settings_button,
            window.vocabulary_button,
            window.analytics_button,
        ):
            assert button.property("nav") is True
        assert window.record_button.property("nav") is not True
        quit_button = next(
            b for b in window.sidebar.findChildren(QPushButton) if b.text() == "Quit LocalPhraser"
        )
        # Quit is a quiet row with the power icon: not navigation, not a boxed button.
        assert quit_button.property("nav") is not True
        assert quit_button.property("quiet") is True and quit_button.glyph == "power"
        window.set_state("Listening", "recording")
        assert window.state_label.text() == "Listening"
        assert window.state_dot.tone == "recording"
        # The dot and its label sit together in one status chip at the foot of the sidebar.
        assert window.state_dot.parentWidget() is window.state_label.parentWidget()
        assert window.sidebar.isAncestorOf(window.state_label)
    finally:
        window.deleteLater()
        history.close()


def test_navigation_rows_have_icons_and_mark_the_current_page(app):
    history = History(None)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock", latest=Mock())
    window.resize(1040, 740)
    window.show()
    app.processEvents()
    try:
        rows = {
            "Home": (window.home_button, "home"),
            "Settings": (window.settings_button, "settings"),
            "Vocabulary": (window.vocabulary_button, "vocabulary"),
            "Analytics": (window.analytics_button, "analytics"),
            "Latest transcript": (
                next(
                    b
                    for b in window.sidebar.findChildren(QPushButton)
                    if b.text() == "Latest transcript"
                ),
                "transcript",
            ),
        }
        image = window.grab().toImage()
        for text, (button, glyph) in rows.items():
            assert button.text() == text and button.glyph == glyph  # Icon beside the label.
            # The icon is really painted: its box holds strokes that differ from the row.
            box = button.glyph_rect().toRect()
            origin = button.mapTo(window, box.topLeft())
            background = image.pixelColor(origin)
            strokes = sum(
                colour_distance(image.pixelColor(origin.x() + x, origin.y() + y), background) > 60
                for x in range(box.width())
                for y in range(box.height())
            )
            assert strokes >= 12, (text, strokes)

        glow = QColor(appearance.current_theme().glow)

        def marker(button):
            app.processEvents()
            rect = button.marker_rect().toRect()
            point = button.mapTo(window, QPoint(rect.center().x(), rect.top() + 2))
            return window.grab().toImage().pixelColor(point)

        assert colour_distance(marker(window.home_button), glow) < 40
        assert colour_distance(marker(window.analytics_button), glow) > 80
        window.show_analytics()
        assert colour_distance(marker(window.analytics_button), glow) < 40
        assert colour_distance(marker(window.home_button), glow) > 80
        assert window.analytics_button.isChecked() and not window.home_button.isChecked()
    finally:
        window.hide()
        window.deleteLater()
        history.close()


def test_invalid_saved_timestamp_does_not_hide_recoverable_words(saved_workspace):
    window, history = saved_workspace
    with history.connection:
        history.connection.execute("UPDATE transcripts SET created='invalid date'")
    window.refresh_history()
    assert "Saved transcription" in window.entries.item(0).text()
    assert window.result_text.toPlainText() == "Recover these words."
