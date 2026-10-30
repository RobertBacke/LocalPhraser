"""Regenerate the multi-resolution Windows icon from the shared application logo."""

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from localphraser.branding import logo_pixmap


def main() -> None:
    app = QApplication.instance() or QApplication([])
    images = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert logo_pixmap(size).save(buffer, "PNG")
        images.append((size, bytes(buffer.data())))
    offset = 6 + 16 * len(images)
    data = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, png in images:
        data.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
        offset += len(png)
    for _, png in images:
        data.extend(png)
    target = Path(__file__).resolve().parents[1] / "packaging" / "localphraser.ico"
    target.write_bytes(data)
    assert len(data) == offset
    assert app is not None
    print(target)


if __name__ == "__main__":
    main()
