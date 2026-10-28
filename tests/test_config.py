import json

import pytest

from localphraser.config import Config, load_config, parse_hotkey, save_config


@pytest.mark.parametrize(
    "hotkey", ["Space", "Ctrl+Ctrl+A", "Ctrl+F12", "Shift+A", "Win+A", "Alt+A"]
)
def test_invalid_shortcuts(hotkey):
    with pytest.raises(ValueError):
        parse_hotkey(hotkey)


def test_hotkey_values():
    assert Config().hotkey == "CapsLock"
    assert parse_hotkey("CapsLock") == (0, 0x14, (0x14,))
    assert parse_hotkey("F9") == (0, 0x78, (0x78,))
    assert parse_hotkey("Ctrl+Alt+Space") == (3, 32, (17, 18, 32))


def test_roundtrip(tmp_path):
    config = Config(hotkey="Ctrl+Shift+F9", model_root=str(tmp_path / "models"))
    path = tmp_path / "settings" / "config.json"
    save_config(config, path)
    assert load_config(path) == config
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.parametrize(
    "values",
    [
        {"max_seconds": True},
        {"max_seconds": 301},
        {"auto_insert": "false"},
        {"cpu_threads": 0},
        {"model": "cloud"},
        {"model_root": "relative"},
        {"microphone": 1},
        {"keep_microphone_ready": "yes"},
    ],
)
def test_invalid_settings(values):
    with pytest.raises(ValueError):
        Config(**values).validate()


def test_corrupt_settings_are_not_overwritten(tmp_path):
    path = tmp_path / "config.json"
    content = json.dumps({"unknown": "value"})
    path.write_text(content)
    with pytest.raises(ValueError):
        load_config(path)
    assert path.read_text() == content
