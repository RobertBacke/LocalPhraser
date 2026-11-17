"""Lightweight glass surfaces using Qt paint and optional Windows 11 composition."""

import ctypes
import random
import sys
from functools import lru_cache
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPalette,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListView,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyleOptionButton,
    QStyleOptionSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from localphraser.typography import interface_family


def high_contrast() -> bool:
    hints = QApplication.styleHints()
    if hasattr(hints, "accessibility"):
        return hints.accessibility().contrastPreference() == Qt.ContrastPreference.HighContrast
    return False


def dark_surface() -> bool:
    # Stylesheets can retain a widget's old palette when the application theme changes.
    return QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128


def ink(dark: bool) -> tuple[str, str]:
    """Body text and muted (hint) text; both stay above WCAG AA on the glass."""
    return ("#edf8f7", "#c0cce1") if dark else ("#163c42", "#435974")


# State colours shared by the listening capsule and the sidebar status (light, dark).
TONES = {
    "recording": ((206, 52, 64), (255, 118, 124)),
    "busy": ((196, 124, 8), (247, 189, 82)),
    "ready": ((32, 140, 104), (86, 212, 164)),
}


def tone_color(tone: str) -> QColor:
    if high_contrast():
        return QApplication.palette().color(QPalette.ColorRole.WindowText)
    dark = dark_surface()
    if tone in TONES:
        return QColor(*TONES[tone][dark])
    return QColor(ink(dark)[1])


@lru_cache(maxsize=1)
def frost_texture() -> QImage:
    texture = QImage(64, 64, QImage.Format.Format_ARGB32_Premultiplied)
    rng = random.Random(17)
    for y in range(64):
        for x in range(64):
            value = 255 if rng.getrandbits(1) else 0
            texture.setPixelColor(x, y, QColor(value, value, value, rng.randrange(1, 4)))
    return texture


def enable_backdrop(widget: QWidget) -> bool:
    """Ask DWM for desktop acrylic; unsupported systems keep an opaque Qt surface."""
    if (
        sys.platform != "win32"
        or QApplication.platformName() != "windows"
        or sys.getwindowsversion().build < 22621
        or high_contrast()
        or not widget.isWindow()
    ):
        return False
    try:
        dwm = ctypes.WinDLL("dwmapi")
        set_attribute = dwm.DwmSetWindowAttribute
        set_attribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        set_attribute.restype = ctypes.c_long
        extend = dwm.DwmExtendFrameIntoClientArea
        extend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        extend.restype = ctypes.c_long
        hwnd = int(widget.winId())
        for attribute, number in ((20, int(dark_surface())), (33, 2), (34, -2), (38, 3)):
            value = ctypes.c_int(number)
            if set_attribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) < 0:
                return False
        margins = (ctypes.c_int * 4)(-1, -1, -1, -1)
        return extend(hwnd, ctypes.byref(margins)) >= 0
    except (OSError, AttributeError):
        return False


def paint_surface(
    widget: QWidget, translucent: bool, radius: float, rim: bool = True, opacity: int = 216
) -> None:
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    area = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    if high_contrast():
        painter.fillRect(widget.rect(), widget.palette().window())
        return
    dark = dark_surface()
    alpha = opacity if translucent else 255
    gradient = QLinearGradient(area.topLeft(), area.bottomRight())
    gradient.setColorAt(0, QColor(21, 27, 49, alpha) if dark else QColor(245, 249, 255, alpha))
    gradient.setColorAt(1, QColor(36, 42, 65, alpha) if dark else QColor(225, 237, 249, alpha))
    painter.setBrush(gradient)
    painter.setPen(
        QPen(QColor(255, 255, 255, 70 if dark else 190), 1) if rim else Qt.PenStyle.NoPen
    )
    painter.drawRoundedRect(area, radius, radius)
    if rim:
        # Diffused light behind the translucent panels also works without desktop acrylic.
        for x, y, scale, rgb in (
            (0.12, 0.08, 0.72, (74, 159, 231)),
            (0.90, 0.18, 0.65, (153, 118, 222)),
            (0.62, 1.05, 0.65, (58, 183, 199)),
        ):
            glow = QRadialGradient(
                QPointF(widget.width() * x, widget.height() * y), widget.width() * scale
            )
            glow.setColorAt(0, QColor(*rgb, 95 if dark else 82))
            glow.setColorAt(0.55, QColor(*rgb, 35 if dark else 24))
            glow.setColorAt(1, QColor(*rgb, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawRoundedRect(area, radius, radius)
        painter.setBrush(QBrush(frost_texture()))
        painter.drawRoundedRect(area, radius, radius)
    if rim:
        painter.setPen(QPen(QColor(255, 255, 255, 95 if dark else 210), 1))
        painter.drawLine(QPointF(radius, 1.5), QPointF(widget.width() - radius, 1.5))


class DragHandle(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setProperty("systemDragHandle", True)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)


class CaptionButton(QPushButton):
    """Caption symbols drawn at logical-pixel sizes, independent of font glyph metrics."""

    def __init__(self, kind: str):
        super().__init__("")
        self.kind = kind
        self.setObjectName("captionButton")
        self.setFixedSize(46, 36)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.palette().color(QPalette.ColorRole.ButtonText), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        box = QRectF((self.width() - 12) / 2, (self.height() - 12) / 2, 12, 12)
        if self.kind == "minimize":
            painter.drawLine(
                QPointF(box.left(), box.center().y()), QPointF(box.right(), box.center().y())
            )
        elif self.kind == "close":
            painter.drawLine(box.topLeft(), box.bottomRight())
            painter.drawLine(box.topRight(), box.bottomLeft())
        elif self.window().isMaximized() or self.window().isFullScreen():
            x, y = box.left(), box.top()
            painter.drawLine(QPointF(x + 3, y + 3), QPointF(x + 3, y))
            painter.drawLine(QPointF(x + 3, y), QPointF(x + 12, y))
            painter.drawLine(QPointF(x + 12, y), QPointF(x + 12, y + 9))
            painter.drawLine(QPointF(x + 12, y + 9), QPointF(x + 9, y + 9))
            painter.drawRect(QRectF(x, y + 3, 9, 9))
        else:
            painter.drawRect(box)


class GlassComboBox(QComboBox):
    """A standard keyboard-accessible list with comfortable, opaque popup rows."""

    def __init__(self) -> None:
        super().__init__()
        view = QListView()
        view.setSpacing(2)
        view.setUniformItemSizes(True)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setView(view)
        self.setMaxVisibleItems(8)
        self.setMinimumHeight(38)
        # Long items elide instead of forcing the page wider; the open list shows them whole.
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)

    def wheelEvent(self, event: Any) -> None:
        # Scrolling a page must not change the setting under the pointer. Ignoring the
        # event hands it to the enclosing scroll area; the open list scrolls on its own.
        event.ignore()

    def select_data(self, value: Any) -> bool:
        """Select the item whose stored value (not its display text) is ``value``."""
        index = self.findData(value)
        if index >= 0:
            self.setCurrentIndex(index)
        return index >= 0

    def showPopup(self) -> None:
        # Native roll-open animation uses the screen-sized geometry before we constrain it.
        animated = QApplication.isEffectEnabled(Qt.UIEffect.UI_AnimateCombo)
        QApplication.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo, False)
        try:
            super().showPopup()
        finally:
            QApplication.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo, animated)
        popup = self.view().window()
        if not popup.isVisible():
            return
        owner = self.window()
        bounds = QRect(owner.mapToGlobal(QPoint()), owner.size()).adjusted(8, 8, -8, -8)
        anchor = QRect(self.mapToGlobal(QPoint()), self.size())
        screen = QApplication.screenAt(anchor.center()) or owner.screen()
        bounds = bounds.intersected(screen.availableGeometry())
        if bounds.isEmpty():
            self.hidePopup()
            return
        below = max(0, bounds.bottom() - anchor.bottom() - 4)
        above = max(0, anchor.top() - bounds.top() - 4)
        open_below = popup.height() <= below or below >= above
        height = min(popup.height(), max(1, below if open_below else above))
        width = min(max(self.width(), popup.width()), bounds.width())
        x = max(bounds.left(), min(anchor.left(), bounds.right() - width + 1))
        y = anchor.bottom() + 5 if open_below else anchor.top() - height - 4
        y = max(bounds.top(), min(y, bounds.bottom() - height + 1))
        popup.setGeometry(x, y, width, height)
        self.view().scrollTo(self.view().currentIndex())

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if high_contrast():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Text), 1.6))
        x, y = self.width() - 18, self.height() / 2
        painter.drawLine(QPointF(x - 4, y - 2), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 4, y - 2))


def draw_chevron(painter: QPainter, centre: QPointF, up: bool, color: QColor) -> None:
    pen = QPen(color, 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    rise = -2.0 if up else 2.0
    x, y = centre.x(), centre.y()
    painter.drawLine(QPointF(x - 4, y - rise), QPointF(x, y + rise))
    painter.drawLine(QPointF(x, y + rise), QPointF(x + 4, y - rise))


class GlassSpinBox(QSpinBox):
    """A number field changed by typing, arrow keys or its buttons, never by scrolling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Style sheets do not pad a spin box's text; line it up with the other fields.
        line = self.lineEdit()
        if line is not None:
            line.setTextMargins(6, 0, 0, 0)

    def wheelEvent(self, event: Any) -> None:
        event.ignore()

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if high_contrast():
            return
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.palette().color(QPalette.ColorRole.Text)
        steps = self.stepEnabled()
        for control, up, flag in (
            (QStyle.SubControl.SC_SpinBoxUp, True, QSpinBox.StepEnabledFlag.StepUpEnabled),
            (QStyle.SubControl.SC_SpinBoxDown, False, QSpinBox.StepEnabledFlag.StepDownEnabled),
        ):
            area = self.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox, option, control, self
            )
            color = QColor(text)
            if not (self.isEnabled() and steps & flag):
                color.setAlpha(80)
            centre = QRectF(area).center()
            draw_chevron(painter, QPointF(centre.x(), centre.y() + (1 if up else -1)), up, color)


class GlassCheckBox(QCheckBox):
    """A check box that always shows its box: empty when off, filled and ticked when on."""

    def indicator_rect(self) -> QRect:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        return self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if high_contrast():
            return  # The native indicator is drawn by the system style.
        dark = dark_surface()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        box = QRectF(self.indicator_rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.hasFocus():
            painter.setPen(QPen(QColor("#9fd9ff" if dark else "#365f95"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box.adjusted(-3, -3, 3, 3), 7, 7)
        if self.isChecked():
            fill = QLinearGradient(box.topLeft(), box.bottomRight())
            fill.setColorAt(0, QColor(52, 92, 150))
            fill.setColorAt(1, QColor(75, 72, 137))
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(219, 236, 255, 150 if dark else 90), 1))
            painter.drawRoundedRect(box, 5, 5)
            tick = QPen(QColor("white"), 2)
            tick.setCapStyle(Qt.PenCapStyle.RoundCap)
            tick.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(tick)
            w, h, x, y = box.width(), box.height(), box.left(), box.top()
            painter.drawPolyline(
                [
                    QPointF(x + w * 0.24, y + h * 0.52),
                    QPointF(x + w * 0.43, y + h * 0.70),
                    QPointF(x + w * 0.77, y + h * 0.32),
                ]
            )
        else:
            painter.setBrush(QColor(16, 25, 48, 140) if dark else QColor(255, 255, 255, 215))
            border = (
                QColor("#8cbddd")
                if self.underMouse()
                else QColor(200, 220, 255, 150)
                if dark
                else QColor(54, 95, 149, 165)
            )
            painter.setPen(QPen(border, 1.4))
            painter.drawRoundedRect(box, 5, 5)


class StatusDot(QWidget):
    """A small painted state dot; the state is always also given as text beside it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tone = "muted"
        self.setFixedSize(10, 10)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_tone(self, tone: str) -> None:
        if tone != self.tone:
            self.tone = tone
            self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tone_color(self.tone))
        painter.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))


class NoteLabel(QLabel):
    """Wrapped plain text. As a hint (the default) it is muted and slightly smaller."""

    def __init__(
        self, text: str = "", *, hint: bool = True, collapse_when_empty: bool = False
    ) -> None:
        super().__init__()
        self.collapse_when_empty = collapse_when_empty
        if hint:
            self.setProperty("hint", True)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setText(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        if not self.collapse_when_empty:
            return
        if not text:
            self.hide()
        elif self.parentWidget() is not None:  # Never show a parentless label as a window.
            self.show()

    def clear(self) -> None:
        self.setText("")


class GlassDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.native_glass = False
        self.surface_mode: tuple[bool, bool] | None = None
        self.setObjectName("glassDialog")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizeGripEnabled(True)
        self.setFont(QFont(interface_family(), 10))
        self.refresh_surface()

    def header(self, title: str, style: str = "windowTitle") -> QHBoxLayout:
        row = QHBoxLayout()
        handle = DragHandle(title)
        handle.setObjectName(style)
        handle.setToolTip("Drag to move this window")
        close = QToolButton()
        close.setText("×")
        close.setAccessibleName("Close window")
        close.setToolTip("Close window")
        close.clicked.connect(self.reject)
        row.addWidget(handle, 1)
        row.addWidget(close)
        return row

    def refresh_surface(self) -> None:
        mode = dark_surface(), high_contrast()
        if self.surface_mode == mode:
            return  # Stylesheet palette notifications must not reapply the same sheet.
        self.surface_mode = mode
        if mode[1]:
            self.setStyleSheet("")
        else:
            dark = mode[0]
            text, muted = ink(dark)
            field = "rgba(16, 25, 48, 125)" if dark else "rgba(255, 255, 255, 155)"
            border = "rgba(227, 239, 255, 50)" if dark else "rgba(255, 255, 255, 220)"
            selected = "rgba(17,35,66,175)" if dark else "rgba(109,164,229,55)"
            focus = "#9fd9ff" if dark else "#365f95"
            glass = (
                "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,255,255,35),"
                "stop:0.45 rgba(228,238,255,16),stop:1 rgba(167,201,245,25))"
                if dark
                else "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,255,255,175),"
                "stop:0.45 rgba(255,255,255,90),stop:1 rgba(238,245,255,135))"
            )
            menu = "#1b2a40" if dark else "#f5faff"
            hover = "rgba(255,255,255,22)" if dark else "rgba(255,255,255,135)"
            handle = "rgba(220,235,255,70)" if dark else "rgba(54,95,149,85)"
            handle_hover = "rgba(220,235,255,125)" if dark else "rgba(54,95,149,145)"
            self.setStyleSheet(
                f"* {{ font-family: '{interface_family()}'; font-size: 10pt; }}"
                f"QDialog#glassDialog {{ color: {text}; }}"
                f"QLabel, QCheckBox, QGroupBox {{ color: {text}; background: transparent; }}"
                "QLabel#windowTitle { font-size: 13px; font-weight: 600; padding: 2px; }"
                "QLabel#brand { font-size: 17px; font-weight: 600; padding: 10px 0; }"
                "QLabel#pageTitle { font-size: 28px; font-weight: 600; }"
                "QLabel#metricNumber { font-size: 28px; font-weight: 600; }"
                f"QFrame#metric, QFrame#sidebar, QWidget#transcriptPanel, QFrame#emptyHistory"
                f" {{ background: {glass}; border: 1px solid {border}; border-radius: 20px; }}"
                f"QFrame#settingsSection {{ background: {glass}; border: 1px solid {border};"
                " border-radius: 18px; }"
                "QLabel[sectionTitle=true] { font-size: 15px; font-weight: 600; }"
                "QLabel#emptyTitle { font-size: 17px; font-weight: 600; }"
                f"QListWidget, QTableWidget {{ color: {text}; background: {glass}; "
                f"border: 1px solid {border};"
                " border-radius: 20px; padding: 8px; }"
                # A transparent border keeps selected rows the same height as the others.
                "QListWidget::item { padding: 12px 8px; border-radius: 8px;"
                " border: 1px solid transparent; }"
                f"QHeaderView::section {{ color: {text}; background: {field}; "
                "border: none; padding: 10px 6px; }"
                "QTableWidget::item { padding: 10px 6px; }"
                f"QListWidget::item:selected {{ background: {selected};"
                f" color: {text}; border: 1px solid {border}; }}"
                "QWidget#glassBody, QScrollArea { background: transparent; border: none; }"
                "QSplitter::handle { background: transparent; }"
                f"QLineEdit, QTextEdit, QComboBox, QSpinBox {{ color: {text};"
                f" background: {field}; border: 1px solid {border}; border-radius: 9px;"
                " padding: 7px; selection-background-color: #287e79; }"
                "QComboBox { padding-right: 32px; }"
                "QComboBox::drop-down { width: 28px; border: none; }"
                "QComboBox::down-arrow { image: none; }"
                "QSpinBox { padding-right: 34px; }"
                "QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border;"
                " width: 26px; border: none; background: transparent; border-radius: 6px; }"
                "QSpinBox::up-button { subcontrol-position: top right; margin: 4px 4px 0 0; }"
                "QSpinBox::down-button { subcontrol-position: bottom right; margin: 0 4px 4px 0; }"
                f"QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {hover}; }}"
                "QSpinBox::up-arrow, QSpinBox::down-arrow { image: none; width: 0; height: 0; }"
                "QCheckBox { spacing: 10px; outline: none; padding: 4px; }"
                "QCheckBox::indicator { width: 20px; height: 20px; border: none;"
                " background: transparent; image: none; }"
                "QScrollBar:vertical { background: transparent; width: 12px; margin: 4px 2px;"
                " border: none; }"
                "QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px 4px;"
                " border: none; }"
                f"QScrollBar::handle {{ background: {handle}; border-radius: 4px; }}"
                "QScrollBar::handle:hover, QScrollBar::handle:pressed {"
                f" background: {handle_hover}; }}"
                "QScrollBar::handle:vertical { min-height: 36px; }"
                "QScrollBar::handle:horizontal { min-width: 36px; }"
                "QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none;"
                " background: none; }"
                "QScrollBar::add-page, QScrollBar::sub-page { background: none; }"
                f"QProgressBar {{ color: {text}; background: {field}; border: 1px solid {border};"
                " border-radius: 7px; min-height: 22px; text-align: center; }"
                "QProgressBar::chunk { background: rgba(71,151,164,160); border-radius: 6px; }"
                f"QComboBox QAbstractItemView {{ color: {text}; background: {menu};"
                f" border: 1px solid {border}; border-radius: 10px; padding: 6px;"
                " outline: 0; selection-background-color: #315aa3; selection-color: white; }"
                "QComboBox QAbstractItemView::item { min-height: 30px; padding: 4px 10px;"
                " border-radius: 6px; }"
                "QComboBox QAbstractItemView::item:selected { background: #315aa3; color: white; }"
                f"QPushButton, QToolButton {{ color: {text}; background: {field};"
                f" border: 1px solid {border}; border-radius: 10px; padding: 8px 12px; }}"
                "QPushButton:hover, QToolButton:hover { border-color: #8cbddd; }"
                "QPushButton#captionButton { padding: 0; }"
                "QPushButton:focus, QToolButton:focus, QLineEdit:focus, QTextEdit:focus,"
                f" QComboBox:focus, QSpinBox:focus {{ border: 2px solid {focus}; }}"
                "QPushButton[primary=true], QPushButton:checked {"
                " background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 rgba(52,92,150,245),stop:1 rgba(75,72,137,245)); color: white;"
                " border-color: rgba(219,236,255,110); font-weight: 600; }"
                f"QPushButton:disabled, QLabel:disabled {{ color: {muted}; }}"
                "QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {"
                f" color: {muted}; background: transparent; }}"
                f"QLabel[hint=true] {{ color: {muted}; font-size: 9pt; }}"
                # Sidebar navigation reads as a list of places, not as buttons.
                "QPushButton[nav=true] { background: transparent; border: 1px solid transparent;"
                " text-align: left; padding: 9px 14px; }"
                f"QPushButton[nav=true]:hover {{ background: {hover}; border-color: {border}; }}"
                "QPushButton[nav=true]:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 rgba(52,92,150,245),stop:1 rgba(75,72,137,245)); color: white;"
                " border-color: rgba(219,236,255,110); font-weight: 600; }"
                f"QPushButton[nav=true]:focus {{ border: 2px solid {focus}; }}"
                f"QGroupBox {{ border: 1px solid {border}; border-radius: 14px;"
                " margin-top: 12px; padding: 18px 12px 12px; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }"
                f"QTabWidget::pane {{ border: 1px solid {border}; border-radius: 9px; }}"
                f"QTabBar::tab {{ color: {text}; padding: 8px 14px; background: transparent;"
                " border: 1px solid transparent; border-radius: 8px; margin-right: 4px; }"
                f"QTabBar::tab:selected {{ background: {field}; border: 1px solid {border}; }}"
            )
        if self.isVisible():
            self.native_glass = enable_backdrop(self)
        self.update()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.native_glass = enable_backdrop(self)
        self.update()

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self.refresh_surface()

    def paintEvent(self, event: Any) -> None:
        if self.isWindow():
            paint_surface(self, self.native_glass, 22, opacity=160 if dark_surface() else 185)


class GlassCapsule(QWidget):
    """A frosted, plain-text capsule: a painted state dot, a short status and the words."""

    def __init__(self) -> None:
        super().__init__()
        self.native_glass = False
        self.surface_mode: tuple[bool, bool] | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QVBoxLayout(self)
        self.capsule_layout = layout
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)  # fit() sizes it.
        layout.setContentsMargins(22, 13, 24, 15)
        layout.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(9)
        self.dot = StatusDot()
        self.status = QLabel()
        self.status.setObjectName("capsuleStatus")
        self.words = QLabel()
        self.words.setObjectName("capsuleWords")
        self.words.setWordWrap(True)
        self.words.hide()
        for label in (self.status, self.words):
            label.setTextFormat(Qt.TextFormat.PlainText)  # Transcripts are never markup.
            label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.words.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        row.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.status, 1)
        layout.addLayout(row)
        layout.addWidget(self.words)
        self.refresh_surface()
        application = QApplication.instance()
        if isinstance(application, QApplication):
            application.paletteChanged.connect(self.refresh_surface)

    def refresh_surface(self) -> None:
        mode = dark_surface(), high_contrast()
        if self.surface_mode == mode:
            return
        self.surface_mode = mode
        if mode[1]:
            color = muted = QApplication.palette().color(QPalette.ColorRole.WindowText).name()
        else:
            color, muted = ink(mode[0])
        self.setStyleSheet(
            f"* {{ background: transparent; font-family: '{interface_family()}'; }}"
            f"QLabel#capsuleStatus {{ color: {muted}; font-size: 12px; font-weight: 600;"
            " letter-spacing: 0.2px; }"
            f"QLabel#capsuleWords {{ color: {color}; font-size: 17px; font-weight: 500; }}"
        )
        self.dot.update()
        self.update()

    def fit(self) -> None:
        """Grow to fit the words on one line within the width limits, then wrap."""
        for label in (self.status, self.words):
            label.ensurePolished()
        margins = self.capsule_layout.contentsMargins()
        status = (
            self.dot.width() + 9 + self.status.fontMetrics().horizontalAdvance(self.status.text())
        )
        words = self.words.fontMetrics().horizontalAdvance(self.words.text())
        wanted = max(status, words if self.words.isVisibleTo(self) else 0)
        width = max(
            self.minimumWidth(),
            min(self.maximumWidth(), wanted + 8 + margins.left() + margins.right()),
        )
        self.capsule_layout.activate()
        height = self.heightForWidth(width)
        if height < 0:
            height = self.sizeHint().height()
        self.resize(width, max(self.minimumHeight(), min(self.maximumHeight(), height)))

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self.refresh_surface()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.native_glass = False  # Keep native rectangular frames out of the capsule.

    def paintEvent(self, event: Any) -> None:
        paint_surface(self, True, min(24, self.height() / 2), rim=False, opacity=250)
