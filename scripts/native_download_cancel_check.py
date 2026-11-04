"""Explicitly start a tiny.en download, cancel its owned process, and check cleanup.

Requires networking for publisher metadata and possibly partial model bytes. No microphone,
dictation, settings changes, or installed model removal. Use an empty, dedicated model root.
"""

import argparse
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer

from localphraser.downloads import ModelDownload
from localphraser.models import staging_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--executable", type=Path, help="Test a frozen installer instead of source")
    parser.add_argument(
        "--wait-for-progress", action="store_true", help="Wait for model byte progress"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if (root / "tiny.en").exists() or list(root.glob(".*.installing")):
        raise ValueError("Use a dedicated model root without an installed model or partial jobs.")
    app = QCoreApplication([])
    job = ModelDownload()
    if args.executable:
        executable = str(args.executable.resolve())
        job._launch = lambda arguments: job.process.start(executable, arguments)
    results = []
    progress = []
    job.progress.connect(lambda count, total: progress.append((count, total)))
    job.finished.connect(
        lambda installed, cancelled: (results.append((installed, cancelled)), app.quit())
    )
    job.start("tiny.en", root)
    stage = staging_path("tiny.en", root, job.job_id)
    timer = QTimer()
    timer.setInterval(20)

    def cancel_when_ready():
        ready = (stage / ".localphraser-job").exists()
        if args.wait_for_progress:
            ready = any(total and 1_000_000 < count < total for count, total in progress)
        if ready:
            job.cancel()

    timer.timeout.connect(cancel_when_ready)
    timer.start()
    QTimer.singleShot(30000, app.quit)
    app.exec()
    timer.stop()
    job.shutdown()
    assert results == [(False, True)], "Owned CLI download did not complete cancellation"
    assert not stage.exists(), "Owned partial download was not removed"
    if args.wait_for_progress:
        assert any(total and 1_000_000 < count < total for count, total in progress)
        print("Real download byte progress and publisher total size received.")
    print(
        "Real CLI download cancellation and offline cleanup passed; no installed model was removed."
    )


if __name__ == "__main__":
    main()
