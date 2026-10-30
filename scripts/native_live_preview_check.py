"""Owned Qt/live-draft check with generated speech; no microphone or target-app input."""

import argparse
import threading
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from localphraser.config import Config
from localphraser.diagnostics import synthetic_audio
from localphraser.hotkey import Hotkey
from localphraser.pipeline import State
from localphraser.refinement import preserve_words
from localphraser.ui import Desktop


def check(root: Path, temporary: Path, capture_rate: int, warm_on_launch: bool = False) -> None:
    temporary.mkdir(parents=True, exist_ok=True)
    reference = synthetic_audio(temporary, capture_rate)
    snapshots = []

    class Capture:
        sample_rate = capture_rate
        full = threading.Event()

        def start(self):
            self.started = time.monotonic()

        def stop(self):
            return reference.copy()

        def preview_audio(self):
            end = min(len(reference), int((time.monotonic() - self.started) * capture_rate))
            audio = reference[max(0, end - capture_rate * 6) : end].copy()
            snapshots.append(audio)
            return audio

        def healthy(self):
            return True

        def cancel(self):
            pass

        def close(self):
            pass

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    config = Config(
        model_root=str(root),
        model="small.en",
        mode="polished",
        keep_microphone_ready=False,
        auto_insert=False,
        live_preview=True,
    )
    completed = 0
    drafts = []
    failures = []
    started = time.monotonic()
    try:
        with (
            patch.object(Hotkey, "register"),
            patch("localphraser.ui.Recorder", lambda *args, **kwargs: Capture()),
        ):
            desktop = Desktop(
                app,
                config,
                temporary / "unused-config.json",
                warm_on_launch=warm_on_launch,
                persist_history=False,
            )
            desktop.tray.hide()
            desktop.notify = lambda message: None
            pipeline = desktop.pipeline

            def draft(text: str) -> None:
                if text:
                    assert pipeline.state == State.RECORDING
                    drafts.append(time.monotonic() - started)
                    desktop.indicator.live_preview(text)
                    assert desktop.indicator.text().startswith("●  Listening\n")
                    desktop.indicator.grab().save(str(temporary / "owned-live-indicator.png"))

            pipeline.live_result = draft

            def begin(duration: int) -> None:
                desktop.latest.clear()
                pipeline.press()
                QTimer.singleShot(duration, pipeline.release)

            def poll() -> None:
                nonlocal completed
                if pipeline.state == State.IDLE and desktop.latest.text.toPlainText():
                    try:
                        raw = desktop.latest.raw.toPlainText()
                        assert all(word in raw.lower() for word in ("speech", "computer"))
                        assert preserve_words(raw, desktop.latest.text.toPlainText())
                        assert pipeline.recognizer.preview_ready
                        assert not desktop.indicator.text()
                        if completed == 0 and not warm_on_launch:
                            assert not drafts and not snapshots, (
                                "Cold capture ran preview inference."
                            )
                        else:
                            assert drafts and snapshots and all(not a.any() for a in snapshots)
                    except Exception:
                        failures.append("Owned live-preview lifecycle check failed.")
                        app.quit()
                        return
                    completed += 1
                    if completed == 1:
                        begin(7000)
                    else:
                        app.quit()
                elif time.monotonic() - started > 70:
                    failures.append("Owned live-preview check timed out.")
                    app.quit()

            timer = QTimer()
            timer.setInterval(50)
            timer.timeout.connect(poll)
            timer.start()

            def first_recording() -> None:
                if pipeline.state == State.WARMING:
                    QTimer.singleShot(50, first_recording)
                    return
                if warm_on_launch:
                    assert pipeline.recognizer.preview_ready
                begin(7000 if warm_on_launch else 100)

            QTimer.singleShot(0, first_recording)
            code = app.exec()
            timer.stop()
            pipeline.executor.shutdown(wait=True)
            desktop.insertion.executor.shutdown(wait=True)
            assert code == 0 and completed == 2 and not failures
            assert pipeline.closed and not desktop.indicator.text()
            assert not desktop.latest.text.toPlainText() and not desktop.latest.raw.toPlainText()
            assert all(not a.any() for a in snapshots)
            print(
                f"Owned Qt live preview passed: startup warm-up={warm_on_launch}; "
                f"{len(drafts)} warm drafts; final recognition/polishing; "
                f"{capture_rate} Hz; clean exit."
            )
    finally:
        reference.fill(0)
        for audio in snapshots:
            audio.fill(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--temp-dir", type=Path, required=True)
    parser.add_argument("--capture-rate", type=int, choices=(16000, 48000), default=16000)
    parser.add_argument("--warm-on-launch", action="store_true")
    args = parser.parse_args()
    check(args.root.resolve(), args.temp_dir.resolve(), args.capture_rate, args.warm_on_launch)
