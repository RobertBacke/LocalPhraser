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
