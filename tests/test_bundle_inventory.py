import base64
import hashlib
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.bundle_inventory import collect_notices, inventory, write_inventory


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "build"
    internal = root / "_internal"
    internal.mkdir(parents=True)
    (root / "LocalPhraser.exe").write_bytes(b"owned executable fixture")
    (internal / "native.dll").write_bytes(b"owned native fixture")
    metadata = internal / "example-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Name: Example\nVersion: 1.0\nLicense-Expression: MIT\nLicense-File: LICENSE.txt\n",
        encoding="utf-8",
    )
    (metadata / "licenses").mkdir()
    (metadata / "licenses/LICENSE.txt").write_text("fixture license", encoding="utf-8")
    return root


def test_inventory_is_offline_repeatable_and_records_actual_binary_hashes(bundle, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Inventory attempted networking")

    monkeypatch.setattr(socket.socket, "connect", deny)
    first = write_inventory(bundle)
    second = write_inventory(bundle)
    assert first == second
    assert first["packages"][0]["version"] == "1.0"
    native = next(item for item in first["native_files"] if item["path"].endswith("native.dll"))
    assert native["sha256"] == hashlib.sha256(b"owned native fixture").hexdigest()
    assert not first["release_approved"]
    assert all(not Path(item["path"]).is_absolute() for item in first["files"])
    (bundle / "_internal/native.dll").write_bytes(b"updated binary")
    assert inventory(bundle)["native_files"] != first["native_files"]


def test_missing_license_is_recorded_without_inventing_terms(bundle):
    (bundle / "_internal/example-1.0.dist-info/licenses/LICENSE.txt").unlink()
    result = inventory(bundle)
    assert any("declared license file absent" in finding for finding in result["review_findings"])


def test_native_attribution_requires_matching_record_hash_not_filename(bundle):
    metadata = bundle / "_internal/example-1.0.dist-info"
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(b"owned native fixture").digest())
        .decode()
        .rstrip("=")
    )
    (metadata / "RECORD").write_text(f"example/native.dll,sha256={digest},20\n")
    result = inventory(bundle)
    assert result["native_provenance"]["matched_files"] == 1
    matched = next(item for item in result["native_files"] if item["wheel_records"])
    assert matched["wheel_records"][0]["distribution"] == "Example"
    (bundle / "_internal/native.dll").write_bytes(b"other bytes with same filename")
    assert inventory(bundle)["native_provenance"]["matched_files"] == 0


@pytest.mark.parametrize(
    "filename",
    [
        "private.wav",
        "model.bin",
        "secret.gguf",
        "config.json",
        ".env",
        "history.sqlite3",
        "history.sqlite3-journal",
        "History.SQLITE3",
        "profile.json.history.sqlite3",
    ],
)
def test_inventory_refuses_local_data_before_hashing(bundle, filename):
    (bundle / filename).write_bytes(b"must not inventory")
    with pytest.raises(ValueError, match="local settings"):
        inventory(bundle)


def test_declared_license_cannot_escape_metadata(bundle):
    metadata = bundle / "_internal/example-1.0.dist-info/METADATA"
    metadata.write_text("Name: Example\nVersion: 1.0\nLicense-File: ../../outside.txt\n")
    with pytest.raises(ValueError, match="Unsafe declared license"):
        inventory(bundle)


def test_external_wheel_notices_are_copied_from_record_without_other_files(tmp_path):
    metadata = tmp_path / "example-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: Example\nVersion: 1.0\n")
    package = tmp_path / "example"
    package.mkdir()
    notice = package / "ThirdPartyNotices.txt"
    notice.write_text("fixture notices")
    (package / "private.txt").write_text("must not copy")
    (metadata / "RECORD").write_text("example/ThirdPartyNotices.txt,,\nexample/private.txt,,\n")
    assert collect_notices([metadata]) == [(str(notice.resolve()), "third_party/example/example")]
    (metadata / "RECORD").write_text("../outside/LICENSE,,\n")
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "LICENSE").write_text("external fixture")
    with pytest.raises(ValueError, match="escapes"):
        collect_notices([metadata])


def test_supplemental_notices_must_match_source_hash(bundle):
    supplemental = bundle / "_internal/third_party/supplemental"
    supplemental.mkdir(parents=True)
    (supplemental / "LICENSE").write_bytes(b"fixture license")
    source = {
        "file": "LICENSE",
        "url": "https://example.invalid/license",
        "component": "fixture",
        "sha256": hashlib.sha256(b"fixture license").hexdigest(),
    }
    index = supplemental / "SOURCES.json"
    index.write_text(json.dumps({"sources": [source]}))
    assert inventory(bundle)["supplemental_sources"][0]["component"] == "fixture"
    (supplemental / "LICENSE").write_bytes(b"modified notice")
    with pytest.raises(ValueError, match="hash"):
        inventory(bundle)
    source["file"] = "../LICENSE"
    index.write_text(json.dumps({"sources": [source]}))
    with pytest.raises(ValueError, match="Unsafe supplemental"):
        inventory(bundle)


def test_ffmpeg_observations_remain_review_evidence(bundle, monkeypatch):
    monkeypatch.setattr(
        "scripts.bundle_inventory.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=json.dumps(
                [{"path": "avcodec.dll", "license": "LGPL", "configuration": "--enable-libx264"}]
            )
        ),
    )
    result = inventory(bundle, probe=True)
    assert result["ffmpeg"][0]["license"] == "LGPL"
    assert any("x264/x265" in finding for finding in result["review_findings"])
    assert not result["release_approved"]
