"""Windows resizing/snap integration for the custom desktop title bar."""

import ctypes
import sys
from ctypes import wintypes
from functools import lru_cache

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget


@lru_cache(maxsize=1)
def api():
    user = ctypes.WinDLL("user32")
    user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    return user


def enable_snap(window: QWidget) -> bool:
    if sys.platform != "win32" or QApplication.platformName() != "windows":
        return False
    user = api()
    hwnd = int(window.winId())
    style = user.GetWindowLongPtrW(hwnd, -16)
    user.SetWindowLongPtrW(hwnd, -16, style | 0x00040000 | 0x00010000 | 0x00020000)
    return bool(user.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037))


def native_message(message: int):
    if sys.platform != "win32" or QApplication.platformName() != "windows":
        return None
    return ctypes.cast(message, ctypes.POINTER(wintypes.MSG)).contents


def hit_test(window: QWidget, message: int) -> int | None:
    msg = native_message(message)
    if msg is None:
        return None
    if msg.message != 0x0084:  # WM_NCHITTEST
        return None
    x = ctypes.c_short(msg.lParam & 0xFFFF).value
    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
    user = api()
    rect = wintypes.RECT()
    if not user.GetWindowRect(msg.hWnd, ctypes.byref(rect)):
        return None
    edge = max(4, round(6 * window.devicePixelRatioF()))
    if not window.isMaximized():
        left, right = x < rect.left + edge, x >= rect.right - edge
        top, bottom = y < rect.top + edge, y >= rect.bottom - edge
        if top:
            return 13 if left else 14 if right else 12
        if bottom:
            return 16 if left else 17 if right else 15
        if left or right:
            return 10 if left else 11
    point = wintypes.POINT(x, y)
    if not user.ScreenToClient(msg.hWnd, ctypes.byref(point)):
        return None
    scale = window.devicePixelRatioF()
    child = window.childAt(QPoint(round(point.x / scale), round(point.y / scale)))
    if child is not None:
        if child.property("systemMaximizeButton"):
            return 9  # HTMAXBUTTON lets Windows show its own Snap Layout menu.
        if child.property("systemDragHandle"):
            return 2  # HTCAPTION uses the OS move/snap loop.
    return None
