"""Taskbar desktop workspace and user-managed local transcript history."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
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

from localphraser.appearance import DragHandle, GlassDialog
from localphraser.history import History


class AppWindow(GlassDialog):
    def __init__(
        self,
        history: History,
        settings: Callable[[], None],
        record: Callable[[], None],
        quit_app: Callable[[], None],
        shortcut: str,
        latest: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.history = history
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setWindowTitle("LocalPhraser")
        self.setMinimumSize(740, 480)
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        self.resize(
            min(1040, area.width() - 48) if area else 1040,
            min(740, area.height() - 48) if area else 740,
        )
        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(24)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(178)
        nav = QVBoxLayout(sidebar)
        nav.setSpacing(12)
        brand = DragHandle("LocalPhraser")
        brand.setObjectName("brand")
        nav.addWidget(brand)
        nav.addSpacing(28)
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
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        self.hint = QLabel(f"Hold {shortcut}, speak naturally, then release.")
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
        split = QSplitter()
        self.entries = QListWidget()
        self.entries.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.entries.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.entries.setAccessibleName("Recent transcriptions")
        self.entries.currentItemChanged.connect(self.select_entry)
        split.addWidget(self.entries)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(8, 0, 0, 0)
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
        content.addWidget(self.pages, 1)
        outer.addLayout(content, 1)
        self.refresh_history()

    def maximize_restore(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def show_home(self) -> None:
        self.home_button.setChecked(True)
        self.pages.setCurrentWidget(self.home)
        self.refresh_history()

    def show_settings(self, widget: QWidget) -> None:
        self.settings_button.setChecked(True)
        if self.pages.indexOf(widget) < 0:
            self.pages.addWidget(widget)
        self.pages.setCurrentWidget(widget)

    def refresh_history(self) -> None:
        self.entries.clear()
        count, words, pace = self.history.stats()
        for label, value in zip(
            self.metric_labels,
            (str(words), str(count), f"{pace:.0f} wpm" if pace else "—"),
            strict=True,
        ):
            label.setText(value)
        self.metric_labels[2].setToolTip(
            "Recognized original words divided by recorded minutes, including pauses."
        )
        for entry in self.history.recent():
            stamp = (
                datetime.fromisoformat(entry["created"]).astimezone().strftime("%b %d · %I:%M %p")
            )
            item = QListWidgetItem(
                f"{stamp}   {entry['words']} words\n{entry['preview'].replace(chr(10), ' ')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.entries.addItem(item)
        self.clear_button.setEnabled(bool(count))
        if count:
            self.entries.setCurrentRow(0)
        else:
            self.select_entry(None)

    def select_entry(self, item: QListWidgetItem | None, previous: Any = None) -> None:
        entry = self.history.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
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
            self.history.delete(item.data(Qt.ItemDataRole.UserRole))
            self.refresh_history()

    def clear_history(self) -> None:
        if (
            QMessageBox.question(
                self, "Clear history", "Delete all saved transcriptions on this device?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.history.clear()
            self.refresh_history()

    def closeEvent(self, event: Any) -> None:
        event.ignore()
        self.hide()
