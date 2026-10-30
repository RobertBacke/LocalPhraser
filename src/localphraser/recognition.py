"""Lazy CPU inference. A model name is never passed to the runtime downloader."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from localphraser.audio import SAMPLE_RATE, Audio


class Recognizer(Protocol):
    def prepare(self) -> None: ...
    def transcribe(self, audio: Audio) -> str: ...
    def transcribe_stream(
        self, audio: Audio, partial: Callable[[str], None] | None = None
    ) -> str: ...


class WhisperRecognizer:
    def __init__(self, model_path: Path, cpu_threads: int = 4, vocabulary: str = ""):
        self.path = model_path
        self.cpu_threads = cpu_threads
        self.vocabulary = vocabulary.strip()
        self._model: Any = None
        self.preview_ready = False

    def prepare(self) -> None:
        """Load verified local weights while microphone capture is stopped."""
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
        return self.transcribe_stream(audio)

    def transcribe_stream(self, audio: Audio, partial: Callable[[str], None] | None = None) -> str:
        self.prepare()
        text = self._decode(audio, partial)
        self.preview_ready = self.preview_ready or bool(text)
        return text

    def warm_preview(self) -> None:
        """Initialize VAD and the speech decoder using discarded local silence."""
        if self.preview_ready:
            return
        self.prepare()
        audio = np.zeros(16000, dtype=np.float32)
        try:
            self._decode(audio)  # Initialize the VAD path, even without detected speech.
            segments, _ = self._model.transcribe(
                audio,
                language="en",
                beam_size=1,
                vad_filter=False,
                condition_on_previous_text=False,
                temperature=0,
                max_new_tokens=1,
            )
            for _ in segments:
                pass  # Silence can produce words; none are displayed or retained.
            self.preview_ready = True
        finally:
            audio.fill(0)

    def preview(self, audio: Audio) -> str:
        # Cold imports/VAD initialization previously starved microphone callbacks.
        if not self.preview_ready or self._model is None:
            return ""
        return self._decode(audio)

    def _decode(self, audio: Audio, partial: Callable[[str], None] | None = None) -> str:
        segments, _ = self._model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            temperature=0,
            # Long recordings need timestamp-guided window advancement to avoid repetition.
            without_timestamps=audio.size <= 30 * SAMPLE_RATE,
            hotwords=self.vocabulary or None,
        )
        parts = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)
                if partial is not None:
                    partial(" ".join(parts))
        return " ".join(parts)
