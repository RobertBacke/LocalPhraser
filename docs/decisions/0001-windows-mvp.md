# ADR 0001: Windows-first Python/Qt MVP

Status: accepted for initial implementation; benchmark before release.

Use Python 3.12, Qt Widgets Essentials, sounddevice and faster-whisper CPU INT8.
Native Rust/Tauri and whisper.cpp are viable alternatives with more initial build/platform
integration work. Python provides a short route to a testable local pipeline while native
libraries perform inference. Costs are runtime footprint, dynamic dependency packaging,
and lifecycle constraints around uninterruptible native inference.

Modifier shortcuts use RegisterHotKey plus scoped release polling. The default Caps Lock
shortcut uses a key-specific hook on a dedicated message thread to prevent toggling
capitalization; unrelated events pass through immediately without collection. UIA validates
selection and target, then SendInput sends Unicode without changing the clipboard. Manual
copy is preferred when verification is unavailable. This trades compatibility coverage for
less destructive behavior. See research references and testing matrix.

The application code is MIT; Qt, PortAudio, models, and bundled dependencies retain their
own licenses. No models are bundled. No external services or telemetry are introduced.
