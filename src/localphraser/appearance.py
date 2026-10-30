"""Lightweight glass surfaces using Qt paint and optional Windows 11 composition."""

import ctypes
import sys
from typing import Any

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPalette, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QToolButton,
    QWidget,
)


def high_contrast() -> bool:
    hints = QApplication.styleHints()
    if hasattr(hints, "accessibility"):
        return hints.accessibility().contrastPreference() == Qt.ContrastPreference.HighContrast
    return False


def dark_surface() -> bool:
    # Stylesheets can retain a widget's old palette when the application theme changes.
    return QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128


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
    gradient.setColorAt(0, QColor(35, 47, 66, alpha) if dark else QColor(251, 254, 255, alpha))
    gradient.setColorAt(1, QColor(19, 29, 45, alpha) if dark else QColor(226, 239, 249, alpha))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor(255, 255, 255, 28 if dark else 95), 1) if rim else Qt.PenStyle.NoPen)
    painter.drawRoundedRect(area, radius, radius)
    if rim and widget.width() > 600:
        glow = QRadialGradient(QPointF(widget.width() * 0.8, 0), widget.width() * 0.7)
        glow.setColorAt(0, QColor(103, 166, 236, 38 if dark else 28))
        glow.setColorAt(1, QColor(103, 166, 236, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(area, radius, radius)
    if rim:
        painter.setPen(QPen(QColor(255, 255, 255, 20 if dark else 80), 1))
        painter.drawLine(QPointF(radius, 1.5), QPointF(widget.width() - radius, 1.5))


class DragHandle(QLabel):
    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)


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
        self.setFont(QFont("Segoe UI", 10))
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
            text, muted = ("#edf8f7", "#adbed4") if dark else ("#163c42", "#4b637e")
            field = "rgba(13, 25, 43, 120)" if dark else "rgba(255, 255, 255, 155)"
            border = "rgba(195, 220, 255, 32)" if dark else "rgba(71, 102, 145, 40)"
            menu = "#1b2a40" if dark else "#f5faff"
            self.setStyleSheet(
                f"QDialog#glassDialog {{ color: {text}; }}"
                f"QLabel, QCheckBox, QGroupBox {{ color: {text}; background: transparent; }}"
                "QLabel#windowTitle { font-size: 13px; font-weight: 600; padding: 2px; }"
                "QLabel#brand { font-size: 17px; font-weight: 600; padding: 10px 0; }"
                "QLabel#pageTitle { font-size: 28px; font-weight: 600; }"
                "QLabel#metricNumber { font-size: 28px; font-weight: 600; }"
                f"QFrame#metric, QFrame#sidebar {{ background: {field}; border-radius: 18px; }}"
                f"QListWidget {{ color: {text}; background: {field}; border: none;"
                " border-radius: 12px; padding: 6px; }"
                "QListWidget::item { padding: 12px 8px; border-radius: 8px; }"
                "QListWidget::item:selected { background: #315aa3; color: white; }"
                "QWidget#glassBody, QScrollArea { background: transparent; border: none; }"
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
                "QPushButton:hover, QToolButton:hover { border-color: #45958e; }"
                "QPushButton:focus, QToolButton:focus, QLineEdit:focus, QTextEdit:focus,"
                " QComboBox:focus, QSpinBox:focus { border: 1px solid #287e79; }"
                "QPushButton[primary=true], QPushButton:checked {"
                " background: #315aa3; color: white;"
                " border-color: #315aa3; font-weight: 600; }"
                f"QPushButton:disabled, QLabel:disabled {{ color: {muted}; }}"
                f"QGroupBox {{ border: 1px solid {border}; border-radius: 14px;"
                " margin-top: 12px; padding: 18px 12px 12px; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }"
                f"QTabWidget::pane {{ border: 1px solid {border}; border-radius: 9px; }}"
                f"QTabBar::tab {{ color: {text}; padding: 8px 14px; }}"
                f"QTabBar::tab:selected {{ background: {field}; border-radius: 8px; }}"
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
        paint_surface(self, self.native_glass, 22)


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
            "font-family: 'Segoe UI'; font-size: 14px; font-weight: 500;"
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
