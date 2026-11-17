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

    page = VocabularyPage(history, lambda: current[0], save, lambda: "note")
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
    page = VocabularyPage(history, lambda: current[0], save, lambda: "note")
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
    page = VocabularyPage(history, lambda: "PySide", save, lambda: "note")
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


def test_engine_note_is_shown_and_follows_the_engine_after_refresh(app, tmp_path):
    history = History(tmp_path / "history.sqlite3")
    note = ["Whisper models use these terms as recognition hints."]
    page = VocabularyPage(history, lambda: "", lambda value: None, lambda: note[0])
    try:
        page.refresh()
        assert page.engine_note.text() == note[0]
        note[0] = "Parakeet restores the spelling of these terms."
        page.refresh()
        assert page.engine_note.text() == note[0]
    finally:
        page.deleteLater()


def test_vocabulary_is_three_cards_with_icon_buttons_and_a_quiet_forget(app):
    from PySide6.QtWidgets import QLabel

    from localphraser.appearance import GlassPanel, Glyph

    history = History(None)
    page = VocabularyPage(history, lambda: "Codex, PySide", lambda value: None, lambda: "note")
    try:
        page.refresh()
        cards = page.findChildren(GlassPanel, "vocabularyCard")
        titles = [
            next(
                label.text()
                for label in card.findChildren(QLabel)
                if label.property("sectionTitle")
            )
            for card in cards
        ]
        assert titles == ["Add a word", "Approved words", "Suggestions to review"]
        assert all(card.findChild(Glyph) is not None for card in cards)
        add, approved, review = cards
        for widget in (page.entry, page.add_button, page.correct_button, page.notice):
            assert add.isAncestorOf(widget)
        for widget in (page.budget, page.words, page.remove_button):
            assert approved.isAncestorOf(widget)
        for widget in (
            page.pending,
            page.empty_suggestions,
            page.accept_button,
            page.dismiss_button,
            page.forget_button,
        ):
            assert review.isAncestorOf(widget)
        assert (page.add_button.role, page.add_button.glyph) == ("primary", "plus")
        assert (page.forget_button.role, page.forget_button.glyph) == ("danger", "trash")
        assert page.accept_button.glyph == "check" and page.dismiss_button.glyph == "close"
        assert page.remove_button.glyph == "trash" and page.remove_button.role != "danger"
        assert page.findChild(QLabel, "pageTitle").text() == "Your vocabulary"
        assert [page.words.item(row).text() for row in range(2)] == ["Codex", "PySide"]
    finally:
        page.deleteLater()
        history.close()
