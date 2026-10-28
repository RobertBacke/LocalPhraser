"""Optional local refinement in a warm, terminable process; no files or servers."""

import multiprocessing as mp
import os
import re
import socket
import sys
import threading
import unicodedata
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Protocol

from localphraser.refinement_models import verify_refiner

MAX_INPUT_CHARS = 3000
FILLERS = {"um", "uh", "erm", "hmm"}
TOKENS = re.compile(
    r"(?:[$€£¥]\s*)?[+-]?\d+(?:[.,:/-]\d+)*(?:%|\b)"
    r"|\w+(?:[.'’:/\\@+-]\w+)*",
    re.UNICODE,
)


class Refiner(Protocol):
    def refine(self, text: str) -> str: ...
    def close(self) -> None: ...


def preserve_words(raw: str, candidate: str) -> bool:
    """Conservative lexical check, not a proof of semantic equivalence."""
    if not candidate.strip() or len(candidate) > MAX_INPUT_CHARS * 3:
        return False
    if any(unicodedata.category(char) in ("Cc", "Cf") and char != "\n" for char in candidate):
        return False

    def words(text: str) -> list[str]:
        return [token.casefold() for token in TOKENS.findall(text)]

    original, edited = words(raw), words(candidate)
    removable = [
        token.casefold() in FILLERS and not token.isupper() for token in TOKENS.findall(raw)
    ]
    # Fillers may be retained or removed, but must never be added or substituted.
    index = 0
    for token in edited:
        while index < len(original) and original[index] != token and removable[index]:
            index += 1
        if index >= len(original) or token != original[index]:
            return False
        index += 1
    return bool(edited) and all(removable[index:])


def _no_network(*args: Any, **kwargs: Any) -> None:
    raise OSError("Network is disabled in the refinement worker.")


def refinement_worker(
    connection: Connection, name: str, root: str, threads: int, prompt: str
) -> None:
    """Child owns all native model state. Only bounded strings cross the pipe."""
    for stream in ("stdout", "stderr"):
        setattr(sys, stream, open(os.devnull, "w", encoding="utf-8"))
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    socket.socket.connect = _no_network  # type: ignore[method-assign]
    socket.socket.connect_ex = _no_network  # type: ignore[method-assign,assignment]
    try:
        from llama_cpp import Llama

        model = Llama(
            model_path=str(verify_refiner(name, Path(root))),
            n_ctx=4096,
            n_threads=threads,
            n_gpu_layers=0,
            verbose=False,
            seed=0,
            chat_format="chatml",
        )
        while True:
            text = connection.recv()
            if not isinstance(text, str) or not 0 < len(text) <= MAX_INPUT_CHARS:
                raise ValueError("Input outside refinement limits.")
            try:
                response: Any = model.create_chat_completion(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text},
                    ],
                    temperature=0,
                    max_tokens=1024,
                    repeat_penalty=1.0,
                )
                choice = response["choices"][0]
                connection.send(
                    {
                        "text": choice["message"]["content"],
                        "complete": choice["finish_reason"] == "stop",
                    }
                )
            finally:
                model.reset()
                text = ""
                response = None
                choice = None
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        try:
            connection.send({"error": True})
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class LocalRefiner:
    def __init__(self, name: str, root: Path, threads: int, prompt: str, timeout: float):
        self.name, self.root, self.threads = name, root, threads
        self.prompt, self.timeout = prompt, timeout
        self.context = mp.get_context("spawn")
        self.process: Any = None
        self.connection: Any = None
        self.closed = False
        self.inflight = False
        self.lifecycle = threading.Lock()

    def _stop_locked(self, *, close_connection: bool = True) -> None:
        if self.connection is not None:
            if close_connection:
                self.connection.close()
            self.connection = None
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=1)
            self.process.close()
            self.process = None

    def refine(self, text: str) -> str:
        if not 0 < len(text) <= MAX_INPUT_CHARS:
            raise ValueError("Input outside refinement limits.")
        with self.lifecycle:
            if self.closed:
                raise RuntimeError("Refinement has closed.")
            if self.inflight:
                raise RuntimeError("Refinement is already running.")
            if self.process is None or not self.process.is_alive():
                self._stop_locked()
                parent, child = self.context.Pipe()
                process = self.context.Process(
                    target=refinement_worker,
                    args=(child, self.name, str(self.root), self.threads, self.prompt),
                    daemon=True,
                )
                try:
                    process.start()
                except Exception:
                    parent.close()
                    child.close()
                    raise
                child.close()
                self.process, self.connection = process, parent
            connection = self.connection
            self.inflight = True
        assert connection is not None
        try:
            try:
                connection.send(text)
                if not connection.poll(self.timeout):
                    raise TimeoutError("Refinement deadline exceeded.")
                response = connection.recv()
                if not isinstance(response, dict) or response.get("error"):
                    raise RuntimeError("Refinement worker failed.")
            except Exception:
                with self.lifecycle:
                    self._stop_locked()
                raise
            candidate = response.get("text")
            if (
                not response.get("complete")
                or not isinstance(candidate, str)
                or not preserve_words(text, candidate)
            ):
                raise ValueError("Refinement did not preserve the transcript.")
            return candidate.strip()
        finally:
            with self.lifecycle:
                self.inflight = False
                if connection is not self.connection:
                    connection.close()

    def close(self) -> None:
        with self.lifecycle:
            self.closed = True
            # Closing a Windows pipe from another thread while it polls can crash
            # Python with INVALID_HANDLE. Kill the child, let the reader see EOF,
            # and let that same reader close its connection in refine's finally.
            self._stop_locked(close_connection=not self.inflight)
