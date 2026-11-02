"""Bundled geometric UI font, with Windows' default as a rendering fallback."""

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QFontDatabase


@lru_cache(maxsize=1)
def interface_family() -> str:
    font = Path(__file__).with_name("assets") / "fonts" / "SpaceGrotesk.ttf"
    identifier = QFontDatabase.addApplicationFont(str(font))
    families = QFontDatabase.applicationFontFamilies(identifier)
    return families[0] if families else "Segoe UI"
