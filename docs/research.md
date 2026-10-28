# Technical research — 2026-10-28

Repository/documentation review, not comparative local benchmarking. No third-party
application source or assets were copied. Maintenance was inferred from current source
and documentation, not independently audited release histories.

| Project | Verified approach | Useful pattern / constraint |
| --- | --- | --- |
| [Handy](https://github.com/cjpais/Handy) | MIT application, Tauri/Rust, tray, configurable push/toggle shortcuts, local model options | Keep dictation a focused utility; separate recording and inference. Its [Cargo manifest](https://github.com/cjpais/Handy/blob/main/src-tauri/Cargo.toml) lists native recording, resampling and input integrations. More native engineering than needed for the first Python increment. Branding is separately restricted. |
| [VoiceInk](https://github.com/Beingpax/VoiceInk) | Native macOS, GPLv3, whisper.cpp and additional native inference options | Platform integration matters; macOS-specific code is not a Windows shortcut. GPL code is not copied into this MIT project. |
| [OpenWhispr](https://github.com/OpenWhispr/openwhispr) | MIT desktop app, Electron/React, whisper.cpp and sherpa-onnx, local and cloud options | Explicit model selection and setup are useful. Browser runtime/cloud/account scope is unnecessary for LocalPhraser. |

None of these projects' memory or speed claims are treated as LocalPhraser measurements.
Packaging approaches include Tauri releases, native macOS builds, and Electron builder;
their installer size, known issue lists, and application coverage need a deeper comparison
before public distribution. We reviewed Handy's documented focus/overlay limitations as
evidence to make our indicator nonactivating and to retain manual recovery.

## Stack decision

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): native CTranslate2 inference,
  CPU INT8, Python API, local directory loading. Published benchmarks depend on model,
  beam size, hardware and batching; they do not establish our latency. Use one worker and
  small English models first. `base.en` is a hypothesis to benchmark against tiny/small.
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp): credible native alternative with
  quantization and broad platform support. More build/binding integration; keep the ASR
  protocol replaceable if measurements justify it.
- [Qt Widgets/PySide6](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html):
  mature tray, settings, threading/signals, DPI support. Essentials avoids unused Qt modules.
  Runtime footprint is larger than a bespoke native utility; measure before rewriting.
- [sounddevice](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html):
  PortAudio input stream into bounded 16 kHz mono float32 RAM. Check callback status,
  close streams, reject incompatible devices clearly. A WASAPI/resampling implementation
  remains an alternative if real microphone testing shows compatibility problems.
- [RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey):
  explicit conflict reporting, no global keyboard hook, MOD_NOREPEAT. Windows reports
  activation, not release; a timer checks only chord keys while held. Reserved chords fail.
- Caps Lock is the default. Native testing showed RegisterHotKey still toggles its Windows
  capitalization state. A [low-level keyboard callback](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelkeyboardproc)
  therefore consumes only Caps Lock events, suppresses repeat presses, and queues UI work.
  A dedicated message thread keeps hook execution independent of potentially slow UIA calls.
  Unrelated events are forwarded without collection; switching to a chord removes the hook.
- [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput):
  Unicode keyboard input, subject to UIPI; no elevation bypass. Selection/caret and identity
  must first be confirmed using [UI Automation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows).
  Clipboard paste supports more fields but creates ownership/race/restoration hazards.
  ValuePattern.SetValue replaces whole values and is unsuitable for insertion.
- Native standard EDIT controls may lack TextPattern. A real fixture demonstrated this,
  so we use [GetGUIThreadInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getguithreadinfo)
  and a 100 ms bounded [EM_GETSEL](https://learn.microsoft.com/en-us/windows/win32/controls/em-getsel)
  query for the exact `Edit` class only. Reject selected text, password/read-only styles,
  changed handles/caret and packed selection positions at or above 65,535. A disposable
  native EDIT fixture passed Unicode insertion and selection refusal outside the execution
  sandbox. This does not establish Notepad or browser compatibility.
- [PyInstaller](https://pyinstaller.org/en/stable/license.html): folder build first; keep Qt
  libraries dynamically replaceable. Packaging remains experimental until clean-machine testing.

## Models and licenses

[Systran base.en](https://huggingface.co/Systran/faster-whisper-base.en) documents an MIT
conversion of OpenAI Whisper. Model weights are setup downloads, not source assets.
Local hash manifests detect accidental corruption, not a malicious actor able to modify
both manifest and files. Repository commit and LFS hashes are checked/recorded on install;
this is HTTPS provenance, not an independently signed model supply chain.

Local LLM model selection/benchmarks are deferred to Phase 2. No remote AI SDK, account,
server, Vercel integration, or external inference provider is needed for this architecture.
