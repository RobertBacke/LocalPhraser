"""Lazy CPU inference. A model name is never passed to the runtime downloader."""

import os
from pathlib import Path
from typing import Any, Protocol

from localphraser.audio import Audio


class Recognizer(Protocol):
    def prepare(self) -> None: ...
    def transcribe(self, audio: Audio) -> str: ...


class WhisperRecognizer:
    def __init__(self, model_path: Path, cpu_threads: int = 4, vocabulary: str = ""):
        self.path = model_path
        self.cpu_threads = cpu_threads
        self.vocabulary = vocabulary.strip()
        self._model: Any = None

    def prepare(self) -> None:
        """Load verified local weights on the inference worker, before speech is released."""
        # Also protects against optional tokenizer fallbacks contacting the model hub.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        if self._model is None:
            from faster_whisper import WhisperModel

            from localphraser.models import verify_model

            verify_model(self.path)
            self._model = WhisperModel(
                str(self.path),
                device="cpu",
                compute_type="int8",
                cpu_threads=self.cpu_threads,
                num_workers=1,
                local_files_only=True,
            )

    def transcribe(self, audio: Audio) -> str:
        self.prepare()
        segments, _ = self._model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            temperature=0,
            hotwords=self.vocabulary or None,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
