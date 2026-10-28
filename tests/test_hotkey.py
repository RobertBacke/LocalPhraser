import ctypes
from ctypes import wintypes
from unittest.mock import Mock

import pytest

from localphraser.hotkey import Hotkey, _CapsListener


def hotkey_fixture():
    # Exercise event logic without constructing Qt timers or registering a real chord.
    hotkey = Hotkey.__new__(Hotkey)
    super(Hotkey, hotkey).__init__()
    hotkey.api = Mock()
    hotkey.identifier = 100
    hotkey.registered = False
    hotkey.capture_callback = None
    hotkey.capture_release_callback = None
    hotkey._caps_handle = None
    hotkey._caps_held = False
    hotkey.keys = (17, 18, 32)
    hotkey.timer = Mock()
    hotkey.press = Mock()
    hotkey.release = Mock()
    hotkey._generation = 0
    return hotkey


def test_release_polls_only_chord_and_stops():
    hotkey = hotkey_fixture()
    hotkey.api.GetAsyncKeyState.side_effect = [0x8000, 0x8000, 0]
    hotkey._check_release()
    assert [call.args[0] for call in hotkey.api.GetAsyncKeyState.call_args_list] == [17, 18, 32]
    hotkey.timer.stop.assert_called_once()
    hotkey.release.assert_called_once()


def test_repeated_notification_does_not_start_again():
    hotkey = hotkey_fixture()
    hotkey.timer.isActive.return_value = True
    message = wintypes.MSG(message=0x0312, wParam=100)
    assert hotkey.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message)) == (True, 0)
    hotkey.press.assert_not_called()


def test_conflict_keeps_working_registration():
    hotkey = hotkey_fixture()
    hotkey.registered = True
    hotkey.api.RegisterHotKey.return_value = False
    with pytest.raises(ValueError, match="unavailable"):
        hotkey.register("Ctrl+Alt+Space")
    hotkey.api.UnregisterHotKey.assert_not_called()
    assert hotkey.identifier == 100


def test_caps_events_suppress_toggle_and_ignore_repeats():
    listener = object.__new__(_CapsListener)
    listener.down = False
    listener.changed = Mock()
    listener.api = Mock()
    key = wintypes.DWORD(0x14)
    pointer = ctypes.addressof(key)
    assert listener._event(0, 0x100, pointer) == 1
    assert listener._event(0, 0x100, pointer) == 1
    assert listener._event(0, 0x101, pointer) == 1
    assert [call.args for call in listener.changed.call_args_list] == [(True,), (False,)]
    listener.api.CallNextHookEx.assert_not_called()


def test_caps_handler_forwards_unrelated_events_without_capture():
    listener = object.__new__(_CapsListener)
    listener.changed = Mock()
    listener.api = Mock()
    listener.api.CallNextHookEx.return_value = 42
    key = wintypes.DWORD(65)
    assert listener._event(0, 0x100, ctypes.addressof(key)) == 42
    assert listener._event(-1, 0x100, 0) == 42
    listener.changed.assert_not_called()


def test_stale_caps_notification_is_ignored_after_shortcut_change():
    hotkey = hotkey_fixture()
    hotkey._caps_handle = Mock()
    hotkey._generation = 2
    hotkey._caps_changed(1, True)
    hotkey.press.assert_not_called()
    hotkey._unhook_caps()
    hotkey._caps_changed(2, False)
    hotkey.release.assert_not_called()


def test_shortcut_capture_does_not_trigger_dictation():
    hotkey = hotkey_fixture()
    hotkey._caps_handle = Mock()
    hotkey.capture_callback = Mock()
    hotkey._caps_changed(0, True)
    hotkey._caps_changed(0, False)
    hotkey.capture_callback.assert_called_once_with()
    hotkey.press.assert_not_called()
    hotkey.release.assert_not_called()


def test_holding_selected_caps_does_not_start_a_new_recording():
    listener = object.__new__(_CapsListener)
    listener.down = True  # Carried across hook restoration after key selection.
    listener.changed = Mock()
    listener.api = Mock()
    key = wintypes.DWORD(0x14)
    pointer = ctypes.addressof(key)
    listener._event(0, 0x100, pointer)
    listener.changed.assert_not_called()
    listener._event(0, 0x101, pointer)
    listener._event(0, 0x100, pointer)
    assert [call.args for call in listener.changed.call_args_list] == [(False,), (True,)]
