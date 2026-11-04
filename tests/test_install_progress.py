import json
import time
from unittest.mock import Mock

from localphraser.config import Config
from localphraser.downloads import ModelDownload
from localphraser.install_progress import PREFIX, TransferProgress, partial_bytes
from localphraser.ui import Settings


def test_partial_progress_counts_transfer_bytes_not_cache_metadata(tmp_path):
    cache = tmp_path / ".cache/huggingface/download"
    cache.mkdir(parents=True)
    (cache / "model.hash.incomplete").write_bytes(b"x" * 27)
    (cache / "model.metadata").write_bytes(b"x" * 100)
    assert partial_bytes(tmp_path) == 27
    (cache / "model.hash.incomplete").rename(tmp_path / "model.bin")
    assert partial_bytes(tmp_path) == 0


def test_watcher_reports_real_bytes_and_stops_before_stage_promotion(tmp_path, capsys):
    cache = tmp_path / ".cache/huggingface/download"
    cache.mkdir(parents=True)
    (cache / "model.hash.incomplete").write_bytes(b"x" * 27)
    with TransferProgress(tmp_path, 10, 100) as watcher:
        time.sleep(0.45)
    assert not watcher.thread.is_alive()
    reports = [json.loads(line[len(PREFIX) :]) for line in capsys.readouterr().out.splitlines()]
    assert reports[0] == {"completed": 10, "total": 100}
    assert {"completed": 37, "total": 100} in reports


def test_fragmented_process_progress_large_bytes_and_cancelled_output(app):
    job = ModelDownload()
    job.phase = "download"
    received, messages = [], []
    job.progress.connect(lambda count, total: received.append((count, total)))
    job.message.connect(messages.append)
    line = PREFIX + json.dumps({"completed": 3_000_000_000, "total": 4_000_000_000})
    job._consume(line[:24])
    assert received == []
    job._consume(line[24:] + "\r\nVerifying model.bin…\n")
    assert received == [(3_000_000_000, 4_000_000_000)]
    assert messages == ["Verifying model.bin…"]
    for payload in ["null", "[]", '{"completed": true,"total":5}', '{"completed":6,"total":5}']:
        job._consume(PREFIX + payload + "\n")
    job.cancelled = True
    job._consume(line + "\n")
    assert len(received) == 1
    job.phase = "idle"


def test_settings_progress_unknown_total_large_model_and_terminal_states(app, monkeypatch):
    monkeypatch.setattr("localphraser.ui.microphones", lambda: [])
    settings = Settings(Config(), Mock())
    try:
        settings.update_download_progress(0, None)
        assert settings.download_bar.maximum() == 0
        settings.update_download_progress(3_000_000_000, 4_000_000_000)
        assert settings.download_bar.value() == 750
        assert settings.download_bytes.text() == "3.00 GB / 4.00 GB"
        settings.download_finished(True, False)
        assert settings.download_bar.format() == "Installed and verified"
        settings.update_download_progress(0, None)
        settings.download_finished(False, True)
        assert settings.download_bar.isHidden() and settings.download_bytes.isHidden()
    finally:
        settings.deleteLater()
