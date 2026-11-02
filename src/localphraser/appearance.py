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
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QToolButton,
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

    def header(self, title: str) -> QHBoxLayout:
        row = QHBoxLayout()
        handle = DragHandle(title)
        handle.setObjectName("windowTitle")
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
            text, muted = ("#edf8f7", "#c0cce1") if dark else ("#163c42", "#435974")
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
            self.setStyleSheet(
                f"* {{ font-family: '{interface_family()}'; font-size: 10pt; }}"
                f"QDialog#glassDialog {{ color: {text}; }}"
                f"QLabel, QCheckBox, QGroupBox {{ color: {text}; background: transparent; }}"
                "QLabel#windowTitle { font-size: 13px; font-weight: 600; padding: 2px; }"
                "QLabel#brand { font-size: 17px; font-weight: 600; padding: 10px 0; }"
                "QLabel#pageTitle { font-size: 28px; font-weight: 600; }"
                "QLabel#metricNumber { font-size: 28px; font-weight: 600; }"
                f"QFrame#metric, QFrame#sidebar, QWidget#transcriptPanel {{ background: {glass};"
                f" border: 1px solid {border}; border-radius: 20px; }}"
                f"QListWidget, QTableWidget {{ color: {text}; background: {glass}; "
                f"border: 1px solid {border};"
                " border-radius: 20px; padding: 8px; }"
                "QListWidget::item { padding: 12px 8px; border-radius: 8px; }"
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


class GlassLabel(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.native_glass = False
        self.surface_mode: tuple[bool, bool] | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.refresh_surface()
        application = QApplication.instance()
        if isinstance(application, QApplication):
            application.paletteChanged.connect(self.refresh_surface)

    def refresh_surface(self) -> None:
        mode = dark_surface(), high_contrast()
        if self.surface_mode == mode:
            return
        self.surface_mode = mode
        color = (
            QApplication.palette().color(QPalette.ColorRole.WindowText).name()
            if mode[1]
            else ("#edf8f7" if mode[0] else "#163c42")
        )
        self.setStyleSheet(
            f"background: transparent; color: {color}; padding: 14px 24px;"
            f"font-family: '{interface_family()}'; font-size: 14px; font-weight: 500;"
        )
        self.update()

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self.refresh_surface()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.native_glass = False  # Keep native rectangular frames out of the capsule.

    def paintEvent(self, event: Any) -> None:
        paint_surface(self, True, min(24, self.height() / 2), rim=False, opacity=250)
        super().paintEvent(event)
