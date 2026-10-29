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
    job.finished.connect(
        lambda installed, cancelled: (results.append((installed, cancelled)), app.quit())
    )
    job.start("tiny.en", root)
    stage = staging_path("tiny.en", root, job.job_id)
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: job.cancel() if (stage / ".localphraser-job").exists() else None)
    timer.start()
    QTimer.singleShot(30000, app.quit)
    app.exec()
    timer.stop()
    job.shutdown()
    assert results == [(False, True)], "Owned CLI download did not complete cancellation"
    assert not stage.exists(), "Owned partial download was not removed"
    print(
        "Real CLI download cancellation and offline cleanup passed; no installed model was removed."
    )


if __name__ == "__main__":
    main()
