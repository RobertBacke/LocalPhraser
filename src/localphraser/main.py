"""Visible first-launch/manual model setup is separate from offline dictation."""

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

from localphraser.config import (
    DEFAULT_REFINEMENT_MODEL,
    MODELS,
    REFINEMENT_MODELS,
    data_dir,
    load_config,
    save_config,
)


def main() -> int:
    # pythonw.exe at sign-in also has absent standard streams, just like the
    # frozen windowed build. Keep libraries usable without creating log files.
    for name, mode in (("stdout", "w"), ("stderr", "w"), ("stdin", "r")):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, mode, encoding="utf-8"))
    parser = argparse.ArgumentParser(description="LocalPhraser offline Windows dictation")
    subparsers = parser.add_subparsers(dest="command")
    install = subparsers.add_parser("install-model", help="Explicitly download a speech model")
    install.add_argument("model", choices=MODELS, nargs="?", default="base.en")
    install.add_argument("--root", type=Path, default=data_dir() / "models")
    install.add_argument("--job-id", help=argparse.SUPPRESS)
    verify = subparsers.add_parser("verify-model", help="Check model integrity without networking")
    verify.add_argument("model", choices=MODELS, nargs="?", default="base.en")
    verify.add_argument("--root", type=Path, default=data_dir() / "models")
    polish_install = subparsers.add_parser(
        "install-refiner", help="Download a local polishing model"
    )
    polish_install.add_argument(
        "model", choices=REFINEMENT_MODELS, nargs="?", default=DEFAULT_REFINEMENT_MODEL
    )
    polish_install.add_argument("--root", type=Path, default=data_dir() / "models")
    polish_install.add_argument("--job-id", help=argparse.SUPPRESS)
    cleanup = subparsers.add_parser("cleanup-install", help="Clean one cancelled download job")
    cleanup.add_argument("model", choices=(*MODELS, *REFINEMENT_MODELS))
    cleanup.add_argument("--root", type=Path, required=True)
    cleanup.add_argument("--job-id", required=True)
    polish_verify = subparsers.add_parser("verify-refiner", help="Verify a local polishing model")
    polish_verify.add_argument(
        "model", choices=REFINEMENT_MODELS, nargs="?", default=DEFAULT_REFINEMENT_MODEL
    )
    polish_verify.add_argument("--root", type=Path, default=data_dir() / "models")
    polish_check = subparsers.add_parser("check-refiner", help="Offline synthetic polishing check")
    polish_check.add_argument(
        "model", choices=REFINEMENT_MODELS, nargs="?", default=DEFAULT_REFINEMENT_MODEL
    )
    polish_check.add_argument("--root", type=Path, default=data_dir() / "models")
    parser.add_argument("--config", type=Path, default=data_dir() / "config.json")
    parser.add_argument(
        "--smoke-test", action="store_true", help="Launch briefly without microphone use"
    )
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    if args.command == "cleanup-install":
        from localphraser.models import cleanup_install

        os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            cleanup_install(args.model, args.root, args.job_id)
            return 0
        except Exception:
            print(
                "Partial download cleanup failed; installed models were not removed.",
                file=sys.stderr,
            )
            return 1
    if args.command == "check-refiner":
        import json
        import time

        from localphraser.config import DEFAULT_PROMPT
        from localphraser.refinement import LocalRefiner

        backend = LocalRefiner(args.model, args.root, 4, DEFAULT_PROMPT, 15)
        try:
            timings = []
            for _ in range(2):
                started = time.perf_counter()
                backend.refine("hello world this is local dictation")
                timings.append(round(time.perf_counter() - started, 3))
            print(json.dumps({"offline_polishing_check": "passed", "seconds": timings}))
            return 0
        except Exception:
            print("Offline polishing check failed. Verify the runtime and model.", file=sys.stderr)
            return 1
        finally:
            backend.close()
    if args.command in ("install-refiner", "verify-refiner"):
        from localphraser.refinement_models import install_refiner, verify_refiner

        os.environ["HF_HUB_OFFLINE"] = "0" if args.command == "install-refiner" else "1"
        try:
            operation = install_refiner if args.command == "install-refiner" else verify_refiner
            if args.command == "install-refiner" and args.job_id:
                install_refiner(args.model, args.root, job_id=args.job_id)
            else:
                operation(args.model, args.root)
        except Exception:
            print(
                "Polishing model operation failed. Check model files or download connectivity.",
                file=sys.stderr,
            )
            return 1
        print("Polishing model verified.")
        return 0
    if args.command == "install-model":
        # A downloader launched by the offline desktop inherits its environment.
        # Only this explicit, separate entry point is permitted to go online.
        os.environ["HF_HUB_OFFLINE"] = "0"
        from localphraser.models import install_model

        try:
            if args.job_id:
                install_model(args.model, args.root, job_id=args.job_id)
            else:
                install_model(args.model, args.root)
        except Exception:
            print(
                "Model installation failed. Check connectivity, disk space, and model directory.",
                file=sys.stderr,
            )
            return 1
        return 0
    os.environ["HF_HUB_OFFLINE"] = "1"
    if args.command == "verify-model":
        from localphraser.models import verify_model

        try:
            verify_model(args.root / args.model)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print("Model verified locally.")
        return 0
    if sys.platform != "win32":
        parser.error("Desktop integration currently supports Windows 10/11 only.")
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

    from localphraser.ui import Desktop, app_icon

    app = QApplication(sys.argv[:1])
    app.setApplicationName("LocalPhraser")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    directory = args.config.parent
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / "localphraser.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(
            None, "LocalPhraser", "LocalPhraser is already running for this configuration."
        )
        return 1
    if not QSystemTrayIcon.isSystemTrayAvailable() and not args.smoke_test:
        QMessageBox.warning(None, "LocalPhraser", "A Windows system tray is required.")
        return 1
    first_launch = not args.config.exists() and not args.smoke_test
    try:
        config = load_config(args.config)
        # Persist before starting setup: failure/cancellation must not cause automatic
        # networking again on every launch. Existing profiles are never overwritten.
        if first_launch:
            save_config(config, args.config)
    except (ValueError, OSError) as exc:
        QMessageBox.warning(None, "Invalid settings", str(exc))
        return 1
    if args.smoke_test:
        config = replace(config, keep_microphone_ready=False)
    desktop = Desktop(app, config, args.config, first_launch=first_launch)
    if args.smoke_test:
        QTimer.singleShot(1500, app.quit)
    code = app.exec()
    # Keep desktop and lock alive until the Qt event loop has shut down.
    del desktop
    lock.unlock()
    return code
