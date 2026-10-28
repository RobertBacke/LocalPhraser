"""Generate nonpersonal speech with installed Windows SAPI, then test local ASR offline.

Explicit opt-in developer check; generated WAV is transient and deleted in finally.
Never records the microphone, types into another application, or prints transcripts.
"""

import argparse
import socket
import tempfile
import time
from pathlib import Path

import numpy as np

from localphraser.recognition import WhisperRecognizer


def main() -> None:
    import av
    import comtypes.client
    import faster_whisper  # noqa: F401

    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("--temp-dir", type=Path, required=True)
    args = parser.parse_args()
    args.temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.temp_dir) as directory:
        wav = Path(directory) / "synthetic.wav"
        voice = comtypes.client.CreateObject("SAPI.SpVoice", dynamic=True)
        stream = comtypes.client.CreateObject("SAPI.SpFileStream", dynamic=True)
        stream.Open(str(wav.resolve()), 3, False)
        try:
            voice.AudioOutputStream = stream
            voice.Speak("Local speech recognition keeps my words on this computer.")
        finally:
            stream.Close()
        with av.open(str(wav)) as container:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            arrays = [
                out.to_ndarray().flatten()
                for frame in container.decode(audio=0)
                for out in resampler.resample(frame)
            ]
            arrays.extend(out.to_ndarray().flatten() for out in resampler.resample(None))
        audio = np.concatenate(arrays).astype(np.float32)

        def forbidden(*unused_args, **unused_kwargs):
            raise AssertionError("Offline inference attempted a network connection")

        socket.socket.connect = forbidden
        socket.socket.connect_ex = forbidden
        recognizer = WhisperRecognizer(args.model)
        try:
            for label in ("cold", "warm"):
                started = time.perf_counter()
                transcript = recognizer.transcribe(audio)
                elapsed = time.perf_counter() - started
                # Meaningful sanity check without exposing recognition output.
                assert "computer" in transcript.lower() and "speech" in transcript.lower()
                print(f"{label}: synthetic speech content check passed ({elapsed:.3f} seconds)")
        finally:
            audio.fill(0)


if __name__ == "__main__":
    main()
