import json

import pytest

from localphraser.models import FILES, digest, verify_model


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
