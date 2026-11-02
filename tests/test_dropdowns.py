from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGroupBox, QListView, QWidget

from localphraser.appearance import GlassComboBox
from localphraser.config import MODELS, Config
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
    assert [combo.itemText(i) for i in range(combo.count())] == list(MODELS)
    combo.setCurrentText("small.en")
    combo.setFocus()
    combo.showPopup()
    app.processEvents()
    assert combo.view().isVisible()
    QTest.keyClick(combo.view(), Qt.Key.Key_Down)
    QTest.keyClick(combo.view(), Qt.Key.Key_Return)
    assert combo.currentText() == "distil-small.en"
    settings.save()
    assert saved.call_args.args[0].model == "distil-small.en"
    assert settings.isVisible()
    settings.close()
    settings.deleteLater()
