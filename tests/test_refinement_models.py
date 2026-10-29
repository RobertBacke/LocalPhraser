import hashlib
from types import SimpleNamespace

import pytest

from localphraser.refinement_models import artifacts, install_refiner, verify_refiner


@pytest.mark.parametrize("valid_hash", [True, False])
def test_pinned_download_integrity_and_cleanup(tmp_path, monkeypatch, valid_hash):
    import huggingface_hub

    name = "qwen2.5-0.5b"
    repo, files = artifacts(name)
    data = b"synthetic model fixture"
    checksum = hashlib.sha256(data).hexdigest()
    siblings = [
        SimpleNamespace(
            rfilename=filename, lfs=SimpleNamespace(sha256=checksum if valid_hash else "0" * 64)
        )
        for filename in files
    ]
    monkeypatch.setattr(
        huggingface_hub.HfApi,
        "model_info",
        lambda *a, **kw: SimpleNamespace(sha="fixed-revision", siblings=siblings),
    )
    downloaded = []

    def download(repository, filename, *, revision, local_dir):
        assert repository == repo and revision == "fixed-revision"
        downloaded.append(filename)
        path = local_dir / filename
        path.write_bytes(data)
        return str(path)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    if valid_hash:
        install_refiner(name, tmp_path)
        model = verify_refiner(name, tmp_path)
        assert model.name == files[0]
        assert downloaded == list(files)
        model.write_bytes(b"changed")
        with pytest.raises(ValueError):
            verify_refiner(name, tmp_path)
    else:
        with pytest.raises(ValueError):
            install_refiner(name, tmp_path)
        assert not (tmp_path / name).exists()
    assert not list(tmp_path.glob(".*.installing"))


def test_missing_refiner_is_only_a_local_check(tmp_path, monkeypatch):
    import socket

    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("Network attempted"))
    with pytest.raises(ValueError):
        verify_refiner("qwen2.5-0.5b", tmp_path)
