"""Explicit local WAV benchmark. Does not print or retain dictated content."""

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import psutil

from localphraser.recognition import WhisperRecognizer


def main() -> None:
    import av

    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.runs <= 100 or not 1 <= args.threads <= 16:
        parser.error("Use 1–100 runs and 1–16 threads.")
    with av.open(str(args.wav)) as container:
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
        arrays = [
            out.to_ndarray().flatten()
            for frame in container.decode(audio=0)
            for out in resampler.resample(frame)
        ]
        arrays.extend(out.to_ndarray().flatten() for out in resampler.resample(None))
    audio = np.concatenate(arrays).astype(np.float32)
    recognizer = WhisperRecognizer(args.model, args.threads)
    times = []
    memory = []
    try:
        for _ in range(args.runs):
            started = time.perf_counter()
            recognizer.transcribe(audio)
            times.append(time.perf_counter() - started)
            memory.append(psutil.Process().memory_info().rss)
        manifest = json.loads((args.model / "localphraser-manifest.json").read_text())
        print(
            json.dumps(
                {
                    "os": platform.platform(),
                    "cpu": platform.processor(),
                    "logical_cpus": psutil.cpu_count(),
                    "ram_bytes": psutil.virtual_memory().total,
                    "model_revision": manifest["revision"],
                    "compute_type": "int8",
                    "cpu_threads": args.threads,
                    "audio_seconds": len(audio) / 16000,
                    "cold_load_plus_first_inference_seconds": times[0],
                    "warm_inference_seconds": times[1:],
                    "observed_rss_bytes": memory,
                    "peak_working_set_bytes": getattr(
                        psutil.Process().memory_info(), "peak_wset", None
                    ),
                },
                indent=2,
            )
        )
    finally:
        audio.fill(0)


if __name__ == "__main__":
    main()
