"""Scoped Caps Lock suppression or registered chords with held-key release polling."""

import ctypes as ct
import threading
from collections.abc import Callable
from ctypes import wintypes as wt
from typing import Any

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, QTimer, Signal

from localphraser.config import parse_hotkey
from localphraser.windows import user32

HOOKPROC = ct.WINFUNCTYPE(ct.c_ssize_t, ct.c_int, wt.WPARAM, wt.LPARAM)


class _CapsEvents(QObject):
    changed = Signal(int, bool)


class _CapsListener:
    """A dedicated message thread keeps Windows' hook deadline independent of the UI."""

    def __init__(self, changed: Callable[[bool], None], initial_down: bool = False):
        self.changed = changed
        self.api = user32()
        self.api.SetWindowsHookExW.argtypes = [ct.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
        self.api.SetWindowsHookExW.restype = wt.HANDLE
        self.api.UnhookWindowsHookEx.argtypes = [wt.HANDLE]
        self.api.UnhookWindowsHookEx.restype = wt.BOOL
        self.api.CallNextHookEx.argtypes = [wt.HANDLE, ct.c_int, wt.WPARAM, wt.LPARAM]
        self.api.CallNextHookEx.restype = ct.c_ssize_t
        self.api.GetMessageW.argtypes = [ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
        self.api.GetMessageW.restype = wt.BOOL
        self.api.PeekMessageW.argtypes = [ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
        self.api.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.thread_id = 0
        self.handle: Any = None
        self.down = initial_down
        self.thread = threading.Thread(target=self._run, name="caps-lock", daemon=True)

    def _event(self, code: int, message: int, pointer: int) -> int:
        # Read only the virtual key first; unrelated input passes through untouched.
        if code >= 0 and ct.cast(pointer, ct.POINTER(wt.DWORD))[0] == 0x14:
            if message in (0x100, 0x104) and not self.down:
                self.down = True
                self.changed(True)
            elif message in (0x101, 0x105) and self.down:
                self.down = False
                self.changed(False)
            return 1  # Prevent Windows from toggling capitalization.
        return self.api.CallNextHookEx(None, code, message, pointer)

    def _run(self) -> None:
        kernel = ct.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [wt.LPCWSTR]
        kernel.GetModuleHandleW.restype = wt.HMODULE
        kernel.GetCurrentThreadId.restype = wt.DWORD
        callback = HOOKPROC(self._event)  # Strong reference lasts until the hook is removed.
        try:
            self.thread_id = kernel.GetCurrentThreadId()
            msg = wt.MSG()
            self.api.PeekMessageW(ct.byref(msg), None, 0, 0, 0)  # Create the message queue.
            self.handle = self.api.SetWindowsHookExW(13, callback, kernel.GetModuleHandleW(None), 0)
            self.ready.set()
            if self.handle:
                while (
                    not self.stopping.is_set()
                    and self.api.GetMessageW(ct.byref(msg), None, 0, 0) > 0
                ):
                    pass  # Low-level hook callbacks are delivered by GetMessage itself.
        finally:
            self.ready.set()
            if self.handle:
                self.api.UnhookWindowsHookEx(self.handle)

    def start(self) -> None:
        self.thread.start()
        if not self.ready.wait(3) or not self.handle:
            self.close()
            raise ValueError("Cannot enable Caps Lock dictation. Choose a modifier shortcut.")

    def close(self) -> None:
        self.stopping.set()
        if self.thread_id:
            self.api.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)  # WM_QUIT
        self.thread.join(timeout=2)


class Hotkey(QAbstractNativeEventFilter):
    def __init__(self, press: Callable[[], None], release: Callable[[], None]):
        super().__init__()
        self.api = user32()
        self.press = press
        self.release = release
        self.identifier = 0x4C50
        self.registered = False
        self.capture_callback: Callable[[], None] | None = None
        self.capture_release_callback: Callable[[], None] | None = None
        self._caps_handle: Any = None
        self._caps_held = False
        self._generation = 0
        self._caps_events = _CapsEvents()
        self._caps_events.changed.connect(self._caps_changed, Qt.ConnectionType.QueuedConnection)
        self.keys: tuple[int, ...] = ()
        self.timer = QTimer()
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._check_release)

    def register(self, shortcut: str) -> None:
        modifiers, vk, keys = parse_hotkey(shortcut)
        if shortcut == "CapsLock":
            if self._caps_handle:
                return
            generation = self._generation + 1
            listener = _CapsListener(
                lambda down: self._caps_events.changed.emit(generation, down),
                initial_down=self._caps_held,
            )
            listener.start()
            if self.registered:
                self.api.UnregisterHotKey(None, self.identifier)
            self.timer.stop()
            self._generation = generation
            self._caps_handle = listener
            self.keys = keys
            self.registered = True
            return
        # New ID allows transactional replacement without dropping the working shortcut.
        next_id = 0x4C51 if self.identifier == 0x4C50 else 0x4C50
        if not self.api.RegisterHotKey(None, next_id, modifiers | 0x4000, vk):
            raise ValueError("Shortcut unavailable. It may be reserved or used by another app.")
        if self.registered and not self._caps_handle:
            self.api.UnregisterHotKey(None, self.identifier)
        self._unhook_caps()
        self._caps_held = False
        self.identifier = next_id
        self.keys = keys
        self.registered = True

    def nativeEventFilter(self, event_type: Any, message: int) -> tuple[bool, int]:
        msg = wt.MSG.from_address(int(message))
        if not self._caps_handle and msg.message == 0x0312 and msg.wParam == self.identifier:
            if not self.timer.isActive():
                self.timer.start()
                self.press()
            return True, 0
        return False, 0

    def _caps_changed(self, generation: int, down: bool) -> None:
        if self._caps_handle and generation == self._generation:
            if self.capture_callback is not None:
                if down:
                    self.capture_callback()
                elif self.capture_release_callback is not None:
                    self.capture_release_callback()
            elif down:
                self.press()
            else:
                self.release()

    def _unhook_caps(self) -> None:
        if self._caps_handle:
            self._caps_handle.close()
            self._caps_held = self._caps_handle.down
            self._caps_handle = None
            self._generation += 1

    def _check_release(self) -> None:
        if not all(self.api.GetAsyncKeyState(k) & 0x8000 for k in self.keys):
            self.timer.stop()
            self.release()

    def close(self) -> None:
        self.timer.stop()
        if self.registered and not self._caps_handle:
            self.api.UnregisterHotKey(None, self.identifier)
        self._unhook_caps()
        self.registered = False
