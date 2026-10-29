"""Exercise an installer only on an ephemeral GitHub Actions Windows runner."""

import argparse
import hashlib
import json
import os
import subprocess
import uuid
import winreg
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, timeout=180)


def check(installer: Path) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.name != "nt":
        raise RuntimeError("Installer acceptance is restricted to disposable Windows CI runners.")
    root = Path(os.environ["RUNNER_TEMP"]).resolve() / ("LocalPhraser test " + uuid.uuid4().hex)
    root.mkdir()
    app = root / "Installed app"
    executable = app / "LocalPhraser.exe"
    config = root / "config.json"
    config.write_text(
        json.dumps({"hotkey": "Ctrl+Shift+F10", "keep_microphone_ready": False}),
        encoding="utf-8",
    )
    # Exercise uninstall preservation of the actual default data location on this owned runner.
    data = Path(os.environ["LOCALAPPDATA"]) / "LocalPhraser"
    data.mkdir(exist_ok=True)
    sentinel = data / ("installer-test-" + uuid.uuid4().hex)
    sentinel.write_text("preserve settings and models", encoding="utf-8")
    options = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/DIR={app}"]
    run([str(installer.resolve()), *options])
    assert executable.is_file(), "Installed executable missing"
    shortcut = (
        Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/LocalPhraser.lnk"
    )
    assert shortcut.is_file(), "Start menu shortcut missing"
    run([str(executable), "--smoke-test", "--config", str(config)])
    # Reinstall over the existing version to exercise the upgrade path.
    run([str(installer.resolve()), *options])
    run([str(executable), "--smoke-test", "--config", str(config)])
    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    owned = "LocalPhraser-" + hashlib.sha256(str(config).encode()).hexdigest()[:12]
    other = "LocalPhraser-" + uuid.uuid4().hex[:12]
    unrelated = "Unrelated-" + uuid.uuid4().hex
    source_command = '"C:\\Other install\\LocalPhraser.exe" --config other.json'
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, run_key) as key:
            winreg.SetValueEx(key, owned, 0, winreg.REG_SZ, f'"{executable}" --config "{config}"')
            winreg.SetValueEx(key, other, 0, winreg.REG_SZ, source_command)
            winreg.SetValueEx(key, unrelated, 0, winreg.REG_SZ, f'"{executable}"')
        run([str(app / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
        assert not executable.exists(), "Uninstaller left the executable"
        assert not shortcut.exists(), "Uninstaller left the Start menu shortcut"
        assert sentinel.read_text(encoding="utf-8") == "preserve settings and models"
        assert config.is_file(), "Uninstaller removed external configuration"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key) as key:
            try:
                winreg.QueryValueEx(key, owned)
            except FileNotFoundError:
                pass
            else:
                raise AssertionError("Uninstaller left its owned startup entry")
            assert winreg.QueryValueEx(key, other)[0] == source_command
            assert winreg.QueryValueEx(key, unrelated)[0] == f'"{executable}"'
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
            for name in (owned, other, unrelated):
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        sentinel.unlink(missing_ok=True)
    print("Installer: install, launch, reinstall, uninstall, data/other-entry preservation passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    check(parser.parse_args().installer)
