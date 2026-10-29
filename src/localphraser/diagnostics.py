"""Explicit synthetic runtime checks. Never capture a microphone or retain transcripts."""

import json
import os
import platform
import socket
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from localphraser import __version__
from localphraser.audio import Audio
from localphraser.config import DEFAULT_PROMPT
from localphraser.models import verify_model
from localphraser.recognition import WhisperRecognizer
from localphraser.refinement import LocalRefiner, preserve_words

SYNTHETIC_TEXT = "Local speech recognition keeps my words on this computer."


def synthetic_audio(directory: Path) -> Audio:
    """Use an installed Windows SAPI voice; remove its generated WAV before inference."""
    import av
    import comtypes.client

    with tempfile.TemporaryDirectory(prefix="localphraser-synthetic-", dir=directory) as temporary:
        wav = Path(temporary) / "synthetic.wav"
        voice = comtypes.client.CreateObject("SAPI.SpVoice", dynamic=True)
        stream = comtypes.client.CreateObject("SAPI.SpFileStream", dynamic=True)
        stream.Open(str(wav), 3, False)
        try:
            voice.AudioOutputStream = stream
            voice.Speak(SYNTHETIC_TEXT)
        finally:
            stream.Close()
        with av.open(str(wav)) as container:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            arrays = [
                frame.to_ndarray().flatten()
                for incoming in container.decode(audio=0)
                for frame in resampler.resample(incoming)
            ]
            arrays.extend(frame.to_ndarray().flatten() for frame in resampler.resample(None))
        return np.concatenate(arrays).astype(np.float32)


def deny_connection(*args: object, **kwargs: object) -> None:
    raise RuntimeError("Runtime check attempted a Python network connection.")


def runtime_check(root: Path, model: str, refiner_model: str | None, temporary: Path) -> dict:
    result: dict[str, Any] = {
        "schema": 1,
        "application_version": __version__,
        "system": platform.system(),
        "system_version": platform.version(),
        "python": platform.python_version(),
        "speech_model": model,
        "polishing_model": refiner_model,
        "status": "failed",
        "stage": "model_verification",
        "checks": [],
        "scope": "Fixed synthetic speech only; no microphone, insertion, downloads "
        "or saved transcript. Python socket connections denied; not a native-library "
        "packet audit or accuracy benchmark.",
    }
    audio: Audio | None = None
    refiner = None
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    with (
        patch.object(socket.socket, "connect", deny_connection),
        patch.object(socket.socket, "connect_ex", deny_connection),
    ):
        try:
            verify_model(root / model)
            if refiner_model:
                refiner = LocalRefiner(refiner_model, root, 4, DEFAULT_PROMPT, 30)
                refiner.prepare()
            result["stage"] = "synthetic_speech"
            audio = synthetic_audio(temporary)
            recognizer = WhisperRecognizer(root / model)
            for label in ("cold", "warm"):
                result["stage"] = "recognition"
                started = time.perf_counter()
                text = recognizer.transcribe(audio)
                entry = {"run": label, "asr_seconds": round(time.perf_counter() - started, 3)}
                if not all(word in text.lower() for word in ("speech", "computer")):
                    raise ValueError("Synthetic content check failed.")
                if refiner is not None:
                    result["stage"] = "polishing"
                    started = time.perf_counter()
                    polished = refiner.refine(text)
                    if not preserve_words(text, polished):
                        raise ValueError("Polishing preservation check failed.")
                    entry["polish_seconds"] = round(time.perf_counter() - started, 3)
                    polished = ""
                text = ""
                result["checks"].append(entry)
            result["status"], result["stage"] = "passed", "complete"
        except Exception:
            # Stage names are fixed. Never serialize exception messages, local paths,
            # recognition output, or text retained inside a failing library.
            pass
        finally:
            if audio is not None:
                audio.fill(0)
            if refiner is not None:
                try:
                    refiner.close()
                except Exception:
                    result["status"], result["stage"] = "failed", "cleanup"
    return result


def write_runtime_report(report: Path, root: Path, model: str, refiner: str | None) -> int:
    if report.suffix.lower() != ".json":
        raise ValueError("Choose a new JSON report file.")
    report.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation refuses existing settings, model files or earlier reports.
    with report.open("x", encoding="utf-8") as stream:
        result = runtime_check(root, model, refiner, report.parent)
        json.dump(result, stream, indent=2)
        stream.write("\n")
    return 0 if result["status"] == "passed" else 1
