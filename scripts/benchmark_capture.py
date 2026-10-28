"""Measure microphone activation; capture briefly in RAM without transcription or files."""

import json
import time

from localphraser.audio import Recorder


def main() -> None:
    results = {}
    for keep_ready in (False, True):
        recorder = Recorder(None, 2, keep_ready=keep_ready)
        trials = []
        try:
            if keep_ready:
                recorder.prepare()
                assert not recorder.stream.active and not recorder.first_frame.is_set()
            for _ in range(3):
                started = time.perf_counter()
                recorder.start()
                start_ms = (time.perf_counter() - started) * 1000
                if not recorder.first_frame.wait(2):
                    raise RuntimeError("No microphone frames received.")
                first_ms = (time.perf_counter() - started) * 1000
                audio = recorder.stop()
                audio.fill(0)
                trials.append(
                    {
                        "start_return_ms": round(start_ms, 2),
                        "first_frame_observed_ms": round(first_ms, 2),
                    }
                )
            results["prepared_stream" if keep_ready else "reopened_stream"] = trials
        finally:
            recorder.close()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
