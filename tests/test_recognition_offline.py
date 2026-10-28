"""Opt-in real local engine check; no microphone or personal speech required."""

import os
import socket
from pathlib import Path

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
    recognizer = WhisperRecognizer(Path(os.environ["LOCALPHRASER_TEST_MODEL"]))
    assert recognizer.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    assert recognizer._model is not None
