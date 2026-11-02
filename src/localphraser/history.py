"""User-enabled local transcript history. No audio, network or background collection."""

import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class History:
    def __init__(self, path: Path | None):
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        # History runs on the UI thread; avoid SQLite's five-second default lock wait.
        self.connection = sqlite3.connect(str(path) if path else ":memory:", timeout=0.2)
        self.connection.row_factory = sqlite3.Row
        try:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise sqlite3.DatabaseError("Unsupported history version")
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS transcripts ("
                "id INTEGER PRIMARY KEY, created TEXT NOT NULL, raw TEXT NOT NULL, "
                "text TEXT NOT NULL, notice TEXT NOT NULL, words INTEGER NOT NULL, "
                "seconds REAL NOT NULL, app TEXT NOT NULL DEFAULT 'Unknown app')"
            )
            columns = {row[1] for row in self.connection.execute("PRAGMA table_info(transcripts)")}
            if "app" not in columns:
                self.connection.execute(
                    "ALTER TABLE transcripts ADD COLUMN app TEXT NOT NULL DEFAULT 'Unknown app'"
                )
            self.connection.execute(
                "SELECT id,created,raw,text,notice,words,seconds,app FROM transcripts LIMIT 0"
            )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS vocabulary_feedback ("
                "term TEXT PRIMARY KEY COLLATE NOCASE, source TEXT NOT NULL)"
            )
            self.connection.execute("PRAGMA secure_delete=ON")
            self.connection.execute("PRAGMA user_version=2")
            self.connection.commit()
        except Exception:
            self.connection.close()
            raise

    def add(
        self, raw: str, text: str, notice: str, seconds: float, app: str = "Unknown app"
    ) -> int:
        if not text.strip() or max(len(text), len(raw), len(notice)) > 100_000:
            raise ValueError("Transcript outside history limits")
        if not 0 <= seconds <= 600:
            raise ValueError("Invalid recording duration")
        if not app or len(app) > 80 or any(char in app for char in "/\\\r\n\x00"):
            raise ValueError("Invalid application name")
        words = len(re.findall(r"\b\w+(?:['’]\w+)*\b", raw))
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO transcripts(created,raw,text,notice,words,seconds,app) "
                "VALUES(?,?,?,?,?,?,?)",
                (datetime.now(UTC).isoformat(), raw, text, notice, words, seconds, app),
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

    def app_stats(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(hours=24)
        week = now - timedelta(days=7)
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT app, count(*) AS total, sum(CASE WHEN julianday(created)>=julianday(?) "
                "AND julianday(created)<=julianday(?) THEN 1 ELSE 0 END) AS recent, "
                "sum(CASE WHEN julianday(created)>=julianday(?) "
                "AND julianday(created)<=julianday(?) "
                "THEN 1 ELSE 0 END) AS week "
                "FROM transcripts GROUP BY app ORDER BY total DESC, app COLLATE NOCASE",
                (cutoff.isoformat(), now.isoformat(), week.isoformat(), now.isoformat()),
            )
        ]

    def vocabulary_samples(self) -> list[str]:
        return [
            row[0]
            for row in self.connection.execute(
                "SELECT substr(raw,1,3000) FROM transcripts ORDER BY id DESC LIMIT 200"
            )
        ]

    def vocabulary_feedback(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT term,source FROM vocabulary_feedback ORDER BY rowid DESC LIMIT 500"
            )
        ]

    def set_vocabulary_feedback(self, term: str, source: str) -> None:
        from localphraser.vocabulary import normalize_term

        term = normalize_term(term)
        if source not in ("correction", "dismissed"):
            raise ValueError("Invalid vocabulary source")
        with self.connection:
            self.connection.execute(
                "INSERT INTO vocabulary_feedback(term,source) VALUES(?,?) "
                "ON CONFLICT(term) DO UPDATE SET term=excluded.term,source=excluded.source",
                (term, source),
            )

    def clear_vocabulary_feedback(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM vocabulary_feedback")

    def delete(self, entry_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM transcripts WHERE id=?", (entry_id,))

    def clear(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM transcripts")
        self.connection.execute("VACUUM")

    def close(self) -> None:
        self.connection.close()
