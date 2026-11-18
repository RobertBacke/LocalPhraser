"""Taskbar desktop workspace and user-managed local transcript history."""

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QEvent, QRect, QRectF, QSignalBlocker, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPen,
    QTextLayout,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localphraser.analytics import AnalyticsPage
from localphraser.appearance import (
    CaptionButton,
    ChipLabel,
    DragHandle,
    GlassDialog,
    GlassPanel,
    Glyph,
    IconButton,
    LevelMeter,
    NoteLabel,
    SegmentedTabs,
    StateChip,
    StatusDot,
    StatusOrb,
    current_theme,
    high_contrast,
    paint_panel,
)
from localphraser.branding import logo_pixmap
from localphraser.history import History
from localphraser.native_frame import enable_snap, hit_test, native_message
from localphraser.pipeline import State

COMPACT_WIDTH = 820  # Below this the window uses its narrow arrangement.
STACKED_WIDTH = 720  # Below this the history list sits above the entry.
STAMP, WORDS, PREVIEW = (Qt.ItemDataRole.UserRole + offset for offset in (1, 2, 3))


def chip_word(text: str, tone: str) -> str:
    """The short word beside the hero's state dot, so red or grey never stands alone."""
    if tone == "ready":
        return "Ready"
    if tone == "busy":
        return "Working"
    if tone == "recording":
        return "Recording" if text == State.RECORDING.value else "Needs attention"
    return "Not ready"


class RecordButton(IconButton):
    """The Home record action: a microphone, or a stop square while it says Stop."""

    def setText(self, text: str) -> None:
        super().setText(text)
        self.set_glyph("stop" if text.startswith("Stop") else "microphone")


def wrapped_lines(text: str, font: QFont, width: float, limit: int) -> list[str]:
    """Break plain text into at most ``limit`` lines, eliding the last one if cut."""
    layout = QTextLayout(text, font)
    layout.beginLayout()
    spans: list[tuple[int, int]] = []
    while len(spans) < limit:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        spans.append((line.textStart(), line.textLength()))
    layout.endLayout()
    lines = [text[start : start + length].rstrip() for start, length in spans]
    if spans and spans[-1][0] + spans[-1][1] < len(text):
        rest = text[spans[-1][0] :]
        lines[-1] = QFontMetricsF(font).elidedText(rest, Qt.TextElideMode.ElideRight, width)
    return lines


class HistoryCards(QStyledItemDelegate):
    """Draws each history row as its own glass card: time, word count, two preview lines."""

    HEIGHT = 86
    GAP = 8

    def card_rect(self, row: QRect) -> QRect:
        """The card inside a row; the rest of the row is the gap to the next card."""
        return row.adjusted(1, 0, -7, -self.GAP)

    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:
        if high_contrast():
            return super().sizeHint(option, index)
        return QSize(120, self.HEIGHT + self.GAP)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
        if high_contrast():
            super().paint(painter, option, index)
            return
        tokens = current_theme()
        state = option.state
        selected = bool(state & QStyle.StateFlag.State_Selected)
        card = QRectF(self.card_rect(option.rect))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_panel(painter, card, tokens, 14, selected=selected)
        outline = card.adjusted(0.5, 0.5, -0.5, -0.5)
        if not selected and state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(*tokens.hover))
            painter.drawRoundedRect(outline, 14, 14)
        if selected and state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QPen(QColor(tokens.focus), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(outline.adjusted(1.5, 1.5, -1.5, -1.5), 12.5, 12.5)
        body = card.adjusted(14, 11, -14, -11)
        small = QFont(option.font)
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1))
        metrics = QFontMetricsF(small)
        row = QRectF(body.left(), body.top(), body.width(), metrics.height() + 6)
        # The word count is a chip at the right when the card is wide enough for both.
        words = str(index.data(WORDS) or "")
        chip_width = metrics.horizontalAdvance(words) + 18
        stamp = str(index.data(STAMP) or "")
        room = body.width()
        if words and body.width() >= metrics.horizontalAdvance(stamp) + chip_width + 10:
            pill = QRectF(body.right() - chip_width, row.top(), chip_width, row.height())
            painter.setPen(QPen(QColor(*tokens.chip_border), 1))
            painter.setBrush(QColor(*tokens.chip))
            painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            painter.setFont(small)
            painter.setPen(QColor(tokens.text))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, words)
            room -= chip_width + 10
        painter.setFont(small)
        painter.setPen(QColor(tokens.muted))
        painter.drawText(
            QRectF(row.left(), row.top(), room, row.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            metrics.elidedText(stamp, Qt.TextElideMode.ElideRight, room),
        )
        font = QFont(option.font)
        if selected:
            font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor(tokens.text))
        spacing = QFontMetricsF(font).lineSpacing()
        top = row.bottom() + 5
        for line in wrapped_lines(str(index.data(PREVIEW) or ""), font, body.width(), 2):
            painter.drawText(
                QRectF(body.left(), top, body.width(), spacing),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                line,
            )
            top += spacing
        painter.restore()


class ScrollPage(QWidget):
    """A scrolled page that asks for its minimum height, so it scrolls only when it must."""

    def heightForWidth(self, width: int) -> int:
        layout = self.layout()
        return layout.totalMinimumHeightForWidth(width) if layout is not None else -1


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
        self.latest_button: IconButton | None = None
        if latest is not None:
            self.latest_button = self.nav_button("Latest transcript", "transcript")
            self.latest_button.setCheckable(True)
            self.navigation.addButton(self.latest_button)
            self.latest_button.clicked.connect(latest)
            nav.addWidget(self.latest_button)
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
        nav.addSpacing(4)
        quit_button = IconButton("Quit LocalPhraser", "power", "quiet")
        quit_button.clicked.connect(quit_app)
        nav.addWidget(quit_button)
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        content.setSpacing(8)
        chrome = QHBoxLayout()
        chrome.setSpacing(2)
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
        # Home scrolls instead of clipping when the window is at its smallest.
        self.home = QScrollArea()
        self.home.setWidgetResizable(True)
        self.home.setFrameShape(QScrollArea.Shape.NoFrame)
        self.home.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.home.viewport().setAutoFillBackground(False)
        self.home_body = ScrollPage()
        self.home_body.setObjectName("glassBody")
        self.home.setWidget(self.home_body)
        layout = QVBoxLayout(self.home_body)
        self.home_layout = layout
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(16)

        # Hero: what the app is doing now, and the one action that starts a dictation.
        self.hero = GlassPanel("hero")
        self.hero_box = QVBoxLayout(self.hero)
        self.hero_box.setSpacing(8)
        self.hero_top = QHBoxLayout()
        self.hero_text = QVBoxLayout()
        self.hero_text.setSpacing(6)
        self.hero_side = QVBoxLayout()
        self.hero_side.setSpacing(10)
        self.hero_foot = QHBoxLayout()
        self.hero_foot.setSpacing(12)
        self.orb = StatusOrb("microphone")
        self.hero_chip = StateChip()
        self.headline = QLabel("Ready to dictate")
        self.headline.setObjectName("pageTitle")
        self.headline.setWordWrap(True)
        self.headline.setTextFormat(Qt.TextFormat.PlainText)
        self.hero_head = QWidget()
        head = QVBoxLayout(self.hero_head)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        head.addWidget(self.hero_chip, 0, Qt.AlignmentFlag.AlignLeft)
        head.addWidget(self.headline)
        self.hint = QLabel()
        self.hint.setProperty("muted", True)
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.record_button = RecordButton("Record to history", "microphone", "primary")
        self.record_button.clicked.connect(record)
        self.record_button.setToolTip("Use your shortcut in another app for automatic insertion.")
        self.hero_meter = LevelMeter(bars=28)
        self.hero_meter.setFixedHeight(26)
        self.hero_meter.setAccessibleName("Microphone level")
        self.hero_top.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignVCenter)
        self.hero_top.addLayout(self.hero_text, 1)
        self.hero_top.addLayout(self.hero_side)
        self.hero_box.addLayout(self.hero_top)
        self.hero_box.addLayout(self.hero_foot)
        self.compact: bool | None = None
        self.stacked: bool | None = None
        layout.addWidget(self.hero)

        self.metric_labels = []
        self.metric_icons = []
        self.metric_boxes = []
        metrics = QHBoxLayout()
        self.metrics_row = metrics
        metrics.setSpacing(14)
        for caption, glyph in (
            ("Saved words", "lines"),
            ("Dictations", "microphone"),
            ("Speaking pace", "gauge"),
        ):
            panel = GlassPanel("metric")
            tile = QHBoxLayout(panel)
            tile.setContentsMargins(14, 12, 14, 12)
            tile.setSpacing(12)
            icon = Glyph(glyph, "glow", 40, badge=True)
            tile.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
            stack = QVBoxLayout()
            stack.setSpacing(0)
            number = QLabel("—")
            number.setObjectName("metricNumber")
            caption_label = QLabel(caption)
            caption_label.setObjectName("metricCaption")
            stack.addWidget(number)
            stack.addWidget(caption_label)
            tile.addLayout(stack, 1)
            self.metric_labels.append(number)
            self.metric_icons.append(icon)
            self.metric_boxes.append(tile)
            metrics.addWidget(panel)
        layout.addLayout(metrics)

        recent = QHBoxLayout()
        recent_title = QLabel("Recent transcriptions")
        recent_title.setProperty("sectionTitle", True)
        recent.addWidget(recent_title, 1)
        self.clear_button = IconButton("Clear history", "trash", "danger")
        self.clear_button.clicked.connect(self.clear_history)
        recent.addWidget(self.clear_button)
        layout.addLayout(recent)
        self.history_notice = QLabel()
        self.history_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.history_notice.setWordWrap(True)
        self.history_notice.hide()
        layout.addWidget(self.history_notice)
        split = QSplitter()
        split.setHandleWidth(12)
        split.setChildrenCollapsible(False)
        self.entries = QListWidget()
        self.entries.setObjectName("historyCards")
        self.entries.setItemDelegate(HistoryCards(self.entries))
        self.entries.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.entries.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.entries.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.entries.setMouseTracking(True)  # Cards respond to the pointer.
        self.entries.setMinimumWidth(150)
        self.entries.setAccessibleName("Recent transcriptions")
        self.entries.currentItemChanged.connect(self.select_entry)
        split.addWidget(self.entries)
        detail = GlassPanel("transcriptPanel")
        detail.setMinimumWidth(190)
        detail_layout = QVBoxLayout(detail)
        self.detail_layout = detail_layout
        detail_layout.setContentsMargins(18, 16, 18, 18)
        detail_layout.setSpacing(10)
        self.entry_info = ChipLabel("Your next dictation will appear here.")
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
        detail_layout.addWidget(self.tabs, 1)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.copy_button = IconButton("Copy text", "copy", "primary")
        self.copy_button.clicked.connect(self.copy_text)
        self.delete_button = IconButton("Delete entry", "trash", "danger")
        self.delete_button.clicked.connect(self.delete_entry)
        actions.addWidget(self.copy_button, 1)
        actions.addWidget(self.delete_button, 1)
        detail_layout.addLayout(actions)
        split.addWidget(detail)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 5)
        split.setSizes([330, 440])
        self.history_split = split
        self.tabs.setMinimumHeight(104)
        self.empty_history = GlassPanel("emptyHistory")
        empty_layout = QVBoxLayout(self.empty_history)
        empty_layout.setContentsMargins(32, 24, 32, 24)
        empty_layout.setSpacing(8)
        empty_layout.addStretch()
        self.empty_icon = Glyph("microphone", "glow", 56, badge=True)
        empty_layout.addWidget(self.empty_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addSpacing(6)
        empty_title = QLabel("No dictations yet")
        empty_title.setObjectName("emptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        self.empty_message = QLabel()
        self.empty_message.setProperty("muted", True)
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
        self.set_compact(self.width() < COMPACT_WIDTH)
        self.set_stacked(self.width() < STACKED_WIDTH)
        self.set_state("Ready", "ready")
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
        """Show the state in the sidebar chip and, in words, in the Home hero."""
        self.state_label.setText(text)
        self.state_dot.set_tone(tone)
        self.headline.setText("Ready to dictate" if text == State.IDLE.value else text)
        self.hero_chip.set_state(chip_word(text, tone), tone)
        self.orb.set_tone(tone)

    def set_level(self, shown: float) -> None:
        """Show the live input level (0..1 on the meter scale) while recording."""
        self.hero_meter.set_level(shown)
        self.orb.set_level(shown)

    def clear_level(self) -> None:
        self.hero_meter.reset()
        self.orb.reset()

    def set_compact(self, compact: bool) -> None:
        """Rearrange for a narrow window: the hero drops its meter, the tiles tighten."""
        if compact == self.compact:
            return
        self.compact = compact
        self.shell_layout.setContentsMargins(*([12] * 4 if compact else [18] * 4))
        self.shell_layout.setSpacing(12 if compact else 22)
        self.sidebar.setFixedWidth(178 if compact else 208)
        self.sidebar_layout.setContentsMargins(*((8, 12, 8, 8) if compact else (12, 16, 12, 12)))
        self.home_layout.setSpacing(10 if compact else 16)
        # Wide: orb | chip, headline, hint | button over meter.
        # Narrow: orb | headline, hint, then the button across the card; no chip or meter.
        for layout in (self.hero_text, self.hero_side, self.hero_foot):
            while layout.count():
                layout.takeAt(0)
        if compact:
            self.hero_box.setContentsMargins(14, 12, 14, 12)
            self.hero_top.setSpacing(12)
            self.orb.set_size(56)
            self.hero_text.addStretch()
            self.hero_text.addWidget(self.hero_head)
            self.hero_text.addWidget(self.hint)
            self.hero_text.addStretch()
            self.hero_foot.addWidget(self.record_button, 1)
            self.record_button.setMinimumWidth(0)
        else:
            self.hero_box.setContentsMargins(22, 18, 24, 18)
            self.hero_top.setSpacing(20)
            self.orb.set_size(96)
            self.hero_text.addStretch()
            self.hero_text.addWidget(self.hero_head)
            self.hero_text.addWidget(self.hint)
            self.hero_text.addStretch()
            self.hero_side.addStretch()
            self.hero_side.addWidget(self.record_button)
            self.hero_side.addWidget(self.hero_meter)
            self.hero_side.addStretch()
            self.record_button.setMinimumWidth(196)
        self.hero_meter.setVisible(not compact)
        self.hero_chip.setVisible(not compact)  # The headline already states the state.
        self.metrics_row.setSpacing(8 if compact else 14)
        for icon, tile in zip(self.metric_icons, self.metric_boxes, strict=True):
            icon.setVisible(not compact)
            tile.setContentsMargins(*((10, 8, 8, 8) if compact else (14, 12, 14, 12)))
        self.detail_layout.setContentsMargins(*((12, 12, 12, 12) if compact else (18, 16, 18, 18)))
        for label in (self.headline, *self.metric_labels):
            label.setProperty("compact", compact)
            label.style().unpolish(label)
            label.style().polish(label)

    def set_stacked(self, stacked: bool) -> None:
        """In a very narrow window the history list sits above the entry, not beside it."""
        if stacked == self.stacked:
            return
        self.stacked = stacked
        self.history_split.setOrientation(
            Qt.Orientation.Vertical if stacked else Qt.Orientation.Horizontal
        )
        card = HistoryCards.HEIGHT + HistoryCards.GAP
        self.entries.setMinimumHeight(card if stacked else 0)
        self.history_split.setSizes([card + 60, 240] if stacked else [330, 440])
        self.history_views.setMinimumHeight(card + 12 + 230 if stacked else 236)

    def maximize_restore(self) -> None:
        self.showNormal() if self.isMaximized() or self.isFullScreen() else self.showMaximized()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        enable_snap(self)

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "stacked"):
            self.set_compact(self.width() < COMPACT_WIDTH)
            self.set_stacked(self.width() < STACKED_WIDTH)
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

    def show_latest(self, widget: QWidget) -> None:
        if self.latest_button is not None:
            self.latest_button.setChecked(True)
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
            preview = entry["preview"].replace(chr(10), " ")
            # The text keeps both lines for assistive technology; the delegate draws a card.
            item = QListWidgetItem(f"{stamp}   {entry['words']} words\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            item.setData(STAMP, stamp)
            item.setData(WORDS, f"{entry['words']} words")
            item.setData(PREVIEW, preview)
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
