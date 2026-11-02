import hashlib
from pathlib import Path

from PySide6.QtGui import QFontInfo

from localphraser.appearance import GlassDialog
from localphraser.typography import interface_family


def test_bundled_font_loads_with_its_license_and_is_used_by_ui(app):
    assets = Path(__file__).resolve().parents[1] / "src/localphraser/assets/fonts"
    assert (
        hashlib.sha256((assets / "SpaceGrotesk.ttf").read_bytes()).hexdigest()
        == "acad6de1fc93436f5c0f1f4137751ef04f1aea3063e7036535970ffcfbd79f72"
    )
    assert "SIL OPEN FONT LICENSE" in (assets / "OFL.txt").read_text()
    assert interface_family() == "Space Grotesk"
    window = GlassDialog()
    assert QFontInfo(window.font()).family() == "Space Grotesk"
    window.deleteLater()
