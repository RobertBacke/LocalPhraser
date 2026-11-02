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
