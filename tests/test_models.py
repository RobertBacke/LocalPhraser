import json

import pytest

from localphraser.models import FILES, digest, verify_model


@pytest.mark.parametrize(
    "name, repo, vocabulary",
    [
        ("medium.en", "Systran/faster-whisper-medium.en", "vocabulary.txt"),
        ("distil-small.en", "Systran/faster-distil-whisper-small.en", "vocabulary.json"),
        ("distil-medium.en", "Systran/faster-distil-whisper-medium.en", "vocabulary.json"),
    ],
)
def test_catalog_install_uses_exact_repository_and_complete_files(
    tmp_path, monkeypatch, name, repo, vocabulary
):
    from unittest.mock import Mock

    from localphraser.models import install_model, model_files

    install = Mock(return_value=tmp_path / name)
    monkeypatch.setattr("localphraser.models.install_artifacts", install)
    assert install_model(name, tmp_path) == tmp_path / name
    install.assert_called_once_with(name, tmp_path, repo, model_files(name), job_id=None)
    folder = tmp_path / name
    folder.mkdir()
    hashes = {}
    assert model_files(name)[-1] == vocabulary
    for filename in model_files(name):
        path = folder / filename
        path.write_bytes(b"catalog fixture")
        hashes[filename] = digest(path)
    (folder / "localphraser-manifest.json").write_text(json.dumps({"sha256": hashes}))
    verify_model(folder)
    (folder / vocabulary).write_bytes(b"corrupted")
    with pytest.raises(ValueError):
        verify_model(folder)


def test_integrity_and_corruption(tmp_path):
    hashes = {}
    for name in FILES:
        path = tmp_path / name
        path.write_bytes(b"model fixture")
        hashes[name] = digest(path)
    (tmp_path / "localphraser-manifest.json").write_text(json.dumps({"sha256": hashes}))
    verify_model(tmp_path)
    (tmp_path / "model.bin").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="missing or damaged"):
        verify_model(tmp_path)


def test_missing_model_does_not_download(tmp_path, monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("Network attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    with pytest.raises(ValueError):
        verify_model(tmp_path)


def test_parakeet_catalog_entry_installs_through_the_verified_installer(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from localphraser.config import PARAKEET_MODEL
    from localphraser.models import install_model, model_files, staging_path

    files = (
        "config.json",
        "vocab.txt",
        "nemo128.onnx",
        "decoder_joint-model.int8.onnx",
        "encoder-model.int8.onnx",
    )
    assert model_files(PARAKEET_MODEL) == files
    install = Mock(return_value=tmp_path / PARAKEET_MODEL)
    monkeypatch.setattr("localphraser.models.install_artifacts", install)
    assert install_model(PARAKEET_MODEL, tmp_path) == tmp_path / PARAKEET_MODEL
    install.assert_called_once_with(
        PARAKEET_MODEL, tmp_path, "istupakov/parakeet-tdt-0.6b-v2-onnx", files, job_id=None
    )
    assert staging_path(PARAKEET_MODEL, tmp_path, "a" * 32).parent == tmp_path.resolve()

    folder = tmp_path / PARAKEET_MODEL
    folder.mkdir()
    hashes = {}
    for filename in files:
        (folder / filename).write_bytes(b"parakeet fixture")
        hashes[filename] = digest(folder / filename)
    (folder / "localphraser-manifest.json").write_text(json.dumps({"sha256": hashes}))
    verify_model(folder)
    (folder / "encoder-model.int8.onnx").unlink()
    (folder / "model.bin").write_bytes(b"parakeet fixture")
    with pytest.raises(ValueError):
        verify_model(folder)
