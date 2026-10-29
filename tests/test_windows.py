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


@pytest.mark.parametrize("change", [None, "caret", "window", "expired"])
def test_gradual_native_delivery_rechecks_every_batch(monkeypatch, change):
    monkeypatch.setattr("localphraser.windows.time.sleep", lambda _: None)
    insertion, _, _ = insertion_fixture()
    position = [10]
    insertion._native_target = lambda hwnd: NativeTarget(123, 42, 456, position[0])

    def send(count, events, size):
        position[0] += count // 2
        if change == "caret":
            position[0] += 1
        elif change == "window":
            insertion.api.GetForegroundWindow.return_value = 999
        return count

    insertion.api.SendInput.side_effect = send

    def allowed():
        return change != "expired" or insertion.api.SendInput.call_count == 0

    if change:
        with pytest.raises(ValueError):
            insertion.insert_gradually(NativeTarget(123, 42, 456, 10), "a" * 80, allowed)
        assert insertion.api.SendInput.call_count == 1
    else:
        insertion.insert_gradually(NativeTarget(123, 42, 456, 10), "a" * 80, allowed)
        assert insertion.api.SendInput.call_count == 3 and position[0] == 90


def test_gradual_delivery_validates_entire_message_before_any_input():
    insertion, _, target = insertion_fixture()
    with pytest.raises(ValueError):
        insertion.insert_gradually(target, "a" * 80 + "\t", lambda: True)
    insertion.api.SendInput.assert_not_called()


def test_uia_provider_without_document_navigation_uses_single_checked_dispatch():
    insertion, _, target = insertion_fixture()
    position = [0]
    control = insertion._selection.return_value[0]

    class Range:
        def __init__(self, value):
            self.value = value
            self.textRange = self

        def Clone(self):
            # Some providers update existing range anchors when the document changes.
            return Range(position[0])

        def Move(self, unit, count, waitTime=0):
            self.value += count
            return count

        def CompareEndpoints(self, *args):
            return 0

        def Compare(self, other):
            return self.value == other.value

    target.caret = Range(0)
    insertion._selection = lambda: (control, Range(position[0]))

    def send(count, events, size):
        position[0] += count // 2
        return count

    insertion.api.SendInput.side_effect = send
    insertion.insert_gradually(target, "a" * 2600, lambda: True)
    insertion.api.SendInput.assert_called_once()
    assert position[0] == 2600


@pytest.mark.parametrize("suffix", ["é", "\n"])
def test_unicode_and_multiline_use_single_checked_delivery(suffix):
    insertion, _, target = insertion_fixture()
    insertion.insert = Mock()
    insertion.insert_gradually(target, "a" * 80 + suffix, lambda: True)
    insertion.insert.assert_called_once()


def test_paced_delivery_does_not_resume_after_observed_field_change(monkeypatch):
    monkeypatch.setattr("localphraser.windows.time.sleep", lambda _: None)
    insertion, _, _ = insertion_fixture()
    position = [0]
    changed = [False]

    def native(hwnd):
        if changed[0]:
            changed[0] = False  # Even an immediate return must not resume insertion.
            return NativeTarget(123, 42, 999, position[0])
        return NativeTarget(123, 42, 456, position[0])

    def send(count, events, size):
        position[0] += count // 2
        changed[0] = True
        return count

    insertion._native_target = native
    insertion.api.SendInput.side_effect = send
    with pytest.raises(ValueError, match="field changed"):
        insertion.insert_gradually(NativeTarget(123, 42, 456, 0), "a" * 80, lambda: True)
    assert insertion.api.SendInput.call_count == 1


def test_paced_partial_send_is_never_retried():
    insertion, _, _ = insertion_fixture()
    insertion._native_target = lambda hwnd: NativeTarget(123, 42, 456, 0)
    insertion.api.SendInput.return_value = 1
    with pytest.raises(RuntimeError, match="partially delivered"):
        insertion.insert_gradually(NativeTarget(123, 42, 456, 0), "a" * 80, lambda: True)
    insertion.api.SendInput.assert_called_once()


@pytest.mark.parametrize("change", [None, "caret", "field", "expired"])
def test_uia_pacing_rebuilds_position_from_current_document(monkeypatch, change):
    monkeypatch.setattr("localphraser.windows.time.sleep", lambda _: None)
    clock = iter(range(1000))
    monkeypatch.setattr("localphraser.windows.time.monotonic", lambda: next(clock) / 10)
    insertion, _, target = insertion_fixture()
    insertion.automation = SimpleNamespace(PatternId=SimpleNamespace(TextPattern=10014))
    position, length, anchor = [15], [15], [15]

    class Range:
        def __init__(self, start, end=None, saved=False):
            self.start, self.end = start, start if end is None else end
            self.saved = saved
            self.textRange = self

        def Clone(self):
            return Range(anchor[0]) if self.saved else Range(self.start, self.end)

        def Move(self, unit, count, waitTime=0):
            previous = self.start
            self.start = min(length[0], max(0, self.start + count))
            self.end = self.start
            return self.start - previous

        def MoveEndpointByRange(self, endpoint, other, other_endpoint):
            assert endpoint == 1 and other_endpoint == 0
            self.end = other.start

        def CompareEndpoints(self, endpoint, other, other_endpoint):
            return (self.start if endpoint == 0 else self.end) - (
                other.start if other_endpoint == 0 else other.end
            )

        def Compare(self, other):
            return self.start == other.start and self.end == other.end

    control = SimpleNamespace(
        ProcessId=42,
        GetRuntimeId=lambda: [9] if change == "field" and position[0] > 15 else [1, 2, 3],
        GetPattern=lambda _: SimpleNamespace(DocumentRange=Range(0, length[0])),
    )
    target.caret = Range(15, saved=True)
    insertion._selection = lambda: (control, Range(position[0]))

    def send(count, events, size):
        position[0] += count // 2
        length[0] += count // 2
        anchor[0] = position[0]
        if change == "caret":
            position[0] += 1
        return count

    insertion.api.SendInput.side_effect = send

    def permitted():
        return change != "expired" or insertion.api.SendInput.call_count == 0

    if change:
        with pytest.raises(ValueError):
            insertion.insert_gradually(target, "a" * 80, permitted)
        assert insertion.api.SendInput.call_count == 1
    else:
        insertion.insert_gradually(target, "a" * 80, permitted)
        assert insertion.api.SendInput.call_count == 3 and position[0] == 95
