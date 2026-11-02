"""Taskbar desktop workspace and user-managed local transcript history."""

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localphraser.analytics import AnalyticsPage
from localphraser.appearance import DragHandle, GlassDialog, dark_surface
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
        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(178)
        nav = QVBoxLayout(sidebar)
        nav.setSpacing(6)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
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
        self.home_button = QPushButton("Home")
        self.home_button.setCheckable(True)
        self.home_button.setChecked(True)
        self.home_button.clicked.connect(self.show_home)
        self.settings_button = QPushButton("Settings")
        self.settings_button.setCheckable(True)
        self.navigation = QButtonGroup(self)
        self.navigation.addButton(self.home_button)
        self.navigation.addButton(self.settings_button)
        self.settings_button.clicked.connect(settings)
        nav.addWidget(self.home_button)
        nav.addWidget(self.settings_button)
        self.vocabulary_button = QPushButton("Vocabulary")
        self.vocabulary_button.setCheckable(True)
        self.navigation.addButton(self.vocabulary_button)
        if vocabulary:
            self.vocabulary_button.clicked.connect(vocabulary)
        nav.addWidget(self.vocabulary_button)
        self.analytics_button = QPushButton("Analytics")
        self.analytics_button.setCheckable(True)
        self.navigation.addButton(self.analytics_button)
        self.analytics_button.clicked.connect(self.show_analytics)
        nav.addWidget(self.analytics_button)
        if latest is not None:
            latest_button = QPushButton("Latest transcript")
            latest_button.clicked.connect(latest)
            nav.addWidget(latest_button)
        nav.addStretch()
        self.state_label = QLabel("Ready")
        self.state_label.setWordWrap(True)
        nav.addWidget(self.state_label)
        self.record_button = QPushButton("Record to history")
        self.record_button.clicked.connect(record)
        self.record_button.setToolTip("Use your shortcut in another app for automatic insertion.")
        nav.addWidget(self.record_button)
        quit_button = QPushButton("Quit LocalPhraser")
        quit_button.clicked.connect(quit_app)
        nav.addWidget(quit_button)
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        chrome = QHBoxLayout()
        drag = DragHandle("Your words. On your device.")
        chrome.addWidget(drag, 1)
        for text, label, callback in (
            ("−", "Minimize window", self.showMinimized),
            ("□", "Maximize or restore window", self.maximize_restore),
            ("×", "Close to background", self.close),
        ):
            button = QPushButton(text)
            button.setAccessibleName(label)
            button.setProperty("systemMaximizeButton", label == "Maximize or restore window")
            button.setToolTip(label)
            button.setFixedWidth(42)
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
        self.hint = QLabel(f"Hold {shortcut}, speak naturally, then release.")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        metrics = QHBoxLayout()
        self.metric_labels = []
        for caption in ("Saved words", "Dictations", "Speaking pace"):
            panel = QFrame()
            panel.setObjectName("metric")
            stack = QVBoxLayout(panel)
            number = QLabel("—")
            number.setObjectName("metricNumber")
            stack.addWidget(number)
            stack.addWidget(QLabel(caption))
            self.metric_labels.append(number)
            metrics.addWidget(panel)
        layout.addLayout(metrics)
        recent = QHBoxLayout()
        recent.addWidget(QLabel("Recent transcriptions"), 1)
        self.clear_button = QPushButton("Clear history")
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
        detail = QWidget()
        detail.setObjectName("transcriptPanel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        self.entry_info = QLabel("Your next dictation will appear here.")
        self.entry_info.setTextFormat(Qt.TextFormat.PlainText)
        self.entry_info.setWordWrap(True)
        detail_layout.addWidget(self.entry_info)
        self.result_text = QTextEdit()
        self.raw = QTextEdit()
        for editor in (self.result_text, self.raw):
            editor.setReadOnly(True)
            editor.setAcceptRichText(False)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.result_text, "Result")
        self.tabs.addTab(self.raw, "Original")
        detail_layout.addWidget(self.tabs)
        actions = QHBoxLayout()
        self.copy_button = QPushButton("Copy text")
        self.copy_button.clicked.connect(self.copy_text)
        self.delete_button = QPushButton("Delete entry")
        self.delete_button.clicked.connect(self.delete_entry)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.delete_button)
        detail_layout.addLayout(actions)
        split.addWidget(detail)
        split.setSizes([260, 420])
        layout.addWidget(split, 1)
        self.storage_note = QLabel(
            "History stays on this device. Showing the latest 200 entries."
            if history.path
            else "History is held in memory for this session."
        )
        self.storage_note.setWordWrap(True)
        layout.addWidget(self.storage_note)
        self.pages.addWidget(self.home)
        self.analytics = AnalyticsPage(history)
        self.pages.addWidget(self.analytics)
        content.addWidget(self.pages, 1)
        outer.addLayout(content, 1)
        self.refresh_history()

    def maximize_restore(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        enable_snap(self)

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "sidebar"):
            compact = self.width() < 820
            self.sidebar.setFixedWidth(150 if compact else 178)
            self.shell_layout.setContentsMargins(*([12] * 4 if compact else [18] * 4))
            self.shell_layout.setSpacing(14 if compact else 24)
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

    def refresh_logo(self, *args: Any) -> None:
        self.logo.setPixmap(logo_pixmap(28, light=dark_surface()))

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
            f"{entry['words']} words · {entry['seconds']:.1f}s recorded\n{entry['notice']}"
            if entry
            else "Your next dictation will appear here."
        )

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
