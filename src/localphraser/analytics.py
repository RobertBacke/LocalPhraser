"""Per-app counts from local history; never read window titles or surrounding text."""

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from localphraser.appearance import GlassPanel, NoteLabel, current_theme, high_contrast

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


def count(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class CountBars(QStyledItemDelegate):
    """Draws a row of the table: the app name, then each count as right-aligned text
    over a thin accent bar proportional to the largest count in its column.

    The numbers remain the items' text, so assistive technology reads them as before.
    """

    PAD = 12

    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self.hover_row = -1

    def fraction(self, index: Any) -> float | None:
        """The share of the column's largest count; None for cells that are not counts."""
        value = count(index.data()) if index.column() else None
        if value is None:
            return None
        model = index.model()
        peak = max(
            (count(model.index(row, index.column()).data()) or 0) for row in range(model.rowCount())
        )
        return value / peak if peak > 0 else 0.0

    def bar_rect(self, cell: QRect, fraction: float) -> QRectF:
        """The filled part of a cell's bar; it grows leftwards from under the number."""
        track = QRectF(cell.left() + self.PAD, cell.bottom() - 8, cell.width() - 2 * self.PAD, 3)
        width = max(3.0, track.width() * fraction) if fraction > 0 else 0.0
        return QRectF(track.right() - width, track.top(), width, track.height())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
        if high_contrast():
            super().paint(painter, option, index)
            return
        tokens = current_theme()
        cell: QRect = option.rect  # type: ignore[attr-defined]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if index.row() == self.hover_row:
            painter.fillRect(cell, QColor(*tokens.hover))
        painter.setFont(option.font)  # type: ignore[attr-defined]
        painter.setPen(QColor(tokens.text))
        fraction = self.fraction(index)
        text = str(index.data() or "")
        area = QRectF(cell).adjusted(self.PAD, 0, -self.PAD, 0)
        if fraction is None:
            metrics = painter.fontMetrics()
            painter.drawText(
                area,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(area.width())),
            )
        else:
            painter.drawText(
                area.adjusted(0, 0, 0, -8),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                text,
            )
            track = QRectF(area.left(), cell.bottom() - 8, area.width(), 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(*tokens.field_border))
            painter.drawRoundedRect(track, 1.5, 1.5)
            bar = self.bar_rect(cell, fraction)
            if bar.width() > 0:
                fill = QLinearGradient(track.topLeft(), track.topRight())
                fill.setColorAt(0, QColor(tokens.violet))
                fill.setColorAt(1, QColor(tokens.glow))
                painter.setBrush(fill)
                painter.drawRoundedRect(bar, 1.5, 1.5)
        painter.restore()


class AnalyticsPage(QWidget):
    def __init__(self, history: "History"):
        super().__init__()
        self.history = history
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(12)
        heading = QLabel("Where you dictate")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        layout.addWidget(
            NoteLabel(
                "Completed dictations by the app focused when recording began. Counts include "
                "manual-copy results, not just confirmed insertions. "
                "Older entries have no app identity."
            )
        )
        card = GlassPanel("analyticsCard")
        self.card = card
        box = QVBoxLayout(card)
        self.card_box = box
        box.setContentsMargins(10, 8, 10, 12)
        box.setSpacing(8)
        self.notice = QLabel()
        self.notice.setProperty("muted", True)
        self.notice.setWordWrap(True)
        self.notice.setContentsMargins(12, 10, 12, 10)
        self.notice.hide()
        box.addWidget(self.notice)
        self.table = QTableWidget(0, 4)
        self.table.setAccessibleName("Dictations by application")
        self.table.setHorizontalHeaderLabels(["Application", "24 hours", "7 days", "All time"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.bars = CountBars(self.table)
        self.table.setItemDelegate(self.bars)
        # Rows respond to the pointer; the delegate paints the hovered row.
        self.table.setMouseTracking(True)
        self.table.cellEntered.connect(self.hover)
        self.table.viewport().installEventFilter(self)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionsClickable(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            title = self.table.horizontalHeaderItem(column)
            if title is not None:  # Numbers and their headings share a right edge.
                title.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        box.addWidget(self.table, 1)
        # The card hugs a short table and takes the page when the table is long.
        layout.addWidget(card, 100)
        layout.addStretch(1)
        layout.addWidget(
            NoteLabel(
                "24 hours and 7 days are rolling windows. All time covers saved history; "
                "deleting entries "
                "also removes their counts. Turning off history stops new counts. App names "
                "stay local; window titles, URLs and document contents are not collected."
            )
        )
        self.size_columns()

    def size_columns(self) -> None:
        """Count columns share a width that leaves the app name most of a narrow table."""
        width = max(76, min(150, self.table.viewport().width() // 5))
        for column in (1, 2, 3):
            self.table.setColumnWidth(column, width)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.size_columns()

    def hover(self, row: int, column: int = 0) -> None:
        if row != self.bars.hover_row:
            self.bars.hover_row = row
            self.table.viewport().update()

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self.table.viewport() and event.type() == QEvent.Type.Leave:
            self.hover(-1)
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        try:
            rows = self.history.app_stats()
        except Exception:
            self.notice.setText("App statistics could not be read. Reopen Analytics to retry.")
            self.notice.show()
            self.fit_card(self.table.rowCount())
            return
        self.notice.setText("" if rows else "Your next saved dictations will appear here.")
        self.notice.setVisible(not rows)
        self.hover(-1)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, value in enumerate(
                (row["app"], str(row["recent"]), str(row["week"]), str(row["total"]))
            ):
                item = QTableWidgetItem(value)
                if column:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(index, column, item)
        self.size_columns()
        self.fit_card(len(rows))

    def fit_card(self, rows: int) -> None:
        self.table.setVisible(rows > 0)
        header = self.table.horizontalHeader().sizeHint().height()
        table = header + rows * self.table.verticalHeader().defaultSectionSize() + 4
        self.table.setMaximumHeight(table)
        margins = self.card_box.contentsMargins()
        notice = self.notice.sizeHint().height() + 24 if self.notice.text() else 0
        self.card.setMaximumHeight(
            margins.top() + margins.bottom() + (table if rows else 0) + notice
        )
