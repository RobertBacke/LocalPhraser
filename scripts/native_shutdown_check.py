"""Opt-in owned Qt/model shutdown check; no microphone, hotkey, tray interaction or insertion."""

import argparse
import json
import platform
import time
from pathlib import Path
from unittest.mock import patch

import psutil
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


def check(
    root: Path,
    temporary: Path,
    case: str,
    capture_rate: int,
    cycles: int = 1,
    report: Path | None = None,
    idle_seconds: int = 5,
) -> None:
    if not 1 <= cycles <= 100 or (cycles != 1 and case != "complete"):
        raise ValueError("Use 1-100 cycles; repeated cycles require the complete case.")
    if report is not None and (case != "complete" or not 1 <= idle_seconds <= 120):
        raise ValueError("Resource reports require complete sessions and 1-120 idle seconds.")
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
    completed = 0
    started = time.monotonic()
    process = psutil.Process()
    peak_rss, sampled_at, last_tick, max_ui_gap = 0, 0.0, started, 0.0
    idle_started: float | None = None
    idle_cpu_start = 0.0
    idle_cpu_percent = 0.0
    cycle_metrics = []

    def resources() -> tuple[int, float]:
        rss, cpu = 0, 0.0
        for member in (process, *process.children(recursive=True)):
            try:
                rss += member.memory_info().rss
                times = member.cpu_times()
                cpu += times.user + times.system
            except psutil.NoSuchProcess:
                pass  # A polishing child can exit between enumeration and sampling.
        return rss, cpu

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
        reference = None
        if case == "loading":
            pending = pipeline.executor.submit(pipeline._prepare_models)
        else:
            reference = synthetic_audio(temporary, capture_rate)
            audio = reference.copy()
            pipeline._state(State.TRANSCRIBING)
            pipeline.executor.submit(pipeline._prepare_models)
            pending = pipeline.executor.submit(pipeline._transcribe, audio, capture_rate)
            pending.add_done_callback(
                lambda result: pipeline._post(lambda: pipeline._finish(result))
            )
        timer = QTimer()
        timer.setInterval(10)

        def poll() -> None:
            nonlocal reached, pending, completed, peak_rss, sampled_at, last_tick, max_ui_gap
            nonlocal idle_started, idle_cpu_start, idle_cpu_percent
            now = time.monotonic()
            max_ui_gap = max(max_ui_gap, now - last_tick)
            last_tick = now
            if report is not None and now - sampled_at >= 0.1:
                peak_rss = max(peak_rss, resources()[0])
                sampled_at = now
            if idle_started is not None:
                if now - idle_started >= idle_seconds:
                    idle_cpu_percent = (
                        max(0, resources()[1] - idle_cpu_start) / (now - idle_started) * 100
                    )
                    timer.stop()
                    app.quit()
                return
            reached = (
                (case == "loading" and backend.process is not None)
                or (case == "polishing" and backend.inflight)
                or (case == "complete" and pending.done() and pipeline.state == State.IDLE)
            )
            if reached:
                if case == "complete":
                    try:
                        result = pending.result()
                        assert result.notice in (
                            "Polishing applied.",
                            "Polishing checked; no changes needed.",
                        )
                        assert "speech" in result.raw.lower()
                    except Exception:
                        failures.append("Synthetic session failed.")
                        app.quit()
                        return
                    completed += 1
                    if report is not None:
                        cycle_metrics.append(
                            {
                                "cycle": completed,
                                "recognition_seconds": result.recognition_seconds,
                                "polishing_seconds": result.polishing_seconds,
                                "process_tree_rss_bytes": resources()[0],
                            }
                        )
                    if completed < cycles:
                        pipeline._state(State.TRANSCRIBING)
                        assert reference is not None
                        audio = reference.copy()
                        pending = pipeline.executor.submit(
                            pipeline._transcribe, audio, capture_rate
                        )
                        pending.add_done_callback(
                            lambda result: pipeline._post(lambda: pipeline._finish(result))
                        )
                        reached = False
                        return
                    if report is not None:
                        idle_started = time.monotonic()
                        idle_cpu_start = resources()[1]
                        # Reduce observer overhead during the loaded idle window.
                        timer.setInterval(250)
                        return
                timer.stop()
                app.quit()
            elif time.monotonic() - started > 45 * cycles:
                failures.append("Target shutdown stage was not reached.")
                app.quit()

        timer.timeout.connect(poll)
        timer.start()
        last_tick = time.monotonic()  # Exclude fixture generation before the event loop starts.
        code = app.exec()
        timer.stop()
        pipeline.executor.shutdown(wait=True)
        if reference is not None:
            reference.fill(0)
        assert code == 0 and reached and not failures
        assert pipeline.closed and backend.process is None
        if case == "complete":
            result = pending.result()
            assert result.notice in ("Polishing applied.", "Polishing checked; no changes needed.")
            assert "speech" in result.raw.lower()
        else:
            pending.result()  # Do not silently discard unexpected background exceptions.
        assert not desktop.latest.text.toPlainText() and not desktop.latest.raw.toPlainText()
        del desktop
    if report is not None:
        assert len(cycle_metrics) == cycles and peak_rss > 0 and idle_started is not None
        metadata = json.loads((root / "base.en/localphraser-manifest.json").read_text())
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "scope": "Owned synthetic Qt sessions; no microphone or insertion",
                    "os": platform.platform(),
                    "cpu": platform.processor(),
                    "logical_cpus": psutil.cpu_count(),
                    "ram_bytes": psutil.virtual_memory().total,
                    "model": "base.en",
                    "model_revision": metadata["revision"],
                    "cpu_threads": config.cpu_threads,
                    "capture_rate": capture_rate,
                    "cycles": cycle_metrics,
                    "sampled_peak_process_tree_rss_bytes": peak_rss,
                    "max_observed_qt_timer_gap_seconds": max_ui_gap,
                    "loaded_idle_seconds": idle_seconds,
                    "idle_process_tree_cpu_percent_of_one_core": idle_cpu_percent,
                    "sampling": "Qt callback; 100 ms RSS / 10 ms heartbeat active; 250 ms idle",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    print(f"Owned Qt shutdown check passed: {case}; {cycles} cycles; no microphone or insertion.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--temp-dir", type=Path, required=True)
    parser.add_argument("--case", choices=("loading", "polishing", "complete"), required=True)
    parser.add_argument("--cycles", type=int, default=1, help="Repeat complete sessions (1-100)")
    parser.add_argument(
        "--report", type=Path, help="Write metadata-only session resource observations"
    )
    parser.add_argument(
        "--idle-seconds", type=int, default=5, help="Loaded idle observation (1-120)"
    )
    parser.add_argument(
        "--capture-rate", type=int, choices=(16000, 44100, 48000, 96000), default=48000
    )
    args = parser.parse_args()
    check(
        args.root.resolve(),
        args.temp_dir.resolve(),
        args.case,
        args.capture_rate,
        args.cycles,
        args.report,
        args.idle_seconds,
    )
