"""Transparent transcription mark shared by runtime icons and the Windows ICO."""

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def logo_pixmap(size: int, recording: bool = False, *, light: bool = False) -> QPixmap:
    source = QPixmap(str(Path(__file__).with_name("assets") / "logo.png"))
    if source.isNull():
        raise RuntimeError("The LocalPhraser logo asset is missing.")
    pixmap = source.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    if light:
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor("#ffffff"))
        painter.end()
    if recording:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff667e"))
        painter.drawEllipse(QRectF(size * 0.68, size * 0.68, size * 0.23, size * 0.23))
        painter.end()
    return pixmap


def dark_taskbar() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "SystemUsesLightTheme")[0] == 0
    except OSError:
        return False


def app_icon(recording: bool = False) -> QIcon:
    icon = QIcon()
    light = dark_taskbar()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(size, recording, light=light))
    return icon
