import sys

from localphraser.main import main


def test_explicit_installer_can_run_from_offline_desktop_environment(monkeypatch, tmp_path):
    import os

    import localphraser.models

    observed = []
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(
        sys, "argv", ["localphraser", "install-model", "base.en", "--root", str(tmp_path)]
    )
    monkeypatch.setattr(
        localphraser.models,
        "install_model",
        lambda *args: observed.append(os.environ["HF_HUB_OFFLINE"]),
    )
    assert main() == 0
    assert observed == ["0"]


def test_refiner_download_is_explicit_and_restores_online_installer_env(monkeypatch, tmp_path):
    import os

    import localphraser.refinement_models

    observed = []
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(sys, "argv", ["localphraser", "install-refiner", "--root", str(tmp_path)])
    monkeypatch.setattr(
        localphraser.refinement_models,
        "install_refiner",
        lambda name, root: observed.append((name, os.environ["HF_HUB_OFFLINE"])),
    )
    assert main() == 0
    assert observed == [("qwen2.5-1.5b", "0")]


def test_windowless_source_entry_uses_null_streams_without_log_files(monkeypatch, tmp_path):
    import localphraser.models

    streams = []
    with monkeypatch.context() as changes:
        changes.setattr(sys, "argv", ["localphraser", "install-model", "--root", str(tmp_path)])
        changes.setattr(localphraser.models, "install_model", lambda *args: None)
        for name in ("stdout", "stderr", "stdin"):
            changes.setattr(sys, name, None)
        assert main() == 0
        streams = [sys.stdout, sys.stderr, sys.stdin]
        assert streams[0].writable() and streams[1].writable() and streams[2].readable()
    for stream in streams:
        stream.close()
    assert not list(tmp_path.iterdir())


def test_invalid_install_job_is_refused_before_filesystem_changes(monkeypatch, tmp_path):
    root = tmp_path / "must-not-be-created"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "localphraser",
            "install-model",
            "tiny.en",
            "--root",
            str(root),
            "--job-id",
            "../other",
        ],
    )
    assert main() == 1
    assert not root.exists()
