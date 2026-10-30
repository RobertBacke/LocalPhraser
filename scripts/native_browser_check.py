"""Opt-in synthetic delivery check in an owned Chrome profile and reactive editor."""

import ctypes as ct
import subprocess
import time
import uuid
from ctypes import wintypes as wt
from pathlib import Path

import psutil

from localphraser.target_worker import TargetWorker
from localphraser.windows import user32


def main() -> None:
    chrome = next(
        (
            path
            for path in (
                Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            )
            if path.is_file()
        ),
        None,
    )
    if chrome is None:
        raise RuntimeError("Chrome is not installed at a standard path.")
    folder = Path(".cache") / ("owned-browser-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    fixture = folder / "fixture.html"
    prefix = "Existing draft. "
    text = "LocalPhraser browser delivery keeps every word in order. " * 48
    fixture.write_text(
        '<title>LocalPhraser owned test</title><div contenteditable="true" role="textbox" '
        'aria-label="LocalPhraser owned field" '
        'style="white-space:pre-wrap;width:90vw;height:80vh">' + prefix + "</div><script>"
        'const e=document.querySelector("div");e.focus();'
        "window.getSelection().collapse(e.firstChild,e.firstChild.length);"
        'e.addEventListener("input",()=>{const s=window.getSelection();'
        "const n=s.anchorOffset;e.textContent=e.textContent;s.collapse(e.firstChild,n)})"
        "</script>",
        encoding="utf-8",
    )
    child = subprocess.Popen(
        [
            str(chrome),
            "--user-data-dir=" + str((folder / "profile").resolve()),
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--force-renderer-accessibility",
            "--app=" + fixture.resolve().as_uri(),
        ]
    )
    process = psutil.Process(child.pid)
    worker = None
    try:
        api = user32()
        time.sleep(3)
        owned = {process.pid, *(p.pid for p in process.children(recursive=True))}
        hwnd = api.GetForegroundWindow()
        pid = wt.DWORD()
        api.GetWindowThreadProcessId(hwnd, ct.byref(pid))
        assert pid.value in owned, "Owned Chrome is not foreground; refusing input."
        worker = TargetWorker()
        native = worker.native
        delivered_batches: list[int] = []
        insert = native.insert

        def checked_insert(target, value, permitted=None):
            insert(target, value, permitted)
            delivered_batches.append(len(value))

        native.insert = checked_insert

        def focused():
            assert api.GetForegroundWindow() == hwnd, "Owned window lost focus."
            control, _ = native._selection()
            assert control.ProcessId == pid.value and control.Name == "LocalPhraser owned field"
            return control

        worker.executor.submit(focused).result(timeout=5)
        token = worker.capture(worker.snapshot()).result(timeout=5)
        worker.insert_async(token, text).result(timeout=30)
        assert delivered_batches == [len(text)], "Expected one complete checked delivery."

        def verify() -> None:
            control = focused()
            deadline = time.monotonic() + 10
            while True:
                observed = control.GetTextPattern().DocumentRange.GetText(-1).rstrip("\r\n")
                if observed == prefix + text:
                    break
                assert time.monotonic() < deadline, "Owned editor text mismatch."
                time.sleep(0.02)
            control.GetTextPattern().DocumentRange.Select(waitTime=0)
            for _ in range(50):
                ranges = control.GetTextPattern().GetSelection()
                if (
                    len(ranges) == 1
                    and ranges[0].textRange.CompareEndpoints(0, ranges[0].textRange, 1) != 0
                ):
                    return
                time.sleep(0.02)
            raise AssertionError("Owned selection did not settle.")

        worker.executor.submit(verify).result(timeout=15)
        try:
            worker.capture(worker.snapshot()).result(timeout=5)
        except ValueError:
            pass
        else:
            raise AssertionError("Selected browser text was not refused.")
        print(
            f"Owned reactive Chrome editor: {len(text)} characters in "
            f"{len(delivered_batches)} checked batches and selection refusal passed."
        )
    finally:
        if worker:
            worker.close()
            worker.executor.shutdown(wait=True)
        try:
            for owned_child in process.children(recursive=True):
                try:
                    owned_child.terminate()
                except psutil.Error:
                    pass
            process.terminate()
        except psutil.Error:
            pass


if __name__ == "__main__":
    main()
