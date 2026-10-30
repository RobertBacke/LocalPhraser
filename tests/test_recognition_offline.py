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
    recognizer.warm_preview()
    assert recognizer.preview_ready


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
    assert kwargs["without_timestamps"] is True


@pytest.mark.parametrize("seconds, timestamps_disabled", [(30, True), (31, False), (90, False)])
def test_long_recordings_retain_timestamp_guided_window_advancement(seconds, timestamps_disabled):
    recognizer = WhisperRecognizer(Path("unused-local-model"))
    engine = Mock()
    engine.transcribe.return_value = (iter([SimpleNamespace(text=" Complete message. ")]), None)
    recognizer._model = engine
    assert recognizer.transcribe(np.zeros(seconds * 16000, dtype=np.float32)) == "Complete message."
    assert engine.transcribe.call_args.kwargs["without_timestamps"] is timestamps_disabled


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


def test_recognition_emits_cumulative_completed_segments():
    recognizer = WhisperRecognizer(Path("unused-local-model"))
    recognizer._model = Mock()
    recognizer._model.transcribe.return_value = (
        iter(
            [
                SimpleNamespace(text=" Hello "),
                SimpleNamespace(text=" "),
                SimpleNamespace(text=" world. "),
            ]
        ),
        None,
    )
    previews = []
    assert (
        recognizer.transcribe_stream(np.zeros(16000, dtype=np.float32), previews.append)
        == "Hello world."
    )
    assert previews == ["Hello", "Hello world."]


def test_live_preview_never_loads_a_cold_model_and_reuses_warm_decoder():
    recognizer = WhisperRecognizer(Path("unused"))
    recognizer.prepare = Mock()
    audio = np.zeros(16000, dtype=np.float32)
    assert recognizer.preview(audio) == ""
    recognizer.prepare.assert_not_called()
    engine = Mock()
    engine.transcribe.side_effect = lambda *args, **kw: (
        iter([SimpleNamespace(text=" recent speech ")]),
        None,
    )
    recognizer._model = engine
    assert recognizer.preview(audio) == ""
    engine.transcribe.assert_not_called()
    assert recognizer.transcribe(audio) == "recent speech"
    recognizer.prepare.reset_mock()
    assert recognizer.preview_ready and recognizer.preview(audio) == "recent speech"
    recognizer.prepare.assert_not_called()


def test_empty_vad_result_does_not_enable_first_live_speech_decode():
    recognizer = WhisperRecognizer(Path("unused"))
    recognizer._model = Mock()
    recognizer._model.transcribe.return_value = (iter([]), None)
    audio = np.zeros(16000, dtype=np.float32)
    assert recognizer.transcribe(audio) == "" and not recognizer.preview_ready
    recognizer._model.transcribe.reset_mock()
    assert recognizer.preview(audio) == ""
    recognizer._model.transcribe.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_startup_warmup_initializes_vad_and_decoder_without_retaining_output(fails):
    recognizer = WhisperRecognizer(Path("unused"))
    engine = Mock()
    recognizer._model = engine
    seen = []
    consumed = []

    def decode(audio, **kwargs):
        assert not np.count_nonzero(audio)
        seen.append((audio, kwargs))

        def segments():
            if len(seen) == 2 and fails:
                raise RuntimeError("decoder failed")
            consumed.append(kwargs["vad_filter"])
            yield SimpleNamespace(text="discard this silence hallucination")

        return segments(), None

    engine.transcribe.side_effect = decode
    if fails:
        with pytest.raises(RuntimeError):
            recognizer.warm_preview()
        assert not recognizer.preview_ready
    else:
        assert recognizer.warm_preview() is None
        assert recognizer.preview_ready
        recognizer.warm_preview()
        assert consumed == [True, False]
    assert len(seen) == 2
    assert seen[0][1]["vad_filter"] is True
    assert seen[1][1]["vad_filter"] is False
    assert seen[1][1]["max_new_tokens"] == 1
    assert all(not np.count_nonzero(audio) for audio, _ in seen)
