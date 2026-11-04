"""One owned installer process and asynchronous cancellation cleanup."""

import json
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from localphraser.install_progress import PREFIX
from localphraser.models import cleanup_install


class ModelDownload(QObject):
    message = Signal(str)
    progress = Signal(object, object)  # Python integers: model sizes can exceed 2 GiB.
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
        self._buffer = ""

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
        self._buffer = ""
        self.phase = "download"
        self.progress.emit(0, None)
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
        self._consume(output)

    def _consume(self, output: str, *, final: bool = False) -> None:
        self._buffer += output.replace("\r", "\n")
        lines = self._buffer.split("\n")
        self._buffer = "" if final else lines.pop()
        for line in lines:
            if self.phase != "download" or self.cancelled or not line.strip():
                continue
            if line.startswith(PREFIX):
                try:
                    data = json.loads(line[len(PREFIX) :])
                    count, total = data["completed"], data["total"]
                    if type(count) is not int or count < 0:
                        continue
                    if total is not None and (type(total) is not int or total < count):
                        continue
                except (ValueError, KeyError, TypeError):
                    continue
                self.progress.emit(count, total)
            elif not any(token in line for token in ("|", "Traceback", 'File "')):
                self.message.emit(line[-200:])
        self._buffer = self._buffer[-8192:]

    def _finish(self, success: bool, text: str) -> None:
        self.phase = "idle"
        self.message.emit(text)
        self.finished.emit(success, self.cancelled)

    def _completed(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        self._output()
        self._consume("", final=True)
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
                    "Installation failed. Check connectivity, free space, files in use "
                    "or other downloads.",
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
