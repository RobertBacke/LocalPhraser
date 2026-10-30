import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from localphraser import startup
from localphraser.config import Config
from localphraser.pipeline import State
from localphraser.ui import Desktop


@pytest.fixture
def registry(monkeypatch):
    values = {"OtherApplication": ("unrelated", 1)}

    @contextmanager
    def open_key(*args):
        yield values

    def query(key, name):
        if name not in key:
            raise FileNotFoundError(name)
        return key[name]

    def remove(key, name):
        if name not in key:
            raise FileNotFoundError(name)
        del key[name]

    monkeypatch.setitem(
        sys.modules,
        "winreg",
        SimpleNamespace(
            HKEY_CURRENT_USER=1,
            KEY_READ=1,
            KEY_SET_VALUE=2,
            REG_SZ=1,
            OpenKey=open_key,
            CreateKeyEx=open_key,
            QueryValueEx=query,
            DeleteValue=remove,
            SetValueEx=lambda key, name, reserved, kind, value: key.__setitem__(
                name, (value, kind)
            ),
        ),
    )
    return values


def test_startup_entry_is_opt_in_and_scoped_to_profile(tmp_path, registry):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert not Config().start_at_login
    assert startup.read_entry(first) is None
    startup.write_entry(first, "first owned command")
    startup.write_entry(second, "second owned command")
    startup.write_entry(first, None)
    assert startup.read_entry(first) is None
    assert startup.read_entry(second) == "second owned command"
    assert registry["OtherApplication"] == ("unrelated", 1)


def test_startup_quotes_paths_and_uses_windowless_source_runtime(monkeypatch):
    directory = Path("C:/Python With Spaces")
    python = directory / "python.exe"
    pythonw = directory / "pythonw.exe"
    monkeypatch.setattr(Path, "is_file", lambda path: path.name == "pythonw.exe")
    monkeypatch.setattr(sys, "executable", str(python))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    config = Path("C:/My Settings/config.json")
    command = startup.startup_command(config)
    assert command.startswith(f'"{pythonw}" -m localphraser')
    assert f'--config "{config}"' in command
    assert "--background" in command
    monkeypatch.setattr(Path, "is_file", lambda path: False)
    with pytest.raises(ValueError, match="pythonw"):
        startup.startup_command(config)


def test_frozen_startup_and_overlong_paths(tmp_path, monkeypatch):
    executable = Path("C:/Apps/LocalPhraser.exe")
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert " -m localphraser" not in startup.startup_command(Path("C:/Settings/config.json"))
    with pytest.raises(ValueError, match="260"):
        startup.startup_command(tmp_path / ("x" * 240) / "config.json")


def test_settings_failure_restores_startup_entry_and_runtime(tmp_path, monkeypatch):
    desktop = object.__new__(Desktop)
    desktop.config = Config()
    desktop.config_path = tmp_path / "config.json"
    desktop.pipeline = Mock(state=State.IDLE)
    desktop.hotkey = Mock(registered=True)
    desktop.notify = Mock()
    writes = Mock()
    monkeypatch.setattr(startup, "read_entry", lambda path: None)
    monkeypatch.setattr(startup, "startup_command", lambda path: "owned command")
    monkeypatch.setattr(startup, "write_entry", writes)
    save = Mock(side_effect=OSError("Cannot write settings"))
    monkeypatch.setattr("localphraser.ui.save_config", save)
    with pytest.raises(OSError):
        desktop.apply(replace(desktop.config, start_at_login=True))
    assert writes.call_args_list == [
        call(desktop.config_path, "owned command"),
        call(desktop.config_path, None),
    ]
    assert desktop.config.start_at_login is False
    desktop.pipeline.shutdown.assert_not_called()


def test_unrelated_settings_save_with_startup_off_does_not_access_registry(tmp_path, monkeypatch):
    desktop = object.__new__(Desktop)
    desktop.closing = False
    desktop.allow_live_warmup = True
    desktop.window = Mock()
    desktop.config = Config()
    desktop.config_path = tmp_path / "config.json"
    desktop.pipeline = Mock(state=State.IDLE)
    desktop.hotkey = Mock(registered=True)
    desktop.make_pipeline = Mock(return_value=Mock())
    desktop.state_changed = Mock()
    monkeypatch.setattr(
        startup, "read_entry", Mock(side_effect=AssertionError("Registry accessed"))
    )
    monkeypatch.setattr("localphraser.ui.save_config", Mock())
    desktop.apply(replace(desktop.config, cpu_threads=2))
    assert desktop.config.cpu_threads == 2
