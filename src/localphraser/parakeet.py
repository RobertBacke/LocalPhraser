"""Parakeet TDT through ONNX Runtime, loaded only from verified local int8 files."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from localphraser.audio import SAMPLE_RATE, Audio
from localphraser.config import inference_threads

# A type selector for onnx-asr; with an existing local directory it never reaches the hub.
ONNX_MODEL_TYPE = "nemo-parakeet-tdt-0.6b-v2"
PIECE_SECONDS = 30  # Memory grows with clip length; longer recordings are cut.
SEARCH_FROM_SECONDS = 20.0
SEARCH_WINDOW = SAMPLE_RATE // 5  # 200 ms
SEARCH_STEP = SAMPLE_RATE // 100  # 10 ms
PUNCTUATION = ".,;:!?\"'()[]{}…"
MAX_TERM_WORDS = 4


def split_long(audio: Audio) -> list[Audio]:
    """Views of at most 30 s, cut at the quietest 200 ms between 20 s and 30 s of each."""
    limit = PIECE_SECONDS * SAMPLE_RATE
    search_start = int(SEARCH_FROM_SECONDS * SAMPLE_RATE)
    pieces: list[Audio] = []
    start = 0
    while audio.size - start > limit:
        # Temporaries cover only the 10 s search region and are zeroed after use.
        region = audio[start + search_start : start + limit]
        temporaries: list[np.ndarray] = []
        try:
            magnitude = np.abs(region)
            temporaries.append(magnitude)
            totals = np.zeros(region.size + 1, dtype=np.float64)
            temporaries.append(totals)
            sums = np.zeros((region.size - SEARCH_WINDOW) // SEARCH_STEP + 1, dtype=np.float64)
            temporaries.append(sums)
            np.cumsum(magnitude, out=totals[1:])
            np.subtract(
                totals[SEARCH_WINDOW::SEARCH_STEP], totals[:-SEARCH_WINDOW:SEARCH_STEP], out=sums
            )
            quietest = int(np.argmin(sums)) * SEARCH_STEP  # argmin keeps the first on a tie
        finally:
            for temporary in temporaries:
                temporary.fill(0)
        cut = start + search_start + quietest + SEARCH_WINDOW // 2
        pieces.append(audio[start:cut])
        start = cut
    pieces.append(audio[start:])
    return pieces


def _key(text: str) -> str:
    return text.casefold().replace(" ", "").replace("-", "")


def restore_spelling(text: str, vocabulary: str) -> str:
    """Replace spans of up to four words whose letters match an approved term."""
    terms: dict[str, str] = {}
    for entry in vocabulary.split(","):
        term = entry.strip()
        if term and _key(term):
            terms.setdefault(_key(term), term)
    if not terms or not text:
        return text
    words = text.split()
    parts = []
    for word in words:
        core = word.lstrip(PUNCTUATION)
        leading = word[: len(word) - len(core)]
        stripped = core.rstrip(PUNCTUATION)
        parts.append((leading, stripped, core[len(stripped) :]))
    output: list[str] = []
    index = 0
    while index < len(words):
        for length in range(MAX_TERM_WORDS, 0, -1):
            span = parts[index : index + length]
            if len(span) < length or not all(core for _, core, _ in span):
                continue
            # Punctuation facing another word of the span separates it: "local, phraser".
            if any(trailing for _, _, trailing in span[:-1]) or any(
                leading for leading, _, _ in span[1:]
            ):
                continue
            approved = terms.get(_key("".join(core for _, core, _ in span)))
            if approved is not None:
                output.append(span[0][0] + approved + span[-1][2])
                index += length
                break
        else:
            output.append(words[index])
            index += 1
    return " ".join(output)


class ParakeetRecognizer:
    def __init__(self, model_path: Path, cpu_threads: int = 0, vocabulary: str = ""):
        self.path = model_path
        self.cpu_threads = inference_threads(cpu_threads)
        self.vocabulary = vocabulary.strip()
        self._model: Any = None
        self.preview_ready = False

    def prepare(self) -> None:
        """Load verified local weights while microphone capture is stopped."""
        if self._model is None:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            import onnx_asr
            import onnxruntime

            from localphraser.models import verify_model

            verify_model(self.path)
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = self.cpu_threads
            options.inter_op_num_threads = 1
            self._model = onnx_asr.load_model(
                ONNX_MODEL_TYPE,
                str(self.path),
                quantization="int8",
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )

    def transcribe(self, audio: Audio) -> str:
        return self.transcribe_stream(audio)

    def transcribe_stream(self, audio: Audio, partial: Callable[[str], None] | None = None) -> str:
        self.prepare()
        parts: list[str] = []
        for piece in split_long(audio):
            piece_text = self._decode(piece)
            if piece_text:
                parts.append(piece_text)
            if partial is not None and parts:
                partial(restore_spelling(" ".join(parts), self.vocabulary))
        text = restore_spelling(" ".join(parts), self.vocabulary)
        self.preview_ready = self.preview_ready or bool(text)
        return text

    def warm_preview(self) -> None:
        """Initialize the encoder and decoder using discarded local silence."""
        if self.preview_ready:
            return
        self.prepare()
        audio = np.zeros(SAMPLE_RATE, dtype=np.float32)
        try:
            self._decode(audio)  # Silence can produce words; none are displayed or retained.
            self.preview_ready = True
        finally:
            audio.fill(0)

    def preview(self, audio: Audio) -> str:
        if not self.preview_ready or self._model is None:
            return ""
        return restore_spelling(self._decode(audio), self.vocabulary)

    def _decode(self, piece: Audio) -> str:
        return str(self._model.recognize(piece, sample_rate=SAMPLE_RATE)).strip()
