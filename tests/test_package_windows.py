import hashlib
from zipfile import ZipFile

import pytest

from scripts.bundle_inventory import write_inventory
from scripts.package_windows import package


@pytest.fixture
def build(tmp_path):
    folder = tmp_path / "build"
    internal = folder / "_internal"
    internal.mkdir(parents=True)
    header = bytearray(128)
    header[:2] = b"MZ"
    header[0x3C:0x40] = (0x40).to_bytes(4, "little")
    header[0x40:0x46] = b"PE\x00\x00\x64\x86"
    (folder / "LocalPhraser.exe").write_bytes(header)
    (internal / "LICENSE").write_text("fixture license")
    (internal / "THIRD_PARTY_NOTICES.md").write_text("fixture notices")
    (internal / "replaceable.dll").write_bytes(b"native library fixture")
    write_inventory(folder)
    return folder


def test_portable_archive_preserves_runtime_and_checksums(build, tmp_path):
    output = package(build, tmp_path / "artifacts" / "preview.zip")
    with ZipFile(output) as archive:
        assert archive.read("LocalPhraser/_internal/replaceable.dll") == b"native library fixture"
        assert "LocalPhraser/START_HERE.txt" in archive.namelist()
        assert "LocalPhraser/BUNDLE_INVENTORY.json" in archive.namelist()
        assert archive.testzip() is None
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert output.with_suffix(".zip.sha256").read_text().startswith(digest + "  preview.zip")


@pytest.mark.parametrize(
    "filename", ["model.bin", "private.wav", "model.gguf", ".env", ".ENV.local", "config.json"]
)
def test_weights_audio_and_local_settings_are_refused(build, tmp_path, filename):
    (build / filename).write_bytes(b"must not ship")
    output = tmp_path / "preview.zip"
    with pytest.raises(ValueError):
        package(build, output)
    assert not output.exists()


def test_output_cannot_be_inside_build(build):
    with pytest.raises(ValueError):
        package(build, build / "preview.zip")


def test_modified_runtime_requires_new_inventory(build, tmp_path):
    (build / "_internal/replaceable.dll").write_bytes(b"changed library")
    with pytest.raises(ValueError, match="changed after inventory"):
        package(build, tmp_path / "preview.zip")


def test_missing_inventory_is_refused(build, tmp_path):
    (build / "BUNDLE_INVENTORY.json").unlink()
    with pytest.raises(ValueError, match="inventory before packaging"):
        package(build, tmp_path / "preview.zip")
