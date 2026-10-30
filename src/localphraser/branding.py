"""Generated glass mark shared by runtime icons and the multi-size Windows ICO."""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def logo_pixmap(size: int, recording: bool = False) -> QPixmap:
    source = QPixmap(str(Path(__file__).with_name("assets") / "logo.png"))
    if source.isNull():
        raise RuntimeError("The LocalPhraser logo asset is missing.")
    pixmap = source.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    if recording:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff667e"))
        painter.drawEllipse(QRectF(size * 0.68, size * 0.68, size * 0.23, size * 0.23))
        painter.end()
    return pixmap


def app_icon(recording: bool = False) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(size, recording))
    return icon
