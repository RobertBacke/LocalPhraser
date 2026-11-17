import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon

from localphraser import icons

REQUIRED = (
    "home",
    "settings",
    "vocabulary",
    "analytics",
    "transcript",
    "microphone",
    "stop",
    "power",
    "copy",
    "trash",
    "download",
    "check",
    "close",
)


def painted(image):
    return sum(
        image.pixelColor(x, y).alpha() > 40
        for x in range(image.width())
        for y in range(image.height())
    )


def near(colour, expected):
    """Equal within the rounding of premultiplied pixels."""
    wanted = QColor(expected)
    return all(
        abs(a - b) <= 2
        for a, b in (
            (colour.red(), wanted.red()),
            (colour.green(), wanted.green()),
            (colour.blue(), wanted.blue()),
        )
    )


def test_every_required_icon_exists():
    assert set(REQUIRED) <= set(icons.NAMES)
    assert len(set(icons.NAMES)) == len(icons.NAMES)


@pytest.mark.parametrize("ratio", [1.0, 2.0])
@pytest.mark.parametrize("name", icons.NAMES)
def test_every_icon_renders_at_both_pixel_ratios(app, name, ratio):
    pixmap = icons.pixmap(name, QColor("#22D3EE"), 20, ratio)
    assert pixmap.devicePixelRatio() == ratio
    assert pixmap.size() == QSize(round(20 * ratio), round(20 * ratio))
    image = pixmap.toImage()
    count = painted(image)
    # Drawn, but as line work: neither empty nor a filled block.
    assert 12 * ratio <= count <= image.width() * image.height() * 0.6, count
    assert image.pixelColor(0, 0).alpha() == 0
    solid = [
        image.pixelColor(x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    ]
    assert all(near(colour, "#22D3EE") for colour in solid)  # Only the requested colour.


def test_icons_are_distinct_drawings(app):
    images = {name: icons.pixmap(name, QColor("white"), 20, 2.0).toImage() for name in icons.NAMES}
    names = list(images)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            assert images[first] != images[second], (first, second)


def test_unknown_icon_name_is_an_error(app):
    with pytest.raises(KeyError):
        icons.pixmap("no-such-icon", QColor("white"))


def test_icon_has_distinct_off_on_and_disabled_colours(app):
    icon = icons.icon("home", QColor("#A7B3D1"), on=QColor("#22D3EE"), disabled=QColor("#55607A"))
    size = QSize(20, 20)

    def colour(mode, state):
        image = icon.pixmap(size, 1.0, mode, state).toImage()
        return next(
            image.pixelColor(x, y)
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() == 255
        )

    assert near(colour(QIcon.Mode.Normal, QIcon.State.Off), "#A7B3D1")
    assert near(colour(QIcon.Mode.Normal, QIcon.State.On), "#22D3EE")
    assert near(colour(QIcon.Mode.Active, QIcon.State.Off), "#A7B3D1")
    assert near(colour(QIcon.Mode.Disabled, QIcon.State.Off), "#55607A")
    # A 2x screen gets a pixmap drawn at 2x, not an upscaled 1x one.
    assert icon.pixmap(size, 2.0).size() == QSize(40, 40)
