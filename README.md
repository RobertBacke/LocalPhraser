# LocalPhraser

Free, open-source, offline push-to-talk dictation for Windows 10/11. Original application
code is MIT licensed, © 2026 Robert Backe.

**Early development / experimental Phase 2. Not a stable release.** A user has verified
microphone dictation, insertion in Codex and Chrome, offline use, and focus/selection safety.
Broader acceptance and clean-machine testing remain. See [testing](docs/testing.md).
The user also reports better results with Polished mode, including with Wi-Fi disconnected,
with noticeable processing delay.

![Settings preview](assets/settings.png)

## Run from source

Use 64-bit Python **3.12** (3.13 is allowed but not currently validated), with a modern
4-core CPU and 8 GB RAM; 16 GB is recommended. No GPU, API key, or account required.
The development setup uses [uv](https://docs.astral.sh/uv/).

```powershell
uv venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\python.exe -m localphraser install-model base.en
.venv\Scripts\python.exe -m localphraser
```

You can also use Python's `venv` and `pip install -e ".[dev]"` instead of uv.
The default installation requires roughly hundreds of MB for the runtime and model;
allow at least 2 GB free disk space for development and build artifacts. Actual installer
size and RAM usage have not yet been benchmarked.

1. Install a model explicitly, through the command above or Settings → Download.
2. Focus a supported editable text field with an empty selection.
3. Hold **Caps Lock**, speak, and release it.
4. The indicator shows listening/transcribing. Verified targets receive Unicode input.
5. If the field cannot be verified or focus/caret changes, use tray → Latest transcript → Copy.

Opening the EXE uses `%LOCALAPPDATA%\LocalPhraser\config.json` and its model directory.
An earlier development command with `--config .cache/dev/config.json` uses a separate profile.
To reuse those settings, launch the EXE with that same absolute `--config` path, or choose the
existing model directory in Settings and Save. Rebuilt EXEs share the normal default profile;
models do not need downloading for every build. No project-folder scan or silent migration occurs.

The tray provides start/stop recording, cancellation, latest transcript, settings, and Quit.
Single-click the tray icon to open or restore Settings; right-click it for the menu.
Tray-started recordings always use manual copy because interacting with the tray changes focus.
Settings include shortcut, microphone, model location/selection, CPU threads, recording limit,
and automatic insertion. Raw mode is the default. Optional Polished mode adds local
punctuation, capitalization, and hesitation removal. **Start LocalPhraser upon startup** is opt-in:
enable it in Settings and Save after choosing a permanent application location.
Microphones use exact device names and audio APIs; ambiguous duplicates are refused.
To choose a shortcut, click its **Change…** button and press Caps Lock, F1–F11, or a
modifier combination; **Save** applies it. Esc or moving focus away cancels selection.
Dictation is suspended while choosing, and Caps Lock selection does not toggle capitalization.
Caps Lock is reserved for dictation while this shortcut is selected; it does not toggle
capitalization. Choose a modifier shortcut such as `Ctrl+Alt+Space` to restore normal Caps Lock use.
Closing Settings leaves the tray utility running. One process is permitted per configuration.

**Keep microphone ready** is enabled by default to reduce activation delay. It opens a
stopped input stream in the background and reuses it between recordings. There is no idle
audio capture or pre-roll buffer. Disable this setting to close the device after each
recording. Windows may show microphone access while the device is open, depending on the
driver. Audio starts before background accessibility verification; initial hardware setup
and driver latency can still affect the first recording after launch.

## Models and offline use

Choose `tiny.en`, `base.en` (default), or `small.en`. They are the MIT-licensed Systran
CTranslate2 conversions of OpenAI Whisper English models. `base.en` is an initial
quality/resource compromise, **not a measured winner**. Inference uses CPU INT8, one worker,
four threads by default, greedy decoding, and bundled Silero voice activity detection.
Models load lazily and remain warm until settings change or the app exits.

Models/configuration default to `%LOCALAPPDATA%\LocalPhraser`; custom `--config` paths
are supported. Model installation resolves and records an immutable repository commit,
checks upstream LFS SHA-256 values, writes a local hash manifest, and publishes the model
directory only after verification. Runtime verifies hashes before first load and refuses
missing/damaged models. Recognition itself never downloads them. A new profile starts
one visible model setup download; later launches do not retry automatically.

```powershell
.venv\Scripts\python.exe -m localphraser verify-model base.en
# Disconnect Wi-Fi/Ethernet, then launch and repeat dictation.
.venv\Scripts\python.exe -m localphraser
```

No telemetry, saved audio, transcript history, cloud inference, or background update checks.
Download actions now have **Cancel download**, with cleanup of only that installation's
temporary files. Wait for cleanup before saving, closing Settings or retrying. Installed
models remain available. See [troubleshooting](docs/troubleshooting.md) for recovery.
Only the latest transcript is retained in RAM for recovery; clear it from the tray dialog.
Settings → Vocabulary hints accepts a short comma-separated list of names or technical
terms (up to 300 characters), for example `Codex, PySide, NumPy`. These optional hints
guide the local recognizer; they do not force a spelling or replace recognized words.
Hints are saved in local settings, independently of transcripts. Clear the field to disable
them. Too many or unrelated hints can reduce accuracy; start with a few relevant terms.
Manual Copy intentionally changes the clipboard and may enter OS clipboard history.
See [privacy](docs/privacy.md) and [third-party licenses](THIRD_PARTY_NOTICES.md).

## Optional local polishing (experimental)

The first Phase 2 build supports publisher-provided Qwen2.5 0.5B and 1.5B Q4_K_M models.
The initial choice is **1.5B**, based on a small fixed-text preservation trial. The 0.5B
option uses less memory but required more raw fallbacks. This is not a broad quality ranking.
Raw mode works without the optional runtime or a polishing model.

![Local polishing options](assets/polishing.png)

For a source installation, add the upstream CPU wheel explicitly:

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements-polish.lock
.venv\Scripts\python.exe -m localphraser install-refiner qwen2.5-1.5b
.venv\Scripts\python.exe -m localphraser check-refiner qwen2.5-1.5b
```

Use `--root <your-model-directory>` for a custom model location. Alternatively choose
**Settings → Mode → Polished**, select a model, and click **Download polishing model**.
Save when installation finishes. The development Polished executable includes the CPU
runtime; models are separate explicit downloads. No local HTTP server or cloud API is used.

Polishing runs in a reusable child process, prepared in the background once a Polished
recording starts so model loading can overlap speaking and transcription. No transcript
is sent until recognition finishes. Raw mode does not start this process.
The configurable limit is 15 seconds by
default, including the cold model load; timeout, missing runtime/model, truncated output,
changed words/numbers, or inputs over 3,000 characters fall back to raw transcription.
The first build permits punctuation, capitalization, and removing `um`, `uh`, `erm`, `hmm`;
it deliberately refuses paraphrases and word substitutions. This guard does not prove that
punctuation preserves meaning. Review important text and compare the **Raw transcription**
tab in Latest transcript. Copy uses the selected tab; Clear removes both displayed versions.

On the development machine, the 1.5B worker used about 1.8 GiB and added roughly 1–1.5 s
for four short warm text trials; the first took 5.3 s. These are single observations,
not an end-to-end or real-voice benchmark. See [performance](docs/performance.md).

## Checks and build

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src
.venv\Scripts\python.exe -m build --no-isolation
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm packaging\localphraser.spec
```

The executable build is an **unsigned development folder build**, not an installer or a
stable release. Keep the complete `dist\LocalPhraser` folder, including shared libraries
and third-party licenses. Speech-recognition models are downloaded separately; the VAD
asset supplied by faster-whisper is bundled with its own license. See [development](docs/development.md).

Inventory the trusted folder build offline, then create a checked portable preview ZIP:

```powershell
.venv\Scripts\python.exe scripts/bundle_inventory.py --probe-ffmpeg
.venv\Scripts\python.exe scripts/package_windows.py --output dist/packages/LocalPhraser-windows-x64-preview.zip
```

The ZIP keeps the complete runtime, first-run instructions and license metadata; a SHA-256
sidecar accompanies it. BUNDLE_INVENTORY.json records runtime file hashes, dependency
versions, notice locations and FFmpeg binary observations; BUNDLE_REVIEW.md lists open review
items. Packaging refuses missing or stale inventories. These reports do not certify license
compliance. The manual Windows preview workflow builds/checks on a fresh runner;
artifact upload defaults off pending bundled license/source review. This is not a signed
installer or a stable release. A separate per-user installer preview is built and checked
by the manual workflow; see the [release checklist](docs/release-checklist.md).

The optional `check-runtime` command exercises recognition and polishing with generated
synthetic speech and writes a small report without microphone capture or transcripts.
See [runtime validation](docs/runtime-validation.md) for usage and limits.

## Limitations and contribution

Windows x64 is the first target; macOS/Linux adapters are not implemented. Text insertion
requires a standard Windows EDIT control or a focused Edit/Document control with usable
UI Automation TextPattern support. The native EDIT fallback supports caret positions below
65,535; longer documents need usable UI Automation or manual copy.
Password fields, unknown/read-only fields, selected text, changed targets/carets, and held
modifiers are refused. No clipboard paste or elevation workaround is attempted. A small
focus race remains between the final OS check and input delivery; no API guarantees atomic
focus-check-and-type. Application handling of Unicode input and newlines varies. Do not
assume success means an application actually accepted every character.

Model processing cannot currently be interrupted once native inference begins; Quit hides
the UI and suppresses insertion, but process exit waits for the active inference to finish.
Recording is bounded to 120 seconds by default. Device names can be ambiguous on systems
with duplicate microphone names. No application compatibility is claimed until recorded
in the test matrix. No performance numbers are invented.

Contributions: use small changes, add meaningful tests for behavior, run the checks above,
document actual platform verification, and never include models, private audio, dictated
text, credentials, or generated binaries. See [architecture](docs/architecture.md),
[research](docs/research.md), and [roadmap](docs/roadmap.md).
See [CONTRIBUTING](CONTRIBUTING.md) and [troubleshooting](docs/troubleshooting.md).
