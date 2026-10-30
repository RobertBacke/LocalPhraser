import struct
from pathlib import Path

from localphraser.branding import app_icon, logo_pixmap


def test_mark_has_transparent_corners_and_native_sizes(app):
    icon = app_icon()
    assert {s.width() for s in icon.availableSizes()} == {16, 20, 24, 32, 48, 64, 128, 256}
    for size in (16, 32, 256):
        image = logo_pixmap(size).toImage()
        assert image.pixelColor(0, 0).alpha() == 0
        assert image.pixelColor(size // 2, size // 2).alpha() == 255
    assert logo_pixmap(64).toImage() != logo_pixmap(64, True).toImage()


def test_windows_icon_contains_valid_images_matching_app_mark(app):
    from PySide6.QtGui import QImage

    data = (Path(__file__).resolve().parents[1] / "packaging/localphraser.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, 7)
    for index in range(count):
        width, height, _, _, planes, depth, length, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * index
        )
        size = width or 256
        assert (height or 256) == size and planes == 1 and depth == 32
        image = QImage.fromData(data[offset : offset + length], "PNG")
        assert image == logo_pixmap(size).toImage().convertToFormat(QImage.Format.Format_ARGB32)
