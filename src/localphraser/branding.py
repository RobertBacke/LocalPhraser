"""Resolution-independent speech prism mark, shared by the app and Windows icon."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def logo_pixmap(size: int, recording: bool = False) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 64, size / 64)
    base = QLinearGradient(8, 4, 52, 60)
    base.setColorAt(0, QColor("#468ad5"))
    base.setColorAt(0.48, QColor("#203f7e"))
    base.setColorAt(1, QColor("#101e42"))
    painter.setBrush(base)
    painter.setPen(QPen(QColor("#8ddaff"), 1.2))
    painter.drawRoundedRect(QRectF(3, 3, 58, 58), 17, 17)
    # A folded speech pane keeps the silhouette clear at 16px.
    pane = QPainterPath()
    pane.moveTo(17, 16)
    pane.lineTo(47, 16)
    pane.quadTo(51, 16, 51, 21)
    pane.lineTo(51, 41)
    pane.quadTo(51, 45, 46, 45)
    pane.lineTo(31, 45)
    pane.lineTo(21, 52)
    pane.lineTo(21, 45)
    pane.quadTo(13, 45, 13, 39)
    pane.lineTo(13, 22)
    pane.quadTo(13, 16, 17, 16)
    glass = QLinearGradient(15, 16, 46, 47)
    glass.setColorAt(0, QColor(207, 245, 255, 155))
    glass.setColorAt(1, QColor(85, 169, 244, 40))
    painter.setBrush(glass)
    painter.setPen(QPen(QColor(205, 241, 255, 205), 1.3))
    painter.drawPath(pane)
    painter.setPen(
        QPen(
            QColor("#ffbac2" if recording else "#f1fcff"),
            3.4,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    for x, height in ((23, 7), (32, 18), (41, 11)):
        painter.drawLine(QPointF(x, 30 - height / 2), QPointF(x, 30 + height / 2))
    painter.end()
    return pixmap


def app_icon(recording: bool = False) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(size, recording))
    return icon
