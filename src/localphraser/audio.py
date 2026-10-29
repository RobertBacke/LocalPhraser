"""Bounded RAM capture with optional pre-opened, stopped microphone streams."""

import json
import threading
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

Audio = npt.NDArray[np.float32]
SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Microphone:
    name: str
    host_api: str

    @property
    def label(self) -> str:
        return f"{self.name} — {self.host_api}"

    @property
    def value(self) -> str:
        return "device:" + json.dumps([self.name, self.host_api], ensure_ascii=False)


def microphones() -> list[Microphone]:
    import sounddevice as sd

    apis = sd.query_hostapis()
    counts = Counter(
        Microphone(d["name"], apis[d["hostapi"]]["name"])
        for d in sd.query_devices()
        if d["max_input_channels"] > 0
    )
    return sorted(
        (item for item, count in counts.items() if count == 1), key=lambda item: item.label
    )


def resolve_microphone(value: str | None) -> int | None:
    """Resolve exact current identity, refusing ambiguous legacy names and duplicates."""
    if value is None:
        return None
    import sounddevice as sd

    api_name = None
    name = value
    if value.startswith("device:"):
        identity = json.loads(value.removeprefix("device:"))
        if (
            not isinstance(identity, list)
            or len(identity) != 2
            or not all(isinstance(x, str) for x in identity)
        ):
            raise ValueError("Invalid microphone identity. Select the device again.")
        name, api_name = identity
    apis = sd.query_hostapis()
    matches = [
        index
        for index, device in enumerate(sd.query_devices())
        if device["max_input_channels"] > 0
        and device["name"] == name
        and (api_name is None or apis[device["hostapi"]]["name"] == api_name)
    ]
    if len(matches) != 1:
        raise ValueError("Microphone is missing or ambiguous. Select the device again.")
    return matches[0]


class Recorder:
    def __init__(self, device: str | None, max_seconds: int, keep_ready: bool = False):
        self.device = device
        self.limit = max_seconds * SAMPLE_RATE
        self.keep_ready = keep_ready
        self.buffer: Audio = np.empty(0, dtype=np.float32)
        self.position = 0
        self.failed = False
        self.full = threading.Event()
        self.first_frame = threading.Event()
        self.stream: Any = None
        self.recording = False
        self.closed = False
        self._lock = threading.RLock()
        self._callback_stop: Any = RuntimeError

    def _callback(self, indata: Any, frames: int, time: Any, status: Any) -> None:
        if status:
            self.failed = True
        count = min(frames, self.limit - self.position)
        self.buffer[self.position : self.position + count] = indata[:count, 0]
        self.position += count
        self.first_frame.set()
        if self.position == self.limit:
            self.full.set()
            raise self._callback_stop

    def prepare(self) -> None:
        """Open an inactive stream; no callbacks or idle pre-roll recording."""
        import sounddevice as sd

        with self._lock:
            if self.closed or self.stream is not None:
                return
            self.buffer = np.zeros(self.limit, dtype=np.float32)
            self._callback_stop = sd.CallbackStop
            try:
                self.stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                    device=resolve_microphone(self.device),
                    latency="low",
                    callback=self._callback,
                )
            except Exception:
                self.cancel()
                raise

    def start(self) -> None:
        with self._lock:
            if self.closed:
                raise RuntimeError("Microphone recorder is closed.")
            self.prepare()
            self.position = 0
            self.failed = False
            self.full.clear()
            self.first_frame.clear()
            try:
                self.stream.start()
                self.recording = True
            except Exception:
                self.cancel()
                raise

    def stop(self) -> Audio:
        with self._lock:
            try:
                if self.stream is not None:
                    try:
                        self.stream.stop()
                    except Exception:
                        self.cancel()
                        raise
                    if not self.keep_ready or self.failed:
                        try:
                            self.stream.close()
                        finally:
                            self.stream = None
                if self.failed:
                    raise RuntimeError("Microphone audio was interrupted. Please record again.")
                return self.buffer[: self.position].copy()
            finally:
                self.recording = False
                self.buffer.fill(0)
                self.position = 0
                if self.stream is None:
                    self.buffer = np.empty(0, dtype=np.float32)

    def cancel(self) -> None:
        with self._lock:
            try:
                if self.stream is not None:
                    try:
                        self.stream.abort()
                    except Exception:
                        pass
                    try:
                        self.stream.close()
                    except Exception:
                        pass
            finally:
                self.stream = None
                self.recording = False
                self.position = 0
                self.buffer.fill(0)
                self.buffer = np.empty(0, dtype=np.float32)

    def close(self) -> None:
        with self._lock:
            self.closed = True
            self.cancel()

    def healthy(self) -> bool:
        return bool(self.stream is not None and (self.stream.active or self.full.is_set()))
