import pytest
from filelock import FileLock, Timeout

from localphraser.models import cleanup_install, install_model, staging_path


def owned_stage(root, job_id):
    stage = staging_path("tiny.en", root, job_id)
    stage.mkdir(parents=True)
    (stage / ".localphraser-job").write_text(job_id, encoding="ascii")
    (stage / "partial.bin").write_bytes(b"partial model")
    return stage


def test_cleanup_only_removes_one_owned_job(tmp_path):
    first = owned_stage(tmp_path, "a" * 32)
    other = owned_stage(tmp_path, "b" * 32)
    installed = tmp_path / "tiny.en"
    installed.mkdir()
    preserved = installed / "model.bin"
    preserved.write_bytes(b"installed model")
    cleanup_install("tiny.en", tmp_path, "a" * 32)
    assert not first.exists()
    assert other.exists()
    assert preserved.read_bytes() == b"installed model"
    cleanup_install("tiny.en", tmp_path, "a" * 32)  # Idempotent.


@pytest.mark.parametrize("job_id", ["", "../outside", "g" * 32, "a" * 33])
def test_invalid_job_identity_is_refused(tmp_path, job_id):
    with pytest.raises(ValueError):
        cleanup_install("tiny.en", tmp_path, job_id)


def test_unowned_partial_directory_is_not_deleted(tmp_path):
    stage = staging_path("tiny.en", tmp_path, "a" * 32)
    stage.mkdir()
    preserved = stage / "user.txt"
    preserved.write_text("unowned")
    with pytest.raises(OSError):
        cleanup_install("tiny.en", tmp_path, "a" * 32)
    assert preserved.read_text() == "unowned"


def test_second_installer_cannot_pass_model_lock(tmp_path):
    with FileLock(str(tmp_path / ".tiny.en.install.lock")):
        with pytest.raises(Timeout):
            install_model("tiny.en", tmp_path)


def test_wrong_owner_is_not_deleted(tmp_path):
    stage = owned_stage(tmp_path, "a" * 32)
    (stage / ".localphraser-job").write_text("b" * 32)
    with pytest.raises(ValueError):
        cleanup_install("tiny.en", tmp_path, "a" * 32)
    assert stage.exists()
