"""Byte progress for the owned Hugging Face staging directory."""

import json
import os
from pathlib import Path
from threading import Event, Thread

PREFIX = "LOCALPHRASER_PROGRESS "


def partial_bytes(stage: Path) -> int:
    """Count only Hub transfer files, never cache metadata or linked directories."""
    total = 0
    cache = stage / ".cache" / "huggingface" / "download"
    if cache.is_symlink() or cache.is_junction():
        return 0
    for folder, directories, files in os.walk(cache, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if not (Path(folder) / name).is_symlink() and not (Path(folder) / name).is_junction()
        ]
        for name in files:
            path = Path(folder) / name
            if name.endswith(".incomplete") and not path.is_symlink():
                try:
                    total += path.stat().st_size
                except FileNotFoundError:
                    pass  # The downloader may have just renamed a finished transfer.
    return total


def report(completed: int, total: int | None) -> None:
    print(PREFIX + json.dumps({"completed": completed, "total": total}), flush=True)


class TransferProgress:
    """Observe bytes on disk without replacing the Hub's HTTP/retry implementation."""

    def __init__(self, stage: Path, completed: int, total: int | None):
        self.stage, self.completed, self.total = stage, completed, total
        self.stop = Event()
        self.thread = Thread(target=self._watch, daemon=True)

    def __enter__(self) -> "TransferProgress":
        report(self.completed, self.total)
        self.thread.start()
        return self

    def _watch(self) -> None:
        while not self.stop.wait(0.2):
            try:
                count = self.completed + partial_bytes(self.stage)
                report(min(count, self.total) if self.total is not None else count, self.total)
            except OSError:
                pass  # Progress must never interrupt installation or integrity checks.

    def __exit__(self, *args: object) -> None:
        self.stop.set()
        self.thread.join()
