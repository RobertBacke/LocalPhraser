import sys
from dataclasses import replace
from unittest.mock import Mock

import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import QAbstractNativeEventFilter

from localphraser import main as entry
from localphraser import ui
from localphraser.config import Config, load_config, save_config
from localphraser.models import FILES
from localphraser.pipeline import State


@pytest.fixture
def launch(app, monkeypatch, tmp_path):
    observed = []
    monkeypatch.setattr(QtWidgets, "QApplication", lambda args: app)
    monkeypatch.setattr(QtWidgets.QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(app, "exec", lambda: 0)
    monkeypatch.setattr(ui, "Desktop", lambda *args, **kwargs: observed.append((args, kwargs)))
    path = tmp_path / "config.json"

    def run(*options):
        monkeypatch.setattr(sys, "argv", ["localphraser", "--config", str(path), *options])
        return entry.main()

    return run, path, observed


def test_new_profile_saved_before_setup_and_existing_profile_never_auto_retries(launch):
    run, path, observed = launch
    assert run() == 0
    assert path.is_file() and observed[-1][1]["first_launch"]
    assert observed[-1][1]["warm_on_launch"]
    config = replace(load_config(path), model="small.en", vocabulary="fixture")
    save_config(config, path)
    assert run() == 0
    assert not observed[-1][1]["first_launch"]
    assert observed[-1][1]["warm_on_launch"]
    assert load_config(path) == config


def test_smoke_launch_never_downloads_or_marks_profile_initialized(launch):
    run, path, observed = launch
    assert run("--smoke-test") == 0
    assert not path.exists()
    assert not observed[-1][1]["first_launch"]
    assert not observed[-1][1]["warm_on_launch"]


def test_profile_save_failure_prevents_auto_download(launch, monkeypatch):
    run, path, observed = launch
    monkeypatch.setattr(entry, "save_config", Mock(side_effect=OSError("fixture disk full")))
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", Mock())
    assert run() == 1
    assert not path.exists() and not observed


def test_manual_launch_is_visible_and_background_or_smoke_launch_is_quiet(launch):
    run, _, observed = launch
    assert run() == 0
    assert observed[-1][1]["show_on_launch"]
    assert run("--background") == 0
    assert not observed[-1][1]["show_on_launch"]
    assert run("--smoke-test") == 0
    assert not observed[-1][1]["show_on_launch"]


class FixtureHotkey(QAbstractNativeEventFilter):
    def __init__(self, *args):
        super().__init__()
        self.registered = True
        self._caps_handle = None

    def register(self, key):
        pass

    def close(self):
        pass

    def nativeEventFilter(self, *args):
        return False, 0


@pytest.fixture
def desktop(app, monkeypatch, tmp_path, request):
    monkeypatch.setattr(ui, "Hotkey", FixtureHotkey)
    monkeypatch.setattr(ui, "TargetWorker", Mock())
    monkeypatch.setattr(ui, "microphones", lambda: [])
    monkeypatch.setattr(ui, "QSystemTrayIcon", Mock())
    monkeypatch.setattr(ui.Desktop, "notify", Mock())
    pipeline = Mock(state=State.IDLE)
    monkeypatch.setattr(ui.Desktop, "make_pipeline", lambda *args: pipeline)
    monkeypatch.setattr(ui.ModelDownload, "start", Mock())
    controller = ui.Desktop(
        app,
        replace(Config(), model_root=str(tmp_path / "models")),
        tmp_path / "config.json",
        show_on_launch=getattr(request, "param", False),
    )
    app.processEvents()
    yield controller
    app.aboutToQuit.disconnect(controller.shutdown)
    app.removeNativeEventFilter(controller.hotkey)
    controller.shutdown()
    if controller.settings:
        controller.settings.close()
        controller.settings.deleteLater()
    controller.latest.deleteLater()
    controller.indicator.deleteLater()


def publish_fixture_model(desktop):
    folder = desktop.config_path.parent / "models/base.en"
    folder.mkdir(parents=True)
    for name in (*FILES, "localphraser-manifest.json"):
        (folder / name).write_bytes(b"presence fixture; not inference")


@pytest.mark.parametrize("desktop", [True], indirect=True)
def test_visible_manual_desktop_shows_settings(desktop):
    assert desktop.settings is not None and desktop.settings.isVisible()


def test_first_setup_downloads_once_and_cancel_does_not_restart(desktop):
    assert "Speech model required" in desktop.status.text()
    desktop.start_first_launch_setup()
    desktop.start_first_launch_setup()
    ui.ModelDownload.start.assert_called_once_with(
        "base.en", desktop.config_path.parent / "models", refiner=False
    )
    desktop.settings.downloader.finished.emit(False, True)
    assert "paused" in desktop.settings.setup_notice.text()
    desktop.start_first_launch_setup()
    assert ui.ModelDownload.start.call_count == 1


def test_missing_model_does_not_capture_and_success_is_ready_without_save(desktop):
    desktop.press()
    desktop.pipeline.press.assert_not_called()
    desktop.start_first_launch_setup()
    publish_fixture_model(desktop)
    desktop.settings.downloader.finished.emit(True, False)
    assert "Speech model required" not in desktop.status.text()
    assert "Speech model ready" in desktop.settings.setup_notice.text()
    desktop.press()
    desktop.pipeline.press.assert_called_once()


def test_preinstalled_model_skips_automatic_download(desktop):
    publish_fixture_model(desktop)
    desktop.start_first_launch_setup()
    ui.ModelDownload.start.assert_not_called()


def test_audio_watchdog_cancels_unhealthy_capture_without_transcribing(desktop):
    desktop.recorder = Mock()
    desktop.recorder.full.is_set.return_value = False
    desktop.recorder.healthy.return_value = False
    desktop.check_audio()
    desktop.pipeline.cancel.assert_called_once()
    desktop.pipeline.release.assert_not_called()
    assert "Recording cancelled" in desktop.notify.call_args.args[0]


@pytest.mark.parametrize(
    "notice",
    [
        "Polishing applied. Inserted.",
        "Polishing checked; no changes needed. Inserted.",
        "Polishing suggested word changes; using raw transcription. Inserted.",
    ],
)
def test_successful_delivery_and_safe_word_preservation_do_not_show_error_toast(desktop, notice):
    desktop.notify.reset_mock()
    desktop.state_changed(State.IDLE, notice)
    desktop.notify.assert_not_called()


def test_real_polishing_timeout_still_notifies(desktop):
    desktop.notify.reset_mock()
    desktop.state_changed(State.IDLE, "Polishing timed out; using raw transcription. Inserted.")
    desktop.notify.assert_called_once()


@pytest.mark.parametrize("blocked", ["disabled", "missing", "smoke", "closing", "none"])
def test_preview_preparation_requires_opt_in_installed_model_and_normal_launch(desktop, blocked):
    if blocked != "missing":
        publish_fixture_model(desktop)
    desktop.config = replace(desktop.config, live_preview=blocked != "disabled")
    desktop.allow_live_warmup = blocked != "smoke"
    desktop.closing = blocked == "closing"
    desktop.prepare_live_preview()
    assert desktop.pipeline.warm_live_preview.call_count == (blocked == "none")


def test_download_warms_preview_and_shortcut_does_not_capture_until_ready(desktop):
    desktop.config = replace(desktop.config, live_preview=True)
    publish_fixture_model(desktop)

    def warming():
        desktop.pipeline.state = State.WARMING
        return True

    desktop.pipeline.warm_live_preview.side_effect = warming
    desktop.model_download_finished(True, False)
    assert "Preparing live preview" in desktop.notify.call_args.args[0]
    desktop.press()
    desktop.pipeline.press.assert_not_called()
    assert "Wait for Ready" in desktop.notify.call_args.args[0]
    desktop.pipeline.state = State.IDLE
    desktop.press()
    desktop.pipeline.press.assert_called_once()


def test_saving_settings_prepares_new_live_recognizer(desktop):
    publish_fixture_model(desktop)
    desktop.pipeline.warm_live_preview.reset_mock()
    desktop.apply(replace(desktop.config, live_preview=True))
    desktop.pipeline.shutdown.assert_called_once()
    desktop.pipeline.warm_live_preview.assert_called_once()
