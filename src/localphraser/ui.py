"""Small Qt tray application; all model work stays off the GUI thread."""

import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
)

from localphraser.audio import Recorder, microphones
from localphraser.config import MODELS, Config, save_config
from localphraser.hotkey import Hotkey
from localphraser.pipeline import Dictation, State
from localphraser.recognition import WhisperRecognizer
from localphraser.shortcut import HINT, ShortcutRecorder
from localphraser.target_worker import TargetWorker


def app_icon(recording: bool = False) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#f06464" if recording else "#428c78"))
    painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(25, 14, 14, 27, 7, 7)
    painter.drawRect(30, 38, 4, 11)
    painter.drawRoundedRect(22, 47, 20, 4, 2, 2)
    painter.end()
    return QIcon(pixmap)


class Bridge(QObject):
    queued = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.queued.connect(self.invoke, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def invoke(self, callback: Callable[[], None]) -> None:
        callback()


class Indicator(QLabel):
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
        self.setStyleSheet(
            "background: #20332e; color: white; padding: 12px 22px;"
            "border-radius: 12px; font-size: 14px;"
        )

    def display(self, state: State) -> None:
        if state == State.IDLE:
            self.hide()
            return
        self.setText(f"●  {state.value}")
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 32)
        self.show()


class Latest(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Latest transcript · LocalPhraser")
        self.resize(560, 320)
        layout = QVBoxLayout(self)
        self.notice = QLabel("No transcript yet. Only the latest result is held in memory.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setAcceptRichText(False)
        layout.addWidget(self.text)
        row = QHBoxLayout()
        copy = QPushButton("Copy to clipboard")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear)
        row.addWidget(copy)
        row.addWidget(clear)
        layout.addLayout(row)

    def clear(self) -> None:
        self.text.clear()
        self.notice.setText("Transcript cleared.")

    def set_transcript(self, text: str, notice: str) -> None:
        self.text.setPlainText(text)
        self.notice.setText(notice)


class Settings(QDialog):
    def __init__(
        self,
        config: Config,
        apply: Callable[[Config], None],
        begin_capture: Callable[[Callable[[], None]], None] | None = None,
        end_capture: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.apply_config = apply
        self.setWindowTitle("LocalPhraser · Settings")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        title = QLabel("LocalPhraser")
        title.setStyleSheet("font-size: 24px; font-weight: 600; margin-bottom: 8px;")
        layout.addWidget(title)
        description = QLabel("Hold your shortcut. Speak naturally. Release to transcribe locally.")
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        form.setVerticalSpacing(14)
        self.hotkey = ShortcutRecorder(config.hotkey, begin_capture, end_capture)
        form.addRow("Global shortcut", self.hotkey)
        shortcut_hint = QLabel(HINT)
        shortcut_hint.setWordWrap(True)
        self.hotkey.message.connect(shortcut_hint.setText)
        form.addRow(shortcut_hint)
        self.device = QComboBox()
        self.device.addItem("System default", None)
        try:
            for name in microphones():
                self.device.addItem(name, name)
        except Exception:
            self.device.addItem("Microphones unavailable", None)
        index = self.device.findData(config.microphone)
        if index < 0:
            self.device.addItem(f"Unavailable: {config.microphone}", config.microphone)
            index = self.device.count() - 1
        self.device.setCurrentIndex(index)
        form.addRow("Microphone", self.device)
        self.model = QComboBox()
        self.model.addItems(MODELS)
        self.model.setCurrentText(config.model)
        form.addRow("English speech model", self.model)
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
        form.addRow("Mode", QLabel("Raw · Local LLM refinement is planned for Phase 2."))
        layout.addLayout(form)
        privacy = QLabel(
            "No accounts, telemetry, audio files, or saved transcript history. "
            "Only model installation uses the network. Latest transcript stays in memory "
            "until cleared, replaced, or the app exits. Copy changes the clipboard explicitly."
        )
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        self.install = QPushButton("Download selected model (internet required)")
        self.install.clicked.connect(self.download)
        layout.addWidget(self.install)
        self.progress = QLabel(
            "Models are downloaded from Systran on Hugging Face. No account needed."
        )
        self.progress.setWordWrap(True)
        layout.addWidget(self.progress)
        self.process: QProcess | None = None
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
        ).validate()

    def save(self) -> None:
        self.hotkey.cancel_capture()
        try:
            self.apply_config(self.values())
        except Exception as exc:
            QMessageBox.warning(self, "Settings could not be saved", str(exc))
            return
        self.accept()

    def download(self) -> None:
        try:
            config = self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return
        self.install.setEnabled(False)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.download_output)
        self.process.finished.connect(self.download_finished)
        self.process.errorOccurred.connect(self.download_error)
        args = ["install-model", config.model, "--root", config.model_root]
        if getattr(sys, "frozen", False):
            self.process.start(sys.executable, args)
        else:
            self.process.start(sys.executable, ["-m", "localphraser", *args])
        self.progress.setText("Installing model… Download runs separately from dictation.")

    def download_output(self) -> None:
        if self.process:
            output = bytes(self.process.readAllStandardOutput().data()).decode(
                "utf-8", errors="replace"
            )
            lines = output.strip().splitlines()
            if lines:
                self.progress.setText(lines[-1][-200:])

    def download_finished(self, exit_code: int, status: Any) -> None:
        self.install.setEnabled(True)
        self.progress.setText(
            "Model installed and verified. Save to use it."
            if exit_code == 0
            else "Installation failed. Check connectivity, disk space, and model folder."
        )

    def download_error(self, error: Any) -> None:
        self.install.setEnabled(True)
        self.progress.setText("Could not run the model installer.")

    def reject(self) -> None:
        self.hotkey.cancel_capture()
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.progress.setText(
                "Wait for the model installation to finish before closing settings."
            )
            return
        super().reject()

    def accept(self) -> None:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.progress.setText("Wait for model installation to finish, then save.")
            return
        super().accept()


class Desktop:
    pipeline: Dictation

    def __init__(self, app: QApplication, config: Config, config_path: Path):
        self.closing = False
        self.app = app
        self.config = config
        self.config_path = config_path
        self.bridge = Bridge()
        self.audio_preparer = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="microphone-setup"
        )
        self.latest = Latest()
        self.indicator = Indicator()
        self.settings: Settings | None = None
        self.tray = QSystemTrayIcon(app_icon(), app)
        self.tray.setToolTip("LocalPhraser · Ready")
        menu = QMenu()
        self.status = menu.addAction("Ready · Raw mode")
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
        self.hotkey = Hotkey(lambda: self.pipeline.press(), lambda: self.pipeline.release())
        app.installNativeEventFilter(self.hotkey)
        self.hotkey_error = ""
        try:
            self.hotkey.register(config.hotkey)
        except ValueError as exc:
            self.hotkey_error = str(exc)
        self.watchdog = QTimer()
        self.watchdog.setInterval(100)
        self.watchdog.timeout.connect(self.check_audio)
        self.tray.show()
        app.aboutToQuit.connect(self.shutdown)
        if self.hotkey_error or not (Path(config.model_root) / config.model).exists():
            QTimer.singleShot(0, self.show_settings)
        if self.hotkey_error:
            QTimer.singleShot(100, lambda: self.notify(self.hotkey_error))

    def make_pipeline(self, config: Config) -> Dictation:
        self.recorder = Recorder(
            config.microphone, config.max_seconds, keep_ready=config.keep_microphone_ready
        )
        if config.keep_microphone_ready:
            # A failed warm-up is retried on press and then reported by the pipeline.
            self.audio_preparer.submit(self.recorder.prepare)
        return Dictation(
            self.recorder,
            WhisperRecognizer(Path(config.model_root) / config.model, config.cpu_threads),
            self.insertion,
            self.bridge.queued.emit,
            self.state_changed,
            self.latest.set_transcript,
            auto_insert=config.auto_insert,
        )

    def notify(self, message: str) -> None:
        self.tray.showMessage(
            "LocalPhraser", message, QSystemTrayIcon.MessageIcon.Information, 5000
        )

    def state_changed(self, state: State, message: str) -> None:
        self.status.setText(f"{state.value} · Raw mode")
        self.tray.setToolTip(f"LocalPhraser · {state.value}")
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
        if message and state == State.IDLE and message != "Inserted.":
            self.notify(message)

    def check_audio(self) -> None:
        if self.recorder.full.is_set():
            self.pipeline.release()
        elif not self.recorder.healthy():
            self.pipeline.cancel()
            self.notify("Microphone disconnected or stopped. Recording cancelled.")

    def toggle(self) -> None:
        if self.pipeline.state == State.RECORDING:
            self.pipeline.release()
        elif self.pipeline.state == State.IDLE:
            self.pipeline.press()
            # Tray interaction has changed focus: always use manual copy for this path.
            self.pipeline._clear_target()
            self.pipeline.target_error = "Tray recording finished. Open Latest transcript to copy."

    def activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_settings()

    def show_latest(self) -> None:
        self.latest.show()
        self.latest.raise_()
        self.latest.activateWindow()

    def show_settings(self) -> None:
        if self.pipeline.state != State.IDLE:
            self.notify("Finish or cancel dictation before changing settings.")
            return
        if self.settings and self.settings.isVisible():
            if self.settings.isMinimized():
                self.settings.showNormal()
            self.settings.raise_()
            self.settings.activateWindow()
            return
        self.settings = Settings(
            self.config, self.apply, self.begin_shortcut_capture, self.end_shortcut_capture
        )
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

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
        changed_hotkey = config.hotkey != self.config.hotkey or not self.hotkey.registered
        if changed_hotkey:
            self.hotkey.register(config.hotkey)
        try:
            save_config(config, self.config_path)
        except Exception:
            if changed_hotkey:
                self.hotkey.register(self.config.hotkey)
            raise
        self.pipeline.shutdown()
        self.config = config
        self.pipeline = self.make_pipeline(config)

    def shutdown(self) -> None:
        self.closing = True
        if self.settings:
            self.settings.hotkey.cancel_capture()
        self.hotkey.close()
        self.watchdog.stop()
        self.pipeline.shutdown()
        self.insertion.close()
        self.audio_preparer.shutdown(wait=False, cancel_futures=True)
        self.latest.clear()
        self.indicator.hide()
        self.tray.hide()
        if self.settings and self.settings.process:
            process = self.settings.process
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(1000):
                    process.kill()
                    process.waitForFinished(1000)
