"""Opt-in owned Qt/model shutdown check; no microphone, hotkey, tray interaction or insertion."""

import argparse
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from localphraser.audio import Recorder
from localphraser.config import Config
from localphraser.diagnostics import synthetic_audio
from localphraser.hotkey import Hotkey
from localphraser.models import verify_model
from localphraser.pipeline import State
from localphraser.refinement_models import verify_refiner
from localphraser.ui import Desktop


def check(root: Path, temporary: Path, case: str, capture_rate: int) -> None:
    verify_model(root / "base.en")
    verify_refiner("qwen2.5-1.5b", root)
    temporary.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    config = Config(
        model_root=str(root), mode="polished", keep_microphone_ready=False, auto_insert=False
    )
    failures = []
    reached = False
    started = time.monotonic()

    # These substitutions prevent native keyboard registration and make unintended
    # microphone use fail. Model inference, Qt dispatch and shutdown use production code.
    with (
        patch.object(Hotkey, "register"),
        patch.object(
            Recorder,
            "start",
            side_effect=AssertionError("Shutdown check attempted microphone capture"),
        ),
    ):
        desktop = Desktop(app, config, temporary / "unused-config.json")
        desktop.tray.hide()
        pipeline = desktop.pipeline
        backend = pipeline.refiner
        assert backend is not None
        if case == "loading":
            pending = pipeline.executor.submit(backend.prepare)
        else:
            audio = synthetic_audio(temporary, capture_rate)
            pipeline._state(State.TRANSCRIBING)
            pipeline.executor.submit(backend.prepare)
            pending = pipeline.executor.submit(pipeline._transcribe, audio, capture_rate)
            pending.add_done_callback(
                lambda result: pipeline._post(lambda: pipeline._finish(result))
            )
        timer = QTimer()
        timer.setInterval(10)

        def poll() -> None:
            nonlocal reached
            reached = (
                (case == "loading" and backend.process is not None)
                or (case == "polishing" and backend.inflight)
                or (case == "complete" and pending.done() and pipeline.state == State.IDLE)
            )
            if reached:
                timer.stop()
                app.quit()
            elif time.monotonic() - started > 45:
                failures.append("Target shutdown stage was not reached.")
                app.quit()

        timer.timeout.connect(poll)
        timer.start()
        code = app.exec()
        timer.stop()
        pipeline.executor.shutdown(wait=True)
        assert code == 0 and reached and not failures
        assert pipeline.closed and backend.process is None
        if case == "complete":
            result = pending.result()
            assert not result.notice and "speech" in result.raw.lower()
        else:
            pending.result()  # Do not silently discard unexpected background exceptions.
        assert not desktop.latest.text.toPlainText() and not desktop.latest.raw.toPlainText()
        del desktop
    print(f"Owned Qt shutdown check passed: {case}; no microphone or insertion.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--temp-dir", type=Path, required=True)
    parser.add_argument("--case", choices=("loading", "polishing", "complete"), required=True)
    parser.add_argument(
        "--capture-rate", type=int, choices=(16000, 44100, 48000, 96000), default=48000
    )
    args = parser.parse_args()
    check(args.root.resolve(), args.temp_dir.resolve(), args.case, args.capture_rate)
