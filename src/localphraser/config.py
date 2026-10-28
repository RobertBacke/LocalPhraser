"""Validated, atomic local configuration. No transcripts belong here."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

MODELS = ("tiny.en", "base.en", "small.en")
MODIFIERS = {"Ctrl": (2, 0x11), "Alt": (1, 0x12), "Shift": (4, 0x10)}


def parse_hotkey(value: str) -> tuple[int, int, tuple[int, ...]]:
    if value == "CapsLock":
        return 0, 0x14, (0x14,)
    if value.startswith("F") and value[1:].isdigit() and 1 <= int(value[1:]) <= 11:
        vk = 0x70 + int(value[1:]) - 1
        return 0, vk, (vk,)
    parts = value.split("+")
    if len(parts) < 2 or len(set(parts)) != len(parts):
        raise ValueError("Use CapsLock or modifiers and a key, e.g. Ctrl+Alt+Space.")
    if any(part not in MODIFIERS for part in parts[:-1]):
        raise ValueError("Supported modifiers: Ctrl, Alt, Shift (case sensitive).")
    key = parts[-1]
    if key == "Space":
        vk = 0x20
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 11:
        vk = 0x70 + int(key[1:]) - 1
    elif len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        vk = ord(key)
    else:
        raise ValueError("Use Space, A–Z, 0–9, or F1–F11; Windows reserves F12.")
    mask = sum(MODIFIERS[p][0] for p in parts[:-1])
    if mask in (1, 4):
        raise ValueError("Use Ctrl or at least two modifiers to avoid ordinary typing conflicts.")
    return mask, vk, tuple(MODIFIERS[p][1] for p in parts[:-1]) + (vk,)


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "LocalPhraser"


@dataclass(frozen=True)
class Config:
    hotkey: str = "CapsLock"
    microphone: str | None = None
    model: str = "base.en"
    model_root: str = str(data_dir() / "models")
    auto_insert: bool = True
    max_seconds: int = 120
    cpu_threads: int = 4
    keep_microphone_ready: bool = True

    def validate(self) -> "Config":
        if not isinstance(self.hotkey, str):
            raise ValueError("Hotkey must be text.")
        parse_hotkey(self.hotkey)
        if self.model not in MODELS:
            raise ValueError("Unsupported speech model.")
        if not isinstance(self.model_root, str) or not self.model_root.strip():
            raise ValueError("Choose a model directory.")
        if not Path(self.model_root).is_absolute():
            raise ValueError("Model directory must be an absolute path.")
        if self.microphone is not None and not isinstance(self.microphone, str):
            raise ValueError("Microphone must be a device name or null.")
        if type(self.auto_insert) is not bool:
            raise ValueError("Automatic insertion must be true or false.")
        if type(self.keep_microphone_ready) is not bool:
            raise ValueError("Keep microphone ready must be true or false.")
        if type(self.max_seconds) is not int or not 1 <= self.max_seconds <= 300:
            raise ValueError("Recording limit must be 1–300 seconds.")
        if type(self.cpu_threads) is not int or not 1 <= self.cpu_threads <= 16:
            raise ValueError("CPU threads must be 1–16.")
        return self


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        return Config(**values).validate()
    except (ValueError, TypeError, OSError) as exc:
        raise ValueError(
            "Settings are invalid. Repair or move config.json; it was not overwritten."
        ) from exc


def save_config(config: Config, path: Path) -> None:
    config.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(asdict(config), stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
