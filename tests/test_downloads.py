import sys
import time

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest

from localphraser.downloads import ModelDownload
from localphraser.models import staging_path

FIXTURE = """
import argparse
import time
from pathlib import Path
from filelock import FileLock
from localphraser.models import cleanup_install, staging_path
parser = argparse.ArgumentParser()
parser.add_argument('command')
parser.add_argument('model')
parser.add_argument('--root', type=Path)
parser.add_argument('--job-id')
args = parser.parse_args()
if args.command == 'cleanup-install':
    cleanup_install(args.model, args.root, args.job_id)
else:
    with FileLock(str(args.root / ('.' + args.model + '.install.lock')), timeout=0):
        stage = staging_path(args.model, args.root, args.job_id)
        stage.mkdir()
        (stage / '.localphraser-job').write_text(args.job_id, encoding='ascii')
        (stage / 'partial.bin').write_bytes(b'synthetic partial model')
        print('Fixture download active', flush=True)
        time.sleep(30)
"""


def wait_for(app, condition):
    deadline = time.monotonic() + 10
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(20)
    assert condition(), "Owned download fixture timed out"


@pytest.fixture
def download(app, tmp_path, monkeypatch):
    script = tmp_path / "fixture.py"
    script.write_text(FIXTURE)
    job = ModelDownload()
    monkeypatch.setattr(
        job, "_launch", lambda args: job.process.start(sys.executable, [str(script), *args])
    )
    yield job
    job.shutdown()
    job.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_real_process_cancellation_cleanup_and_retry(download, app, tmp_path):
    finished = []
    download.finished.connect(lambda success, cancelled: finished.append((success, cancelled)))
    installed = tmp_path / "base.en"
    installed.mkdir()
    (installed / "model.bin").write_bytes(b"installed model fixture")
    for _attempt in range(2):
        download.start("tiny.en", tmp_path)
        stage = staging_path("tiny.en", tmp_path, download.job_id)
        wait_for(app, lambda stage=stage: (stage / "partial.bin").exists())
        with pytest.raises(ValueError):
            download.start("tiny.en", tmp_path)
        download.cancel()
        wait_for(app, lambda: not download.busy)
        assert finished[-1] == (False, True)
        assert not stage.exists()
        assert (installed / "model.bin").read_bytes() == b"installed model fixture"
    assert len(finished) == 2


def test_shutdown_stops_only_owned_download_and_removes_its_stage(download, app, tmp_path):
    download.start("tiny.en", tmp_path)
    stage = staging_path("tiny.en", tmp_path, download.job_id)
    wait_for(app, lambda: (stage / "partial.bin").exists())
    download.shutdown()
    assert not download.busy and not stage.exists()
