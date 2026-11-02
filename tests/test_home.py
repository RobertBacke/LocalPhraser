import sqlite3
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

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


def test_invalid_saved_timestamp_does_not_hide_recoverable_words(saved_workspace):
    window, history = saved_workspace
    with history.connection:
        history.connection.execute("UPDATE transcripts SET created='invalid date'")
    window.refresh_history()
    assert "Saved transcription" in window.entries.item(0).text()
    assert window.result_text.toPlainText() == "Recover these words."
