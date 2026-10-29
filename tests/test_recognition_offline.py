"""Opt-in real local engine check; no microphone or personal speech required."""

import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from localphraser.recognition import WhisperRecognizer


@pytest.mark.skipif(
    not os.environ.get("LOCALPHRASER_TEST_MODEL"), reason="No local test model selected"
)
def test_real_model_load_and_vad_with_network_denied(monkeypatch):
    # Import the libraries first; deny actual socket connections, not Python class creation.
    import faster_whisper  # noqa: F401

    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    recognizer = WhisperRecognizer(
        Path(os.environ["LOCALPHRASER_TEST_MODEL"]), vocabulary="Codex, PySide"
    )
    assert recognizer.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    assert recognizer._model is not None


@pytest.mark.parametrize(
    "vocabulary, expected", [("", None), ("  Codex, PySide  ", "Codex, PySide")]
)
def test_hints_reach_engine_without_replacing_recognized_words(vocabulary, expected):
    recognizer = WhisperRecognizer(Path("unused-local-model"), vocabulary=vocabulary)
    engine = Mock()
    # A hint must not trigger a blind replacement of a valid recognized word.
    engine.transcribe.return_value = (iter([SimpleNamespace(text=" Codecs are useful. ")]), None)
    recognizer._model = engine
    audio = np.zeros(16000, dtype=np.float32)
    assert recognizer.transcribe(audio) == "Codecs are useful."
    args, kwargs = engine.transcribe.call_args
    assert args[0] is audio
    assert kwargs["hotwords"] == expected
    assert kwargs["vad_filter"] is True


def test_prepare_loads_local_model_once_without_inference(monkeypatch, tmp_path):
    verify = Mock()
    factory = Mock()
    factory.return_value.transcribe.return_value = (iter([]), None)
    monkeypatch.setattr("localphraser.models.verify_model", verify)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=factory))
    recognizer = WhisperRecognizer(tmp_path, cpu_threads=2)
    recognizer.prepare()
    recognizer.prepare()
    factory.return_value.transcribe.assert_not_called()
    assert recognizer.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    verify.assert_called_once_with(tmp_path)
    factory.assert_called_once_with(
        str(tmp_path),
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        num_workers=1,
        local_files_only=True,
    )
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_failed_prepare_can_retry_at_transcription(monkeypatch, tmp_path):
    monkeypatch.setattr("localphraser.models.verify_model", Mock())
    engine = Mock()
    engine.transcribe.return_value = (iter([]), None)
    factory = Mock(side_effect=[OSError("loading failed"), engine])
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=factory))
    recognizer = WhisperRecognizer(tmp_path)
    with pytest.raises(OSError):
        recognizer.prepare()
    assert recognizer._model is None
    assert recognizer.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    assert factory.call_count == 2
