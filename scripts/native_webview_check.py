"""Opt-in insertion check in an owned WebView2 editor, never Teams or Outlook.

Requires the installed WebView2 runtime and Microsoft's official SDK unpacked at --sdk.
SDK files are test-only dependencies, not installed or bundled with LocalPhraser.
"""

import argparse
import ctypes as ct
import subprocess
import time
import uuid
from pathlib import Path

from localphraser.target_worker import TargetWorker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    args = parser.parse_args()
    folder = Path(".cache") / ("owned-webview-" + uuid.uuid4().hex)
    folder.mkdir()
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(Path(__file__).parent / "fixtures/webview_editor.ps1"),
            "-Folder",
            str(folder.resolve()),
            "-Sdk",
            str(args.sdk.resolve()),
        ],
        check=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    child = subprocess.Popen([str(folder / "editor.exe"), str(folder.resolve())])
    worker = None
    hwnd = 0
    try:
        deadline = time.monotonic() + 30
        while not (folder / "ready.txt").exists():
            if child.poll() is not None:
                raise RuntimeError("Owned editor fixture did not start.")
            assert time.monotonic() < deadline, "Owned editor initialization timed out."
            time.sleep(0.1)
        hwnd = int((folder / "ready.txt").read_text())
        worker = TargetWorker()
        native = worker.native
        while native.api.GetForegroundWindow() != hwnd and time.monotonic() < deadline:
            time.sleep(0.05)
        assert native.api.GetForegroundWindow() == hwnd, "Owned editor is not foreground."

        def owned():
            assert native.api.GetForegroundWindow() == hwnd, "Owned editor lost focus."
            control, _ = native._selection()
            assert control.Name == "LocalPhraser owned field"
            return control

        snapshot = worker.snapshot()
        provider_pid = worker.executor.submit(lambda: owned().ProcessId).result(timeout=5)
        assert provider_pid != snapshot.process_id, "Fixture must exercise cross-process ownership."
        token = worker.capture(snapshot).result(timeout=5)
        text = " " + " ".join(["LocalPhraser keeps every embedded editor word."] * 30)
        worker.insert_async(token, text).result(timeout=15)

        def verify():
            control = owned()
            end = time.monotonic() + 10
            while True:
                observed = control.GetTextPattern().DocumentRange.GetText(-1)
                # Chromium represents some inserted spaces as NBSP in contenteditable.
                if observed.split() == ("Existing draft." + text).split():
                    break
                assert time.monotonic() < end, "Owned editor word preservation mismatch."
                time.sleep(0.05)
            control.GetTextPattern().DocumentRange.Select(waitTime=0)
            end = time.monotonic() + 5
            while True:
                ranges = control.GetTextPattern().GetSelection()
                if (
                    len(ranges) == 1
                    and ranges[0].textRange.CompareEndpoints(0, ranges[0].textRange, 1) != 0
                ):
                    break
                assert time.monotonic() < end, "Owned editor selection did not settle."
                time.sleep(0.02)

        worker.executor.submit(verify).result(timeout=15)
        try:
            worker.capture(worker.snapshot()).result(timeout=5)
        except ValueError as exc:
            assert "Selection" in str(exc)
        else:
            raise AssertionError("Selected text was not refused.")
        print(
            "Owned WebView2: cross-process capture, long insertion, draft preservation "
            "and selection refusal passed."
        )
    finally:
        if worker:
            if hwnd and worker.native.api.IsWindow(hwnd):
                api = worker.native.api
                api.PostMessageW.argtypes = [ct.c_void_p, ct.c_uint, ct.c_size_t, ct.c_ssize_t]
                api.PostMessageW(hwnd, 0x0010, 0, 0)  # Close only this owned fixture.
            worker.close()
            worker.executor.shutdown(wait=True)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)


if __name__ == "__main__":
    main()
