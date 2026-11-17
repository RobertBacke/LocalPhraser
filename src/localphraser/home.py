"""Taskbar desktop workspace and user-managed local transcript history."""

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QEvent, QSignalBlocker, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localphraser.analytics import AnalyticsPage
from localphraser.appearance import (
    CaptionButton,
    DragHandle,
    GlassDialog,
    GlassPanel,
    IconButton,
    NoteLabel,
    SegmentedTabs,
    StatusDot,
    current_theme,
    high_contrast,
)
from localphraser.branding import logo_pixmap
from localphraser.history import History
from localphraser.native_frame import enable_snap, hit_test, native_message


class AppWindow(GlassDialog):
    def __init__(
        self,
        history: History,
        settings: Callable[[], None],
        record: Callable[[], None],
        quit_app: Callable[[], None],
        shortcut: str,
        latest: Callable[[], None] | None = None,
        vocabulary: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.history = history
        self._maximize_pressed = False
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setWindowTitle("LocalPhraser")
        self.setMinimumSize(600, 480)
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        self.resize(
            min(1040, area.width() - 48) if area else 1040,
            min(740, area.height() - 48) if area else 740,
        )
        outer = QHBoxLayout(self)
        self.shell_layout = outer
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(24)
        sidebar = GlassPanel("sidebar")
        self.sidebar = sidebar
        sidebar.setFixedWidth(208)
        nav = QVBoxLayout(sidebar)
        self.sidebar_layout = nav
        nav.setContentsMargins(12, 16, 12, 12)
        nav.setSpacing(4)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(8, 0, 0, 0)
        brand_row.setSpacing(10)
        logo = QLabel()
        self.logo = logo
        self.refresh_logo()
        application = QApplication.instance()
        if isinstance(application, QApplication):
            application.paletteChanged.connect(self.refresh_logo)
        logo.setAccessibleName("LocalPhraser speech prism")
        brand_row.addWidget(logo)
        brand = DragHandle("LocalPhraser")
        brand.setObjectName("brand")
        brand_row.addWidget(brand, 1)
        nav.addLayout(brand_row)
        nav.addSpacing(18)
        self.home_button = self.nav_button("Home", "home")
        self.home_button.setCheckable(True)
        self.home_button.setChecked(True)
        self.home_button.clicked.connect(self.show_home)
        self.settings_button = self.nav_button("Settings", "settings")
        self.settings_button.setCheckable(True)
        self.navigation = QButtonGroup(self)
        self.navigation.addButton(self.home_button)
        self.navigation.addButton(self.settings_button)
        self.settings_button.clicked.connect(settings)
        nav.addWidget(self.home_button)
        nav.addWidget(self.settings_button)
        self.vocabulary_button = self.nav_button("Vocabulary", "vocabulary")
        self.vocabulary_button.setCheckable(True)
        self.navigation.addButton(self.vocabulary_button)
        if vocabulary:
            self.vocabulary_button.clicked.connect(vocabulary)
        nav.addWidget(self.vocabulary_button)
        self.analytics_button = self.nav_button("Analytics", "analytics")
        self.analytics_button.setCheckable(True)
        self.navigation.addButton(self.analytics_button)
        self.analytics_button.clicked.connect(self.show_analytics)
        nav.addWidget(self.analytics_button)
        if latest is not None:
            latest_button = self.nav_button("Latest transcript", "transcript")
            latest_button.clicked.connect(latest)
            nav.addWidget(latest_button)
        nav.addStretch()
        # The status chip: the state as a dot and as words, never by colour alone.
        self.state_chip = GlassPanel("stateChip", nested=True, radius=12)
        state_row = QHBoxLayout(self.state_chip)
        state_row.setContentsMargins(12, 9, 12, 9)
        state_row.setSpacing(9)
        self.state_dot = StatusDot()
        self.state_label = QLabel("Ready")
        self.state_label.setWordWrap(True)
        dot_column = QVBoxLayout()
        dot_column.setContentsMargins(0, 4, 0, 0)  # Centre on the first line of text.
        dot_column.addWidget(self.state_dot, 0, Qt.AlignmentFlag.AlignTop)
        state_row.addLayout(dot_column)
        state_row.addWidget(self.state_label, 1)
        nav.addWidget(self.state_chip)
        nav.addSpacing(6)
        self.record_button = IconButton("Record to history", "microphone", "primary")
        self.record_button.clicked.connect(record)
        self.record_button.setToolTip("Use your shortcut in another app for automatic insertion.")
        nav.addWidget(self.record_button)
        quit_button = IconButton("Quit LocalPhraser", "power", "quiet")
        quit_button.clicked.connect(quit_app)
        nav.addWidget(quit_button)
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        chrome = QHBoxLayout()
        chrome.setSpacing(6)
        drag = DragHandle("Your words. On your device.")
        drag.setObjectName("tagline")
        chrome.addWidget(drag, 1)
        for kind, label, callback in (
            ("minimize", "Minimize window", self.showMinimized),
            ("maximize", "Maximize or restore window", self.maximize_restore),
            ("close", "Close to background", self.close),
        ):
            button = CaptionButton(kind)
            button.setAccessibleName(label)
            button.setProperty("systemMaximizeButton", label == "Maximize or restore window")
            button.setToolTip(label)
            button.clicked.connect(callback)
            chrome.addWidget(button)
        content.addLayout(chrome)
        self.pages = QStackedWidget()
        self.home = QWidget()
        layout = QVBoxLayout(self.home)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(18)
        heading = QLabel("A space for your words")
        heading.setWordWrap(True)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        metrics = QHBoxLayout()
        self.metric_labels = []
        for caption in ("Saved words", "Dictations", "Speaking pace"):
            panel = GlassPanel("metric")
            stack = QVBoxLayout(panel)
            number = QLabel("—")
            number.setObjectName("metricNumber")
            stack.addWidget(number)
            stack.addWidget(QLabel(caption))
            self.metric_labels.append(number)
            metrics.addWidget(panel)
        layout.addLayout(metrics)
        recent = QHBoxLayout()
        recent_title = QLabel("Recent transcriptions")
        recent_title.setProperty("sectionTitle", True)
        recent.addWidget(recent_title, 1)
        self.clear_button = QPushButton("Clear history")
        self.clear_button.setProperty("danger", True)
        self.clear_button.clicked.connect(self.clear_history)
        recent.addWidget(self.clear_button)
        layout.addLayout(recent)
        self.history_notice = QLabel()
        self.history_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.history_notice.setWordWrap(True)
        self.history_notice.hide()
        layout.addWidget(self.history_notice)
        split = QSplitter()
        split.setHandleWidth(16)
        self.entries = QListWidget()
        self.entries.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.entries.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.entries.setAccessibleName("Recent transcriptions")
        self.entries.currentItemChanged.connect(self.select_entry)
        split.addWidget(self.entries)
        detail = GlassPanel("transcriptPanel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        self.entry_info = QLabel("Your next dictation will appear here.")
        self.entry_info.setTextFormat(Qt.TextFormat.PlainText)
        self.entry_info.setWordWrap(True)
        detail_layout.addWidget(self.entry_info)
        self.entry_notice = NoteLabel(collapse_when_empty=True)
        detail_layout.addWidget(self.entry_notice)
        self.result_text = QTextEdit()
        self.raw = QTextEdit()
        for editor in (self.result_text, self.raw):
            editor.setReadOnly(True)
            editor.setAcceptRichText(False)
        self.tabs = SegmentedTabs()
        self.tabs.addTab(self.result_text, "Result")
        self.tabs.addTab(self.raw, "Original")
        detail_layout.addWidget(self.tabs)
        actions = QHBoxLayout()
        self.copy_button = QPushButton("Copy text")
        self.copy_button.clicked.connect(self.copy_text)
        self.delete_button = QPushButton("Delete entry")
        self.delete_button.setProperty("danger", True)
        self.delete_button.clicked.connect(self.delete_entry)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.delete_button)
        detail_layout.addLayout(actions)
        split.addWidget(detail)
        split.setSizes([260, 420])
        self.history_split = split
        self.empty_history = GlassPanel("emptyHistory")
        empty_layout = QVBoxLayout(self.empty_history)
        empty_layout.setContentsMargins(32, 28, 32, 28)
        empty_layout.setSpacing(8)
        empty_layout.addStretch()
        empty_title = QLabel("No dictations yet")
        empty_title.setObjectName("emptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        self.empty_message = QLabel()
        self.empty_message.setTextFormat(Qt.TextFormat.PlainText)
        self.empty_message.setWordWrap(True)
        self.empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_message)
        empty_layout.addStretch()
        self.history_views = QStackedWidget()
        self.history_views.addWidget(split)
        self.history_views.addWidget(self.empty_history)
        layout.addWidget(self.history_views, 1)
        self.storage_note = NoteLabel(
            "History stays on this device. Showing the latest 200 entries."
            if history.path
            else "History is held in memory for this session."
        )
        layout.addWidget(self.storage_note)
        self.pages.addWidget(self.home)
        self.analytics = AnalyticsPage(history)
        self.pages.addWidget(self.analytics)
        content.addWidget(self.pages, 1)
        outer.addLayout(content, 1)
        self.set_hint(f"Hold {shortcut}, speak naturally, then release.")
        self.refresh_history()

    def nav_button(self, text: str, glyph: str) -> IconButton:
        return IconButton(text, glyph, "nav")

    def set_hint(self, text: str) -> None:
        """Show how to dictate with the current shortcut, also in the empty history."""
        self.hint.setText(text)
        self.empty_message.setText(
            f"{text} Speak in any app; your first dictation will appear here."
        )

    def set_state(self, text: str, tone: str) -> None:
        self.state_label.setText(text)
        self.state_dot.set_tone(tone)

    def maximize_restore(self) -> None:
        self.showNormal() if self.isMaximized() or self.isFullScreen() else self.showMaximized()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        enable_snap(self)

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "sidebar"):
            compact = self.width() < 820
            self.shell_layout.setContentsMargins(*([12] * 4 if compact else [18] * 4))
            self.shell_layout.setSpacing(12 if compact else 22)
            self.sidebar.setFixedWidth(178 if compact else 208)
            self.sidebar_layout.setContentsMargins(
                *((8, 12, 8, 8) if compact else (12, 16, 12, 12))
            )
        super().resizeEvent(event)

    def nativeEvent(self, event_type: Any, message: int) -> Any:
        msg = native_message(int(message))
        if msg is not None:
            if msg.message == 0x00A1 and msg.wParam == 9:  # Native maximize press.
                self._maximize_pressed = True
                return True, 0
            if msg.message == 0x00A2 and self._maximize_pressed:
                self._maximize_pressed = False
                if msg.wParam == 9:
                    self.maximize_restore()
                return True, 0
            if msg.message in (0x0201, 0x00A1):
                self._maximize_pressed = False
        result = hit_test(self, int(message))
        if result is not None:
            return True, result
        return super().nativeEvent(event_type, message)

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            for button in self.findChildren(CaptionButton):
                button.update()

    def refresh_logo(self, *args: Any) -> None:
        tokens = current_theme()
        ratio = self.devicePixelRatioF()
        size = round(28 * ratio)
        if high_contrast():
            mark = logo_pixmap(size, light=tokens.dark)
        else:  # The mark carries the accent.
            tint = QLinearGradient(0, 0, size, size)
            for stop, colour in zip((0.0, 0.5, 1.0), tokens.brand, strict=True):
                tint.setColorAt(stop, QColor(colour))
            mark = logo_pixmap(size, tint=QBrush(tint))
        mark.setDevicePixelRatio(ratio)
        self.logo.setPixmap(mark)

    def show_home(self) -> None:
        self.home_button.setChecked(True)
        self.pages.setCurrentWidget(self.home)
        self.refresh_history()

    def show_settings(self, widget: QWidget) -> None:
        self.settings_button.setChecked(True)
        if self.pages.indexOf(widget) < 0:
            self.pages.addWidget(widget)
        self.pages.setCurrentWidget(widget)

    def show_vocabulary(self, widget: QWidget) -> None:
        self.vocabulary_button.setChecked(True)
        if self.pages.indexOf(widget) < 0:
            self.pages.addWidget(widget)
        self.pages.setCurrentWidget(widget)

    def show_analytics(self) -> None:
        self.analytics_button.setChecked(True)
        self.analytics.refresh()
        self.pages.setCurrentWidget(self.analytics)

    def refresh_history(self) -> None:
        try:
            count, words, pace = self.history.stats()
            entries = self.history.recent()
            first = self.history.get(entries[0]["id"]) if entries else None
        except (sqlite3.DatabaseError, OSError):
            self.history_failed("History could not be read. Click Home to retry.")
            return
        self.history_notice.clear()
        self.history_notice.hide()
        blocker = QSignalBlocker(self.entries)
        self.entries.clear()
        for label, value in zip(
            self.metric_labels,
            (str(words), str(count), f"{pace:.0f} wpm" if pace else "—"),
            strict=True,
        ):
            label.setText(value)
        self.metric_labels[2].setToolTip(
            "Recognized original words divided by recorded minutes, including pauses."
        )
        for entry in entries:
            try:
                stamp = (
                    datetime.fromisoformat(entry["created"])
                    .astimezone()
                    .strftime("%b %d · %I:%M %p")
                )
            except (ValueError, TypeError, OverflowError):
                stamp = "Saved transcription"
            item = QListWidgetItem(
                f"{stamp}   {entry['words']} words\n{entry['preview'].replace(chr(10), ' ')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.entries.addItem(item)
        self.clear_button.setEnabled(bool(count))
        self.history_views.setCurrentWidget(self.history_split if count else self.empty_history)
        if count:
            self.entries.setCurrentRow(0)
        blocker.unblock()
        self.display_entry(first)

    def select_entry(self, item: QListWidgetItem | None, previous: Any = None) -> None:
        try:
            entry = self.history.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        except (sqlite3.DatabaseError, OSError):
            self.history_failed("This entry could not be read. Click Home to retry.")
            return
        self.display_entry(entry)

    def display_entry(self, entry: dict[str, Any] | None) -> None:
        self.copy_button.setEnabled(entry is not None)
        self.delete_button.setEnabled(entry is not None)
        self.result_text.setPlainText(entry["text"] if entry else "")
        self.raw.setPlainText(entry["raw"] if entry else "")
        self.entry_info.setText(
            f"{entry['words']} words · {entry['seconds']:.1f}s recorded"
            if entry
            else "Your next dictation will appear here."
        )
        self.entry_notice.setText(entry["notice"] if entry else "")

    def copy_text(self) -> None:
        editor = self.result_text if self.tabs.currentIndex() == 0 else self.raw
        QApplication.clipboard().setText(editor.toPlainText())

    def delete_entry(self) -> None:
        item = self.entries.currentItem()
        if item:
            try:
                self.history.delete(item.data(Qt.ItemDataRole.UserRole))
            except (sqlite3.DatabaseError, OSError):
                self.history_failed(
                    "Entry could not be deleted. Click Home to check saved history."
                )
                return
            self.refresh_history()

    def clear_history(self) -> None:
        if (
            QMessageBox.question(
                self, "Clear history", "Delete all saved transcriptions on this device?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            try:
                self.history.clear()
            except (sqlite3.DatabaseError, OSError):
                self.history_failed(
                    "History cleanup did not finish. Click Home to check saved entries."
                )
                return
            self.refresh_history()

    def history_failed(self, message: str) -> None:
        self.history_notice.setText(message)
        self.history_notice.show()
        self.delete_button.setEnabled(False)
        self.clear_button.setEnabled(False)

    def closeEvent(self, event: Any) -> None:
        event.ignore()
        self.hide()
