import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from localphraser.windows import (
    INPUT,
    NativeTarget,
    Target,
    WindowsInsertion,
    WindowSnapshot,
    unicode_inputs,
)


def test_input_abi_and_unicode_surrogates():
    assert ctypes.sizeof(INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
    events = unicode_inputs("A😀\n")
    assert [event.ki.wScan for event in events[::2]] == [65, 0xD83D, 0xDE00, 13]
    assert all(event.ki.dwFlags == 6 for event in events[1::2])


@pytest.mark.parametrize("text", ["", "bad\x00", "bad\t", "x" * 16001])
def test_reject_controls_and_unbounded_input(text):
    with pytest.raises(ValueError):
        unicode_inputs(text)


def insertion_fixture():
    insertion = object.__new__(WindowsInsertion)
    insertion.api = Mock()
    insertion.api.IsWindow.return_value = True
    insertion.api.GetForegroundWindow.return_value = 123
    insertion.api.GetAsyncKeyState.return_value = 0
    control = SimpleNamespace(ProcessId=42, GetRuntimeId=lambda: [1, 2, 3])
    caret = Mock()
    caret.Compare.return_value = True
    insertion._selection = Mock(return_value=(control, caret))
    return insertion, caret, Target(123, 42, (1, 2, 3), object())


@pytest.mark.parametrize("change", ["window", "caret", "modifier", "identity"])
def test_target_change_never_sends(change):
    insertion, caret, target = insertion_fixture()
    if change == "window":
        insertion.api.GetForegroundWindow.return_value = 999
    elif change == "caret":
        caret.Compare.return_value = False
    elif change == "modifier":
        insertion.api.GetAsyncKeyState.return_value = 0x8000
    else:
        target.runtime_id = (9,)
    with pytest.raises(ValueError):
        insertion.insert(target, "hello")
    insertion.api.SendInput.assert_not_called()


def test_partial_delivery_is_not_retried():
    insertion, _, target = insertion_fixture()
    insertion.api.SendInput.return_value = 1
    with pytest.raises(RuntimeError):
        insertion.insert(target, "hello")
    insertion.api.SendInput.assert_called_once()


@pytest.mark.parametrize("unsafe", ["password", "disabled", "selection", "readonly", "unknown"])
def test_selection_safety_checks(unsafe):
    insertion = object.__new__(WindowsInsertion)
    caret = Mock()
    caret.textRange.CompareEndpoints.return_value = 1 if unsafe == "selection" else 0
    caret.GetAttributeValue.return_value = (
        1 if unsafe == "readonly" else object() if unsafe == "unknown" else False
    )
    pattern = Mock()
    pattern.GetSelection.return_value = [caret]
    control = SimpleNamespace(
        IsPassword=unsafe == "password",
        IsEnabled=unsafe != "disabled",
        ControlType=1,
        GetPattern=lambda _: pattern,
    )
    insertion.automation = SimpleNamespace(
        GetFocusedControl=lambda: control,
        ControlType=SimpleNamespace(EditControl=1, DocumentControl=2),
        PatternId=SimpleNamespace(TextPattern=10014),
    )
    with pytest.raises(ValueError):
        insertion._selection()


def test_native_target_recheck_refuses_moved_caret():
    insertion, _, _ = insertion_fixture()
    target = NativeTarget(123, 42, 456, 10)
    insertion._native_target = Mock(return_value=NativeTarget(123, 42, 456, 11))
    with pytest.raises(ValueError, match="Native field or caret changed"):
        insertion.insert(target, "hello")
    insertion.api.SendInput.assert_not_called()


def test_expired_insertion_never_sends_input():
    insertion, _, target = insertion_fixture()
    with pytest.raises(ValueError, match="timed out"):
        insertion.insert(target, "hello", permitted=lambda: False)
    insertion.api.SendInput.assert_not_called()


def test_caret_snapshot_change_during_start_rejects_new_target():
    insertion, _, _ = insertion_fixture()
    expected = WindowSnapshot(123, 42, 456, 456, (1, 2, 3, 4))
    insertion.snapshot = Mock(return_value=WindowSnapshot(123, 42, 456, 456, (5, 6, 7, 8)))
    with pytest.raises(ValueError, match="Focus changed"):
        insertion.capture(expected)
    insertion._selection.assert_not_called()
