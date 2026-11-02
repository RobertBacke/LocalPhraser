"""Fixed synthetic speech quality/search comparison; no microphone or transcript logs."""

import argparse
import json
import re
import tempfile
import time
from collections import Counter
from pathlib import Path

from localphraser import diagnostics
from localphraser.config import MODELS, RECOGNITION_QUALITY
from localphraser.recognition import WhisperRecognizer

CASES = (
    (
        "last_less",
        "Maybe include the last seven days too, or the last week, "
        "along with twenty-four hours and all time.",
        ["last", "last", "week", "days"],
    ),
    (
        "technical_names",
        "I use Codex and LocalPhraser for transcription in Google Chrome.",
        ["Codex", "LocalPhraser", "Google", "Chrome"],
    ),
    (
        "negation",
        "Do not send the files until next week. We need the last version, not the first one.",
        ["not", "not", "last", "first"],
    ),
)


def check(root: Path, models: list[str], temporary: Path) -> dict:
    temporary.mkdir(parents=True, exist_ok=True)
    rows = []
    original = diagnostics.SYNTHETIC_TEXT
    try:
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            for model in models:
                recognizer = WhisperRecognizer(root / model, quality="fast")
                recognizer.prepare()
                for name, text, keywords in CASES:
                    diagnostics.SYNTHETIC_TEXT = text
                    audio = diagnostics.synthetic_audio(Path(directory))
                    try:
                        for quality, beam in RECOGNITION_QUALITY.items():
                            recognizer.beam_size = beam
                            started = time.perf_counter()
                            result = recognizer.transcribe(audio)
                            observed = Counter(re.findall(r"\w+", result.casefold()))
                            wanted = Counter(word.casefold() for word in keywords)
                            rows.append(
                                {
                                    "model": model,
                                    "case": name,
                                    "quality": quality,
                                    "seconds": round(time.perf_counter() - started, 3),
                                    "keyword_hits": sum((wanted & observed).values()),
                                    "keyword_total": len(keywords),
                                }
                            )
                    finally:
                        audio.fill(0)
    finally:
        diagnostics.SYNTHETIC_TEXT = original
    return {
        "scope": "Fixed SAPI speech; keyword checks, not a human speech accuracy benchmark. "
        "No microphone or insertion. First decode includes initialization.",
        "results": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=["base.en", "small.en"])
    parser.add_argument("--temp-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.root, args.models, args.temp_dir), indent=2))
