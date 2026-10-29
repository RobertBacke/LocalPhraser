"""Opt-in, per-configuration Windows startup entry. Never reconciled at app launch."""

import hashlib
import subprocess
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def value_name(config_path: Path) -> str:
    identity = str(config_path.resolve()).casefold().encode("utf-8")
    return "LocalPhraser-" + hashlib.sha256(identity).hexdigest()[:12]


def startup_command(config_path: Path) -> str:
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        arguments = [str(executable)]
    else:
        executable = executable.with_name("pythonw.exe")
        if not executable.is_file():
            raise ValueError(
                "Launch upon startup requires pythonw.exe or the Windows folder build."
            )
        arguments = [str(executable), "-m", "localphraser"]
    arguments += ["--config", str(config_path.resolve())]
    command = subprocess.list2cmdline(arguments)
    if len(command.encode("utf-16-le")) // 2 > 260:
        raise ValueError("Startup paths exceed Windows' 260-character Run command limit.")
    return command


def read_entry(config_path: Path) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, kind = winreg.QueryValueEx(key, value_name(config_path))
            if kind != winreg.REG_SZ or not isinstance(value, str):
                raise ValueError("The LocalPhraser startup entry has an unsupported format.")
            return value
    except FileNotFoundError:
        return None


def write_entry(config_path: Path, command: str | None) -> None:
    import winreg

    if command is not None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, value_name(config_path), 0, winreg.REG_SZ, command)
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, value_name(config_path))
        except FileNotFoundError:
            pass
