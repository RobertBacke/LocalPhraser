import sqlite3
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
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


def test_history_rows_are_separate_cards_showing_time_and_preview_selected_or_not(app):
    history = History(None)
    history.add("first words", "Hello there, everyone.", "Inserted.", 2)
    history.add("second words", "Thanks again for coming.", "Inserted.", 3)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    window.resize(1040, 740)
    window.show()
    app.processEvents()
    try:
        assert window.entries.currentRow() == 0
        delegate = window.entries.itemDelegate()
        cards = []
        for row in (0, 1):
            item = window.entries.item(row)
            assert item.isSelected() is (row == 0)
            # The row's text still carries both lines for assistive technology.
            assert "words\n" in item.text()
            card = delegate.card_rect(window.entries.visualItemRect(item))
            cards.append(card)
            # Inside the card's rim: the time line and the preview line, selected or not.
            inner = card.adjusted(6, 6, -6, -6)
            image = window.entries.viewport().grab(inner).toImage()
            assert text_bands(image) == 2, f"row {row} shows {text_bands(image)} line(s)"
        # Separate cards: a gap of the backdrop between one card and the next.
        assert cards[1].top() - cards[0].bottom() >= 6
        view = window.entries.viewport().grab().toImage()
        edge = QPoint(cards[0].left(), cards[0].center().y())
        # The selected card is outlined in the accent; the other has a quiet glass rim.
        accent = QColor(appearance.current_theme().accent[0])
        assert colour_distance(view.pixelColor(edge), accent) < 70
        other = QPoint(cards[1].left(), cards[1].center().y())
        assert colour_distance(view.pixelColor(other), accent) > 120
    finally:
        window.hide()
        window.deleteLater()
        history.close()


def test_long_previews_take_two_elided_lines_and_never_more(app):
    history = History(None)
    words = "A much longer dictation that keeps going well past the width of a card. " * 4
    history.add(words, words, "Inserted.", 9)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    window.resize(1040, 740)
    window.show()
    app.processEvents()
    try:
        delegate = window.entries.itemDelegate()
        card = delegate.card_rect(window.entries.visualItemRect(window.entries.item(0)))
        image = window.entries.viewport().grab(card.adjusted(6, 6, -6, -6)).toImage()
        assert text_bands(image) == 3  # Time line, then exactly two preview lines.
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


@pytest.fixture
def workspace(app):
    history = History(None)
    record = Mock()
    window = AppWindow(history, Mock(), record, Mock(), "CapsLock", latest=Mock())
    window.resize(1040, 740)
    window.show()
    app.processEvents()
    yield window, history, record
    window.hide()
    window.deleteLater()
    history.close()


def test_hero_states_the_state_in_words_with_a_chip_and_an_orb(workspace):
    window, _, _ = workspace
    seen = {}
    for label, tone, headline in (
        ("Ready", "ready", "Ready to dictate"),
        ("Listening", "recording", "Listening"),
        ("Transcribing", "busy", "Transcribing"),
        ("Speech model required", "muted", "Speech model required"),
        ("Preparing speech model", "muted", "Preparing speech model"),
        ("Error", "recording", "Error"),
    ):
        window.set_state(label, tone)
        assert window.headline.text() == headline
        assert window.state_label.text() == label  # The sidebar keeps the plain label.
        assert window.orb.tone == window.hero_chip.dot.tone == window.state_dot.tone == tone
        # Never by colour alone: the chip always says a word beside its dot.
        assert window.hero_chip.label.text()
        seen[label] = window.hero_chip.label.text()
    assert seen["Listening"] != seen["Error"]  # Both are red; the words tell them apart.
    assert len({seen["Ready"], seen["Listening"], seen["Transcribing"]}) == 3
    for widget in (window.orb, window.hero_chip, window.headline, window.hint):
        assert window.hero.isAncestorOf(widget) and widget.isVisible()
    assert window.hint.text() == "Hold CapsLock, speak naturally, then release."
    assert window.orb.glyph == "microphone"


def test_record_button_is_the_hero_primary_action_and_shows_microphone_or_stop(workspace):
    window, _, record = workspace
    button = window.record_button
    assert window.hero.isAncestorOf(button) and not window.sidebar.isAncestorOf(button)
    assert button.property("primary") is True and button.property("nav") is not True
    assert button.text() == "Record to history" and button.glyph == "microphone"
    button.setText("Stop recording")
    assert button.glyph == "stop"
    for label in ("Record (manual copy)", "Record to history"):
        button.setText(label)
        assert button.glyph == "microphone" and button.text() == label
    assert "shortcut" in button.toolTip()
    button.click()
    record.assert_called_once_with()


def test_hero_meter_and_orb_follow_the_level_and_are_flat_when_idle(workspace, app):
    window, _, _ = workspace
    meter = window.hero_meter
    assert window.hero.isAncestorOf(meter) and meter.isVisible()
    assert not meter.active and not any(meter.levels) and window.orb.level == 0.0
    window.set_state("Listening", "recording")
    app.processEvents()
    quiet = window.orb.grab().toImage()
    window.set_level(0.8)
    assert meter.active and meter.levels[-1] == 0.8 and window.orb.level == 0.8
    app.processEvents()
    assert window.orb.grab().toImage() != quiet  # The ring responds to the level.
    window.clear_level()
    assert not meter.active and not any(meter.levels) and window.orb.level == 0.0


def test_stats_are_three_tiles_with_an_icon_a_number_and_a_label(workspace):
    from PySide6.QtWidgets import QLabel

    from localphraser.appearance import GlassPanel, Glyph

    window, history, _ = workspace
    history.add("one two three", "One two three.", "Inserted.", 2)
    window.refresh_history()
    tiles = window.findChildren(GlassPanel, "metric")
    assert len(tiles) == 3
    captions = []
    for tile, number in zip(tiles, window.metric_labels, strict=True):
        assert tile.isAncestorOf(number) and tile.findChild(Glyph) is not None
        captions.append(
            next(label.text() for label in tile.findChildren(QLabel) if label is not number)
        )
    assert captions == ["Saved words", "Dictations", "Speaking pace"]
    assert [label.text() for label in window.metric_labels] == ["3", "1", "90 wpm"]


def test_detail_card_has_chips_a_primary_copy_and_a_quiet_delete(workspace, app):
    window, history, _ = workspace
    history.add("words here", "Words here.", "Inserted.", 2)
    window.refresh_history()
    app.processEvents()
    assert window.entry_info.text() == "2 words · 2.0s recorded"
    assert window.entry_info.parts() == ["2 words", "2.0s recorded"]  # One chip each.
    assert window.entry_info.textFormat() == Qt.TextFormat.PlainText
    assert (window.copy_button.role, window.copy_button.glyph) == ("primary", "copy")
    assert (window.delete_button.role, window.delete_button.glyph) == ("danger", "trash")
    assert (window.clear_button.role, window.clear_button.glyph) == ("danger", "trash")
    window.tabs.setCurrentIndex(1)
    window.copy_button.click()
    assert app.clipboard().text() == "words here"


def test_empty_history_is_a_centred_card_with_the_microphone_icon(workspace):
    from localphraser.appearance import Glyph

    window, _, _ = workspace
    assert window.empty_history.isVisible()
    icon = window.empty_history.findChild(Glyph)
    assert icon is not None and icon.name == "microphone" and icon.isVisible()
    centre = icon.mapTo(window.empty_history, icon.rect().center()).x()
    assert abs(centre - window.empty_history.width() / 2) <= 2


def test_nothing_in_the_hero_clips_or_overlaps_at_the_minimum_window_size(workspace, app):
    window, history, _ = workspace
    history.add("words here", "Words here.", "Inserted.", 2)
    window.refresh_history()
    window.set_state("Speech model required", "muted")  # The longest headline.
    window.record_button.setText("Record (manual copy)")  # The longest label.

    def boxes():
        for _ in range(3):
            app.processEvents()
        found = {}
        for name in ("orb", "hero_chip", "headline", "hint", "record_button", "hero_meter"):
            widget = getattr(window, name)
            if widget.isVisible():
                found[name] = QRect(widget.mapTo(window.hero, QPoint(0, 0)), widget.size())
        return found

    for size in (window.minimumSize(), QSize(1040, 740)):
        window.resize(size)
        found = boxes()
        names = list(found)
        for name in names:
            assert window.hero.rect().contains(found[name]), (size, name)
            widget = getattr(window, name)
            assert widget.width() >= widget.minimumSizeHint().width(), (size, name)
        for index, first in enumerate(names):
            for second in names[index + 1 :]:
                assert not found[first].intersects(found[second]), (size, first, second)
        # The page never needs more width than it has; a short window scrolls instead.
        page = window.home_body
        assert page.minimumSizeHint().width() <= window.home.viewport().width()
        assert page.height() >= page.heightForWidth(page.width())
        card = window.entries.itemDelegate().HEIGHT
        assert window.entries.isVisible() and window.entries.height() >= card
        for widget in (window.copy_button, window.delete_button, window.clear_button):
            assert widget.isVisible() and widget.width() >= widget.minimumSizeHint().width()
            assert widget.height() >= widget.minimumSizeHint().height()
        assert window.result_text.height() >= 40
    assert window.hero_meter.isVisible()  # Back at full size the meter returns...
    window.resize(window.minimumSize())
    boxes()
    assert not window.hero_meter.isVisible()  # ...and the smallest window drops it.


def test_latest_row_exists_only_with_a_latest_action_and_shows_a_given_page(app):
    from PySide6.QtWidgets import QWidget

    history = History(None)
    plain = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    opened = Mock()
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock", latest=opened)
    try:
        assert plain.latest_button is None  # The rule for showing the row is unchanged.
        assert window.latest_button is not None
        assert window.latest_button in window.navigation.buttons()
        window.latest_button.click()
        opened.assert_called_once_with()
        page = QWidget()
        window.show_latest(page)
        assert window.pages.currentWidget() is page and page.parent() is not None
        assert window.latest_button.isChecked()
        window.show_home()
        assert window.home_button.isChecked() and not window.latest_button.isChecked()
        window.show_latest(page)
        assert window.pages.count() == 3  # Home, Analytics and the one Latest page.
    finally:
        for widget in (plain, window):
            widget.deleteLater()
        history.close()
