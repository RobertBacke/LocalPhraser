from unittest.mock import Mock

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QListView

from localphraser.config import MODELS, Config
from localphraser.ui import Settings


def test_model_popup_preserves_keyboard_selection_and_catalog_ids(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    saved = Mock()
    settings = Settings(Config(), saved)
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
