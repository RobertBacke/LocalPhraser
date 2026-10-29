# Architecture

Windows x64 desktop MVP. UI and lifecycle run on Qt's owner thread. A single executor
per pipeline runs model loading/transcription; queued signals marshal results back.
No audio or transcription files are produced.

```text
Caps Lock hook / WM_HOTKEY → cheap native window/caret snapshot → microphone RAM buffer
  → background accessibility verification (concurrent with recording) → shortcut release
  → one ASR worker (local directory only) → optional polishing child → target-worker recheck
  → one Unicode SendInput batch OR latest-transcript/manual-copy recovery
```

- `config.py`: validated immutable settings, atomic JSON saves.
- `hotkey.py`: Caps Lock-specific suppression on a dedicated Windows message thread,
  with queued UI signals; registered modifier shortcuts use 15 ms release polling while held.
- `audio.py`: bounded preallocated RAM, PortAudio cleanup, overflow/disconnect handling.
- `shortcut.py`: focused key/chord recorder with cancellation and validation.
- `target_worker.py`: single COM owner thread, opaque target tokens, verification deadlines.
- `pipeline.py`: explicit Idle/Recording/Transcribing/Inserting/Error lifecycle; backend protocols.
- `recognition.py`: lazy CPU INT8 local Whisper model, bundled VAD, optional user-entered
  vocabulary hints through `hotwords`, no implicit downloads or word-replacement rules.
- `refinement.py`: optional warm CPU llama.cpp process, bounded pipe requests, network-denied
  Python sockets, lexical preservation check, time limit and raw fallback.
- `refinement_models.py`: fixed publisher GGUF catalog with explicit download and verification.
- `windows.py`: pointer-safe Win32 ABI, UIA identity/selection/editability/caret validation;
  exact-class native EDIT fallback with bounded EM_GETSEL queries and matching focus/handle.
- `models.py`: explicit online installation with provenance and hashes, offline verification.
- `downloads.py`: owned QProcess installer lifecycle, cancellation and separate offline cleanup.
- `startup.py`: quoted windowless startup command and per-profile current-user Run entry.
- `ui.py`: tray, nonactivating multi-monitor indicator, settings, recovery transcript, UI dispatcher.
- `main.py`: CLI, one-instance lock, separate online/offline entry paths.

Recording and inference never overlap; repeat events are ignored. Errors return to idle,
with sanitized messages. Polished mode adds a Polishing state. Text stays available on insertion failures. No automatic retry
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
Launch upon startup is disabled by default; saving a changed preference updates only its profile's
registry value, with rollback if configuration persistence fails. Normal launches do not
reconcile registration. New microphone identities combine exact name/API rather than relying
on ambiguous PortAudio substring matching or a persistent numeric index.
Phase 2 adds an independent Refiner protocol. Raw mode never loads llama.cpp. Polished
mode starts a spawn child on the existing background executor after the microphone starts
and keeps its model warm. Preparation loads the model without sending any text; recording
and ASR can overlap that loading. Raw mode does not prepare a model. The ASR executor waits on
a bounded pipe reply while the GUI remains responsive. Timeout/close terminates the child.
The pipe reader owns closing its handle: closing it from the UI while Windows polls it
reproduced an INVALID_HANDLE crash and is explicitly avoided. Shutdown suppresses queued
inference results. Frozen entry points call multiprocessing.freeze_support.

Audio is cleared before refinement begins. Raw and result text for the latest dictation are
held in RAM for comparison. There are no transcript files, disk prompt caches, HTTP servers,
or cloud clients. Input is capped at 3,000 characters, context at 4,096 tokens, output at
1,024 tokens, and the default process response wait at 15 seconds. Oversize/context failures
and non-preserving edits fall back to raw. Cancellation/termination adds small OS overhead.
Custom instructions cannot bypass lexical preservation, which still cannot certify meaning.

The focus-check/input-delivery interval cannot be made atomic. UIA range tracking is provider
dependent. Selected text and uncertain targets are refused; privileged input is unsupported.
Do not represent this as universal compatibility or a formal security boundary.
