import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import psutil
import pytest

from localphraser.analytics import AnalyticsPage, application_name
from localphraser.history import History


def test_app_counts_rolling_day_week_all_time_and_deletion(app):
    history = History(None)
    now = datetime(2026, 11, 2, 12, tzinfo=UTC)
    try:
        ids = []
        for name, age in [
            ("Codex", 1),
            ("Codex", 24),
            ("Codex", 25),
            ("Codex", 168),
            ("Codex", 169),
            ("Google Chrome", 2),
        ]:
            entry = history.add("test words", "Test words.", "Inserted.", 1, name)
            with history.connection:
                history.connection.execute(
                    "UPDATE transcripts SET created=? WHERE id=?",
                    ((now - timedelta(hours=age)).isoformat(), entry),
                )
            ids.append(entry)
        assert history.app_stats(now) == [
            {"app": "Codex", "total": 5, "recent": 2, "week": 4},
            {"app": "Google Chrome", "total": 1, "recent": 1, "week": 1},
        ]
        history.delete(ids[0])
        assert history.app_stats(now)[0]["total"] == 4
        page = AnalyticsPage(history)
        page.refresh()
        assert page.table.columnCount() == 4 and page.table.rowCount() == 2
        history.clear()
        page.refresh()
        assert page.table.rowCount() == 0
        page.deleteLater()
    finally:
        history.close()


def test_existing_database_upgrade_preserves_old_text_with_unknown_app(tmp_path):
    path = tmp_path / "history.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE transcripts (id INTEGER PRIMARY KEY, created TEXT NOT NULL, "
            "raw TEXT NOT NULL, text TEXT NOT NULL, notice TEXT NOT NULL, "
            "words INTEGER NOT NULL, seconds REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO transcripts VALUES(1,'2026-11-01T00:00:00+00:00',"
            "'old text','Old text.','Inserted.',2,2)"
        )
        connection.execute("PRAGMA user_version=1")
    history = History(path)
    try:
        assert history.get(1)["text"] == "Old text."
        assert history.get(1)["app"] == "Unknown app"
        assert history.connection.execute("PRAGMA user_version").fetchone()[0] == 2
        history.set_vocabulary_feedback("Codex", "correction")
        history.add("new", "New.", "", 1, "Codex")
    finally:
        history.close()


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Codex.exe", "Codex"),
        ("chrome.exe", "Google Chrome"),
        ("AnotherApp.exe", "AnotherApp"),
        ("C:/private/name.exe", "Unknown app"),
    ],
)
def test_app_identity_uses_process_name_only(monkeypatch, name, expected):
    process = Mock()
    process.name.return_value = name
    monkeypatch.setattr(psutil, "Process", Mock(return_value=process))
    assert application_name(123) == expected
    process.exe.assert_not_called()
    process.cmdline.assert_not_called()


def test_dead_or_inaccessible_app_has_unknown_identity(monkeypatch):
    monkeypatch.setattr(psutil, "Process", Mock(side_effect=psutil.AccessDenied(123)))
    assert application_name(123) == "Unknown app"


def test_counts_are_right_aligned_text_with_bars_proportional_to_the_column(app):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    from localphraser import appearance
    from localphraser.analytics import CountBars
    from localphraser.home import AppWindow

    history = History(None)
    for name, count in (("Codex", 4), ("Google Chrome", 2), ("Notepad", 1)):
        for _ in range(count):
            history.add("test words", "Test words.", "Inserted.", 1, name)
    window = AppWindow(history, Mock(), Mock(), Mock(), "CapsLock")
    window.resize(1040, 740)
    window.show()
    window.show_analytics()
    for _ in range(3):
        app.processEvents()
    try:
        table = window.analytics.table
        delegate = table.itemDelegate()
        assert isinstance(delegate, CountBars)
        # The numbers stay ordinary text for assistive technology, right-aligned.
        assert [table.item(row, 0).text() for row in range(3)] == [
            "Codex",
            "Google Chrome",
            "Notepad",
        ]
        for column in (1, 2, 3):
            assert [table.item(row, column).text() for row in range(3)] == ["4", "2", "1"]
            for row in range(3):
                assert table.item(row, column).textAlignment() & Qt.AlignmentFlag.AlignRight
        fractions = [delegate.fraction(table.model().index(row, 3)) for row in range(3)]
        assert fractions == [1.0, 0.5, 0.25]
        assert delegate.fraction(table.model().index(0, 0)) is None  # Names have no bar.
        view = table.viewport().grab().toImage()

        def bar_pixels(row):
            # The accent bar is the only saturated, mid-light paint in a count cell.
            rect = table.visualItemRect(table.item(row, 3))
            return sum(
                view.pixelColor(x, y).saturation() > 120 and view.pixelColor(x, y).lightness() > 60
                for x in range(rect.left(), rect.right() + 1)
                for y in range(rect.top(), rect.bottom() + 1)
            )

        assert bar_pixels(0) > bar_pixels(1) > bar_pixels(2) > 0
        widths = [
            delegate.bar_rect(table.visualItemRect(table.item(row, 3)), fractions[row]).width()
            for row in range(3)
        ]
        assert widths[0] == pytest.approx(2 * widths[1])
        assert widths[0] == pytest.approx(4 * widths[2])
        end = QColor(appearance.current_theme().glow)
        right = table.visualItemRect(table.item(0, 3))
        tip = view.pixelColor(right.right() - delegate.PAD - 2, right.bottom() - 7)
        assert abs(tip.hue() - end.hue()) <= 12  # The bar ends in the glow colour.
        # A quiet header: the same surface as the rows, not an opaque band.
        page = window.analytics.grab().toImage()
        header = table.horizontalHeader()
        band = page.pixelColor(header.mapTo(window.analytics, header.rect().center()))
        body = page.pixelColor(
            table.viewport().mapTo(window.analytics, table.viewport().rect().bottomRight())
        )
        assert abs(band.lightness() - body.lightness()) <= 12
    finally:
        window.hide()
        window.deleteLater()
        history.close()


def test_empty_analytics_says_so_and_draws_no_bars(app):
    from localphraser.analytics import CountBars

    history = History(None)
    page = AnalyticsPage(history)
    try:
        page.refresh()
        assert page.table.rowCount() == 0
        assert page.notice.text() == "Your next saved dictations will appear here."
        assert isinstance(page.table.itemDelegate(), CountBars)
    finally:
        page.deleteLater()
        history.close()
