"""Keep accessibility providers off the UI thread and COM targets on their owning thread."""

import itertools
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from localphraser.windows import WindowsInsertion, WindowSnapshot


class TargetWorker:
    def __init__(self, timeout: float = 2):
        self.native = WindowsInsertion()
        self.timeout = timeout
        self.closed = False
        self.targets: dict[int, Any] = {}
        self.ids = itertools.count(1)
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="target-verification", initializer=self._initialize
        )

    @staticmethod
    def _initialize() -> None:
        import comtypes

        comtypes.CoInitializeEx(0)  # UI Automation runs on this MTA thread, never the Qt thread.

    def snapshot(self) -> WindowSnapshot:
        return self.native.snapshot()  # Fast Win32 call only; no COM objects leave the worker.

    def capture(self, expected: WindowSnapshot) -> Future[int]:
        result: Future[int] = Future()
        guard = threading.Lock()

        def expired() -> None:
            with guard:
                if not result.done():
                    result.set_exception(TimeoutError("Target verification timed out."))

        timer = threading.Timer(self.timeout, expired)
        timer.daemon = True

        def work() -> int:
            if self.closed or result.done():
                raise RuntimeError("Target verification cancelled.")
            target = self.native.capture(expected)
            token = next(self.ids)
            self.targets[token] = target
            return token

        def completed(future: Future[int]) -> None:
            timer.cancel()
            try:
                token = future.result()
            except Exception as exc:
                with guard:
                    if not result.done():
                        result.set_exception(exc)
            else:
                with guard:
                    if result.done():
                        self.discard(token)
                    else:
                        result.set_result(token)

        timer.start()
        try:
            self.executor.submit(work).add_done_callback(completed)
        except RuntimeError:
            timer.cancel()
            with guard:
                if not result.done():
                    result.set_exception(RuntimeError("Target worker is closed."))
        return result

    def discard(self, token: int) -> None:
        if not self.closed:
            self.executor.submit(lambda: self.targets.pop(token, None))

    def insert(self, token: int, text: str) -> None:
        deadline = time.monotonic() + self.timeout
        cancelled = threading.Event()

        def work() -> None:
            target = self.targets.pop(token)
            self.native.insert(
                target,
                text,
                permitted=lambda: (
                    not self.closed and not cancelled.is_set() and time.monotonic() < deadline
                ),
            )

        # Only the final insertion stage waits; no active microphone capture is blocked.
        try:
            self.executor.submit(work).result(timeout=self.timeout)
        finally:
            # Future waits and monotonic deadlines can disagree at the timeout
            # boundary. Once the caller stops waiting, late work must stay revoked.
            cancelled.set()

    def insert_async(self, token: int, text: str) -> Future[None]:
        duration = min(30.0, self.timeout + len(text) / 200)
        deadline = time.monotonic() + duration
        cancelled = threading.Event()
        result: Future[None] = Future()
        guard = threading.Lock()

        def expired() -> None:
            cancelled.set()
            with guard:
                if not result.done():
                    result.set_exception(
                        TimeoutError("Insertion timed out; check for partial text.")
                    )

        timer = threading.Timer(duration, expired)
        timer.daemon = True

        def work() -> None:
            target = self.targets.pop(token)
            self.native.insert_gradually(
                target,
                text,
                permitted=lambda: (
                    not self.closed and not cancelled.is_set() and time.monotonic() < deadline
                ),
            )

        def completed(future: Future[None]) -> None:
            timer.cancel()
            cancelled.set()
            with guard:
                if not result.done():
                    try:
                        result.set_result(future.result())
                    except Exception as exc:
                        result.set_exception(exc)

        timer.start()
        try:
            self.executor.submit(work).add_done_callback(completed)
        except RuntimeError:
            timer.cancel()
            cancelled.set()
            result.set_exception(RuntimeError("Target worker is closed."))
        return result

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True

        def cleanup() -> None:
            import comtypes

            self.targets.clear()
            comtypes.CoUninitialize()

        try:
            self.executor.submit(cleanup)
        except RuntimeError:
            pass  # A failed COM initializer leaves no target objects to release.
        finally:
            self.executor.shutdown(wait=False)
