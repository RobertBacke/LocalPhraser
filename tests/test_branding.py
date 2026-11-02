import struct
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from localphraser.branding import app_icon, dark_taskbar, logo_pixmap


def test_mark_has_transparent_corners_and_native_sizes(app):
    icon = app_icon()
    assert {s.width() for s in icon.availableSizes()} == {16, 20, 24, 32, 48, 64, 128, 256}
    for size in (16, 32, 256):
        image = logo_pixmap(size).toImage()
        assert image.pixelColor(0, 0).alpha() == 0
        assert max(image.pixelColor(x, y).alpha() for y in range(size) for x in range(size)) >= 240
    assert logo_pixmap(64).toImage() != logo_pixmap(64, True).toImage()


def test_transparent_mark_fills_icon_width_and_has_light_variant(app):
    from PySide6.QtGui import QImage

    black = logo_pixmap(256).toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    white = logo_pixmap(256, light=True).toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    data = np.frombuffer(black.bits(), dtype=np.uint8).reshape(256, 256, 4)
    light = np.frombuffer(white.bits(), dtype=np.uint8).reshape(256, 256, 4)
    _, columns = np.nonzero(data[:, :, 3] > 128)
    assert 0.88 <= (columns.max() - columns.min() + 1) / 256 <= 0.92
    assert data[25, 128, 3] == 0  # The former tile is transparent above the symbol.
    assert data[:, :, :3][data[:, :, 3] > 0].max() == 0
    assert light[:, :, :3][light[:, :, 3] > 0].min() == 255
    assert np.array_equal(data[:, :, 3], light[:, :, 3])


@pytest.mark.parametrize("setting, expected", [(0, True), (1, False), (None, False)])
def test_taskbar_variant_uses_windows_system_theme_and_safe_fallback(
    monkeypatch, setting, expected
):
    query = Mock(return_value=(setting, 4))
    if setting is None:
        query.side_effect = OSError("Theme unavailable")
    registry = SimpleNamespace(
        HKEY_CURRENT_USER=0, OpenKey=Mock(return_value=nullcontext(None)), QueryValueEx=query
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr("localphraser.branding.sys.platform", "win32")
    assert dark_taskbar() is expected
    query.assert_called_once_with(None, "SystemUsesLightTheme")


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
        assert not image.isNull() and image.width() == size and image.height() == size
        # Compare premultiplied colors: PNG round-trips/SIMD scaling can round by 1-2 levels.
        actual = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        expected = (
            logo_pixmap(size).toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        )
        difference = np.abs(
            np.frombuffer(actual.bits(), dtype=np.uint8).astype(np.int16)
            - np.frombuffer(expected.bits(), dtype=np.uint8).astype(np.int16)
        )
        assert difference.max() <= 2
