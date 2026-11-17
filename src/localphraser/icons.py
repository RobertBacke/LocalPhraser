"""Vector icons painted with Qt: one 20 px box, one stroke, round caps and joins.

No image files and no icon fonts. Icons are decoration: every control that shows one
keeps its text and accessible name.
"""

import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

BOX = 20.0
STROKE = 1.7

# Shapes in the 20 px box: ("path", commands), ("rect", x, y, w, h, radius),
# ("circle", cx, cy, r), ("arc", x, y, w, h, start, sweep), ("dot", cx, cy, r) and
# ("block", x, y, w, h, radius); dots and blocks are filled, the rest are stroked.
Shape = tuple
ICONS: dict[str, tuple[Shape, ...]] = {
    "home": (
        ("path", "M3 9.4 L10 3.2 L17 9.4"),
        ("path", "M5 8 V16.6 H15 V8"),
        ("path", "M8.4 16.6 V12 H11.6 V16.6"),
    ),
    "settings": (
        ("path", "M3 5 H9.4 M14.6 5 H17"),
        ("circle", 12, 5, 2.2),
        ("path", "M3 10 H4.4 M9.6 10 H17"),
        ("circle", 7, 10, 2.2),
        ("path", "M3 15 H10.4 M15.6 15 H17"),
        ("circle", 13, 15, 2.2),
    ),
    "vocabulary": (
        (
            "path",
            "M10 5.6 C8.4 4.3 5.9 4 3.4 4.4 V15.4 C5.9 15 8.4 15.3 10 16.6 "
            "C11.6 15.3 14.1 15 16.6 15.4 V4.4 C14.1 4 11.6 4.3 10 5.6 Z",
        ),
        ("path", "M10 5.6 V16.6"),
    ),
    "analytics": (
        ("rect", 3.4, 10, 3.2, 6.6, 1.2),
        ("rect", 8.4, 3.4, 3.2, 13.2, 1.2),
        ("rect", 13.4, 7, 3.2, 9.6, 1.2),
    ),
    "transcript": (
        ("path", "M5 2.8 H11.4 L15.4 6.8 V17.2 H5 Z"),
        ("path", "M11.4 2.8 V6.8 H15.4"),
        ("path", "M7.6 10.6 H12.8 M7.6 13.6 H12.8"),
    ),
    "microphone": (
        ("rect", 7.4, 2.4, 5.2, 9.4, 2.6),
        ("path", "M4.4 9.4 C4.4 13 6.8 15 10 15 C13.2 15 15.6 13 15.6 9.4"),
        ("path", "M10 15 V17.6 M7 17.6 H13"),
    ),
    "stop": (("block", 5, 5, 10, 10, 2.4),),
    "power": (
        ("arc", 4, 4.6, 12, 12, 125, 290),
        ("path", "M10 2.8 V9.6"),
    ),
    "copy": (
        ("rect", 7.6, 7.6, 9, 9, 2),
        (
            "path",
            "M12.4 7.4 V5.4 Q12.4 3.4 10.4 3.4 H5.4 Q3.4 3.4 3.4 5.4 V10.4 Q3.4 12.4 5.4 12.4 H7.4",
        ),
    ),
    "trash": (
        ("path", "M3.4 5.6 H16.6"),
        ("path", "M7.6 5.4 V3.4 H12.4 V5.4"),
        ("path", "M5.2 5.8 L6 16.6 H14 L14.8 5.8"),
        ("path", "M8.6 8.8 V13.4 M11.4 8.8 V13.4"),
    ),
    "download": (
        ("path", "M10 3 V12.4"),
        ("path", "M6 8.8 L10 12.8 L14 8.8"),
        ("path", "M3.4 14 V16.6 H16.6 V14"),
    ),
    "check": (("path", "M4 10.6 L8.2 14.6 L16 5.8"),),
    "close": (("path", "M5 5 L15 15 M15 5 L5 15"),),
    "plus": (("path", "M10 4 V16 M4 10 H16"),),
    "keyboard": (
        ("rect", 2.4, 5, 15.2, 10, 2.2),
        ("dot", 6, 8.6, 0.95),
        ("dot", 10, 8.6, 0.95),
        ("dot", 14, 8.6, 0.95),
        ("path", "M6.6 12 H13.4"),
    ),
    "waveform": (
        ("path", "M3.4 8.4 V11.6 M6.7 5.4 V14.6 M10 3 V17 M13.3 6.4 V13.6 M16.6 8.6 V11.4"),
    ),
    "text": (
        ("path", "M4.4 6.8 V4.6 H15.6 V6.8"),
        ("path", "M10 4.6 V15.6 M7.6 15.6 H12.4"),
    ),
    "shield": (
        ("path", "M10 2.8 L16 5 V9.6 C16 13.6 13.5 16 10 17.4 C6.5 16 4 13.6 4 9.6 V5 Z"),
        ("path", "M7.4 9.9 L9.3 11.8 L12.8 8"),
    ),
    "grid": (
        ("rect", 3.4, 3.4, 5.4, 5.4, 1.6),
        ("rect", 11.2, 3.4, 5.4, 5.4, 1.6),
        ("rect", 3.4, 11.2, 5.4, 5.4, 1.6),
        ("rect", 11.2, 11.2, 5.4, 5.4, 1.6),
    ),
    "gauge": (
        ("arc", 3, 5, 14, 14, 0, 180),
        ("path", "M10 12 L13.4 8"),
        ("dot", 10, 12, 1.2),
    ),
    "lines": (("path", "M4 6 H16 M4 10 H16 M4 14 H11"),),
    "folder": (("path", "M3 5.4 H8.2 L10 7.6 H17 V15.6 H3 Z"),),
    "sparkle": (
        (
            "path",
            "M10 3 C10.6 7 13 9.4 17 10 C13 10.6 10.6 13 10 17 C9.4 13 7 10.6 3 10 "
            "C7 9.4 9.4 7 10 3 Z",
        ),
    ),
}
NAMES = tuple(ICONS)


def _path(commands: str) -> QPainterPath:
    """Absolute M, L, H, V, C, Q and Z commands, enough for these icons."""
    path = QPainterPath()
    tokens = re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?", commands)
    index = 0
    x = y = 0.0

    def take(count: int) -> list[float]:
        nonlocal index
        values = [float(token) for token in tokens[index : index + count]]
        index += count
        return values

    while index < len(tokens):
        command = tokens[index]
        index += 1
        if command == "M":
            x, y = take(2)
            path.moveTo(x, y)
        elif command == "L":
            x, y = take(2)
            path.lineTo(x, y)
        elif command == "H":
            (x,) = take(1)
            path.lineTo(x, y)
        elif command == "V":
            (y,) = take(1)
            path.lineTo(x, y)
        elif command == "C":
            a, b, c, d, x, y = take(6)
            path.cubicTo(a, b, c, d, x, y)
        elif command == "Q":
            a, b, x, y = take(4)
            path.quadTo(a, b, x, y)
        elif command == "Z":
            path.closeSubpath()
        else:
            raise ValueError(f"Unsupported icon path command: {command}")
    return path


def paint(painter: QPainter, name: str, area: QRectF, color: QColor) -> None:
    """Draw the named icon into ``area`` in one colour."""
    shapes = ICONS[name]
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(area.topLeft())
    painter.scale(area.width() / BOX, area.height() / BOX)
    pen = QPen(color, STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    for shape in shapes:
        kind = shape[0]
        filled = kind in ("dot", "block")
        painter.setPen(Qt.PenStyle.NoPen if filled else pen)
        painter.setBrush(color if filled else Qt.BrushStyle.NoBrush)
        if kind == "path":
            painter.drawPath(_path(shape[1]))
        elif kind in ("rect", "block"):
            painter.drawRoundedRect(QRectF(*shape[1:5]), shape[5], shape[5])
        elif kind in ("circle", "dot"):
            painter.drawEllipse(QPointF(shape[1], shape[2]), shape[3], shape[3])
        elif kind == "arc":
            arc = QPainterPath()
            box = QRectF(*shape[1:5])
            arc.arcMoveTo(box, shape[5])
            arc.arcTo(box, shape[5], shape[6])
            painter.drawPath(arc)
    painter.restore()


def pixmap(name: str, color: QColor, size: int = 20, ratio: float = 1.0) -> QPixmap:
    """The icon as a transparent pixmap drawn at the given device pixel ratio."""
    if name not in ICONS:
        raise KeyError(name)
    result = QPixmap(round(size * ratio), round(size * ratio))
    result.setDevicePixelRatio(ratio)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    try:
        paint(painter, name, QRectF(0, 0, size, size), color)
    finally:
        painter.end()
    return result


def icon(
    name: str,
    color: QColor,
    on: QColor | None = None,
    disabled: QColor | None = None,
    size: int = 20,
) -> QIcon:
    """A QIcon drawn at 1x and 2x, with its own colours when checked and when disabled."""
    result = QIcon()
    if disabled is None:
        disabled = QColor(color)
        disabled.setAlpha(110)
    for ratio in (1.0, 2.0):
        for state, tint in ((QIcon.State.Off, color), (QIcon.State.On, on or color)):
            for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
                result.addPixmap(pixmap(name, tint, size, ratio), mode, state)
            result.addPixmap(pixmap(name, disabled, size, ratio), QIcon.Mode.Disabled, state)
    return result
