from unittest.mock import Mock

import pytest

from localphraser.activation import ShortcutActivation
from localphraser.config import Config


@pytest.fixture
def gesture():
    now, active, scheduled = [0.0], [False], []
    press = Mock(side_effect=lambda: active.__setitem__(0, True))
    release = Mock(side_effect=lambda: active.__setitem__(0, False))
    cancel = Mock(side_effect=lambda: active.__setitem__(0, False))
    toggle = Mock(side_effect=lambda: active.__setitem__(0, not active[0]))
    handler = ShortcutActivation(
        press,
        release,
        toggle,
        cancel,
        lambda: active[0],
        clock=lambda: now[0],
        schedule=lambda ms, call: scheduled.append(call),
    )

    def tap(duration=0.04, pause=0.08):
        handler.key_down()
        now[0] += duration
        handler.key_up()
        now[0] += pause

    return handler, now, active, scheduled, press, release, cancel, toggle, tap


def test_default_supports_hold_and_latched_double_tap(gesture):
    handler, now, active, scheduled, press, release, cancel, _, tap = gesture
    assert Config().activation_mode == "both"
    handler.key_down()
    assert active[0]  # Opening audio is captured immediately.
    handler.key_down()  # Auto-repeat is ignored.
    now[0] += 0.4
    handler.key_up()
    assert not active[0] and press.call_count == 1 and release.call_count == 1
    tap()
    tap()
    assert active[0] and release.call_count == 1
    for expire in scheduled:
        expire()  # Stale timeout must not cancel latched recording.
    cancel.assert_not_called()
    now[0] += 2
    tap()
    tap()
    assert not active[0] and release.call_count == 2


def test_lone_tap_cancels_buffer_without_transcription(gesture):
    _, _, active, scheduled, _, release, cancel, _, tap = gesture
    tap()
    assert active[0]
    scheduled.pop()()
    assert not active[0]
    cancel.assert_called_once()
    release.assert_not_called()


def test_lone_tap_during_latched_recording_does_not_stop_it(gesture):
    _, now, active, scheduled, _, release, cancel, _, tap = gesture
    tap()
    tap()
    now[0] += 1
    tap()
    scheduled[-1]()
    assert active[0]
    release.assert_not_called()
    cancel.assert_not_called()


def test_slow_taps_do_not_latch_and_reset_revokes_timeouts(gesture):
    handler, now, active, scheduled, _, release, cancel, _, tap = gesture
    tap()
    now[0] += 1
    tap()
    assert cancel.call_count == 1 and active[0]
    handler.reset()
    for expire in scheduled:
        expire()
    assert active[0] and cancel.call_count == 1
    release.assert_not_called()


@pytest.mark.parametrize("mode", ["hold", "double_tap"])
def test_optional_single_gesture_modes(gesture, mode):
    handler, _, active, _, press, release, _, toggle, tap = gesture
    handler.mode = mode
    tap()
    if mode == "hold":
        press.assert_called_once()
        release.assert_called_once()
        assert not active[0]
    else:
        press.assert_not_called()
        release.assert_not_called()
        tap()
        assert active[0] and toggle.call_count == 1
        tap()
        tap()
        assert not active[0] and toggle.call_count == 2


def test_auto_stop_between_taps_does_not_restart_recording(gesture):
    handler, _, active, _, _, release, _, _, tap = gesture
    tap()
    tap()
    tap()
    active[0] = False  # Recording limit or cancellation.
    handler.reset()
    release.assert_not_called()


def test_real_qt_timeout_revokes_only_the_lone_tap(app):
    from PySide6.QtTest import QTest

    active = [False]
    cancel = Mock(side_effect=lambda: active.__setitem__(0, False))
    release = Mock(side_effect=lambda: active.__setitem__(0, False))
    handler = ShortcutActivation(
        lambda: active.__setitem__(0, True), release, Mock(), cancel, lambda: active[0]
    )
    handler.key_down()
    QTest.qWait(20)
    handler.key_up()
    QTest.qWait(390)
    cancel.assert_called_once()
    handler.key_down()
    QTest.qWait(20)
    handler.key_up()
    QTest.qWait(50)
    handler.key_down()
    QTest.qWait(20)
    handler.key_up()
    QTest.qWait(390)
    assert active[0] and cancel.call_count == 1
    release.assert_not_called()
