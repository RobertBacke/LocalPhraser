import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest

from localphraser import diagnostics
from localphraser.main import main


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    audio = np.ones(16000, dtype=np.float32)
    monkeypatch.setattr(diagnostics, "verify_model", Mock())
    monkeypatch.setattr(diagnostics, "synthetic_audio", lambda directory, rate: audio)
    recognizer = Mock()
    recognizer.transcribe.return_value = "local speech recognition keeps my words on this computer"
    monkeypatch.setattr(diagnostics, "make_recognizer", Mock(return_value=recognizer))
    refiner = Mock()
    refiner.refine.side_effect = lambda text: text.capitalize() + "."
    factory = Mock(return_value=refiner)
    monkeypatch.setattr(diagnostics, "LocalRefiner", factory)
    return tmp_path, audio, recognizer, refiner, factory


def test_raw_checks_cold_warm_without_loading_refiner_or_saving_transcript(runtime):
    root, audio, recognizer, _, factory = runtime
    report = root / "report.json"
    assert diagnostics.write_runtime_report(report, root / "models", "base.en", None) == 0
    result = json.loads(report.read_text())
    assert result["status"] == "passed" and len(result["checks"]) == 2
    assert recognizer.transcribe.call_count == 2
    diagnostics.make_recognizer.assert_called_once_with(
        root / "models", "base.en", 0, "", "balanced"
    )
    factory.assert_not_called()
    assert not audio.any()
    assert "my words" not in report.read_text() and str(root) not in report.read_text()


def test_polished_preservation_and_cleanup(runtime):
    root, audio, _, refiner, _ = runtime
    result = diagnostics.runtime_check(root, "base.en", "qwen2.5-1.5b", root)
    assert result["status"] == "passed"
    refiner.prepare.assert_called_once()
    assert refiner.refine.call_count == 2
    refiner.close.assert_called_once()
    assert not audio.any()


def test_synthetic_native_rate_is_converted_before_recognition(runtime, monkeypatch):
    root, _, recognizer, _, _ = runtime
    native = np.ones(48000, dtype=np.float32)
    monkeypatch.setattr(diagnostics, "synthetic_audio", lambda directory, rate: native)
    observed = []

    def transcribe(audio):
        assert audio.shape == (16000,)
        observed.append(audio)
        return "speech on this computer"

    recognizer.transcribe.side_effect = transcribe
    result = diagnostics.runtime_check(root, "base.en", None, root, 48000)
    assert result["status"] == "passed" and result["synthetic_capture_rate"] == 48000
    assert not native.any() and not observed[0].any()


def test_private_error_text_is_not_serialized_and_buffers_are_cleared(runtime):
    root, audio, recognizer, refiner, _ = runtime
    recognizer.transcribe.side_effect = RuntimeError("private exception text and C:/private/path")
    report = root / "failed.json"
    assert diagnostics.write_runtime_report(report, root, "base.en", "qwen2.5-1.5b") == 1
    assert "private" not in report.read_text()
    assert json.loads(report.read_text())["stage"] == "recognition"
    assert not audio.any()
    refiner.close.assert_called_once()


def test_refiner_word_change_is_failure_in_diagnostic(runtime):
    root, _, _, refiner, _ = runtime
    refiner.refine.side_effect = None
    refiner.refine.return_value = "Different words."
    result = diagnostics.runtime_check(root, "base.en", "qwen2.5-1.5b", root)
    assert result["status"] == "failed" and result["stage"] == "polishing"
    refiner.close.assert_called_once()


def test_network_is_denied_and_socket_patches_are_restored(runtime):
    root, _, recognizer, _, _ = runtime
    previous = socket.socket.connect

    def connect(*args):
        with socket.socket() as connection:
            connection.connect(("127.0.0.1", 9))

    recognizer.transcribe.side_effect = connect
    result = diagnostics.runtime_check(root, "base.en", None, root)
    assert result["status"] == "failed"
    assert socket.socket.connect is previous


def test_existing_file_is_never_overwritten_or_used_to_start_checks(runtime, monkeypatch):
    root, _, _, _, _ = runtime
    report = root / "config.json"
    report.write_text("existing settings")
    check = Mock()
    monkeypatch.setattr(diagnostics, "runtime_check", check)
    with pytest.raises(FileExistsError):
        diagnostics.write_runtime_report(report, root, "base.en", None)
    assert report.read_text() == "existing settings"
    check.assert_not_called()


def test_cleanup_failure_is_reflected_in_report(runtime):
    root, _, _, refiner, _ = runtime
    refiner.close.side_effect = RuntimeError("fixture cleanup error")
    result = diagnostics.runtime_check(root, "base.en", "qwen2.5-1.5b", root)
    assert result["status"] == "failed" and result["stage"] == "cleanup"


def test_missing_models_write_failure_without_audio_or_downloads(tmp_path, monkeypatch):
    audio = Mock(side_effect=AssertionError("Synthetic speech started without a model"))
    monkeypatch.setattr(diagnostics, "synthetic_audio", audio)
    report = tmp_path / "failure.json"
    root = tmp_path / "missing-models"
    monkeypatch.setattr(
        sys, "argv", ["localphraser", "check-runtime", "--root", str(root), "--report", str(report)]
    )
    assert main() == 1
    assert json.loads(report.read_text())["stage"] == "model_verification"
    assert not root.exists()
    audio.assert_not_called()


def _fake_sapi(monkeypatch, tmp_path):
    spoken = []
    voice = Mock()
    voice.Speak.side_effect = lambda *args: spoken.append(args)
    stream = Mock()
    stream.Open.side_effect = lambda path, *_: Path(path).write_bytes(b"")
    created = {"SAPI.SpVoice": voice, "SAPI.SpFileStream": stream}
    client = SimpleNamespace(CreateObject=lambda name, **_: created[name])
    monkeypatch.setitem(sys.modules, "comtypes", SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "comtypes.client", client)
    container = MagicMock()
    container.__enter__.return_value.decode.return_value = []
    resampler = Mock()
    resampler.resample.return_value = [
        SimpleNamespace(to_ndarray=lambda: np.ones((1, 8), dtype=np.float32))
    ]
    av = SimpleNamespace(open=lambda path: container, AudioResampler=lambda **_: resampler)
    monkeypatch.setitem(sys.modules, "av", av)
    return spoken


def test_synthetic_audio_speaks_given_text_as_xml(monkeypatch, tmp_path):
    spoken = _fake_sapi(monkeypatch, tmp_path)
    audio = diagnostics.synthetic_audio(tmp_path, text="x", xml=True)
    assert spoken == [("x", 8)] and audio.dtype == np.float32


def test_synthetic_audio_defaults_to_synthetic_text_without_flag(monkeypatch, tmp_path):
    spoken = _fake_sapi(monkeypatch, tmp_path)
    diagnostics.synthetic_audio(tmp_path)
    assert spoken == [(diagnostics.SYNTHETIC_TEXT,)]
