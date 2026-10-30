"""User-enabled local transcript history. No audio, network or background collection."""

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class History:
    def __init__(self, path: Path | None):
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path) if path else ":memory:")
        self.connection.row_factory = sqlite3.Row
        try:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise sqlite3.DatabaseError("Unsupported history version")
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS transcripts ("
                "id INTEGER PRIMARY KEY, created TEXT NOT NULL, raw TEXT NOT NULL, "
                "text TEXT NOT NULL, notice TEXT NOT NULL, words INTEGER NOT NULL, "
                "seconds REAL NOT NULL)"
            )
            self.connection.execute(
                "SELECT id,created,raw,text,notice,words,seconds FROM transcripts LIMIT 0"
            )
            self.connection.execute("PRAGMA secure_delete=ON")
            self.connection.execute("PRAGMA user_version=1")
            self.connection.commit()
        except Exception:
            self.connection.close()
            raise

    def add(self, raw: str, text: str, notice: str, seconds: float) -> int:
        if not text.strip() or max(len(text), len(raw), len(notice)) > 100_000:
            raise ValueError("Transcript outside history limits")
        if not 0 <= seconds <= 600:
            raise ValueError("Invalid recording duration")
        words = len(re.findall(r"\b\w+(?:['’]\w+)*\b", raw))
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO transcripts(created,raw,text,notice,words,seconds) "
                "VALUES(?,?,?,?,?,?)",
                (datetime.now(UTC).isoformat(), raw, text, notice, words, seconds),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def recent(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT id,created,substr(text,1,140) AS preview,words,seconds "
                "FROM transcripts ORDER BY id DESC LIMIT 200"
            )
        ]

    def get(self, entry_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM transcripts WHERE id=?", (entry_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def stats(self) -> tuple[int, int, float | None]:
        count, words, seconds, paced_words = self.connection.execute(
            "SELECT count(*),coalesce(sum(words),0),coalesce(sum(seconds),0),"
            "coalesce(sum(CASE WHEN seconds>0 THEN words ELSE 0 END),0) FROM transcripts"
        ).fetchone()
        return count, words, paced_words * 60 / seconds if seconds else None

    def delete(self, entry_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM transcripts WHERE id=?", (entry_id,))

    def clear(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM transcripts")
        self.connection.execute("VACUUM")

    def close(self) -> None:
        self.connection.close()
