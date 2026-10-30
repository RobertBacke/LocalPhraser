import sqlite3

import pytest

from localphraser.config import profile_file
from localphraser.history import History


def test_history_persists_exact_text_and_computes_recorded_speech_pace(tmp_path):
    path = tmp_path / "history.sqlite3"
    history = History(path)
    first = history.add("hello world", "Hello, world.", "Inserted.", 2)
    history.add("three more words", "Three more words.", "Manual copy.", 3)
    assert history.stats() == (2, 5, 60)
    history.close()
    reopened = History(path)
    assert reopened.get(first)["text"] == "Hello, world."
    assert reopened.get(first)["raw"] == "hello world"
    assert reopened.recent()[1]["id"] == first
    reopened.delete(first)
    assert reopened.get(first) is None
    reopened.clear()
    assert reopened.stats() == (0, 0, None)
    reopened.close()


def test_in_memory_history_and_unknown_recording_duration():
    history = History(None)
    history.add("<b>don't execute SQL ' ;</b>", "Text stays literal.", "", 0)
    assert history.stats()[2] is None
    assert history.get(999) is None
    history.close()


def test_corrupt_history_is_preserved(tmp_path):
    path = tmp_path / "history.sqlite3"
    path.write_bytes(b"preserve this damaged file")
    with pytest.raises(sqlite3.DatabaseError):
        History(path)
    assert path.read_bytes() == b"preserve this damaged file"


def test_custom_profiles_in_one_folder_do_not_share_transcript_history(tmp_path):
    first = History(profile_file(tmp_path / "first.json", "history.sqlite3"))
    second = History(profile_file(tmp_path / "second.json", "history.sqlite3"))
    try:
        first.add("first profile words", "First profile words.", "", 2)
        assert first.stats()[0] == 1
        assert second.stats()[0] == 0
        assert (
            profile_file(tmp_path / "config.json", "history.sqlite3")
            == tmp_path / "history.sqlite3"
        )
        assert profile_file(tmp_path / "first.json", "localphraser.lock") != profile_file(
            tmp_path / "second.json", "localphraser.lock"
        )
    finally:
        first.close()
        second.close()
