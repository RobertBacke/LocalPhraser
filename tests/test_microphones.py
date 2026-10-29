import sys
from types import SimpleNamespace

import pytest

from localphraser.audio import Microphone, microphones, resolve_microphone


@pytest.fixture
def devices(monkeypatch):
    inputs = [
        {"name": "Studio Mic", "hostapi": 0, "max_input_channels": 1},
        {"name": "Studio Mic", "hostapi": 1, "max_input_channels": 2},
        {"name": "Speakers", "hostapi": 1, "max_input_channels": 0},
    ]
    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(
            query_devices=lambda: inputs,
            query_hostapis=lambda: [{"name": "MME"}, {"name": "Windows WASAPI"}],
        ),
    )
    return inputs


def test_host_api_identity_and_resolution_after_device_reordering(devices):
    choices = microphones()
    assert len(choices) == 2
    selected = Microphone("Studio Mic", "Windows WASAPI")
    assert selected in choices
    assert resolve_microphone(selected.value) == 1
    devices.reverse()
    assert resolve_microphone(selected.value) == 1
    devices.insert(0, {"name": "Other Mic", "hostapi": 0, "max_input_channels": 1})
    assert resolve_microphone(selected.value) == 2


def test_ambiguous_names_and_duplicates_are_refused(devices):
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_microphone("Studio Mic")
    devices.append(dict(devices[1]))
    assert Microphone("Studio Mic", "Windows WASAPI") not in microphones()
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_microphone(Microphone("Studio Mic", "Windows WASAPI").value)


def test_default_and_unique_legacy_selection(devices):
    assert resolve_microphone(None) is None
    devices.pop(1)
    assert resolve_microphone("Studio Mic") == 0
    with pytest.raises(ValueError):
        resolve_microphone('device:{"wrong": "format"}')
    with pytest.raises(ValueError):
        resolve_microphone("missing device")
