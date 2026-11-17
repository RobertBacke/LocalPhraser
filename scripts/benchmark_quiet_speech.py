"""Synthetic quiet and paused speech benchmark; no microphone, no recognised text kept.

Speech is Windows SAPI speech with a key click and background noise added, at several
peak levels, continuous and with 700 ms between words. JSON goes to stdout, progress to
stderr. The clip recipe is the appendix of docs/superpowers/specs/2026-11-16-recognition-
accuracy-design.md.
"""

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from localphraser import diagnostics
from localphraser.config import MODELS
from localphraser.recognition import (
    SAMPLE_RATE,
    Recognizer,
    WhisperRecognizer,
    make_recognizer,
)

SENTENCES = (
    "I think we should move the meeting to Thursday afternoon because several people are away",
    "Please remind me to call the dentist tomorrow morning before I leave for work",
    "The new version fixes the problem where the window would not open after a restart",
    "Can you send me the notes from yesterday so I can read them on the train",
    "We need to order more paper and a new keyboard for the front desk",
    "It was not the first time the delivery arrived late and nobody told us",
)
LEVELS = (0.25, 0.02, 0.014, 0.011, 0.008)
NOISE_RMS = 0.002
LONG_SECONDS = 128
RETRY_TEMPERATURES = (0.0, 0.2, 0.4)
SCOPE = (
    "Synthetic Windows SAPI speech with a key click and white noise; words invented on "
    "noise-only clips; no microphone. Errors are word edits per 100 reference words."
)


def paused_markup(text: str) -> str:
    return '<rate speed="-3">' + ' <silence msec="700"/> '.join(text.split()) + "</rate>"


def words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """(word edit distance, number of reference words)."""
    ref, hyp = words(reference), words(hypothesis)
    previous = list(range(len(hyp) + 1))
    for i, expected in enumerate(ref, 1):
        current = [i]
        for j, observed in enumerate(hyp, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (expected != observed))
            )
        previous = current
    return previous[-1], len(ref)


def degrade(audio: np.ndarray, peak: float, seed: int) -> np.ndarray:
    """Scale to `peak`, pad half a second each side, add white noise of RMS 0.002."""
    scaled = audio * (peak / max(1e-9, float(np.max(np.abs(audio)))))
    padding = np.zeros(SAMPLE_RATE // 2, dtype=np.float32)
    padded = np.concatenate([padding, scaled, padding])
    noise = np.random.default_rng(seed).normal(0, NOISE_RMS, padded.size)
    return (padded + noise).astype(np.float32)


def click(audio: np.ndarray, seed: int) -> np.ndarray:
    """Key-down 50 ms after the start and key-up 120 ms before the end: 8 ms bursts."""
    rng = np.random.default_rng(1000 + seed)
    out = audio.copy()
    length = int(0.008 * SAMPLE_RATE)
    burst = rng.normal(0, 1, length).astype(np.float32)
    burst *= np.exp(-np.arange(length) / (length / 4)).astype(np.float32)
    burst *= 0.35 / float(np.max(np.abs(burst)))
    for start in (int(0.05 * SAMPLE_RATE), out.size - int(0.12 * SAMPLE_RATE)):
        out[start : start + length] += burst
    return out


def noise_clips() -> list[np.ndarray]:
    rng = np.random.default_rng(7)
    return [
        click(rng.normal(0, rms, SAMPLE_RATE * seconds).astype(np.float32), seed)
        for seed, (rms, seconds) in enumerate([(0.002, 3), (0.002, 8), (0.0005, 5), (0.006, 5)])
    ]


def long_clip(spoken: list[np.ndarray]) -> tuple[np.ndarray, str]:
    """Whole sentences at peak 0.25 with 1 s gaps, until at least LONG_SECONDS."""
    gap = np.zeros(SAMPLE_RATE, dtype=np.float32)
    parts: list[np.ndarray] = []
    reference: list[str] = []
    index = 0
    while sum(part.size for part in parts) < LONG_SECONDS * SAMPLE_RATE:
        clip = spoken[index % len(spoken)]
        parts += [clip * (0.25 / float(np.max(np.abs(clip)))), gap]
        reference.append(SENTENCES[index % len(SENTENCES)])
        index += 1
    audio = np.concatenate(parts)
    for part in parts:
        part.fill(0)
    noise = np.random.default_rng(3).normal(0, NOISE_RMS, audio.size)
    audio = (audio + noise).astype(np.float32)
    return audio, " ".join(reference)


def _score(recognizer: Recognizer, clips: list[tuple[np.ndarray, str]]) -> tuple[float, float]:
    """(errors per 100 words, mean seconds per clip); the clips are zeroed afterwards."""
    distance = total = 0
    started = time.perf_counter()
    try:
        for audio, sentence in clips:
            text = recognizer.transcribe(audio)
            edits, count = word_errors(sentence, text)
            distance, total = distance + edits, total + count
    finally:
        for audio, _ in clips:
            audio.fill(0)
    return 100 * distance / total, (time.perf_counter() - started) / len(clips)


def _speak(directory: Path, text: str, paused: bool) -> np.ndarray:
    markup = paused_markup(text) if paused else text
    return diagnostics.synthetic_audio(directory, text=markup, xml=paused)


def _variants(models: list[str], retry: bool) -> list[tuple[str, str, tuple[float, ...]]]:
    rows = [(model, model, (0.0,)) for model in models]
    if retry:
        rows += [
            (f"{model}+retry", model, RETRY_TEMPERATURES)
            for model in models
            if not model.startswith("parakeet")
        ]
    return rows


def check(
    root: Path,
    models: list[str],
    temporary: Path,
    *,
    threads: int = 0,
    retry: bool = False,
    long: bool = False,
) -> dict:
    import psutil

    temporary.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    noise_only: list[dict] = []
    timing: list[dict] = []
    long_rows: list[dict] = []
    process = psutil.Process()
    with tempfile.TemporaryDirectory(dir=temporary) as directory:
        spoken = {
            (index, paused): _speak(Path(directory), sentence, paused)
            for index, sentence in enumerate(SENTENCES)
            for paused in (False, True)
        }
        ten_seconds = _speak(Path(directory), " ".join(SENTENCES[:2]), False)
        try:
            for label, model, temperatures in _variants(models, retry):
                recognizer = make_recognizer(root, model, threads, "", "accurate")
                if isinstance(recognizer, WhisperRecognizer):
                    recognizer.temperatures = temperatures
                recognizer.prepare()
                warm = np.zeros(SAMPLE_RATE, dtype=np.float32)
                recognizer.transcribe(warm)
                loaded = process.memory_info().rss
                for peak in LEVELS:
                    for paused in (False, True):
                        clips = [
                            (click(degrade(spoken[index, paused], peak, index), index), sentence)
                            for index, sentence in enumerate(SENTENCES)
                        ]
                        errors, seconds = _score(recognizer, clips)
                        results.append(
                            {
                                "model": label,
                                "level": peak,
                                "paused": paused,
                                "errors_per_100": round(errors, 1),
                                "seconds_per_clip": round(seconds, 2),
                            }
                        )
                        print(json.dumps(results[-1]), file=sys.stderr, flush=True)
                invented = []
                for clip in noise_clips():
                    try:
                        text = recognizer.transcribe(clip)
                        invented.append(len(words(text)))
                    finally:
                        clip.fill(0)
                noise_only.append({"model": label, "words_invented": invented})
                clip = click(degrade(ten_seconds, 0.25, 0), 0)
                try:
                    started = time.perf_counter()
                    recognizer.transcribe(clip)
                    timing.append(
                        {"model": label, "seconds": round(time.perf_counter() - started, 2)}
                    )
                finally:
                    clip.fill(0)
                if long and label == model:
                    audio, reference = long_clip(
                        [spoken[index, False] for index in range(len(SENTENCES))]
                    )
                    try:
                        started = time.perf_counter()
                        text = recognizer.transcribe(audio)
                        seconds = time.perf_counter() - started
                        edits, count = word_errors(reference, text)
                        long_rows.append(
                            {
                                "model": label,
                                "clip_seconds": round(audio.size / SAMPLE_RATE),
                                "errors_per_100": round(100 * edits / count, 1),
                                "seconds": round(seconds, 2),
                                "loaded_mb": round(loaded / 2**20),
                                "peak_mb": round(process.memory_info().peak_wset / 2**20),
                            }
                        )
                    finally:
                        audio.fill(0)
                # Release this model before the next one loads: never two alive at once.
                del recognizer
        finally:
            for audio in [*spoken.values(), ten_seconds]:
                audio.fill(0)
    report: dict = {
        "scope": SCOPE,
        "threads": threads,
        "results": results,
        "noise_only": noise_only,
        "timing_10s": timing,
    }
    if long:
        report["long"] = long_rows
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Model directory.")
    parser.add_argument("--models", nargs="+", default=["base.en"], help="Model names.")
    parser.add_argument("--temp-dir", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=0, help="0 means automatic.")
    parser.add_argument(
        "--retry", action="store_true", help="Add Whisper rows with temperatures 0, 0.2, 0.4."
    )
    parser.add_argument(
        "--long",
        action="store_true",
        help="Add a 128 s clip with memory use. Run with one model per process: peak memory "
        "is for the whole process.",
    )
    args = parser.parse_args(argv)
    unknown = [name for name in args.models if name not in MODELS]
    if unknown:
        parser.error(f"unknown model: {', '.join(unknown)}")
    return args


if __name__ == "__main__":
    arguments = parse_args()
    print(
        json.dumps(
            check(
                arguments.root,
                arguments.models,
                arguments.temp_dir,
                threads=arguments.threads,
                retry=arguments.retry,
                long=arguments.long,
            ),
            indent=2,
        )
    )
