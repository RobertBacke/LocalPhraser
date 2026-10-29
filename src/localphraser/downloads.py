"""One owned installer process and asynchronous cancellation cleanup."""

import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from localphraser.models import cleanup_install


class ModelDownload(QObject):
    message = Signal(str)
    finished = Signal(bool, bool)  # Installed successfully, user cancelled.

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._output)
        self.process.finished.connect(self._completed)
        self.process.errorOccurred.connect(self._error)
        self.phase = "idle"
        self.cancelled = False
        self.job_id = ""
        self.name = ""
        self.root = Path()

    @property
    def busy(self) -> bool:
        return self.phase != "idle"

    def _launch(self, args: list[str]) -> None:
        if getattr(sys, "frozen", False):
            self.process.start(sys.executable, args)
        else:
            self.process.start(sys.executable, ["-m", "localphraser", *args])

    def start(self, name: str, root: Path, *, refiner: bool = False) -> None:
        if self.busy:
            raise ValueError("A model download or cleanup is already running.")
        self.job_id, self.name, self.root = uuid.uuid4().hex, name, root.resolve()
        self.cancelled = False
        self.phase = "download"
        self.message.emit("Installing model… You can cancel this download.")
        self._launch(
            [
                "install-refiner" if refiner else "install-model",
                name,
                "--root",
                str(self.root),
                "--job-id",
                self.job_id,
            ]
        )

    def cancel(self) -> None:
        if self.phase != "download" or self.cancelled:
            return
        self.cancelled = True
        self.message.emit("Cancelling download…")
        self.process.terminate()
        job_id = self.job_id
        QTimer.singleShot(800, lambda: self._kill_download(job_id))

    def _kill_download(self, job_id: str) -> None:
        if self.phase == "download" and self.job_id == job_id and self.cancelled:
            if self.process.state() != QProcess.ProcessState.NotRunning:
                self.process.kill()

    def _output(self) -> None:
        output = bytes(self.process.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        if self.phase == "download" and not self.cancelled:
            lines = output.strip().splitlines()
            if lines:
                self.message.emit(lines[-1][-200:])

    def _finish(self, success: bool, text: str) -> None:
        self.phase = "idle"
        self.message.emit(text)
        self.finished.emit(success, self.cancelled)

    def _completed(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        if self.phase == "download":
            if exit_code == 0 and status == QProcess.ExitStatus.NormalExit and not self.cancelled:
                self._finish(True, "Model installed and verified. Save if you changed settings.")
                return
            self.phase = "cleanup"
            self.message.emit("Cleaning partial download…")
            self._launch(
                [
                    "cleanup-install",
                    self.name,
                    "--root",
                    str(self.root),
                    "--job-id",
                    self.job_id,
                ]
            )
        elif self.phase == "cleanup":
            if exit_code != 0:
                self._finish(False, "Download stopped. Some temporary files could not be cleaned.")
            elif self.cancelled:
                self._finish(False, "Download cancelled. You can retry when ready.")
            else:
                self._finish(
                    False,
                    "Installation failed. Check connectivity, free space or other downloads.",
                )

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish(False, "Could not start the installer or its cleanup process.")

    def shutdown(self) -> None:
        if not self.busy:
            return
        self.process.blockSignals(True)
        self.process.kill()
        if (
            self.process.waitForFinished(2000)
            or self.process.state() == QProcess.ProcessState.NotRunning
        ):
            try:
                cleanup_install(self.name, self.root, self.job_id)
            except (OSError, ValueError):
                pass  # A later install uses a new job; never remove uncertain files.
        self.phase = "idle"
