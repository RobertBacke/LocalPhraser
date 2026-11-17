"""Parakeet recogniser: long-recording cuts, spelling restore and offline local loading."""

import os
import socket
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from localphraser.parakeet import ParakeetRecognizer, restore_spelling, split_long
from localphraser.recognition import WhisperRecognizer, make_recognizer

RATE = 16000


def test_short_audio_is_one_piece():
    audio = np.zeros(30 * RATE, dtype=np.float32)
    assert [p.size for p in split_long(audio)] == [30 * RATE]


def test_long_audio_is_cut_at_the_quietest_window_between_20_and_30_seconds():
    rng = np.random.default_rng(0)
    audio = rng.normal(0, 0.05, 70 * RATE).astype(np.float32)
    audio[int(24.0 * RATE) : int(24.4 * RATE)] = 0  # a pause
    pieces = split_long(audio)
    assert abs(pieces[0].size - int(24.2 * RATE)) <= int(0.11 * RATE)
    assert all(p.size <= 30 * RATE for p in pieces)
    assert np.array_equal(np.concatenate(pieces), audio)
    assert all(np.shares_memory(p, audio) for p in pieces)


def test_steady_noise_and_exact_boundary_still_cover_every_sample_once():
    rng = np.random.default_rng(1)
    for seconds in (30, 30.01, 95):
        audio = rng.normal(0, 0.05, int(seconds * RATE)).astype(np.float32)
        pieces = split_long(audio)
        assert np.array_equal(np.concatenate(pieces), audio)
        assert all(0 < p.size <= 30 * RATE for p in pieces)


@pytest.mark.parametrize(
    "text,vocabulary,expected",
    [
        ("I use local phraser daily.", "LocalPhraser", "I use LocalPhraser daily."),
        ("pyside, and Codex.", "PySide, Codex", "PySide, and Codex."),
        ("(local-phraser)", "LocalPhraser", "(LocalPhraser)"),
        ("the local, phraser", "LocalPhraser", "the local, phraser"),
        ("local phrase", "LocalPhraser", "local phrase"),
        ("we tried c++ and Node.JS.", "C++, node.js", "we tried C++ and node.js."),
        ("new york city is big", "New York, New York City", "New York City is big"),
        ("nothing to change", "", "nothing to change"),
        ("", "LocalPhraser", ""),
    ],
)
def test_restore_spelling(text, vocabulary, expected):
    assert restore_spelling(text, vocabulary) == expected


def test_transcribe_decodes_pieces_in_order_and_reports_partials():
    recognizer = ParakeetRecognizer(Path("unused"), vocabulary="LocalPhraser")
    recognizer._model = Mock(recognize=Mock(side_effect=[" one local", "phraser two ", "three"]))
    rng = np.random.default_rng(2)
    partials: list[str] = []
    text = recognizer.transcribe_stream(
        rng.normal(0, 0.05, 70 * RATE).astype(np.float32), partials.append
    )
    assert text == "one LocalPhraser two three"
    assert partials[-1] == text and len(partials) == 3
    calls = recognizer._model.recognize.call_args_list
    assert all(c.kwargs == {"sample_rate": 16000} for c in calls)


def test_partials_start_only_once_there_is_text():
    recognizer = ParakeetRecognizer(Path("unused"))
    recognizer._model = Mock(recognize=Mock(side_effect=["  ", "two", "three"]))
    rng = np.random.default_rng(3)
    partials: list[str] = []
    text = recognizer.transcribe_stream(
        rng.normal(0, 0.05, 70 * RATE).astype(np.float32), partials.append
    )
    assert text == "two three"
    assert partials == ["two", "two three"]


def test_cut_search_zeroes_its_first_temporary_when_a_later_allocation_fails(monkeypatch):
    from localphraser import parakeet

    made: list[np.ndarray] = []

    class FailingNumpy:
        def __getattr__(self, name):
            return getattr(np, name)

        def abs(self, values):
            made.append(np.abs(values))
            return made[-1]

        def zeros(self, *args, **kwargs):
            raise MemoryError("fixture allocation failure")

    monkeypatch.setattr(parakeet, "np", FailingNumpy())
    audio = np.random.default_rng(4).normal(0, 0.05, 40 * RATE).astype(np.float32)
    with pytest.raises(MemoryError):
        split_long(audio)
    assert len(made) == 1 and not made[0].any()


def test_prepare_verifies_then_loads_local_int8_files_offline(monkeypatch, tmp_path):
    import onnx_asr

    order: list[str] = []
    verify = Mock(side_effect=lambda path: order.append("verify"))
    load = Mock(side_effect=lambda *args, **kwargs: order.append("load") or Mock())
    monkeypatch.setattr("localphraser.models.verify_model", verify)
    monkeypatch.setattr(onnx_asr, "load_model", load)
    monkeypatch.setattr("localphraser.config.thread_limit", lambda: 6)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_TELEMETRY", raising=False)

    recognizer = ParakeetRecognizer(tmp_path, cpu_threads=16)
    recognizer.prepare()

    verify.assert_called_once_with(tmp_path)
    assert order == ["verify", "load"]
    assert load.call_args.args == ("nemo-parakeet-tdt-0.6b-v2", str(tmp_path))
    kwargs = load.call_args.kwargs
    assert kwargs["quantization"] == "int8"
    assert kwargs["providers"] == ["CPUExecutionProvider"]
    assert kwargs["sess_options"].intra_op_num_threads == 6
    assert kwargs["sess_options"].inter_op_num_threads == 1
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"
    recognizer.prepare()
    assert load.call_count == 1 and verify.call_count == 1


def test_preview_is_empty_until_warm_then_decodes_without_cutting():
    recognizer = ParakeetRecognizer(Path("unused"))
    recognizer._model = Mock(recognize=Mock(return_value="words"))
    assert recognizer.preview(np.zeros(RATE, dtype=np.float32)) == ""
    recognizer._model.recognize.assert_not_called()
    recognizer.warm_preview()
    assert recognizer.preview_ready
    long = np.zeros(40 * RATE, dtype=np.float32)
    assert recognizer.preview(long) == "words"
    assert recognizer._model.recognize.call_args.args[0] is long


@pytest.mark.skipif(
    not os.environ.get("LOCALPHRASER_TEST_PARAKEET"), reason="No local Parakeet model"
)
def test_real_parakeet_loads_and_hears_nothing_in_silence_with_network_denied(monkeypatch):
    # Import the libraries first; deny actual socket connections, not Python class creation.
    import onnx_asr  # noqa: F401
    import onnxruntime  # noqa: F401

    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")
    recognizer = ParakeetRecognizer(Path(os.environ["LOCALPHRASER_TEST_PARAKEET"]))
    assert recognizer.transcribe(np.zeros(RATE, dtype=np.float32)) == ""


def test_factory_picks_the_engine_by_model_name(tmp_path):
    parakeet = make_recognizer(tmp_path, "parakeet-tdt-0.6b-v2", 0, "A", "fast")
    assert isinstance(parakeet, ParakeetRecognizer)
    assert parakeet.path == tmp_path / "parakeet-tdt-0.6b-v2" and parakeet.vocabulary == "A"
    whisper = make_recognizer(tmp_path, "small.en", 0, "A", "fast")
    assert isinstance(whisper, WhisperRecognizer) and whisper.path == tmp_path / "small.en"
    assert whisper.beam_size == 1 and whisper.vocabulary == "A"
