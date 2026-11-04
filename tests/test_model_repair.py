import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from localphraser.models import FILES, digest, install_model, verify_model


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    payloads = {name: ("verified replacement " + name).encode() for name in FILES}
    api = Mock()
    api.model_info.return_value = SimpleNamespace(
        sha="fixed-revision",
        siblings=[
            SimpleNamespace(
                rfilename=name,
                size=len(data),
                lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()),
            )
            for name, data in payloads.items()
        ],
    )

    def download(repo, name, *, revision, local_dir):
        assert revision == "fixed-revision"
        path = Path(local_dir) / name
        path.write_bytes(payloads[name])
        return str(path)

    fetch = Mock(side_effect=download)
    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(HfApi=lambda: api, hf_hub_download=fetch)
    )
    return tmp_path, payloads, api, fetch


def test_install_reports_aggregate_bytes_before_verified_publication(catalog, capsys):
    from localphraser.install_progress import PREFIX

    root, payloads, _, _ = catalog
    install_model("tiny.en", root)
    lines = capsys.readouterr().out.splitlines()
    reports = [json.loads(line[len(PREFIX) :]) for line in lines if line.startswith(PREFIX)]
    expected = sum(len(data) for data in payloads.values())
    assert reports[0] == {"completed": 0, "total": expected}
    assert reports[-1] == {"completed": expected, "total": expected}
    assert all(report["total"] == expected for report in reports)
    assert next(i for i, line in enumerate(lines) if "Verification complete" in line) > max(
        i for i, line in enumerate(lines) if line.startswith(PREFIX)
    )
    verify_model(root / "tiny.en")


def damaged_model(root, name="tiny.en", files=FILES):
    folder = root / name
    folder.mkdir()
    checksums = {}
    for name in files:
        path = folder / name
        path.write_bytes(b"original bytes")
        checksums[name] = digest(path)
    (folder / "localphraser-manifest.json").write_text(json.dumps({"sha256": checksums}))
    weight = next(name for name in files if name.endswith((".bin", ".gguf")))
    (folder / weight).write_bytes(b"damaged original")
    (folder / "user-note.txt").write_text("preserve extra files")
    return folder


def test_damaged_install_is_repaired_only_after_replacement_is_verified(catalog):
    root, payloads, _, fetch = catalog
    original = damaged_model(root)
    download = fetch.side_effect

    def checked_download(*args, **kwargs):
        assert (original / "model.bin").read_bytes() == b"damaged original"
        return download(*args, **kwargs)

    fetch.side_effect = checked_download
    installed = install_model("tiny.en", root, job_id="a" * 32)
    verify_model(installed)
    assert (installed / "model.bin").read_bytes() == payloads["model.bin"]
    backups = list(root.glob(".tiny.en.*.damaged"))
    assert len(backups) == 1
    assert (backups[0] / "model.bin").read_bytes() == b"damaged original"
    assert (backups[0] / "user-note.txt").read_text() == "preserve extra files"


@pytest.mark.parametrize("failure", [OSError, TimeoutError, KeyboardInterrupt])
def test_failed_or_interrupted_download_preserves_original(catalog, failure):
    root, _, _, fetch = catalog
    original = damaged_model(root)
    fetch.side_effect = failure("download stopped")
    with pytest.raises(failure):
        install_model("tiny.en", root, job_id="a" * 32)
    assert (original / "model.bin").read_bytes() == b"damaged original"
    assert (original / "user-note.txt").read_text() == "preserve extra files"
    assert not list(root.glob("*.installing")) and not list(root.glob("*.damaged"))


def test_failed_hash_check_never_replaces_existing_model(catalog):
    root, _, _, fetch = catalog
    original = damaged_model(root)
    download = fetch.side_effect

    def wrong_bytes(*args, **kwargs):
        path = Path(download(*args, **kwargs))
        if path.name == "model.bin":
            path.write_bytes(b"bad replacement")
        return path

    fetch.side_effect = wrong_bytes
    with pytest.raises(ValueError, match="hash"):
        install_model("tiny.en", root, job_id="a" * 32)
    assert (original / "model.bin").read_bytes() == b"damaged original"
    assert not list(root.glob("*.damaged"))


def test_publish_failure_restores_original_directory(catalog, monkeypatch):
    root, _, _, _ = catalog
    original = damaged_model(root)
    rename = Path.rename

    def fail_promotion(path, target):
        if path.name.endswith(".installing"):
            raise PermissionError("Replacement is locked")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_promotion)
    with pytest.raises(PermissionError):
        install_model("tiny.en", root, job_id="a" * 32)
    assert (original / "model.bin").read_bytes() == b"damaged original"
    assert (original / "user-note.txt").read_text() == "preserve extra files"
    assert not list(root.glob("*.damaged")) and not list(root.glob("*.installing"))


def test_valid_install_is_unchanged_and_needs_no_network(catalog):
    root, _, api, fetch = catalog
    original = damaged_model(root)
    (original / "model.bin").write_bytes(b"original bytes")
    assert install_model("tiny.en", root) == original
    api.model_info.assert_not_called()
    fetch.assert_not_called()
    assert not list(root.glob("*.damaged"))


def test_backup_collision_does_not_overwrite_either_directory(catalog):
    root, _, _, _ = catalog
    original = damaged_model(root)
    backup = root / (".tiny.en." + "a" * 32 + ".damaged")
    backup.mkdir()
    (backup / "preserve.txt").write_text("other backup")
    with pytest.raises(ValueError, match="backup already exists"):
        install_model("tiny.en", root, job_id="a" * 32)
    assert (backup / "preserve.txt").read_text() == "other backup"
    assert (original / "model.bin").read_bytes() == b"damaged original"


def test_linked_destination_is_refused_without_download(catalog, monkeypatch):
    root, _, api, fetch = catalog
    monkeypatch.setattr(Path, "is_junction", lambda path: path == root / "tiny.en")
    with pytest.raises(ValueError, match="linked"):
        install_model("tiny.en", root)
    api.model_info.assert_not_called()
    fetch.assert_not_called()


def test_polishing_model_repair_preserves_damaged_weights(catalog):
    from localphraser.refinement_models import artifacts, install_refiner, verify_refiner

    root, payloads, api, _ = catalog
    name = "qwen2.5-0.5b"
    _, files = artifacts(name)
    payloads.clear()
    payloads.update({filename: ("replacement " + filename).encode() for filename in files})
    api.model_info.return_value.siblings = [
        SimpleNamespace(rfilename=f, lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()))
        for f, data in payloads.items()
    ]
    damaged_model(root, name, files)
    install_refiner(name, root, job_id="b" * 32)
    assert verify_refiner(name, root).read_bytes() == payloads[files[0]]
    backup = next(root.glob(f".{name}.*.damaged"))
    assert (backup / files[0]).read_bytes() == b"damaged original"


def test_file_at_model_directory_is_not_moved(catalog):
    root, _, api, _ = catalog
    original = root / "tiny.en"
    original.write_text("not a model directory")
    with pytest.raises(ValueError, match="not a directory"):
        install_model("tiny.en", root)
    assert original.read_text() == "not a model directory"
    api.model_info.assert_not_called()
