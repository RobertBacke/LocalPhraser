"""Small Qt tray application; all model work stays off the GUI thread."""

import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localphraser import startup
from localphraser.appearance import GlassComboBox, GlassDialog, GlassLabel
from localphraser.audio import Recorder, microphones
from localphraser.branding import app_icon
from localphraser.config import (
    DEFAULT_PROMPT,
    MODEL_HINTS,
    MODELS,
    REFINEMENT_MODELS,
    Config,
    profile_file,
    save_config,
)
from localphraser.downloads import ModelDownload
from localphraser.history import History
from localphraser.home import AppWindow
from localphraser.hotkey import Hotkey
from localphraser.models import model_present
from localphraser.pipeline import Dictation, State
from localphraser.recognition import WhisperRecognizer
from localphraser.refinement import LocalRefiner
from localphraser.shortcut import HINT, ShortcutRecorder
from localphraser.target_worker import TargetWorker


def set_appearance(theme: str) -> None:
    QApplication.styleHints().setColorScheme(
        {
            "system": Qt.ColorScheme.Unknown,
            "light": Qt.ColorScheme.Light,
            "dark": Qt.ColorScheme.Dark,
        }[theme]
    )


class Bridge(QObject):
    queued = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.queued.connect(self.invoke, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def invoke(self, callback: Callable[[], None]) -> None:
        callback()


class Indicator(GlassLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(560)

    def display(self, state: State) -> None:
        if state == State.IDLE:
            self.clear()
            self.hide()
            return
        self._show_text(f"●  {state.value}")

    def preview(self, text: str) -> None:
        self._show_text(f"●  Transcribing · preview\n{text[-200:]}")

    def live_preview(self, text: str) -> None:
        if text:
            self._show_text(f"●  Listening\n{text[-200:]}")
        else:
            self.display(State.RECORDING)

    def _show_text(self, text: str) -> None:
        self.setText(text)
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 32)
        self.show()


class Latest(GlassDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Latest transcript · LocalPhraser")
        self.resize(560, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 24)
        layout.setSpacing(14)
        layout.addLayout(self.header("Latest transcript"))
        self.notice = QLabel("No transcript yet. Only the latest result is held in memory.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.timing = QLabel()
        self.timing.setWordWrap(True)
        layout.addWidget(self.timing)
        self.last_error = QLabel()
        self.last_error.setWordWrap(True)
        layout.addWidget(self.last_error)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setAcceptRichText(False)
        self.raw = QTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setAcceptRichText(False)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.text, "Result")
        self.tabs.addTab(self.raw, "Raw transcription")
        layout.addWidget(self.tabs)
        row = QHBoxLayout()
        copy = QPushButton("Copy to clipboard")
        copy.clicked.connect(
            lambda: QApplication.clipboard().setText(
                (self.raw if self.tabs.currentIndex() == 1 else self.text).toPlainText()
            )
        )
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear)
        row.addWidget(copy)
        row.addWidget(clear)
        layout.addLayout(row)

    def clear(self) -> None:
        self.text.clear()
        self.raw.clear()
        self.notice.setText("Transcript cleared.")
        self.timing.clear()
        self.last_error.clear()

    def set_transcript(self, text: str, notice: str) -> None:
        self.text.setPlainText(text)
        self.notice.setText(notice)
        self.timing.clear()

    def record_error(self, message: str) -> None:
        self.last_error.setText(f"Last error: {message}")

    def set_timing(self, recognition: float, polishing: float, total: float) -> None:
        self.timing.setText(
            f"After release: {total:.1f}s · Recognition: {recognition:.1f}s · "
            f"Polishing: {polishing:.1f}s"
        )
        self.timing.setToolTip(
            "Total includes any remaining model loading, recognition, polishing and target checks. "
            "Recognition includes audio conversion; polishing includes any remaining polishing "
            "model loading. Timings stay in memory with the latest transcript."
        )


class Settings(GlassDialog):
    theme_changed = Signal(str)
    dismissed = Signal()
    saved = Signal()

    def __init__(
        self,
        config: Config,
        apply: Callable[[Config], None],
        begin_capture: Callable[[Callable[[], None]], None] | None = None,
        end_capture: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.apply_config = apply
        self.pending_save: Config | None = None
        self.embedded = False
        self.setWindowTitle("LocalPhraser · Settings")
        self.setMinimumWidth(540)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 24)
        outer.setSpacing(16)
        self.header_widget = QWidget()
        self.header_widget.setLayout(self.header("LocalPhraser settings"))
        outer.addWidget(self.header_widget)
        scroll = QScrollArea()
        self.scroll_area = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setObjectName("glassBody")
        scroll.setWidget(body)
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        title = QLabel("LocalPhraser")
        title.setStyleSheet("font-size: 28px; font-weight: 600; margin-bottom: 6px;")
        layout.addWidget(title)
        description = QLabel("Hold your shortcut. Speak naturally. Release to transcribe locally.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.setup_notice = QLabel()
        self.setup_notice.setWordWrap(True)
        self.setup_notice.hide()
        self.automatic_setup = False
        layout.addWidget(self.setup_notice)
        form = QFormLayout()
        form.setVerticalSpacing(14)
        self.theme = GlassComboBox()
        for label, value in (("System", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme.addItem(label, value)
        self.theme.setCurrentIndex(self.theme.findData(config.theme))
        self.theme.setToolTip("Updates and saves immediately. Other changes use Save.")
        self.theme.currentIndexChanged.connect(self.preview_theme)
        form.addRow("Appearance", self.theme)
        self.keep_history = QCheckBox("Keep transcript history on this device")
        self.keep_history.setChecked(config.keep_history)
        self.keep_history.setToolTip(
            "Stores text locally between launches without encryption. Audio is never saved. "
            "Turn off to stop saving new entries; use Clear history to delete existing text."
        )
        form.addRow(self.keep_history)
        self.hotkey = ShortcutRecorder(config.hotkey, begin_capture, end_capture)
        form.addRow("Global shortcut", self.hotkey)
        shortcut_hint = QLabel(HINT)
        shortcut_hint.setWordWrap(True)
        self.hotkey.message.connect(shortcut_hint.setText)
        form.addRow(shortcut_hint)
        self.device = GlassComboBox()
        self.device.addItem("System default", None)
        choices = []
        try:
            choices = microphones()
            for microphone in choices:
                self.device.addItem(microphone.label, microphone.value)
        except Exception:
            self.device.addItem("Microphones unavailable", None)
        index = self.device.findData(config.microphone)
        if index < 0:
            legacy_matches = [
                i + 1 for i, choice in enumerate(choices) if choice.name == config.microphone
            ]
            if len(legacy_matches) == 1:
                index = legacy_matches[0]
        if index < 0:
            self.device.addItem(f"Unavailable: {config.microphone}", config.microphone)
            index = self.device.count() - 1
        self.device.setCurrentIndex(index)
        self.device.setToolTip(
            "Choose an exact device and audio API. Indistinguishable duplicates are omitted; "
            "use System default for those devices."
        )
        form.addRow("Microphone", self.device)
        self.model = GlassComboBox()
        self.model.addItems(MODELS)
        self.model.setCurrentText(config.model)
        form.addRow("English speech model", self.model)
        model_hint = QLabel(MODEL_HINTS[config.model])
        model_hint.setWordWrap(True)
        self.model.currentTextChanged.connect(lambda name: model_hint.setText(MODEL_HINTS[name]))
        for index, name in enumerate(MODELS):
            self.model.setItemData(index, MODEL_HINTS[name], Qt.ItemDataRole.ToolTipRole)
        form.addRow(model_hint)
        install_hint = QLabel(
            "Save downloads the selected speech model if needed, then returns Home. "
            "A new download requires internet and can be cancelled."
        )
        install_hint.setWordWrap(True)
        form.addRow(install_hint)
        self.vocabulary = QLineEdit(config.vocabulary)
        self.vocabulary.setMaxLength(300)
        self.vocabulary.setPlaceholderText("Optional names or terms, separated by commas")
        self.vocabulary.setAccessibleName("Vocabulary hints")
        form.addRow("Vocabulary hints", self.vocabulary)
        vocabulary_hint = QLabel(
            "Hints guide recognition; they do not guarantee spelling. Keep the list short. "
            "Saved locally in settings. Clear the field to turn off."
        )
        vocabulary_hint.setWordWrap(True)
        form.addRow(vocabulary_hint)
        self.root = QLineEdit(config.model_root)
        folder = QPushButton("Browse…")
        folder.clicked.connect(self.browse)
        paths = QHBoxLayout()
        paths.addWidget(self.root)
        paths.addWidget(folder)
        form.addRow("Model directory", paths)
        self.threads = QSpinBox()
        self.threads.setRange(1, 16)
        self.threads.setValue(config.cpu_threads)
        form.addRow("CPU inference threads", self.threads)
        self.duration = QSpinBox()
        self.duration.setRange(1, 300)
        self.duration.setSuffix(" seconds")
        self.duration.setValue(config.max_seconds)
        form.addRow("Maximum recording", self.duration)
        self.insert = QCheckBox("Insert into verified text fields automatically")
        self.insert.setChecked(config.auto_insert)
        form.addRow(self.insert)
        self.keep_ready = QCheckBox("Keep microphone ready for faster recording")
        self.keep_ready.setChecked(config.keep_microphone_ready)
        self.keep_ready.setToolTip(
            "Keeps the input stream open but stopped between recordings. "
            "No audio is captured while idle. Turn off to close the device after each recording."
        )
        form.addRow(self.keep_ready)
        self.live_preview = QCheckBox("Live speech preview (experimental)")
        self.live_preview.setChecked(config.live_preview)
        self.live_preview.setToolTip(
            "Shows recent words in the floating indicator while recording. "
            "Prepares the speech model at startup, after download and after saving settings. "
            "Wait for Ready before speaking. "
            "Draft words may change. Uses extra CPU; final text is polished after stopping."
        )
        form.addRow(self.live_preview)
        self.start_at_login = QCheckBox("Start LocalPhraser upon startup")
        self.start_at_login.setChecked(config.start_at_login)
        self.start_at_login.setToolTip(
            "Opt-in startup for this configuration and current Windows user. "
            "Keep this application folder in place after enabling."
        )
        form.addRow(self.start_at_login)
        self.mode = GlassComboBox()
        self.mode.addItem("Raw", "raw")
        self.mode.addItem("Polished (experimental, local)", "polished")
        self.mode.setCurrentIndex(self.mode.findData(config.mode))
        form.addRow("Mode", self.mode)
        mode_hint = QLabel(
            "Raw delivers recognized text fastest. Polished adds a local editing step after "
            "recognition; larger polishing models can take longer."
        )
        mode_hint.setWordWrap(True)
        form.addRow(mode_hint)
        layout.addLayout(form)
        self.polishing = QGroupBox("Local polishing")
        polishing_form = QFormLayout(self.polishing)
        self.refinement_model = GlassComboBox()
        self.refinement_model.addItems(REFINEMENT_MODELS)
        self.refinement_model.setCurrentText(config.refinement_model)
        polishing_form.addRow("Q4 CPU model", self.refinement_model)
        self.refinement_timeout = QSpinBox()
        self.refinement_timeout.setRange(2, 60)
        self.refinement_timeout.setSuffix(" seconds")
        self.refinement_timeout.setValue(config.refinement_timeout)
        polishing_form.addRow("Polishing time limit", self.refinement_timeout)
        self.refinement_prompt = QTextEdit()
        self.refinement_prompt.setAcceptRichText(False)
        self.refinement_prompt.setPlainText(config.refinement_prompt)
        self.refinement_prompt.setMaximumHeight(100)
        self.refinement_prompt.setAccessibleName("Polishing instructions")
        polishing_form.addRow("Instructions", self.refinement_prompt)
        reset_prompt = QPushButton("Restore default instructions")
        reset_prompt.clicked.connect(lambda: self.refinement_prompt.setPlainText(DEFAULT_PROMPT))
        polishing_form.addRow(reset_prompt)
        self.install_refinement = QPushButton("Download polishing model (internet required)")
        self.install_refinement.clicked.connect(lambda: self.download(True))
        polishing_form.addRow(self.install_refinement)
        polishing_hint = QLabel(
            "Optional CPU runtime and a downloaded model are required. Words and numbers "
            "must be preserved; failures and time limits fall back to Raw. The original "
            "is available in Latest transcript. Models are shared under Model directory."
        )
        polishing_hint.setWordWrap(True)
        polishing_form.addRow(polishing_hint)
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()
        layout.addWidget(self.polishing)
        privacy = QLabel(
            "No accounts, telemetry, audio files, or saved transcript history. "
            "Only model installation uses the network. Latest transcript stays in memory "
            "until cleared, replaced, or the app exits. Copy changes the clipboard explicitly."
        )
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        self.install = QPushButton("Download speech model (internet required)")
        self.install.clicked.connect(self.download)
        layout.addWidget(self.install)
        self.progress = QLabel(
            "Speech models: Systran. Polishing models: Qwen. Downloads use Hugging Face."
        )
        self.progress.setWordWrap(True)
        layout.addWidget(self.progress)
        self.cancel_download = QPushButton("Cancel download")
        self.cancel_download.setEnabled(False)
        layout.addWidget(self.cancel_download)
        self.downloader = ModelDownload(self)
        self.downloader.message.connect(self.progress.setText)
        self.downloader.finished.connect(self.download_finished)
        self.cancel_download.clicked.connect(self.downloader.cancel)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("primary", True)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        screen = QApplication.primaryScreen()
        height = min(820, screen.availableGeometry().height() - 100) if screen else 700
        self.resize(620, max(360, height))

    def update_mode(self) -> None:
        self.polishing.setVisible(self.mode.currentData() == "polished")

    def browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Model directory", self.root.text())
        if selected:
            self.root.setText(selected)

    def values(self) -> Config:
        return Config(
            hotkey=self.hotkey.shortcut_value,
            microphone=self.device.currentData(),
            model=self.model.currentText(),
            model_root=self.root.text().strip(),
            auto_insert=self.insert.isChecked(),
            max_seconds=self.duration.value(),
            cpu_threads=self.threads.value(),
            keep_microphone_ready=self.keep_ready.isChecked(),
            vocabulary=self.vocabulary.text().strip(),
            mode=self.mode.currentData(),
            refinement_model=self.refinement_model.currentText(),
            refinement_prompt=self.refinement_prompt.toPlainText().strip(),
            refinement_timeout=self.refinement_timeout.value(),
            start_at_login=self.start_at_login.isChecked(),
            live_preview=self.live_preview.isChecked(),
            theme=self.theme.currentData(),
            keep_history=self.keep_history.isChecked(),
        ).validate()

    def save(self) -> None:
        self.hotkey.cancel_capture()
        if self.downloader.busy:
            self.progress.setText(
                "Cancel the download or wait for installation/cleanup before saving."
            )
            return
        try:
            config = self.values()
            if not model_present(config.model, Path(config.model_root)):
                self.pending_save = config
                self.setup_notice.setText(
                    f"Downloading {config.model} before saving. Your current model stays active "
                    "until installation succeeds. Internet is required; you can cancel below."
                )
                self.setup_notice.show()
                self.download()
                return
            self.finish_save(config)
        except Exception as exc:
            self.pending_save = None
            QMessageBox.warning(self, "Settings could not be saved", str(exc))
            return

    def finish_save(self, config: Config) -> None:
        self.apply_config(config)
        self.progress.setText("Settings saved.")
        self.saved.emit()

    def preview_theme(self) -> None:
        theme = self.theme.currentData()
        set_appearance(theme)
        self.theme_changed.emit(theme)

    def embed(self, parent: QWidget) -> None:
        self.embedded = True
        self.setParent(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumWidth(0)
        self.setSizeGripEnabled(False)
        self.header_widget.hide()

    def download(self, refiner: bool = False) -> None:
        if self.downloader.busy:
            return
        try:
            config = self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return
        self.install.setEnabled(False)
        self.install_refinement.setEnabled(False)
        self.cancel_download.setEnabled(True)
        self.downloader.start(
            config.refinement_model if refiner else config.model,
            Path(config.model_root),
            refiner=refiner,
        )
        self.scroll_area.ensureWidgetVisible(self.cancel_download)

    def download_finished(self, success: bool, cancelled: bool) -> None:
        self.install.setEnabled(True)
        self.install_refinement.setEnabled(True)
        self.cancel_download.setEnabled(False)
        pending, self.pending_save = self.pending_save, None
        if pending is not None:
            if success and model_present(pending.model, Path(pending.model_root)):
                try:
                    if self.values() != pending:
                        self.setup_notice.setText(
                            "Model downloaded. You changed settings during installation; "
                            "press Save to apply your current choices."
                        )
                        return
                    self.finish_save(pending)
                except Exception as exc:
                    QMessageBox.warning(self, "Settings could not be saved", str(exc))
            else:
                self.setup_notice.setText(
                    "Download cancelled. Settings were not saved."
                    if cancelled
                    else "Model installation failed. Settings were not saved. "
                    "Check your connection and model directory, then press Save to retry."
                )
            return
        if self.automatic_setup:
            self.automatic_setup = False
            self.setup_notice.setText(
                "Speech model ready. Hold your shortcut to dictate; no Save step is needed "
                "unless you changed settings."
                if success
                else "First-launch setup paused. Use Download speech model to retry when ready. "
                "Later launches will not retry automatically."
            )

    def reject(self) -> None:
        self.hotkey.cancel_capture()
        if self.downloader.busy:
            self.progress.setText(
                "Cancel the download or wait for installation/cleanup before closing settings."
            )
            return
        if self.embedded:
            self.dismissed.emit()
        else:
            super().reject()

    def accept(self) -> None:
        if self.downloader.busy:
            self.progress.setText("Wait for model installation to finish, then save.")
            return
        super().accept()


class Desktop:
    pipeline: Dictation

    def __init__(
        self,
        app: QApplication,
        config: Config,
        config_path: Path,
        *,
        first_launch: bool = False,
        show_on_launch: bool = False,
        warm_on_launch: bool = True,
        persist_history: bool = True,
    ):
        self.closing = False
        self.allow_live_warmup = warm_on_launch
        self.first_launch_setup_started = False
        self.app = app
        self.config = config
        set_appearance(config.theme)
        self.config_path = config_path
        self.bridge = Bridge()
        self.audio_preparer = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="microphone-setup"
        )
        self.latest = Latest()
        self.indicator = Indicator()
        self.settings: Settings | None = None
        self.history_error = ""
        try:
            self.history = History(
                profile_file(config_path, "history.sqlite3") if persist_history else None
            )
        except (sqlite3.DatabaseError, OSError):
            self.history = History(None)
            self.history_error = "Saved history could not be opened. This session stays in memory."
        self.tray = QSystemTrayIcon(app_icon(), app)
        self.tray.setToolTip("LocalPhraser")
        menu = QMenu()
        menu.addAction("Open LocalPhraser", self.show_home)
        self.status = menu.addAction(f"Ready · {config.mode.title()} mode")
        self.status.setEnabled(False)
        menu.addSeparator()
        self.toggle_action = menu.addAction("Start recording (manual copy)")
        self.toggle_action.triggered.connect(self.toggle)
        self.cancel_action = menu.addAction("Cancel recording")
        self.cancel_action.triggered.connect(lambda: self.pipeline.cancel())
        menu.addAction("Latest transcript…", self.show_latest)
        menu.addAction("Settings…", self.show_settings)
        menu.addSeparator()
        menu.addAction("Quit", app.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.activated)
        self.insertion = TargetWorker()
        self.pipeline = self.make_pipeline(config)
        self.hotkey = Hotkey(self.press, lambda: self.pipeline.release())
        app.installNativeEventFilter(self.hotkey)
        self.hotkey_error = ""
        try:
            self.hotkey.register(config.hotkey)
        except ValueError as exc:
            self.hotkey_error = str(exc)
        self.watchdog = QTimer()
        self.watchdog.setInterval(100)
        self.watchdog.timeout.connect(self.check_audio)
        self.window = AppWindow(
            self.history,
            self.show_settings,
            self.toggle,
            app.quit,
            config.hotkey,
            latest=self.show_latest,
        )
        self.window.setWindowIcon(app_icon())
        self.tray.show()
        app.aboutToQuit.connect(self.shutdown)
        self.state_changed(State.IDLE, "")
        if first_launch and not self.speech_model_present():
            QTimer.singleShot(0, self.start_first_launch_setup)
        elif self.hotkey_error or not self.speech_model_present():
            QTimer.singleShot(0, self.show_settings)
        elif show_on_launch:
            QTimer.singleShot(0, self.show_home)
        if self.hotkey_error:
            QTimer.singleShot(100, lambda: self.notify(self.hotkey_error))
        if self.history_error:
            QTimer.singleShot(100, lambda: self.notify(self.history_error))
        QTimer.singleShot(0, self.prepare_live_preview)

    def prepare_live_preview(self) -> bool:
        if (
            self.closing
            or not self.allow_live_warmup
            or not self.config.live_preview
            or not self.speech_model_present()
        ):
            return False
        return self.pipeline.warm_live_preview()

    def speech_model_present(self) -> bool:
        # Readiness here is a quick local presence check. Recognition still verifies
        # all hashes before loading; the installer verifies hashes before publishing.
        return model_present(self.config.model, Path(self.config.model_root))

    def start_first_launch_setup(self) -> None:
        if self.closing or self.first_launch_setup_started or self.speech_model_present():
            return
        self.first_launch_setup_started = True
        self.show_settings()
        if self.settings is None:
            return
        self.settings.setup_notice.setText(
            "First launch: downloading the default base.en speech model from Hugging Face. "
            "Internet is needed for this setup only. You can cancel; retry using Download "
            "speech model. Dictation becomes available when installation finishes. "
            "Already have models? Cancel, then choose their directory and Save."
        )
        self.settings.setup_notice.show()
        self.settings.automatic_setup = True
        self.settings.download()

    def model_download_finished(self, success: bool, cancelled: bool) -> None:
        if self.closing:
            return
        self.state_changed(self.pipeline.state, "")
        if success and self.speech_model_present():
            self.prepare_live_preview()
            if self.pipeline.state == State.WARMING:
                self.notify("Speech model installed. Preparing live preview.")
            else:
                self.notify("Speech model ready. Hold your shortcut to dictate.")

    def press(self) -> None:
        if self.closing:
            return
        if self.pipeline.state == State.WARMING:
            self.notify("Preparing speech model. Wait for Ready before speaking.")
            return
        if not self.speech_model_present():
            self.show_settings()
            self.notify("Speech model required. Finish setup in Settings before dictating.")
            return
        self.pipeline.press()

    def make_pipeline(self, config: Config) -> Dictation:
        self.recorder = Recorder(
            config.microphone, config.max_seconds, keep_ready=config.keep_microphone_ready
        )
        if config.keep_microphone_ready:
            # A failed warm-up is retried on press and then reported by the pipeline.
            self.audio_preparer.submit(self.recorder.prepare)
        return Dictation(
            self.recorder,
            WhisperRecognizer(
                Path(config.model_root) / config.model, config.cpu_threads, config.vocabulary
            ),
            self.insertion,
            self.bridge.queued.emit,
            self.state_changed,
            self.complete_transcript,
            auto_insert=config.auto_insert,
            refiner=(
                LocalRefiner(
                    config.refinement_model,
                    Path(config.model_root),
                    config.cpu_threads,
                    config.refinement_prompt,
                    config.refinement_timeout,
                )
                if config.mode == "polished"
                else None
            ),
            raw_result=self.latest.raw.setPlainText,
            timing_result=self.latest.set_timing,
            partial_result=self.indicator.preview,
            live_preview=config.live_preview,
            live_result=self.indicator.live_preview,
        )

    def notify(self, message: str) -> None:
        self.tray.showMessage(
            "LocalPhraser", message, QSystemTrayIcon.MessageIcon.Information, 5000
        )

    def complete_transcript(self, text: str, notice: str) -> None:
        if self.closing:
            return
        self.latest.set_transcript(text, notice)
        if self.config.keep_history:
            try:
                self.history.add(
                    self.latest.raw.toPlainText(), text, notice, self.pipeline.audio_seconds
                )
                self.window.refresh_history()
            except (sqlite3.DatabaseError, OSError, ValueError):
                self.notify(
                    "History could not be saved. Your text is available in Latest transcript."
                )

    def state_changed(self, state: State, message: str) -> None:
        if state == State.ERROR and message:
            self.latest.record_error(message)
        label = (
            "Speech model required"
            if state == State.IDLE and not self.speech_model_present()
            else state.value
        )
        self.status.setText(f"{label} · {self.config.mode.title()} mode")
        self.window.state_label.setText(label)
        self.window.record_button.setText(
            "Stop recording"
            if state == State.RECORDING
            else ("Record to history" if self.config.keep_history else "Record (manual copy)")
        )
        self.window.record_button.setEnabled(state in (State.IDLE, State.RECORDING))
        self.tray.setToolTip(f"LocalPhraser · {label}")
        self.tray.setIcon(app_icon(state == State.RECORDING))
        self.indicator.display(state)
        self.toggle_action.setText(
            "Stop recording" if state == State.RECORDING else "Start recording (manual copy)"
        )
        self.toggle_action.setEnabled(state in (State.IDLE, State.RECORDING))
        self.cancel_action.setEnabled(state == State.RECORDING)
        if state == State.RECORDING:
            self.watchdog.start()
        else:
            self.watchdog.stop()
        if (
            message
            and state == State.IDLE
            and message
            not in (
                "Inserted.",
                "Polishing applied. Inserted.",
                "Polishing checked; no changes needed. Inserted.",
                "Polishing suggested word changes; using raw transcription. Inserted.",
            )
        ):
            self.notify(message)

    def check_audio(self) -> None:
        if self.recorder.full.is_set():
            self.pipeline.release()
        elif not self.recorder.healthy():
            self.pipeline.cancel()
            message = "Microphone disconnected or audio stopped arriving. Recording cancelled."
            self.latest.record_error(message)
            self.notify(message)
        else:
            self.pipeline.request_live_preview()

    def toggle(self) -> None:
        if self.pipeline.state == State.RECORDING:
            self.pipeline.release()
        elif self.pipeline.state == State.IDLE:
            self.press()
            if self.pipeline.state != State.RECORDING:
                return
            # Tray interaction has changed focus: always use manual copy for this path.
            self.pipeline._clear_target()
            self.pipeline.target_error = "Tray recording finished. Open Latest transcript to copy."

    def activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_home()

    def show_home(self) -> None:
        self.window.show_home()
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def show_latest(self) -> None:
        self.latest.show()
        self.latest.raise_()
        self.latest.activateWindow()

    def show_settings(self) -> None:
        if self.settings is None:
            self.settings = Settings(
                self.config, self.apply, self.begin_shortcut_capture, self.end_shortcut_capture
            )
            self.settings.downloader.finished.connect(self.model_download_finished)
            self.settings.theme_changed.connect(self.save_appearance)
            self.settings.dismissed.connect(self.discard_settings)
            self.settings.saved.connect(self.discard_settings)
            self.settings.embed(self.window.pages)
        self.window.show_settings(self.settings)
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def discard_settings(self) -> None:
        if self.settings is not None:
            previous = self.settings
            self.settings = None
            self.window.pages.removeWidget(previous)
            previous.downloader.shutdown()
            previous.deleteLater()
        self.show_home()

    def save_appearance(self, theme: str) -> None:
        config = replace(self.config, theme=theme)
        try:
            save_config(config, self.config_path)
        except OSError:
            self.notify("Appearance changed for this session, but could not be saved.")
            return
        self.config = config

    def begin_shortcut_capture(self, captured_caps: Callable[[], None]) -> None:
        if self.pipeline.state != State.IDLE:
            raise ValueError("Finish dictation before choosing a shortcut.")
        self.hotkey.close()
        self.hotkey.capture_release_callback = None
        self.hotkey.capture_callback = captured_caps
        try:
            # Keep Caps Lock suppressed while selecting it; ordinary chords reach the button.
            self.hotkey.register("CapsLock")
        except Exception:
            self.hotkey.capture_callback = None
            self.hotkey.register(self.config.hotkey)
            raise

    def end_shortcut_capture(self) -> None:
        if not self.closing and self.hotkey._caps_handle and self.hotkey._caps_handle.down:
            # Keep suppressing a held selection key until key-up; repeats must neither
            # start dictation nor toggle Caps Lock after the button has accepted it.
            self.hotkey.capture_callback = lambda: None
            self.hotkey.capture_release_callback = self.end_shortcut_capture
            return
        self.hotkey.close()
        self.hotkey.capture_callback = None
        self.hotkey.capture_release_callback = None
        if not self.closing:
            try:
                self.hotkey.register(self.config.hotkey)
            except ValueError as exc:
                self.notify(str(exc))

    def apply(self, config: Config) -> None:
        if self.pipeline.state != State.IDLE:
            raise ValueError("Finish dictation before saving settings.")
        config.validate()
        changed_hotkey = config.hotkey != self.config.hotkey or not self.hotkey.registered
        if changed_hotkey:
            self.hotkey.register(config.hotkey)
        previous_startup = None
        startup_changed = False
        try:
            if config.start_at_login or config.start_at_login != self.config.start_at_login:
                previous_startup = startup.read_entry(self.config_path)
                command = (
                    startup.startup_command(self.config_path) if config.start_at_login else None
                )
                if command != previous_startup:
                    startup.write_entry(self.config_path, command)
                    startup_changed = True
            save_config(config, self.config_path)
        except Exception:
            if startup_changed:
                try:
                    startup.write_entry(self.config_path, previous_startup)
                except OSError:
                    self.notify("Settings were not saved; the startup entry could not be restored.")
            if changed_hotkey:
                self.hotkey.register(self.config.hotkey)
            raise
        appearance_only = (
            replace(config, theme=self.config.theme, keep_history=self.config.keep_history)
            == self.config
        )
        if config.theme != self.config.theme:
            set_appearance(config.theme)
        self.config = config
        self.window.hint.setText(f"Hold {config.hotkey}, speak naturally, then release.")
        self.window.record_button.setText(
            "Record to history" if config.keep_history else "Record (manual copy)"
        )
        self.window.storage_note.setText(
            "History stays on this device. Showing the latest 200 entries."
            if config.keep_history
            else "New transcripts are not saved. Existing history is kept until deleted."
        )
        if appearance_only:
            return
        self.pipeline.shutdown()
        self.pipeline = self.make_pipeline(config)
        self.state_changed(State.IDLE, "")
        self.prepare_live_preview()

    def shutdown(self) -> None:
        self.closing = True
        if self.settings:
            self.settings.hotkey.cancel_capture()
        self.hotkey.close()
        self.watchdog.stop()
        self.pipeline.shutdown()
        self.insertion.close()
        self.audio_preparer.shutdown(wait=False, cancel_futures=True)
        self.window.hide()
        self.window.entries.clear()
        self.window.result_text.clear()
        self.window.raw.clear()
        self.window.entry_info.clear()
        self.history.close()
        self.latest.clear()
        self.indicator.display(State.IDLE)
        self.tray.hide()
        if self.settings:
            self.settings.downloader.shutdown()
