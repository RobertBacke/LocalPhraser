"""Entry points separate explicit online installation from offline desktop operation."""

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

from localphraser.config import MODELS, data_dir, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="LocalPhraser offline Windows dictation")
    subparsers = parser.add_subparsers(dest="command")
    install = subparsers.add_parser("install-model", help="Explicitly download a speech model")
    install.add_argument("model", choices=MODELS, nargs="?", default="base.en")
    install.add_argument("--root", type=Path, default=data_dir() / "models")
    verify = subparsers.add_parser("verify-model", help="Check model integrity without networking")
    verify.add_argument("model", choices=MODELS, nargs="?", default="base.en")
    verify.add_argument("--root", type=Path, default=data_dir() / "models")
    parser.add_argument("--config", type=Path, default=data_dir() / "config.json")
    parser.add_argument(
        "--smoke-test", action="store_true", help="Launch briefly without microphone use"
    )
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    if args.command == "install-model":
        # A downloader launched by the offline desktop inherits its environment.
        # Only this explicit, separate entry point is permitted to go online.
        os.environ["HF_HUB_OFFLINE"] = "0"
        from localphraser.models import install_model

        try:
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
    try:
        config = load_config(args.config)
    except ValueError as exc:
        QMessageBox.warning(None, "Invalid settings", str(exc))
        return 1
    if args.smoke_test:
        config = replace(config, keep_microphone_ready=False)
    desktop = Desktop(app, config, args.config)
    if args.smoke_test:
        QTimer.singleShot(1500, app.quit)
    code = app.exec()
    # Keep desktop and lock alive until the Qt event loop has shut down.
    del desktop
    lock.unlock()
    return code
