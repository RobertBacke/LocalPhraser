import sys
import threading
from types import SimpleNamespace

import pytest

from localphraser.target_worker import TargetWorker


@pytest.fixture
def backend(monkeypatch):
    class Native:
        def __init__(self):
            self.capture_gate = threading.Event()
            self.capture_gate.set()
            self.insert_gate = threading.Event()
            self.insert_gate.set()
            self.started = threading.Event()
            self.threads = []
            self.delivered = []

        def snapshot(self):
            return 123

        def capture(self, expected):
            assert expected == 123
            self.threads.append(threading.get_ident())
            self.started.set()
            self.capture_gate.wait(3)
            return object()

        def insert(self, target, text, permitted):
            self.threads.append(threading.get_ident())
            self.insert_gate.wait(3)
            if not permitted():
                raise ValueError("Expired")
            self.delivered.append(text)

        insert_gradually = insert

    native = Native()
    monkeypatch.setattr("localphraser.target_worker.WindowsInsertion", lambda: native)
    monkeypatch.setitem(
        sys.modules,
        "comtypes",
        SimpleNamespace(
            CoInitializeEx=lambda flags: None,
            CoUninitialize=lambda: None,
        ),
    )
    worker = TargetWorker(timeout=0.2)
    yield worker, native
    native.capture_gate.set()
    native.insert_gate.set()
    worker.close()
    worker.executor.shutdown(wait=True)


def barrier(worker):
    # Flush completion callbacks and their queued discards, too.
    worker.executor.submit(lambda: None).result(timeout=3)
    worker.executor.submit(lambda: None).result(timeout=3)


def test_target_stays_on_one_worker_thread(backend):
    worker, native = backend
    token = worker.capture(123).result(timeout=2)
    assert isinstance(token, int)
    worker.insert(token, "text")
    assert native.delivered == ["text"]
    assert len(set(native.threads)) == 1
    assert native.threads[0] != threading.get_ident()
    assert worker.targets == {}


def test_late_capture_is_discarded_after_timeout(backend):
    worker, native = backend
    native.capture_gate.clear()
    result = worker.capture(123)
    assert native.started.wait(1)
    with pytest.raises(TimeoutError):
        result.result(timeout=2)
    native.capture_gate.set()
    barrier(worker)
    assert worker.targets == {}


def test_slow_insertion_cannot_deliver_after_timeout(backend):
    worker, native = backend
    token = worker.capture(123).result(timeout=2)
    native.insert_gate.clear()
    with pytest.raises(TimeoutError):
        worker.insert(token, "text")
    native.insert_gate.set()
    barrier(worker)
    assert not native.delivered


def test_wait_timeout_revokes_insertion_even_before_clock_deadline(backend, monkeypatch):
    worker, native = backend
    token = worker.capture(123).result(timeout=2)
    # Reproduce a Future wait returning before the permission clock reaches its
    # deadline, independently of the host's timer resolution and scheduling.
    monkeypatch.setattr("localphraser.target_worker.time.monotonic", lambda: 100.0)
    native.insert_gate.clear()
    with pytest.raises(TimeoutError):
        worker.insert(token, "text")
    native.insert_gate.set()
    barrier(worker)
    assert not native.delivered
    assert worker.targets == {}


def test_async_insertion_timeout_cancels_late_work(backend):
    worker, native = backend
    token = worker.capture(123).result(timeout=2)
    native.insert_gate.clear()
    worker.timeout = 0.01
    future = worker.insert_async(token, "x")
    with pytest.raises(TimeoutError):
        future.result(timeout=2)
    native.insert_gate.set()
    barrier(worker)
    assert not native.delivered and worker.targets == {}
