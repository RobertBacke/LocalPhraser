import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import QAbstractNativeEventFilter

from localphraser import main as entry
from localphraser import ui
from localphraser.config import DEFAULT_MODEL, PARAKEET_MODEL, Config, load_config, save_config
from localphraser.pipeline import QUIET_MESSAGE, State

MAKE_PIPELINE = ui.Desktop.make_pipeline


@pytest.fixture
def launch(app, monkeypatch, tmp_path):
    observed = []
    monkeypatch.setattr(QtWidgets, "QApplication", lambda args: app)
    monkeypatch.setattr(QtWidgets.QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(app, "exec", lambda: 0)

    def fake_desktop(*args, **kwargs):
        observed.append((args, kwargs))
        return Mock()

    monkeypatch.setattr(ui, "Desktop", fake_desktop)
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
    controller.window.deleteLater()


def publish_fixture_model(desktop, model=DEFAULT_MODEL):
    from localphraser.models import model_files

    folder = desktop.config_path.parent / "models" / model
    folder.mkdir(parents=True)
    for name in (*model_files(model), "localphraser-manifest.json"):
        (folder / name).write_bytes(b"presence fixture; not inference")


@pytest.mark.parametrize("state", ["maximized", "fullscreen"])
def test_workspace_navigation_keeps_window_state(desktop, state, app):
    if state == "maximized":
        desktop.window.showMaximized()
    else:
        desktop.window.showFullScreen()
    expected = desktop.window.windowState()
    for navigate in (desktop.show_settings, desktop.show_vocabulary, desktop.show_home):
        navigate()
        app.processEvents()
        assert desktop.window.windowState() == expected
    desktop.window.showMinimized()
    desktop.show_home()
    app.processEvents()
    assert not desktop.window.isMinimized()
    assert desktop.window.windowState() == expected


def test_workspace_navigation_keeps_normal_window_geometry(desktop, app):
    desktop.window.setGeometry(40, 40, 900, 700)
    desktop.window.show()
    app.processEvents()
    expected = desktop.window.geometry()
    desktop.show_settings()
    desktop.show_vocabulary()
    desktop.show_home()
    app.processEvents()
    assert desktop.window.geometry() == expected


def test_explicit_quit_hides_workspace_and_cleans_up_once(desktop):
    from PySide6.QtWidgets import QPushButton

    desktop.show_home()
    application = Mock()
    desktop.app = application
    button = next(
        b for b in desktop.window.findChildren(QPushButton) if b.text() == "Quit LocalPhraser"
    )
    button.click()
    assert desktop.closing and not desktop.window.isVisible()
    application.quit.assert_called_once_with()
    desktop.pipeline.shutdown.assert_called_once_with()
    desktop.shutdown()
    desktop.pipeline.shutdown.assert_called_once_with()


@pytest.mark.parametrize("model", ["distil-small.en", "distil-medium.en", "medium.en"])
def test_save_downloads_missing_selection_before_switching_and_returns_home(desktop, model):
    from localphraser.models import model_files

    desktop.show_settings()
    settings = desktop.settings
    settings.model.select_data(model)
    settings.save()
    settings.downloader.start.assert_called_once_with(
        model, Path(desktop.config.model_root), refiner=False
    )
    assert desktop.config.model == DEFAULT_MODEL
    assert settings.isVisible() and "Downloading" in settings.setup_notice.text()
    folder = Path(desktop.config.model_root) / model
    folder.mkdir(parents=True)
    for filename in (*model_files(model), "localphraser-manifest.json"):
        (folder / filename).touch()
    settings.download_finished(True, False)
    assert desktop.config.model == model
    assert load_config(desktop.config_path).model == model
    assert desktop.settings is None
    assert desktop.window.pages.currentWidget() is desktop.window.home


@pytest.mark.parametrize("cancelled", [False, True])
def test_unsuccessful_model_install_does_not_switch_or_save_settings(desktop, cancelled):
    desktop.show_settings()
    settings = desktop.settings
    settings.model.select_data("distil-small.en")
    settings.duration.setValue(200)
    settings.save()
    settings.download_finished(False, cancelled)
    assert desktop.config.model == DEFAULT_MODEL and desktop.config.max_seconds == 120
    assert desktop.settings is settings and settings.isVisible()
    assert "not saved" in settings.setup_notice.text()
    assert settings.pending_save is None


def test_edits_during_download_are_preserved_for_explicit_save(desktop):
    from localphraser.models import model_files

    desktop.show_settings()
    settings = desktop.settings
    settings.model.select_data("distil-small.en")
    settings.save()
    settings.duration.setValue(200)
    folder = Path(desktop.config.model_root) / "distil-small.en"
    folder.mkdir(parents=True)
    for filename in (*model_files("distil-small.en"), "localphraser-manifest.json"):
        (folder / filename).touch()
    settings.download_finished(True, False)
    assert desktop.config.model == DEFAULT_MODEL and desktop.config.max_seconds == 120
    assert desktop.settings is settings and settings.duration.value() == 200
    assert "press Save" in settings.setup_notice.text()
    settings.save()
    assert desktop.config.model == "distil-small.en" and desktop.config.max_seconds == 200
    assert desktop.settings is None


@pytest.mark.parametrize("desktop", [True], indirect=True)
def test_visible_manual_desktop_shows_settings(desktop):
    assert desktop.settings is not None and desktop.settings.isVisible()


def test_first_launch_notice_names_the_parakeet_download(desktop):
    desktop.start_first_launch_setup()
    assert desktop.settings.setup_notice.text() == (
        "First launch: downloading the default Parakeet speech model (~660 MB) from Hugging Face. "
        "Internet is needed for this setup only. You can cancel; retry using Download speech "
        "model. Dictation becomes available when installation finishes. Already have models? "
        "Cancel, then choose their directory and Save."
    )


def test_first_setup_downloads_once_and_cancel_does_not_restart(desktop):
    assert "Speech model required" in desktop.status.text()
    desktop.start_first_launch_setup()
    desktop.start_first_launch_setup()
    ui.ModelDownload.start.assert_called_once_with(
        DEFAULT_MODEL, desktop.config_path.parent / "models", refiner=False
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
    assert desktop.settings.setup_notice.text() == (
        "Speech model installed. Dictation is available when the status shows Ready; "
        "no Save step is needed unless you changed settings."
    )
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
        publish_fixture_model(desktop, "base.en")
    desktop.config = replace(desktop.config, model="base.en", live_preview=blocked != "disabled")
    desktop.allow_live_warmup = blocked != "smoke"
    desktop.closing = blocked == "closing"
    desktop.prepare_live_preview()
    assert desktop.pipeline.warm_live_preview.call_count == (blocked == "none")


@pytest.mark.parametrize(
    ("model", "live_preview", "warms"),
    [(PARAKEET_MODEL, False, True), ("base.en", False, False), ("base.en", True, True)],
)
def test_parakeet_warms_at_start_without_live_preview_and_whisper_does_not(
    desktop, model, live_preview, warms
):
    publish_fixture_model(desktop, model)
    desktop.config = replace(desktop.config, model=model, live_preview=live_preview)
    desktop.pipeline.warm_live_preview.reset_mock()
    desktop.prepare_live_preview()
    assert desktop.pipeline.warm_live_preview.call_count == warms


def test_pipeline_warms_on_start_only_for_parakeet(desktop, monkeypatch):
    seen = []
    monkeypatch.setattr(ui, "Dictation", lambda *a, **k: seen.append(k) or Mock())
    monkeypatch.setattr(ui, "Recorder", Mock())
    monkeypatch.setattr(ui, "make_recognizer", Mock())
    for model in (PARAKEET_MODEL, "small.en"):
        MAKE_PIPELINE(desktop, replace(desktop.config, model=model))
    assert [k["warm_on_start"] for k in seen] == [True, False]


def test_capsule_invites_speech_only_when_live_preview_is_on(desktop, monkeypatch):
    monkeypatch.setattr(ui, "Dictation", Mock())
    monkeypatch.setattr(ui, "Recorder", Mock())
    monkeypatch.setattr(ui, "make_recognizer", Mock())
    for live in (False, True):
        MAKE_PIPELINE(desktop, replace(desktop.config, live_preview=live))
        desktop.indicator.display(State.RECORDING)
        expected = "Listening — speak now" if live else "Listening"
        assert desktop.indicator.status.text() == expected
        desktop.indicator.display(State.IDLE)


@pytest.mark.parametrize(
    ("state", "colour"),
    [
        (State.RECORDING, "recording"),
        (State.TRANSCRIBING, "busy"),
        (State.WARMING, "muted"),
        (State.ERROR, "recording"),
    ],
)
def test_sidebar_status_dot_uses_the_capsule_colours(desktop, state, colour):
    desktop.state_changed(state, "")
    assert desktop.window.state_label.text() == state.value
    assert desktop.window.state_dot.tone == colour
    assert desktop.indicator.dot.tone == colour


def test_sidebar_status_dot_is_ready_only_with_a_model(desktop):
    desktop.state_changed(State.IDLE, "")
    assert desktop.window.state_label.text() == "Speech model required"
    assert desktop.window.state_dot.tone == "muted"
    publish_fixture_model(desktop)
    desktop.state_changed(State.IDLE, "")
    assert desktop.window.state_label.text() == "Ready"
    assert desktop.window.state_dot.tone == "ready"


def test_download_warms_preview_and_shortcut_does_not_capture_until_ready(desktop):
    desktop.config = replace(desktop.config, live_preview=True)
    publish_fixture_model(desktop)

    def warming():
        desktop.pipeline.state = State.WARMING
        return True

    desktop.pipeline.warm_live_preview.side_effect = warming
    desktop.model_download_finished(True, False)
    assert desktop.notify.call_args.args[0] == "Speech model installed. Preparing live preview."
    desktop.press()
    desktop.pipeline.press.assert_not_called()
    assert "Wait for Ready" in desktop.notify.call_args.args[0]
    desktop.pipeline.state = State.IDLE
    desktop.press()
    desktop.pipeline.press.assert_called_once()


def test_download_warming_without_live_preview_does_not_mention_it(desktop):
    desktop.config = replace(desktop.config, model=PARAKEET_MODEL, live_preview=False)
    publish_fixture_model(desktop, PARAKEET_MODEL)

    def warming():
        desktop.pipeline.state = State.WARMING
        return True

    desktop.pipeline.warm_live_preview.side_effect = warming
    desktop.model_download_finished(True, False)
    assert desktop.notify.call_args.args[0] == (
        "Speech model installed. Preparing it now; wait for Ready before dictating."
    )


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (State.WARMING, "Wait for the speech model to finish preparing before saving settings."),
        (State.RECORDING, "Finish dictation before saving settings."),
        (State.TRANSCRIBING, "Finish dictation before saving settings."),
    ],
)
def test_saving_settings_while_busy_names_the_reason(desktop, state, message):
    desktop.pipeline.state = state
    with pytest.raises(ValueError) as raised:
        desktop.apply(replace(desktop.config, max_seconds=200))
    assert str(raised.value) == message


@pytest.mark.parametrize(
    ("state", "vocabulary", "shortcut"),
    [
        (
            State.WARMING,
            "Wait for the speech model to finish preparing before changing vocabulary.",
            "Wait for the speech model to finish preparing before choosing a shortcut.",
        ),
        (
            State.RECORDING,
            "Finish dictation before changing vocabulary.",
            "Finish dictation before choosing a shortcut.",
        ),
    ],
)
def test_vocabulary_and_shortcut_while_busy_name_the_reason(desktop, state, vocabulary, shortcut):
    desktop.pipeline.state = state
    with pytest.raises(ValueError) as raised:
        desktop.save_vocabulary("Codex")
    assert str(raised.value) == vocabulary
    with pytest.raises(ValueError) as raised:
        desktop.begin_shortcut_capture(lambda: None)
    assert str(raised.value) == shortcut


@pytest.mark.parametrize(
    ("model", "note"),
    [
        (
            PARAKEET_MODEL,
            "Parakeet restores the spelling of these terms when it hears them exactly. Every "
            "exact occurrence is rewritten, so avoid ordinary words. It does not correct "
            "sound-alike words.",
        ),
        ("base.en", "Whisper models use these terms as recognition hints."),
    ],
)
def test_vocabulary_page_explains_what_the_engine_does_with_terms(desktop, model, note):
    desktop.config = replace(desktop.config, model=model)
    desktop.show_vocabulary()
    assert desktop.vocabulary_page.engine_note.text() == note


def test_saving_settings_prepares_new_live_recognizer(desktop):
    publish_fixture_model(desktop)
    desktop.config = replace(desktop.config, live_preview=False)
    desktop.pipeline.warm_live_preview.reset_mock()
    desktop.apply(replace(desktop.config, live_preview=True))
    desktop.pipeline.shutdown.assert_called_once()
    desktop.pipeline.warm_live_preview.assert_called_once()


def test_appearance_save_preserves_warm_pipeline_and_latest_transcript(desktop, monkeypatch):
    appearance = Mock()
    monkeypatch.setattr(ui, "set_appearance", appearance)
    pipeline = desktop.pipeline
    desktop.latest.set_transcript("Keep this result.", "Manual copy.")
    desktop.apply(replace(desktop.config, theme="dark"))
    assert desktop.pipeline is pipeline
    pipeline.shutdown.assert_not_called()
    pipeline.warm_live_preview.assert_not_called()
    assert desktop.latest.text.toPlainText() == "Keep this result."
    assert load_config(desktop.config_path).theme == "dark"
    appearance.assert_called_once_with("dark")


def test_workspace_theme_autosaves_without_applying_other_unsaved_fields(desktop, app):
    publish_fixture_model(desktop)
    desktop.show_settings()
    desktop.settings.duration.setValue(200)
    desktop.settings.theme.setCurrentIndex(desktop.settings.theme.findData("dark"))
    app.processEvents()
    assert desktop.config.theme == "dark"
    saved = load_config(desktop.config_path)
    assert saved.theme == "dark" and saved.max_seconds == 120
    desktop.pipeline.shutdown.assert_not_called()
    desktop.settings.save()
    assert desktop.window.isVisible() and desktop.settings is None
    assert desktop.window.pages.currentWidget() is desktop.window.home
    assert desktop.config.max_seconds == 200


def test_completed_dictation_is_saved_without_raising_the_home_window(desktop):
    desktop.window.hide()
    desktop.pipeline.audio_seconds = 2.0
    desktop.latest.raw.setPlainText("hello world")
    desktop.complete_transcript("Hello, world.", "Inserted.")
    assert desktop.history.stats() == (1, 2, 60)
    assert not desktop.window.isVisible()
    desktop.config = replace(desktop.config, keep_history=False)
    desktop.complete_transcript("A private next result.", "Inserted.")
    assert desktop.history.stats()[0] == 1
    assert desktop.latest.text.toPlainText() == "A private next result."


@pytest.mark.parametrize("failure", ["readonly", "full"])
def test_history_write_failure_preserves_latest_result_and_recovers(desktop, failure):
    text = "Recover these words. " * 400
    desktop.pipeline.audio_seconds = 2.0
    desktop.latest.raw.setPlainText(text)
    connection = desktop.history.connection
    if failure == "readonly":
        connection.execute("PRAGMA query_only=ON")
    else:
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
        connection.execute(f"PRAGMA max_page_count={pages}")
    desktop.complete_transcript(text, "Inserted.")
    assert desktop.latest.text.toPlainText() == text
    assert desktop.history.stats()[0] == 0
    assert not desktop.window.history_notice.isHidden()
    assert "could not be saved" in desktop.window.history_notice.text()
    desktop.notify.assert_called()
    connection.execute("PRAGMA query_only=OFF")
    connection.execute("PRAGMA max_page_count=1073741823")
    desktop.complete_transcript(text, "Inserted.")
    assert desktop.history.stats()[0] == 1
    assert desktop.window.history_notice.isHidden()


def test_cancel_discards_unsaved_fields_but_keeps_immediate_appearance(desktop):
    desktop.show_settings()
    desktop.settings.duration.setValue(180)
    desktop.settings.theme.setCurrentIndex(desktop.settings.theme.findData("dark"))
    desktop.settings.reject()
    assert desktop.settings is None
    desktop.show_settings()
    assert desktop.settings.duration.value() == 120
    assert desktop.settings.theme.currentData() == "dark"


def test_history_preference_change_preserves_loaded_pipeline(desktop):
    desktop.apply(replace(desktop.config, keep_history=False))
    desktop.pipeline.shutdown.assert_not_called()
    assert not load_config(desktop.config_path).keep_history
    assert "manual copy" in desktop.window.record_button.text()


def test_vocabulary_page_save_preserves_pipeline_and_unsaved_settings(desktop):
    desktop.show_settings()
    desktop.settings.duration.setValue(180)
    desktop.show_vocabulary()
    assert desktop.window.pages.currentWidget() is desktop.vocabulary_page
    desktop.save_vocabulary("Codex, PySide")
    assert desktop.config.vocabulary == "Codex, PySide"
    assert desktop.pipeline.recognizer.vocabulary == "Codex, PySide"
    assert desktop.settings.values().vocabulary == "Codex, PySide"
    assert desktop.settings.duration.value() == 180
    desktop.pipeline.shutdown.assert_not_called()
    assert load_config(desktop.config_path).vocabulary == "Codex, PySide"


def test_history_uses_recording_app_identity_and_skips_counts_when_disabled(desktop):
    from concurrent.futures import Future

    origin = Future()
    origin.set_result("Codex")
    desktop.recording_app = origin
    desktop.pipeline.audio_seconds = 1
    desktop.latest.raw.setPlainText("test words")
    desktop.complete_transcript("Test words.", "Inserted.")
    assert desktop.history.app_stats()[0]["app"] == "Codex"
    desktop.config = replace(desktop.config, keep_history=False)
    desktop.complete_transcript("Not saved.", "Inserted.")
    assert desktop.history.app_stats()[0]["total"] == 1


def test_tray_shows_quiet_notice_once_per_session(desktop):
    desktop.pipeline.audio_seconds = 2.0
    desktop.notify.reset_mock()
    desktop.complete_transcript("First.", f"Inserted. {QUIET_MESSAGE}")
    desktop.complete_transcript("Second.", f"Polishing applied. Inserted. {QUIET_MESSAGE}")
    desktop.complete_transcript("Third.", "Inserted.")
    assert [c.args[0] for c in desktop.notify.call_args_list].count(QUIET_MESSAGE) == 1


def test_tray_shows_no_quiet_notice_for_normal_results(desktop):
    desktop.pipeline.audio_seconds = 2.0
    desktop.notify.reset_mock()
    desktop.complete_transcript("Fine.", "Inserted.")
    assert QUIET_MESSAGE not in [c.args[0] for c in desktop.notify.call_args_list]


def test_nothing_recognised_quiet_message_notifies_every_time(desktop):
    desktop.notify.reset_mock()
    desktop.state_changed(State.IDLE, QUIET_MESSAGE)
    desktop.state_changed(State.IDLE, QUIET_MESSAGE)
    assert desktop.notify.call_count == 2
