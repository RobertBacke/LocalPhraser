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
    pipeline.input_level.return_value = 0.0
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


def test_level_timer_runs_only_while_recording_and_zeroes_afterwards(desktop):
    from localphraser.levels import display_level

    desktop.pipeline.input_level.return_value = 0.1
    assert not desktop.level_timer.isActive()
    assert 20 <= desktop.level_timer.interval() <= 50
    desktop.state_changed(State.RECORDING, "")
    assert desktop.level_timer.isActive()
    desktop.update_level()
    meter = desktop.indicator.meter
    assert meter.active and meter.levels[-1] == pytest.approx(display_level(0.1))
    hero = desktop.window.hero_meter  # The Home hero shows the same level.
    assert hero.active and hero.levels[-1] == pytest.approx(display_level(0.1))
    assert desktop.window.orb.level == pytest.approx(display_level(0.1))
    desktop.pipeline.input_level.return_value = 0.5
    desktop.update_level()
    assert list(meter.levels)[-2:] == pytest.approx([display_level(0.1), display_level(0.5)])
    for state in (State.TRANSCRIBING, State.POLISHING, State.INSERTING, State.ERROR, State.IDLE):
        desktop.state_changed(State.RECORDING, "")
        desktop.update_level()
        assert desktop.level_timer.isActive() and any(meter.levels)
        desktop.state_changed(state, "")
        assert not desktop.level_timer.isActive(), state
        assert not meter.active and not any(meter.levels), state
        assert not hero.active and not any(hero.levels) and desktop.window.orb.level == 0.0
    desktop.state_changed(State.WARMING, "")
    assert not desktop.level_timer.isActive()


def test_level_timer_stops_and_zeroes_on_shutdown(desktop):
    desktop.pipeline.input_level.return_value = 0.5
    desktop.state_changed(State.RECORDING, "")
    desktop.update_level()
    assert desktop.level_timer.isActive() and any(desktop.indicator.meter.levels)
    desktop.shutdown()
    assert not desktop.level_timer.isActive()
    assert not any(desktop.indicator.meter.levels)
    assert not any(desktop.window.hero_meter.levels)


def visible_windows(app):
    return {widget for widget in app.topLevelWidgets() if widget.isVisible()}


def latest_row(desktop):
    from PySide6.QtWidgets import QPushButton

    return next(
        button
        for button in desktop.window.sidebar.findChildren(QPushButton)
        if button.text() == "Latest transcript"
    )


def test_sidebar_entry_opens_latest_as_a_page_of_the_main_window(desktop, app):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QLabel

    from localphraser import appearance

    desktop.show_home()
    desktop.window.resize(1040, 740)
    app.processEvents()
    before = visible_windows(app)
    row = latest_row(desktop)
    assert row is desktop.window.latest_button and row.isCheckable() and not row.isChecked()
    assert row.property("nav") is True and row.glyph == "transcript"
    row.click()
    app.processEvents()
    # The same window shows the page; nothing else opened.
    assert visible_windows(app) == before
    assert desktop.window.pages.currentWidget() is desktop.latest
    assert desktop.latest.window() is desktop.window and not desktop.latest.isWindow()
    assert desktop.latest.isVisible()
    # The current-page marker moved from Home to Latest transcript.
    assert row.isChecked() and not desktop.window.home_button.isChecked()
    image = desktop.window.grab().toImage()
    glow = QColor(appearance.current_theme().glow)

    def marker(button):
        rect = button.marker_rect().toRect()
        pixel = image.pixelColor(
            button.mapTo(desktop.window, QPoint(rect.center().x(), rect.top() + 2))
        )
        return (
            abs(pixel.red() - glow.red())
            + abs(pixel.green() - glow.green())
            + abs(pixel.blue() - glow.blue())
        )

    assert marker(row) < 60 < marker(desktop.window.home_button)
    # The title sits where every other page's title sits, in the same style.
    title = desktop.latest.findChild(QLabel, "pageTitle")
    assert title.text() == "Latest transcript"
    here = title.mapTo(desktop.window, QPoint(0, 0))
    desktop.window.analytics_button.click()
    app.processEvents()
    other = desktop.window.analytics.findChild(QLabel, "pageTitle")
    assert other.mapTo(desktop.window, QPoint(0, 0)) == here
    assert other.font() == title.font()
    assert not row.isChecked() and not desktop.latest.isVisible()
    # Keyboard: the row is reached and activated like the other navigation rows.
    assert row.focusPolicy() == desktop.window.analytics_button.focusPolicy()
    row.setFocus()
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.keyClick(row, Qt.Key.Key_Space)
    assert desktop.window.pages.currentWidget() is desktop.latest and row.isChecked()


@pytest.mark.parametrize("start", ["hidden", "minimised", "another page"])
def test_tray_action_reveals_the_window_on_the_latest_page(desktop, app, start):
    action = next(a for a in desktop.menu.actions() if a.text() == "Latest transcript…")
    if start == "minimised":
        desktop.show_home()
        desktop.window.showMinimized()
    elif start == "another page":
        desktop.show_vocabulary()
    else:
        desktop.window.hide()
    app.processEvents()
    assert desktop.window.pages.currentWidget() is not desktop.latest
    before = visible_windows(app) - {desktop.window}
    action.trigger()
    app.processEvents()
    assert desktop.window.isVisible() and not desktop.window.isMinimized()
    assert desktop.window.pages.currentWidget() is desktop.latest
    assert desktop.window.latest_button.isChecked()
    assert visible_windows(app) - {desktop.window} == before  # No separate window.
    assert not desktop.latest.isWindow()


def test_latest_page_shows_an_empty_state_until_there_is_something_to_recover(desktop, app):
    from localphraser.appearance import Glyph

    desktop.show_latest()
    app.processEvents()
    latest = desktop.latest
    assert latest.empty.isVisible() and not latest.card.isVisible()
    assert not latest.text.isVisible() and not latest.tabs.isVisible()
    icon = latest.empty.findChild(Glyph)
    assert icon is not None and icon.isVisible()
    centre = icon.mapTo(latest.empty, icon.rect().center()).x()
    assert abs(centre - latest.empty.width() / 2) <= 2
    assert latest.empty_title.text() == "No transcript yet"
    assert "held in memory" in latest.empty_message.text()
    # The raw transcription arrives first from the pipeline; the card replaces the empty state.
    latest.raw.setPlainText("hello world")
    app.processEvents()
    assert latest.card.isVisible() and not latest.empty.isVisible()
    latest.set_transcript("Hello, world.", "Inserted.")
    latest.set_timing(0.5, 0.0, 0.7)
    app.processEvents()
    assert latest.card.isVisible() and latest.tabs.isVisible() and latest.text.isVisible()
    assert latest.notice.text() == "Inserted." and latest.notice.isVisible()
    assert latest.timing.isVisible() and latest.last_error.isHidden()
    latest.clear()
    app.processEvents()
    assert latest.empty.isVisible() and not latest.card.isVisible()
    assert latest.empty_title.text() == "Transcript cleared"
    assert latest.notice.text() == "Transcript cleared."
    assert latest.timing.isHidden() and latest.last_error.isHidden()
    # An error with no transcript is still shown, with Clear in reach.
    latest.record_error("Cannot open microphone.")
    app.processEvents()
    assert latest.card.isVisible() and not latest.empty.isVisible()
    assert latest.last_error.isVisible()
    assert latest.last_error.text() == "Last error: Cannot open microphone."
    latest.clear()
    app.processEvents()
    assert latest.empty.isVisible() and not latest.last_error.text()


def test_a_result_arriving_while_the_latest_page_is_open_updates_it_in_place(desktop, app):
    desktop.show_latest()
    app.processEvents()
    windows = visible_windows(app)
    assert desktop.latest.empty.isVisible()
    desktop.pipeline.audio_seconds = 2
    desktop.latest.raw.setPlainText("new words <b>plain</b>")
    desktop.complete_transcript("New words <b>plain</b>.", "Inserted.")
    desktop.latest.set_timing(0.4, 0.0, 0.6)
    app.processEvents()
    latest = desktop.latest
    assert desktop.window.pages.currentWidget() is latest and visible_windows(app) == windows
    assert latest.card.isVisible() and not latest.empty.isVisible()
    assert latest.text.toPlainText() == "New words <b>plain</b>."  # Never markup.
    assert latest.raw.toPlainText() == "new words <b>plain</b>"
    assert latest.notice.text() == "Inserted." and "After release: 0.6s" in latest.timing.text()
    desktop.state_changed(State.ERROR, "Recording failed.")
    app.processEvents()
    assert latest.last_error.isVisible()
    assert latest.last_error.text() == "Last error: Recording failed."
    assert latest.text.toPlainText() == "New words <b>plain</b>."
    desktop.complete_transcript("A second result.", "Inserted.")
    app.processEvents()
    assert latest.text.toPlainText() == "A second result."
    assert latest.last_error.text() == "Last error: Recording failed."  # Kept until Clear.


def test_latest_page_is_owned_by_the_window_from_the_start_and_cleared_on_shutdown(desktop):
    assert desktop.latest.parent() is not None and not desktop.latest.isWindow()
    assert desktop.window.pages.indexOf(desktop.latest) >= 0
    assert desktop.window.pages.currentWidget() is not desktop.latest
    desktop.latest.set_transcript("Private words.", "Inserted.")
    desktop.shutdown()
    assert not desktop.latest.text.toPlainText() and not desktop.latest.raw.toPlainText()


def test_latest_page_fits_the_smallest_window_without_scrolling_or_clipping(desktop, app):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QPushButton

    desktop.show_latest()
    desktop.window.resize(desktop.window.minimumSize())
    latest = desktop.latest
    for filled in (False, True):
        if filled:
            latest.raw.setPlainText("hello world")
            latest.set_transcript("Hello, world.", "Inserted.")
            latest.set_timing(0.5, 0.0, 0.7)
        for _ in range(3):
            app.processEvents()
        assert latest.verticalScrollBar().maximum() == 0, filled  # Nothing to scroll to.
        shown = latest.card if filled else latest.empty
        bottom = shown.mapTo(desktop.window, QPoint(0, shown.height())).y()
        assert bottom <= desktop.window.height()
    for button in latest.findChildren(QPushButton):
        assert button.isVisible() and button.height() >= button.minimumSizeHint().height()
        assert latest.card.rect().contains(button.geometry())
    assert latest.text.height() >= 40
    # A long notice and an error in the smallest window scroll rather than clip.
    latest.set_transcript("Hello, world.", "Target could not be verified. " * 12)
    latest.record_error("Microphone disconnected or audio stopped arriving. " * 4)
    for _ in range(3):
        app.processEvents()
    body = latest.widget()
    assert body.height() >= body.heightForWidth(body.width())
    assert latest.text.height() >= 40
