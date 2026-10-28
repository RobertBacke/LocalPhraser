"""Windows integration. No keyboard hooks, clipboard paste, or focus activation."""

import ctypes as ct
from collections.abc import Callable
from ctypes import wintypes as wt
from dataclasses import dataclass
from typing import Any


class KEYBDINPUT(ct.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ct.c_size_t),
    ]


class MOUSEINPUT(ct.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ct.c_size_t),
    ]


class HARDWAREINPUT(ct.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class INPUTUNION(ct.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ct.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wt.DWORD), ("union", INPUTUNION)]


class GUITHREADINFO(ct.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("flags", wt.DWORD),
        ("hwndActive", wt.HWND),
        ("hwndFocus", wt.HWND),
        ("hwndCapture", wt.HWND),
        ("hwndMenuOwner", wt.HWND),
        ("hwndMoveSize", wt.HWND),
        ("hwndCaret", wt.HWND),
        ("rcCaret", wt.RECT),
    ]


def user32() -> Any:
    api = ct.WinDLL("user32", use_last_error=True)
    api.GetForegroundWindow.argtypes = []
    api.GetForegroundWindow.restype = wt.HWND
    api.IsWindow.argtypes = [wt.HWND]
    api.IsWindow.restype = wt.BOOL
    api.GetWindowThreadProcessId.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
    api.GetWindowThreadProcessId.restype = wt.DWORD
    api.SendInput.argtypes = [wt.UINT, ct.POINTER(INPUT), ct.c_int]
    api.SendInput.restype = wt.UINT
    api.GetAsyncKeyState.argtypes = [ct.c_int]
    api.GetAsyncKeyState.restype = wt.SHORT
    api.RegisterHotKey.argtypes = [wt.HWND, ct.c_int, wt.UINT, wt.UINT]
    api.RegisterHotKey.restype = wt.BOOL
    api.UnregisterHotKey.argtypes = [wt.HWND, ct.c_int]
    api.UnregisterHotKey.restype = wt.BOOL
    api.GetGUIThreadInfo.argtypes = [wt.DWORD, ct.POINTER(GUITHREADINFO)]
    api.GetGUIThreadInfo.restype = wt.BOOL
    api.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ct.c_int]
    api.GetClassNameW.restype = ct.c_int
    api.GetAncestor.argtypes = [wt.HWND, wt.UINT]
    api.GetAncestor.restype = wt.HWND
    api.GetWindowLongW.argtypes = [wt.HWND, ct.c_int]
    api.GetWindowLongW.restype = wt.LONG
    api.IsWindowEnabled.argtypes = [wt.HWND]
    api.IsWindowEnabled.restype = wt.BOOL
    api.SendMessageTimeoutW.argtypes = [
        wt.HWND,
        wt.UINT,
        wt.WPARAM,
        wt.LPARAM,
        wt.UINT,
        wt.UINT,
        ct.POINTER(ct.c_size_t),
    ]
    api.SendMessageTimeoutW.restype = ct.c_ssize_t
    return api


def unicode_inputs(text: str) -> Any:
    if not text or len(text) > 16000 or any(ord(c) < 32 and c != "\n" for c in text):
        raise ValueError("Transcript is empty, too long, or contains control characters.")
    encoded = text.replace("\n", "\r").encode("utf-16-le")
    units = [int.from_bytes(encoded[i : i + 2], "little") for i in range(0, len(encoded), 2)]
    events = (INPUT * (len(units) * 2))()
    for index, unit in enumerate(units):
        events[index * 2] = INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=4))
        events[index * 2 + 1] = INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=6))
    return events


@dataclass
class Target:
    hwnd: int
    process_id: int
    runtime_id: tuple[int, ...]
    caret: Any


@dataclass(frozen=True)
class NativeTarget:
    hwnd: int
    process_id: int
    edit: int
    caret: int


@dataclass(frozen=True)
class WindowSnapshot:
    hwnd: int
    process_id: int
    focus: int
    caret_owner: int
    caret_rect: tuple[int, int, int, int]


class WindowsInsertion:
    def __init__(self) -> None:
        import uiautomation as automation

        self.automation = automation
        self.api = user32()

    def _native_target(self, hwnd: int) -> NativeTarget | None:
        pid = wt.DWORD()
        thread = self.api.GetWindowThreadProcessId(hwnd, ct.byref(pid))
        info = GUITHREADINFO(cbSize=ct.sizeof(GUITHREADINFO))
        if not self.api.GetGUIThreadInfo(thread, ct.byref(info)) or not info.hwndFocus:
            return None
        edit = info.hwndFocus
        name = ct.create_unicode_buffer(64)
        self.api.GetClassNameW(edit, name, len(name))
        if name.value != "Edit":
            return None
        if self.api.GetAncestor(edit, 2) != hwnd or not self.api.IsWindowEnabled(edit):
            raise ValueError("Native field is not active or enabled.")
        style = self.api.GetWindowLongW(edit, -16)
        if style & (0x800 | 0x20):  # ES_READONLY / ES_PASSWORD
            raise ValueError("Native field is password-protected or read-only.")
        selection = ct.c_size_t()
        if not self.api.SendMessageTimeoutW(
            edit,
            0x00B0,
            0,
            0,
            3,
            100,
            ct.byref(selection),
        ):
            raise ValueError("Native selection query timed out.")
        packed = selection.value & 0xFFFFFFFF
        # EM_GETSEL returns -1 when either position is outside its packed 16-bit range.
        if packed == 0xFFFFFFFF or (packed & 0xFFFF) != (packed >> 16):
            raise ValueError("Native selection is nonempty or exceeds supported range.")
        return NativeTarget(hwnd, pid.value, edit, packed & 0xFFFF)

    def _selection(self) -> tuple[Any, Any]:
        auto = self.automation
        control = auto.GetFocusedControl()
        if (
            control is None
            or control.IsPassword
            or not control.IsEnabled
            or control.ControlType
            not in (auto.ControlType.EditControl, auto.ControlType.DocumentControl)
        ):
            raise ValueError("Focus is not a supported non-password text field.")
        pattern = control.GetPattern(auto.PatternId.TextPattern)
        if pattern is None:
            raise ValueError("Field does not expose text selection.")
        # Read-only is a TextPattern attribute (40015), also works for Document controls.
        ranges = pattern.GetSelection()
        # uiautomation 2.0.29 passes its wrapper instead of the COM pointer here.
        # Use IUIAutomationTextRange directly; never read selected document text.
        if len(ranges) != 1 or ranges[0].textRange.CompareEndpoints(0, ranges[0].textRange, 1) != 0:
            raise ValueError("Selection must be a single empty caret.")
        if ranges[0].GetAttributeValue(40015) != 0:
            raise ValueError("Field is read-only or editability is unknown.")
        return control, ranges[0]

    def snapshot(self) -> WindowSnapshot:
        """Cheap native identity check before audio starts; no accessibility calls."""
        hwnd = self.api.GetForegroundWindow()
        if not hwnd:
            raise ValueError("No foreground window.")
        pid = wt.DWORD()
        thread = self.api.GetWindowThreadProcessId(hwnd, ct.byref(pid))
        info = GUITHREADINFO(cbSize=ct.sizeof(GUITHREADINFO))
        if not self.api.GetGUIThreadInfo(thread, ct.byref(info)):
            raise ValueError("Focused window is unavailable.")
        rect = info.rcCaret
        return WindowSnapshot(
            hwnd,
            pid.value,
            info.hwndFocus or 0,
            info.hwndCaret or 0,
            (rect.left, rect.top, rect.right, rect.bottom),
        )

    def capture(self, expected: WindowSnapshot | None = None) -> Target | NativeTarget:
        before = self.snapshot()
        if expected is not None and before != expected:
            raise ValueError("Focus changed while the microphone was starting.")
        hwnd = before.hwnd
        native = self._native_target(hwnd)
        if native is not None:
            if self.snapshot() != before:
                raise ValueError("Focus changed during target verification.")
            return native
        control, caret = self._selection()
        pid = wt.DWORD()
        self.api.GetWindowThreadProcessId(hwnd, ct.byref(pid))
        if not hwnd or control.ProcessId != pid.value:
            raise ValueError("Focused field does not belong to foreground window.")
        runtime_id = tuple(control.GetRuntimeId())
        if not runtime_id:
            raise ValueError("Field identity unavailable.")
        if self.snapshot() != before:
            raise ValueError("Focus changed during target verification.")
        return Target(hwnd, pid.value, runtime_id, caret.Clone())

    def insert(
        self,
        target: Target | NativeTarget,
        text: str,
        permitted: Callable[[], bool] | None = None,
    ) -> None:
        events = unicode_inputs(text)
        if not self.api.IsWindow(target.hwnd) or self.api.GetForegroundWindow() != target.hwnd:
            raise ValueError("Target window changed.")
        if isinstance(target, NativeTarget):
            if self._native_target(target.hwnd) != target:
                raise ValueError("Native field or caret changed.")
        else:
            control, caret = self._selection()
            if (
                control.ProcessId != target.process_id
                or tuple(control.GetRuntimeId()) != target.runtime_id
                or not caret.Compare(target.caret)
            ):
                raise ValueError("Target field or caret changed.")
        # Do not release user-held modifiers or send text while they are held.
        if any(self.api.GetAsyncKeyState(k) & 0x8000 for k in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
            raise ValueError("Release modifier keys before insertion.")
        if self.api.GetForegroundWindow() != target.hwnd:
            raise ValueError("Target window changed.")
        if permitted is not None and not permitted():
            raise ValueError("Insertion was cancelled or timed out.")
        count = self.api.SendInput(len(events), events, ct.sizeof(INPUT))
        if count != len(events):
            raise RuntimeError(
                "Input was blocked or partially delivered; do not retry automatically."
            )
