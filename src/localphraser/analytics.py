"""Per-app counts from local history; never read window titles or surrounding text."""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from localphraser.history import History

APP_NAMES = {
    "codex.exe": "Codex",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "notepad.exe": "Notepad",
    "localphraser.exe": "LocalPhraser",
    "code.exe": "Visual Studio Code",
    "winword.exe": "Microsoft Word",
}


def application_name(process_id: int) -> str:
    import psutil

    try:
        name = psutil.Process(process_id).name()
        if not name or len(name) > 80 or any(char in name for char in "/\\\r\n\x00"):
            return "Unknown app"
        return APP_NAMES.get(name.casefold(), name.removesuffix(".exe").removesuffix(".EXE"))
    except (psutil.Error, ValueError):
        return "Unknown app"


class AnalyticsPage(QWidget):
    def __init__(self, history: "History"):
        super().__init__()
        self.history = history
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 0)
        heading = QLabel("Where you dictate")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        explanation = QLabel(
            "Completed dictations by the app focused when recording began. Counts include "
            "manual-copy results, not just confirmed insertions. "
            "Older entries have no app identity."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.table = QTableWidget(0, 4)
        self.table.setAccessibleName("Dictations by application")
        self.table.setHorizontalHeaderLabels(["Application", "24 hours", "7 days", "All time"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        layout.addWidget(self.table, 1)
        note = QLabel(
            "24 hours and 7 days are rolling windows. All time covers saved history; "
            "deleting entries "
            "also removes their counts. Turning off history stops new counts. App names stay "
            "local; window titles, URLs and document contents are not collected."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

    def refresh(self) -> None:
        try:
            rows = self.history.app_stats()
        except Exception:
            self.notice.setText("App statistics could not be read. Reopen Analytics to retry.")
            return
        self.notice.setText("" if rows else "Your next saved dictations will appear here.")
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, value in enumerate(
                (row["app"], str(row["recent"]), str(row["week"]), str(row["total"]))
            ):
                self.table.setItem(index, column, QTableWidgetItem(value))
