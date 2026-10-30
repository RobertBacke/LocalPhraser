from unittest.mock import Mock

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
