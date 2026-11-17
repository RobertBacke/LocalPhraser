"""Aurora glass: one theme, the stylesheet built from it, and the painted glass widgets."""

import ctypes
import random
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
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
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from localphraser.typography import interface_family

Rgba = tuple[int, int, int, int]
Glow = tuple[float, float, float, tuple[int, int, int], int]


@dataclass(frozen=True)
class Theme:
    """Every colour of one appearance. The stylesheet and all painters read from here."""

    dark: bool
    backdrop: tuple[str, str, str]  # Diagonal window gradient.
    glows: tuple[Glow, ...]  # Aurora light: x, y, radius (fractions of the size), rgb, alpha.
    window_alpha: int  # Painted opacity over desktop acrylic.
    rim: Rgba  # Window edge.
    rim_inner: Rgba
    text: str
    muted: str
    panel_tint: Rgba  # Laid under a panel so its contrast never depends on the aurora.
    panel: tuple[Rgba, Rgba]  # Diagonal glass fill.
    panel_border: Rgba
    panel_highlight: Rgba  # Top edge.
    hairline: Rgba  # Outer definition line (light theme).
    card: tuple[Rgba, Rgba]  # A panel nested in a panel: one step brighter.
    card_border: Rgba
    selected: tuple[Rgba, Rgba]  # Fill of the selected card.
    field: Rgba
    field_border: Rgba
    focus: str
    accent: tuple[str, str, str]  # Primary gradient, 135 degrees, white text.
    accent_pressed: tuple[str, str, str]
    glow: str  # Indicator colour: meters, markers, numbers, progress.
    violet: str  # Where glow-coloured gradients end.
    brand: tuple[str, str, str]  # Logo tint.
    button: Rgba
    button_hover: Rgba
    button_pressed: Rgba
    button_border: Rgba
    hover: Rgba  # Quiet hover fill for rows and glyph buttons.
    nav_selected: Rgba
    danger: str
    danger_border: Rgba
    danger_hover: Rgba
    close_hover: str
    menu: str  # Opaque popup surface.
    menu_border: Rgba
    scroll: Rgba
    scroll_hover: Rgba
    switch_off: Rgba
    switch_border: Rgba
    thumb: str
    chip: Rgba
    chip_border: Rgba
    progress: tuple[Rgba, Rgba]
    hud: tuple[Rgba, Rgba]  # The floating capsule: the same dark pill in both themes.
    hud_rim: tuple[str, str]


ACCENT = ("#4F46E5", "#7C3AED", "#C026D3")
ACCENT_PRESSED = ("#4338CA", "#6D28D9", "#A21CAF")
HUD: tuple[Rgba, Rgba] = ((16, 19, 44, 250), (7, 8, 22, 250))
HUD_RIM = ("#22D3EE", "#8B5CF6")

DARK = Theme(
    dark=True,
    backdrop=("#060913", "#0B1024", "#120B2A"),
    glows=(
        (0.08, 0.04, 0.62, (34, 211, 238), 76),
        (0.98, 0.30, 0.58, (139, 92, 246), 104),
        (0.52, 1.08, 0.56, (236, 72, 153), 54),
    ),
    window_alpha=238,
    rim=(255, 255, 255, 44),
    rim_inner=(0, 0, 0, 0),
    text="#F3F6FF",
    muted="#A7B3D1",
    panel_tint=(9, 13, 30, 158),
    panel=((255, 255, 255, 23), (255, 255, 255, 10)),
    panel_border=(255, 255, 255, 36),
    panel_highlight=(255, 255, 255, 71),
    hairline=(0, 0, 0, 0),
    card=((255, 255, 255, 18), (255, 255, 255, 8)),
    card_border=(255, 255, 255, 32),
    selected=((255, 255, 255, 40), (190, 180, 255, 22)),
    field=(8, 12, 28, 140),
    field_border=(255, 255, 255, 31),
    focus="#22D3EE",
    accent=ACCENT,
    accent_pressed=ACCENT_PRESSED,
    glow="#22D3EE",
    violet="#8B5CF6",
    brand=("#22D3EE", "#8B5CF6", "#EC4899"),
    button=(255, 255, 255, 20),
    button_hover=(255, 255, 255, 38),
    button_pressed=(255, 255, 255, 12),
    button_border=(255, 255, 255, 40),
    hover=(255, 255, 255, 18),
    nav_selected=(255, 255, 255, 30),
    danger="#FF9CAB",
    danger_border=(255, 156, 171, 90),
    danger_hover=(255, 107, 129, 36),
    close_hover="#E5484D",
    menu="#12172E",
    menu_border=(255, 255, 255, 40),
    scroll=(255, 255, 255, 56),
    scroll_hover=(255, 255, 255, 110),
    switch_off=(255, 255, 255, 34),
    switch_border=(255, 255, 255, 60),
    thumb="#F3F6FF",
    chip=(255, 255, 255, 20),
    chip_border=(255, 255, 255, 34),
    progress=((34, 211, 238, 115), (139, 92, 246, 140)),
    hud=HUD,
    hud_rim=HUD_RIM,
)

LIGHT = Theme(
    dark=False,
    backdrop=("#F4F7FF", "#E9EEFF", "#F3E9FF"),
    glows=(
        (0.06, 0.02, 0.62, (56, 189, 248), 120),
        (0.98, 0.26, 0.56, (139, 92, 246), 66),
        (0.50, 1.08, 0.58, (244, 114, 182), 80),
    ),
    window_alpha=236,
    rim=(30, 41, 90, 46),
    rim_inner=(255, 255, 255, 200),
    text="#0B1433",
    muted="#46527A",
    panel_tint=(0, 0, 0, 0),
    panel=((255, 255, 255, 184), (255, 255, 255, 133)),
    panel_border=(255, 255, 255, 235),
    panel_highlight=(255, 255, 255, 255),
    hairline=(30, 41, 90, 26),
    card=((255, 255, 255, 150), (255, 255, 255, 96)),
    card_border=(255, 255, 255, 240),
    selected=((255, 255, 255, 240), (240, 238, 255, 215)),
    field=(255, 255, 255, 217),
    field_border=(30, 41, 90, 41),
    focus="#4F46E5",
    accent=ACCENT,
    accent_pressed=ACCENT_PRESSED,
    glow="#0891B2",
    violet="#7C3AED",
    brand=ACCENT,
    button=(255, 255, 255, 166),
    button_hover=(255, 255, 255, 240),
    button_pressed=(228, 232, 255, 240),
    button_border=(30, 41, 90, 40),
    hover=(79, 70, 229, 22),
    nav_selected=(255, 255, 255, 210),
    danger="#A1112B",
    danger_border=(161, 17, 43, 90),
    danger_hover=(220, 38, 62, 26),
    close_hover="#E5484D",
    menu="#FBFCFF",
    menu_border=(30, 41, 90, 46),
    scroll=(30, 41, 90, 70),
    scroll_hover=(30, 41, 90, 130),
    switch_off=(30, 41, 90, 84),
    switch_border=(30, 41, 90, 30),
    thumb="#FFFFFF",
    chip=(79, 70, 229, 20),
    chip_border=(79, 70, 229, 48),
    progress=((8, 145, 178, 90), (124, 58, 237, 90)),
    hud=HUD,
    hud_rim=HUD_RIM,
)


def theme(dark: bool) -> Theme:
    return DARK if dark else LIGHT


def high_contrast() -> bool:
    hints = QApplication.styleHints()
    if hasattr(hints, "accessibility"):
        return hints.accessibility().contrastPreference() == Qt.ContrastPreference.HighContrast
    return False


def dark_surface() -> bool:
    # Stylesheets can retain a widget's old palette when the application theme changes.
    return QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128


def current_theme() -> Theme:
    return theme(dark_surface())


def rgba(value: Rgba) -> str:
    return f"rgba({value[0]},{value[1]},{value[2]},{value[3]})"


# State colours shared by the capsule, the sidebar status and the Home hero (light, dark).
TONES = {
    "recording": ((214, 40, 66), (255, 107, 129)),
    "busy": ((176, 98, 0), (251, 191, 36)),
    "ready": ((4, 135, 95), (52, 211, 153)),
}


def tone_color(tone: str, dark: bool | None = None) -> QColor:
    if high_contrast():
        return QApplication.palette().color(QPalette.ColorRole.WindowText)
    if dark is None:
        dark = dark_surface()
    if tone in TONES:
        return QColor(*TONES[tone][dark])
    return QColor(theme(dark).muted)


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


def rounded(area: QRectF, radius: float) -> QPainterPath:
    shape = QPainterPath()
    shape.addRoundedRect(area, radius, radius)
    return shape


def diagonal(area: QRectF, first: QColor, last: QColor, middle: QColor | None = None) -> QBrush:
    gradient = QLinearGradient(area.topLeft(), area.bottomRight())
    gradient.setColorAt(0, first)
    if middle is not None:
        gradient.setColorAt(0.5, middle)
    gradient.setColorAt(1, last)
    return QBrush(gradient)


def accent_brush(area: QRectF, tokens: Theme, pressed: bool = False) -> QBrush:
    first, middle, last = tokens.accent_pressed if pressed else tokens.accent
    return diagonal(area, QColor(first), QColor(last), QColor(middle))


def paint_backdrop(
    painter: QPainter, area: QRectF, tokens: Theme, translucent: bool, radius: float
) -> None:
    """The window surface: a deep or luminous gradient lit by soft aurora glows."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = rounded(area.adjusted(0.5, 0.5, -0.5, -0.5), radius)
    alpha = tokens.window_alpha if translucent else 255
    first, middle, last = (QColor(colour) for colour in tokens.backdrop)
    for colour in (first, middle, last):
        colour.setAlpha(alpha)
    painter.fillPath(shape, diagonal(area, first, last, middle))
    for x, y, scale, rgb, strength in tokens.glows:
        centre = QPointF(area.left() + area.width() * x, area.top() + area.height() * y)
        glow = QRadialGradient(centre, max(area.width(), area.height() * 1.2) * scale)
        glow.setColorAt(0, QColor(*rgb, strength))
        glow.setColorAt(0.5, QColor(*rgb, round(strength * 0.42)))
        glow.setColorAt(1, QColor(*rgb, 0))
        painter.fillPath(shape, glow)
    painter.fillPath(shape, QBrush(frost_texture()))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(*tokens.rim), 1))
    painter.drawPath(shape)
    if tokens.rim_inner[3]:
        painter.setPen(QPen(QColor(*tokens.rim_inner), 1))
        painter.drawPath(rounded(area.adjusted(1.5, 1.5, -1.5, -1.5), radius - 1))
    painter.restore()


def paint_panel(
    painter: QPainter,
    area: QRectF,
    tokens: Theme,
    radius: float,
    *,
    nested: bool = False,
    selected: bool = False,
) -> None:
    """A glass panel: translucent fill, bright rim and a top highlight."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    outline = area.adjusted(0.5, 0.5, -0.5, -0.5)
    shape = rounded(outline, radius)
    if not nested and tokens.panel_tint[3]:
        painter.fillPath(shape, QColor(*tokens.panel_tint))
    top, bottom = tokens.selected if selected else tokens.card if nested else tokens.panel
    painter.fillPath(shape, diagonal(area, QColor(*top), QColor(*bottom)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if selected:
        painter.setPen(QPen(accent_brush(area, tokens), 1.6))
        painter.drawPath(rounded(outline.adjusted(0.3, 0.3, -0.3, -0.3), radius))
        painter.restore()
        return
    border = QColor(*(tokens.card_border if nested else tokens.panel_border))
    faded = QColor(border)
    faded.setAlpha(round(border.alpha() * 0.55))
    edge = QLinearGradient(outline.topLeft(), outline.bottomLeft())
    edge.setColorAt(0, QColor(*tokens.panel_highlight))
    edge.setColorAt(min(0.5, (radius + 6) / max(1.0, outline.height())), border)
    edge.setColorAt(1, border if tokens.hairline[3] else faded)
    painter.setPen(QPen(QBrush(edge), 1))
    if tokens.hairline[3]:
        # A bright inner rim inside a faint dark line keeps light panels defined.
        painter.drawPath(rounded(outline.adjusted(1, 1, -1, -1), max(0.0, radius - 1)))
        painter.setPen(QPen(QColor(*tokens.hairline), 1))
    painter.drawPath(shape)
    painter.restore()


class GlassPanel(QFrame):
    """A painted glass panel; ``nested`` is the brighter card used inside another panel."""

    def __init__(self, name: str = "", *, nested: bool = False, radius: float | None = None):
        super().__init__()
        self.nested = nested
        self.radius = radius if radius is not None else (14.0 if nested else 18.0)
        if name:
            self.setObjectName(name)

    def paintEvent(self, event: Any) -> None:
        if high_contrast():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        paint_panel(painter, QRectF(self.rect()), current_theme(), self.radius, nested=self.nested)


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


def glyph_pen(color: QColor, width: float = 1.4) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def glyph_color(button: QWidget, close: bool) -> QColor:
    """Caption glyphs follow the text; the close glyph turns white on its red hover."""
    if close and button.underMouse() and button.isEnabled() and not high_contrast():
        return QColor("white")
    return button.palette().color(QPalette.ColorRole.ButtonText)


class CaptionButton(QPushButton):
    """Borderless caption glyphs drawn at logical-pixel sizes, with a hover fill."""

    def __init__(self, kind: str):
        super().__init__("")
        self.kind = kind
        self.setObjectName("captionButton")
        self.setProperty("closes", kind == "close")
        self.setFixedSize(42, 32)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(glyph_pen(glyph_color(self, self.kind == "close")))
        box = QRectF((self.width() - 11) / 2, (self.height() - 11) / 2, 11, 11)
        if self.kind == "minimize":
            painter.drawLine(
                QPointF(box.left(), box.center().y()), QPointF(box.right(), box.center().y())
            )
        elif self.kind == "close":
            painter.drawLine(box.topLeft(), box.bottomRight())
            painter.drawLine(box.topRight(), box.bottomLeft())
        elif self.window().isMaximized() or self.window().isFullScreen():
            x, y = box.left(), box.top()
            back = [(3, 3), (3, 0), (11, 0), (11, 8), (8, 8)]
            painter.drawPolyline([QPointF(x + dx, y + dy) for dx, dy in back])
            painter.drawRoundedRect(QRectF(x, y + 3, 8, 8), 1.5, 1.5)
        else:
            painter.drawRoundedRect(box, 2, 2)


class CloseGlyph(QToolButton):
    """The borderless close cross of the smaller glass windows."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("closeGlyph")
        self.setAccessibleName("Close window")
        self.setToolTip("Close window")
        self.setFixedSize(36, 30)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(glyph_pen(glyph_color(self, True)))
        box = QRectF((self.width() - 11) / 2, (self.height() - 11) / 2, 11, 11)
        painter.drawLine(box.topLeft(), box.bottomRight())
        painter.drawLine(box.topRight(), box.bottomLeft())


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
        color = QColor(current_theme().muted if self.isEnabled() else current_theme().muted)
        if not self.isEnabled():
            color.setAlpha(110)
        draw_chevron(painter, QPointF(self.width() - 19, self.height() / 2), False, color)


def draw_chevron(painter: QPainter, centre: QPointF, up: bool, color: QColor) -> None:
    painter.setPen(glyph_pen(color, 1.6))
    rise = -2.0 if up else 2.0
    x, y = centre.x(), centre.y()
    painter.drawLine(QPointF(x - 4, y - rise), QPointF(x, y + rise))
    painter.drawLine(QPointF(x, y + rise), QPointF(x + 4, y - rise))


class GlassSpinBox(QSpinBox):
    """A number field changed by typing, arrow keys or its buttons, never by scrolling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(38)
        # Style sheets do not pad a spin box's text; line it up with the other fields.
        line = self.lineEdit()
        if line is not None:
            line.setTextMargins(10, 0, 0, 0)

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
        text = QColor(current_theme().muted)
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
    """A check box painted as a switch: the thumb rests left when off, right when on."""

    def indicator_rect(self) -> QRect:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        return self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if high_contrast():
            return  # The native indicator is drawn by the system style.
        tokens = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        track = QRectF(self.indicator_rect()).adjusted(1, 1, -1, -1)
        radius = track.height() / 2
        if self.hasFocus():
            painter.setPen(QPen(QColor(tokens.focus), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track.adjusted(-3, -3, 3, 3), radius + 3, radius + 3)
        if self.isChecked():
            painter.setPen(QPen(QColor(255, 255, 255, 70), 1))
            painter.setBrush(accent_brush(track, tokens))
        else:
            off = QColor(*tokens.switch_off)
            if self.underMouse():
                off.setAlpha(min(255, off.alpha() + 30))
            painter.setPen(QPen(QColor(*tokens.switch_border), 1))
            painter.setBrush(off)
        painter.drawRoundedRect(track, radius, radius)
        size = track.height() - 6
        x = track.right() - size - 3 if self.isChecked() else track.left() + 3
        painter.setPen(QPen(QColor(11, 20, 51, 40), 1))
        painter.setBrush(QColor(tokens.thumb))
        painter.drawEllipse(QRectF(x, track.top() + 3, size, size))


class SegmentedBar(QTabBar):
    """A tab bar painted as one pill track with the selected segment filled."""

    def __init__(self) -> None:
        super().__init__()
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def tabSizeHint(self, index: int) -> QSize:
        if high_contrast():
            return super().tabSizeHint(index)
        return QSize(self.fontMetrics().horizontalAdvance(self.tabText(index)) + 34, 36)

    def minimumTabSizeHint(self, index: int) -> QSize:
        return self.tabSizeHint(index)

    def paintEvent(self, event: Any) -> None:
        if high_contrast():
            super().paintEvent(event)
            return
        tokens = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF()
        for index in range(self.count()):
            track = track.united(QRectF(self.tabRect(index)))
        track = track.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(*tokens.field_border), 1))
        painter.setBrush(QColor(*tokens.field))
        painter.drawRoundedRect(track, 12, 12)
        for index in range(self.count()):
            area = QRectF(self.tabRect(index)).adjusted(4, 4, -4, -4)
            current = index == self.currentIndex()
            font = self.font()
            if current:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(accent_brush(area, tokens))
                painter.drawRoundedRect(area, 8.5, 8.5)
                if self.hasFocus():
                    painter.setPen(QPen(QColor(tokens.focus), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(area.adjusted(-2, -2, 2, 2), 10.5, 10.5)
                font.setWeight(QFont.Weight.DemiBold)
                painter.setPen(QColor("white"))
            else:
                painter.setPen(QColor(tokens.text if self.isEnabled() else tokens.muted))
            painter.setFont(font)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, self.tabText(index))


class SegmentedTabs(QTabWidget):
    """A tab widget whose tabs are a segmented control; keys and roles are unchanged."""

    def __init__(self) -> None:
        super().__init__()
        self.setTabBar(SegmentedBar())
        self.setDocumentMode(True)


class StatusDot(QWidget):
    """A small painted state dot; the state is always also given as text beside it."""

    def __init__(self, parent: QWidget | None = None, *, dark: bool | None = None) -> None:
        super().__init__(parent)
        self.tone = "muted"
        self.dark = dark  # Fixed for the capsule, which is dark in both themes.
        self.setFixedSize(12, 12)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_tone(self, tone: str) -> None:
        if tone != self.tone:
            self.tone = tone
            self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        color = tone_color(self.tone, self.dark)
        area = QRectF(self.rect())
        if not high_contrast():
            halo = QColor(color)
            halo.setAlpha(60)
            painter.setBrush(halo)
            painter.drawEllipse(area)
        painter.setBrush(color)
        painter.drawEllipse(area.adjusted(2, 2, -2, -2))


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


def gradient_css(stops: tuple[str, ...], horizontal: bool = False) -> str:
    last = len(stops) - 1
    points = ",".join(f"stop:{index / last:g} {stop}" for index, stop in enumerate(stops))
    return f"qlineargradient(x1:0,y1:0,x2:1,y2:{0 if horizontal else 1},{points})"


def stylesheet(tokens: Theme) -> str:
    """The one stylesheet, built from the theme. Panels and switches paint themselves."""
    text, muted, focus = tokens.text, tokens.muted, tokens.focus
    field, field_border = rgba(tokens.field), rgba(tokens.field_border)
    accent = gradient_css(tokens.accent)
    pressed = gradient_css(tokens.accent_pressed)
    hover = rgba(tokens.hover)
    return (
        f"* {{ font-family: '{interface_family()}'; font-size: 10pt; }}"
        f"QDialog#glassDialog {{ color: {text}; }}"
        f"QLabel, QCheckBox, QGroupBox {{ color: {text}; background: transparent; }}"
        "QLabel#windowTitle { font-size: 13px; font-weight: 600; padding: 2px; }"
        f"QLabel#tagline {{ color: {muted}; font-size: 12px; }}"
        "QLabel#brand { font-size: 17px; font-weight: 700; }"
        "QLabel#pageTitle { font-size: 26px; font-weight: 700; }"
        f"QLabel#metricNumber {{ color: {tokens.glow}; font-size: 22px; font-weight: 700; }}"
        "QLabel[sectionTitle=true] { font-size: 15px; font-weight: 600; }"
        "QLabel#emptyTitle { font-size: 17px; font-weight: 600; }"
        f"QLabel[muted=true] {{ color: {muted}; }}"
        f"QLabel[hint=true] {{ color: {muted}; font-size: 9pt; }}"
        f"QLabel:disabled {{ color: {muted}; }}"
        "QWidget#glassBody, QScrollArea, QStackedWidget { background: transparent;"
        " border: none; }"
        "QSplitter::handle { background: transparent; }"
        # Lists and tables.
        f"QListWidget {{ color: {text}; background: {field}; border: 1px solid {field_border};"
        " border-radius: 12px; padding: 6px; outline: 0; }"
        "QListWidget#historyCards { background: transparent; border: none; padding: 0; }"
        # A transparent border keeps selected rows the same height as the others.
        "QListWidget::item { padding: 9px 10px; border-radius: 8px;"
        " border: 1px solid transparent; }"
        f"QListWidget::item:hover {{ background: {hover}; }}"
        f"QListWidget::item:selected {{ background: {rgba(tokens.nav_selected)};"
        f" color: {text}; border: 1px solid {tokens.focus}; }}"
        f"QTableWidget {{ color: {text}; background: transparent; border: none; outline: 0;"
        " selection-background-color: transparent; }"
        f"QHeaderView {{ background: transparent; }}"
        f"QHeaderView::section {{ color: {muted}; background: transparent; border: none;"
        f" border-bottom: 1px solid {field_border}; padding: 10px 12px; font-size: 9pt;"
        " font-weight: 600; }"
        "QTableCornerButton::section { background: transparent; border: none; }"
        # Fields.
        f"QLineEdit, QTextEdit, QComboBox, QSpinBox {{ color: {text}; background: {field};"
        f" border: 1px solid {field_border}; border-radius: 12px; padding: 7px 10px;"
        f" selection-background-color: {tokens.accent[0]}; selection-color: white; }}"
        "QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {"
        f" border: 2px solid {focus}; padding: 6px 9px; }}"
        "QComboBox, QComboBox:focus { padding-right: 34px; }"
        "QComboBox::drop-down { width: 30px; border: none; }"
        "QComboBox::down-arrow { image: none; }"
        "QSpinBox, QSpinBox:focus { padding-right: 34px; }"
        "QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border;"
        " width: 26px; border: none; background: transparent; border-radius: 6px; }"
        "QSpinBox::up-button { subcontrol-position: top right; margin: 4px 4px 0 0; }"
        "QSpinBox::down-button { subcontrol-position: bottom right; margin: 0 4px 4px 0; }"
        f"QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {hover}; }}"
        "QSpinBox::up-arrow, QSpinBox::down-arrow { image: none; width: 0; height: 0; }"
        "QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {"
        f" color: {muted}; background: transparent; }}"
        f"QComboBox QAbstractItemView {{ color: {text}; background: {tokens.menu};"
        f" border: 1px solid {rgba(tokens.menu_border)}; border-radius: 12px; padding: 6px;"
        f" outline: 0; selection-background-color: {tokens.accent[0]};"
        " selection-color: white; }"
        "QComboBox QAbstractItemView::item { min-height: 30px; padding: 4px 10px;"
        " border-radius: 8px; }"
        f"QComboBox QAbstractItemView::item:selected {{ background: {accent}; color: white; }}"
        # Switches paint themselves over a transparent indicator.
        "QCheckBox { spacing: 10px; outline: none; padding: 4px; }"
        "QCheckBox::indicator { width: 36px; height: 20px; border: none;"
        " background: transparent; image: none; }"
        # Scroll bars.
        "QScrollBar:vertical { background: transparent; width: 12px; margin: 4px 2px;"
        " border: none; }"
        "QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px 4px;"
        " border: none; }"
        f"QScrollBar::handle {{ background: {rgba(tokens.scroll)}; border-radius: 4px; }}"
        "QScrollBar::handle:hover, QScrollBar::handle:pressed {"
        f" background: {rgba(tokens.scroll_hover)}; }}"
        "QScrollBar::handle:vertical { min-height: 36px; }"
        "QScrollBar::handle:horizontal { min-width: 36px; }"
        "QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none;"
        " background: none; }"
        "QScrollBar::add-page, QScrollBar::sub-page { background: none; }"
        f"QProgressBar {{ color: {text}; background: {field}; border: 1px solid {field_border};"
        " border-radius: 9px; min-height: 22px; text-align: center; }"
        "QProgressBar::chunk { border-radius: 8px; background: "
        f"{gradient_css(tuple(rgba(stop) for stop in tokens.progress), horizontal=True)}; }}"
        f"QToolTip {{ color: {text}; background: {tokens.menu};"
        f" border: 1px solid {rgba(tokens.menu_border)}; padding: 6px 8px; }}"
        # Buttons: glass by default, the accent gradient for the one primary action.
        f"QPushButton, QToolButton {{ color: {text}; background: {rgba(tokens.button)};"
        f" border: 1px solid {rgba(tokens.button_border)}; border-radius: 12px;"
        " padding: 8px 14px; }"
        f"QPushButton:hover, QToolButton:hover {{ background: {rgba(tokens.button_hover)}; }}"
        f"QPushButton:pressed, QToolButton:pressed {{ background: {rgba(tokens.button_pressed)}; }}"
        f"QPushButton:focus, QToolButton:focus {{ border: 2px solid {focus};"
        " padding: 7px 13px; }"
        f"QPushButton:disabled {{ color: {muted}; background: transparent; }}"
        "QPushButton[primary=true], QPushButton:checked {"
        f" background: {accent}; color: white; border: 1px solid rgba(255,255,255,70);"
        " font-weight: 600; }"
        "QPushButton[primary=true]:hover, QPushButton:checked:hover {"
        f" background: {accent}; border: 1px solid rgba(255,255,255,190); }}"
        f"QPushButton[primary=true]:pressed {{ background: {pressed}; }}"
        f"QPushButton[primary=true]:focus, QPushButton:checked:focus {{"
        f" border: 2px solid {focus}; }}"
        f"QPushButton[primary=true]:disabled {{ color: {muted};"
        f" background: {rgba(tokens.button)}; border: 1px solid {rgba(tokens.button_border)}; }}"
        # Destructive actions stay quiet: red text and border, never a filled red.
        f"QPushButton[danger=true] {{ color: {tokens.danger}; background: transparent;"
        f" border: 1px solid {rgba(tokens.danger_border)}; }}"
        f"QPushButton[danger=true]:hover {{ background: {rgba(tokens.danger_hover)}; }}"
        f"QPushButton[danger=true]:focus {{ border: 2px solid {focus}; }}"
        f"QPushButton[danger=true]:disabled {{ color: {muted};"
        f" border: 1px solid {rgba(tokens.button_border)}; }}"
        # Sidebar navigation reads as a list of places, not as buttons.
        f"QPushButton[nav=true] {{ color: {muted}; background: transparent;"
        " border: 1px solid transparent; text-align: left; padding: 9px 12px; }"
        f"QPushButton[nav=true]:hover {{ color: {text}; background: {hover}; }}"
        f"QPushButton[nav=true]:checked {{ color: {text};"
        f" background: {rgba(tokens.nav_selected)};"
        f" border: 1px solid {rgba(tokens.button_border)}; font-weight: 600; }}"
        f"QPushButton[nav=true]:focus {{ border: 2px solid {focus}; padding: 8px 11px; }}"
        # Caption glyphs: no box, a hover fill, red for close.
        "QPushButton#captionButton, QToolButton#closeGlyph { background: transparent;"
        " border: none; border-radius: 8px; padding: 0; }"
        f"QPushButton#captionButton:hover, QToolButton#closeGlyph:hover {{ background: {hover}; }}"
        "QPushButton#captionButton[closes=true]:hover, QToolButton#closeGlyph:hover {"
        f" background: {tokens.close_hover}; }}"
        f"QPushButton#captionButton:focus, QToolButton#closeGlyph:focus {{"
        f" border: 2px solid {focus}; padding: 0; }}"
        # A group box is a nested card with its title inside.
        f"QGroupBox {{ background: {rgba(tokens.card[1])};"
        f" border: 1px solid {rgba(tokens.card_border)}; border-radius: 14px;"
        " margin-top: 0; padding: 42px 14px 14px 14px; }"
        "QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left;"
        " left: 14px; top: 13px; padding: 0; }"
        "QTabWidget::pane { border: none; }"
        "QTabWidget::tab-bar { left: 0; }"
        f"QMessageBox, QFileDialog {{ background: {tokens.menu}; }}"
    )


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
        close = CloseGlyph()
        close.clicked.connect(self.reject)
        row.addWidget(handle, 1)
        row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def refresh_surface(self) -> None:
        mode = dark_surface(), high_contrast()
        if self.surface_mode == mode:
            return  # Stylesheet palette notifications must not reapply the same sheet.
        self.surface_mode = mode
        self.setStyleSheet("" if mode[1] else stylesheet(theme(mode[0])))
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
        if not self.isWindow():
            return
        painter = QPainter(self)
        if high_contrast():
            painter.fillRect(self.rect(), self.palette().window())
            return
        paint_backdrop(painter, QRectF(self.rect()), current_theme(), self.native_glass, 22)


class GlassCapsule(QWidget):
    """A dark, plain-text HUD pill: a painted state dot, a short status and the words."""

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
        self.dot = StatusDot(dark=True)
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
            color, muted = DARK.text, DARK.muted  # The capsule is dark in both themes.
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(24.0, area.height() / 2)
        if high_contrast():
            painter.setPen(QPen(self.palette().color(QPalette.ColorRole.WindowText), 1))
            painter.setBrush(self.palette().window())
            painter.drawRoundedRect(area, radius, radius)
            return
        top, bottom = DARK.hud
        fill = QLinearGradient(area.topLeft(), area.bottomLeft())
        fill.setColorAt(0, QColor(*top))
        fill.setColorAt(1, QColor(*bottom))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(area, radius, radius)
        # A faint inner top highlight under a cyan-to-violet rim.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        shine = QLinearGradient(area.topLeft(), area.bottomLeft())
        shine.setColorAt(0, QColor(255, 255, 255, 46))
        shine.setColorAt(0.5, QColor(255, 255, 255, 0))
        painter.setPen(QPen(QBrush(shine), 1))
        painter.drawRoundedRect(area.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        rim = QLinearGradient(area.topLeft(), area.topRight())
        rim.setColorAt(0, QColor(DARK.hud_rim[0]))
        rim.setColorAt(1, QColor(DARK.hud_rim[1]))
        painter.setPen(QPen(QBrush(rim), 1))
        painter.drawRoundedRect(area, radius, radius)
