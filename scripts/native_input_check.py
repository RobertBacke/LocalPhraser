"""Opt-in test against an owned, disposable Windows EDIT control.

Never captures microphone audio or reads/types in unrelated windows. Refuses insertion
unless the foreground handle matches the fixture process. Not a Notepad acceptance test.
"""

import ctypes as ct
import json
import subprocess
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

from localphraser.target_worker import TargetWorker
from localphraser.windows import WindowsInsertion, user32


def qt_fixture() -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QTextEdit, QVBoxLayout, QWidget

    app = QApplication([])
    window = QWidget()
    window.setWindowTitle("LocalPhraser disposable UI Automation fixture")
    layout = QVBoxLayout(window)
    edit = QTextEdit()
    layout.addWidget(edit)
    window.resize(500, 200)
    window.show()
    edit.setFocus()
    app.processEvents()
    api = user32()
    api.SetForegroundWindow.argtypes = [wt.HWND]
    api.SetForegroundWindow(int(window.winId()))
    edit.setFocus()
    app.processEvents()
    print(json.dumps({"window": int(window.winId()), "qt": True}), flush=True)
    reported = False

    def report() -> None:
        nonlocal reported
        if not reported:
            reported = True
            text = edit.toPlainText()
            edit.selectAll()
            print(json.dumps({"text": text}), flush=True)

    def check() -> None:
        if edit.toPlainText() == "LocalPhraser Unicode café":
            timer.stop()
            report()

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(check)
    timer.start()
    QTimer.singleShot(5000, report)
    app.exec()


def fixture() -> None:
    api = user32()
    kernel = ct.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.restype = wt.HMODULE
    instance = kernel.GetModuleHandleW(None)
    api.CreateWindowExW.argtypes = [
        wt.DWORD,
        wt.LPCWSTR,
        wt.LPCWSTR,
        wt.DWORD,
        ct.c_int,
        ct.c_int,
        ct.c_int,
        ct.c_int,
        wt.HWND,
        wt.HMENU,
        wt.HINSTANCE,
        ct.c_void_p,
    ]
    api.CreateWindowExW.restype = wt.HWND
    api.SetForegroundWindow.argtypes = [wt.HWND]
    api.SetFocus.argtypes = [wt.HWND]
    api.GetMessageW.argtypes = [ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    api.DispatchMessageW.argtypes = [ct.POINTER(wt.MSG)]
    api.DispatchMessageW.restype = ct.c_ssize_t
    parent = api.CreateWindowExW(
        0,
        "STATIC",
        "LocalPhraser disposable input test",
        0x10CF0000,
        200,
        200,
        520,
        220,
        None,
        None,
        instance,
        None,
    )
    rich = ct.WinDLL("Msftedit.dll") if "--rich-fixture" in sys.argv else None
    edit = api.CreateWindowExW(
        0x200,
        "RICHEDIT50W" if rich else "EDIT",
        "",
        0x50000000 | 0x0004 | 0x0040,
        15,
        15,
        470,
        140,
        parent,
        None,
        instance,
        None,
    )
    if not parent or not edit:
        raise ct.WinError(ct.get_last_error())
    api.SetForegroundWindow(parent)
    api.SetFocus(edit)
    print(json.dumps({"window": parent, "edit": edit}), flush=True)
    msg = wt.MSG()
    while api.GetMessageW(ct.byref(msg), None, 0, 0) > 0:
        api.TranslateMessage(ct.byref(msg))
        api.DispatchMessageW(ct.byref(msg))


def main() -> None:
    child = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--qt-fixture"
            if "--qt" in sys.argv
            else "--rich-fixture"
            if "--rich" in sys.argv
            else "--fixture",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    worker = None
    try:
        assert child.stdout is not None
        handles = json.loads(child.stdout.readline())
        api = user32()
        api.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ct.c_int]
        api.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        api.SendMessageW.restype = ct.c_ssize_t
        worker = TargetWorker() if "--direct" not in sys.argv else None
        native = worker.native if worker else WindowsInsertion()
        insertion = worker or native

        def capture():
            if worker:
                snapshot = worker.snapshot()
                assert snapshot.hwnd == handles["window"]
                return worker.capture(snapshot).result(timeout=3)
            return native.capture()

        deadline = time.monotonic() + 3
        while api.GetForegroundWindow() != handles["window"] and time.monotonic() < deadline:
            time.sleep(0.05)
        if api.GetForegroundWindow() != handles["window"]:
            raise RuntimeError("Fixture could not gain foreground. No input was sent.")
        target = capture()
        expected_text = (
            "LocalPhraser Unicode café" if handles.get("qt") else "LocalPhraser Unicode 😀"
        )
        insertion.insert(target, expected_text)
        time.sleep(0.1)
        if handles.get("qt"):
            observed = json.loads(child.stdout.readline())["text"]
        else:
            buffer = ct.create_unicode_buffer(100)
            result = ct.c_size_t()
            assert api.SendMessageTimeoutW(
                handles["edit"],
                0x000D,
                len(buffer),
                ct.addressof(buffer),
                3,
                1000,
                ct.byref(result),
            )
            observed = buffer.value
            api.SendMessageW(handles["edit"], 0x00B1, 0, -1)  # EM_SETSEL
        assert observed == expected_text, "Synthetic fixture Unicode delivery mismatch"
        try:
            capture()
        except ValueError:
            print("Owned input fixture: worker Unicode insertion and selected-text refusal passed.")
        else:
            raise AssertionError("Selected text was not refused")
    finally:
        if worker:
            worker.close()
            worker.executor.shutdown(wait=True)
        child.terminate()
        child.wait(timeout=5)


if __name__ == "__main__":
    if "--qt-fixture" in sys.argv:
        qt_fixture()
    elif "--fixture" in sys.argv or "--rich-fixture" in sys.argv:
        fixture()
    else:
        main()
