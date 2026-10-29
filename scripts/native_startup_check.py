"""Exercise an owned disposable registry key; never enable actual sign-in startup."""

import uuid
import winreg
from pathlib import Path
from unittest.mock import patch

from localphraser import startup


def main() -> None:
    key_name = rf"Software\LocalPhraser-StartupTest-{uuid.uuid4().hex}"
    config = Path(".cache/startup-test/config.json").resolve()
    try:
        with patch.object(startup, "RUN_KEY", key_name):
            assert startup.read_entry(config) is None
            command = startup.startup_command(config)
            startup.write_entry(config, command)
            assert startup.read_entry(config) == command
            startup.write_entry(config, None)
            assert startup.read_entry(config) is None
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_name)
    print("Disposable registry round-trip passed; actual Run key was untouched.")


if __name__ == "__main__":
    main()
