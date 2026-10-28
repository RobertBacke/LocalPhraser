# Architecture

Windows x64 desktop MVP. UI and lifecycle run on Qt's owner thread. A single executor
per pipeline runs model loading/transcription; queued signals marshal results back.
No audio or transcription files are produced.

```text
Caps Lock hook / WM_HOTKEY → cheap native window/caret snapshot → microphone RAM buffer
  → background accessibility verification (concurrent with recording) → shortcut release
  → one ASR worker (local directory only) → target-worker recheck
  → one Unicode SendInput batch OR latest-transcript/manual-copy recovery
```

- `config.py`: validated immutable settings, atomic JSON saves.
- `hotkey.py`: Caps Lock-specific suppression on a dedicated Windows message thread,
  with queued UI signals; registered modifier shortcuts use 15 ms release polling while held.
- `audio.py`: bounded preallocated RAM, PortAudio cleanup, overflow/disconnect handling.
- `shortcut.py`: focused key/chord recorder with cancellation and validation.
- `target_worker.py`: single COM owner thread, opaque target tokens, verification deadlines.
- `pipeline.py`: explicit Idle/Recording/Transcribing/Inserting/Error lifecycle; backend protocols.
- `recognition.py`: lazy CPU INT8 local Whisper model, bundled VAD, no implicit downloads.
- `windows.py`: pointer-safe Win32 ABI, UIA identity/selection/editability/caret validation;
  exact-class native EDIT fallback with bounded EM_GETSEL queries and matching focus/handle.
- `models.py`: explicit online installation with provenance and hashes, offline verification.
- `ui.py`: tray, nonactivating multi-monitor indicator, settings, recovery transcript, UI dispatcher.
- `main.py`: CLI, one-instance lock, separate online/offline entry paths.

Recording and inference never overlap; repeat events are ignored. Errors return to idle,
with sanitized messages. Text stays available on insertion failures. No automatic retry
is allowed after input delivery because partial insertion cannot be rolled back safely.
Microphone callback only copies into bounded memory; a UI watchdog handles duration and
disconnection. Audio starts before accessibility calls, which execute on a dedicated MTA
worker. The UI retains only opaque target tokens; COM ranges never cross threads. Target
verification times out to manual recovery after two seconds, and late targets are discarded.
The final insertion stage waits up to two seconds, with a deadline checked before SendInput
to prevent delayed delivery after a timeout. An isolated process for forcibly terminating
a hung native provider remains release hardening; threads cannot interrupt such calls.

By default an additional worker prepares an inactive input stream at startup/settings save.
Stop clears audio RAM and keeps the stream stopped for reuse. Opting out closes it after
each recording. Shutdown closes it permanently, including races with pending preparation.

Shutdown cancels capture and ignores worker results. Native inference cannot currently be
interrupted; Python executor shutdown allows the native call to finish before process exit.
Models remain warm for repeated use; changing settings releases the previous pipeline.
No speculative LLM backend is shipped in Phase 1. Add refinement as an independent protocol
with raw-text fallback in Phase 2.

The focus-check/input-delivery interval cannot be made atomic. UIA range tracking is provider
dependent. Selected text and uncertain targets are refused; privileged input is unsupported.
Do not represent this as universal compatibility or a formal security boundary.
