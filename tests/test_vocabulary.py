from unittest.mock import Mock

import pytest

from localphraser.history import History
from localphraser.vocabulary import VocabularyPage, normalize_term, suggestions


def test_recurring_terms_need_distinct_dictations_and_ignore_addresses_and_common_words():
    rows = suggestions(
        [
            "Hello I use Codex Codex and PySide",
            "Hello I use Codex with PySide at a@Example.com https://Example.com",
        ],
        [],
        "PySide",
    )
    assert rows == [{"term": "Codex", "source": "repeated", "count": 2}]
    assert not suggestions(["Codex Codex"], [], "")
    assert not suggestions(["Codex", "Codex"], [{"term": "codex", "source": "dismissed"}], "")


@pytest.mark.parametrize("term", ["", " ", "foo,bar", "x\nword", "wrong\u202ename", "x" * 65])
def test_invalid_terms_are_rejected(term):
    with pytest.raises(ValueError):
        normalize_term(term)


def test_vocabulary_page_migrates_existing_hints_and_reviews_corrections(app, tmp_path):
    history = History(tmp_path / "history.sqlite3")
    current = ["Codex"]

    def save(value):
        current[0] = value

    page = VocabularyPage(history, lambda: current[0], save)
    try:
        page.refresh()
        assert page.words.item(0).text() == "Codex"
        page.entry.setText("PySide")
        page.suggest_correction()
        assert current[0] == "Codex" and page.pending.count() == 1
        page.pending.setCurrentRow(0)
        page.approve()
        assert current[0] == "Codex, PySide" and page.pending.count() == 0
        page.words.setCurrentRow(0)
        page.remove_word()
        assert current[0] == "PySide"
        page.entry.setText("LocalPhraser")
        page.suggest_correction()
        page.pending.setCurrentRow(0)
        page.dismiss()
        assert not page.pending.count()
        history.close()
        history = History(tmp_path / "history.sqlite3")
        assert {row["source"] for row in history.vocabulary_feedback()} == {
            "correction",
            "dismissed",
        }
    finally:
        page.deleteLater()
        history.close()


def test_vocabulary_save_failure_or_budget_does_not_publish_changes(app):
    history = History(None)
    save = Mock(side_effect=OSError("private path"))
    current = [""]
    page = VocabularyPage(history, lambda: current[0], save)
    try:
        page.entry.setText("Codex")
        page.add_word()
        assert current[0] == "" and "private" not in page.notice.text()
        current[0] = "a" * 295
        save.reset_mock()
        page.entry.setText("LocalPhraser")
        page.add_word()
        save.assert_not_called()
        assert "300" in page.notice.text()
    finally:
        page.deleteLater()
        history.close()


def test_forgetting_suggestions_preserves_approved_words_and_requires_confirmation(
    app, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    history = History(None)
    history.set_vocabulary_feedback("Codex", "correction")
    save = Mock()
    page = VocabularyPage(history, lambda: "PySide", save)
    try:
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
        page.forget_suggestions()
        assert len(history.vocabulary_feedback()) == 1
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
        page.forget_suggestions()
        assert not history.vocabulary_feedback()
        save.assert_not_called()
        assert page.words.item(0).text() == "PySide"
    finally:
        page.deleteLater()
        history.close()
