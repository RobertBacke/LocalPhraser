# Validation and Windows acceptance

Phase 1 is **implemented, not yet accepted** until real human speech and target applications
pass the checklist. Automated test results and environment are recorded below after execution.

Unit/integration tests cover config rejection/roundtrip, bounded capture, repeated events,
silence, errors/recovery, serial execution, shutdown while processing, manual copy recovery,
model integrity, target mismatch, held modifiers, Unicode ABI and partial input delivery.
Additional real-engine validation is opt-in with a locally installed model; it blocks Python
networking and transcribes synthetic silence, without claiming speech accuracy.

## Manual acceptance (record OS/app/version and model)

1. Launch; verify tray, one-instance guard and settings. Install base.en explicitly.
2. Notepad: place empty caret; hold configured chord, speak, release all keys. Confirm exact
   output, return to idle, and repeat at least ten times without restart.
3. Select existing text and dictate; ensure no text is overwritten and manual recovery works.
4. Change app, field, caret, or close target during inference; ensure no arbitrary insertion.
5. Test Unicode, punctuation, multiline behavior, modifier release order, shortcut conflict,
   key repeats, rapid taps, long recordings and Ctrl/Alt normal typing.
6. Test Chrome/Edge textarea and messaging draft, Word if installed. Verify no unexpected
   send/submit action for multiline text. Record actual compatibility below.
7. Verify clipboard text, images/files are unchanged unless Copy is explicitly clicked.
8. Disconnect microphone, deny microphone permissions, choose missing device, feed silence,
   remove/corrupt model, use malformed config. Verify errors and repeatable recovery.
9. Quit while recording and during inference; no later insertion, stream closes, eventual exit.
10. Disconnect networking after model install and repeat the workflow. Observe traffic with
    an independent firewall/packet capture if privacy assurance needs deeper evidence.
11. Test scaling/multiple monitors and verify indicator never takes keyboard focus.
12. Copy built folder to a Windows machine without Python and repeat.

| Application | Actual dictation/insertion verification |
| --- | --- |
| Codex desktop app | User reports microphone dictation and insertion working; recognition sometimes misses/misspells words. App version and repeat count not recorded. |
| Notepad | Pending interactive acceptance |
| Google Chrome | User reports microphone dictation and insertion working; recognition accuracy needs further evaluation. Browser version and field type not recorded. |
| Microsoft Edge | Pending interactive acceptance |
| Word | Pending; availability not established |
| Messaging interfaces | Pending interactive acceptance |
| Elevated apps / password fields | Intentionally unsupported |

Synthetic/model-free test success does not establish speech quality, ASR latency, microphone
compatibility, or daily usability. Native Windows UI interaction from this agent is not used
to read or modify unrelated user applications.

## Executed on 2026-10-28

Environment: Windows 11 build 26200 x64, Python 3.12.12. An initial pytest attempt hit
sandbox temporary-directory permissions; using a workspace-local `--basetemp` resolved it.

- **51 pytest tests passed**, including the opt-in real base.en load/VAD check with Python
  socket connections denied (`LOCALPHRASER_TEST_MODEL` selected the installed model).
- Ruff check, Ruff format check and mypy passed for application source; Ruff also checks
  tests, scripts and the packaging entry point. Native dependency APIs were inspected locally.
- Source wheel and sdist built successfully; archive inspected for exclusion of runtime,
  model and development caches.
- The Windows folder executable built successfully. Its initial frozen smoke test exposed
  an incompatible ICU DLL from an unrelated tool on the host PATH. Removing that dependency
  made the smoke launch return exit code 0; the spec now isolates dependency discovery PATH.
  A subsequent **clean rebuild also passed the executable smoke test with exit code 0**.
  This verifies startup, not frozen model installation or microphone-to-editor dictation.
- Source Qt/tray/UIA/hotkey application smoke launch returned exit code 0, without audio
  capture or insertion. Settings rendered and visually reviewed with a loaded system font.
- `scripts/synthetic_speech_check.py` passed cold/warm real local transcription of generated
  Windows SAPI speech with Python socket connections denied. No personal audio was used.
- `scripts/native_input_check.py` passed actual Unicode/emoji SendInput delivery and selected
  text refusal in an owned disposable Windows EDIT fixture. The sandbox blocked input;
  the test passed outside it, with foreground ownership checked before insertion.
- `scripts/native_hotkey_check.py` passed actual RegisterHotKey → Qt native event filter →
  scoped release timer behavior, including duplicate-key suppression. It used only an owned
  fixture and the registered test chord.

Commands for the optional checks:

```powershell
$env:LOCALPHRASER_TEST_MODEL = (Resolve-Path .cache\models\base.en).Path
.venv\Scripts\python.exe -m pytest --basetemp=.cache\pytest-manual
.venv\Scripts\python.exe scripts\synthetic_speech_check.py .cache\models\base.en --temp-dir .cache\speech-check
.venv\Scripts\python.exe scripts\native_input_check.py
.venv\Scripts\python.exe scripts\native_hotkey_check.py
```

The two native scripts briefly show disposable test windows. Run on an interactive desktop;
do not type during them. They do not validate the live microphone or third-party editors.
Default CI skips the installed-model test and does not download weights or run native UI scripts.

Caps Lock default update: native shortcut validation passed for both `CapsLock` and
`Ctrl+Shift+F9`; Caps Lock capitalization state remained unchanged. Automated tests also
cover repeat suppression, forwarding unrelated/negative-code events, and stale queued events
after reconfiguration. Existing explicitly saved shortcuts are retained; the generated local
development configuration was updated to Caps Lock.
The updated suite passed **54 tests**, including the opt-in offline model check; Ruff and
mypy passed. The source app smoke test also passed with the new default.

## Shortcut picker and capture-start update

- **77 tests passed**, including real-engine offline loading/VAD, explicit key/chord choice,
  cancellation/focus loss, held-key repeat suppression, stopped-stream preparation/reuse,
  audio buffering during target verification, startup window/caret changes, cancellation
  with a late target result, target timeouts and prevention of delayed input after expiry.
- Ruff, formatting and mypy passed for the updated source.
- Actual Windows Caps Lock selection was verified in an owned Settings window, with both
  existing Caps Lock and modifier configurations. Holding/repeating the selection key did
  not start dictation; the saved shortcut was restored on release.
- Worker-thread insertion/selection refusal passed against owned native EDIT and Rich Edit
  controls, including emoji. An owned Qt text field passed BMP Unicode (including accents)
  and selected-text refusal through UI Automation on the MTA worker.
- A supplemental emoji test in the Qt 6.12 fixture failed ordering: its supplementary character
  appeared before the preceding text. Unicode delivery behavior was not changed to work
  around this provider-specific observation. Qt supplementary-character compatibility remains
  a known limitation to investigate; do not infer universal Unicode support from other tests.
- `scripts/benchmark_capture.py` measured start/callback timing with temporary RAM-only
  captures; results and limits are in performance.md. No personal speech was transcribed.
- Updated Windows folder build succeeded in `dist/interaction-update/LocalPhraser`.
  Its startup smoke test exited with code 0, using a separate configuration and no audio
  capture or microphone preparation. Source and packaged immediate-speech behavior still
  require a human trial.

The user subsequently confirmed the shortcut picker works and opening words are captured
better. This qualitative result is not a measured onset/clipping bound.
Microphone readiness can be disabled in Settings; verify this releases the device
between dictations on representative drivers. Actual Windows tray single-click opening was
confirmed by the user before this update.

## User-reported live trial

The user confirmed actual microphone capture, local transcription, and insertion across
Codex desktop and Google Chrome. Results were fairly accurate overall, with occasional
incorrect or misspelled words. This is user-reported compatibility evidence, not an automated
accuracy measurement or a claim of support for every field in those applications.

The user subsequently selected `small.en` and reported successful dictation with networking
disconnected. The basic microphone → local ASR → cross-application insertion workflow now
has user-reported offline verification on this machine. This does not establish compatibility
on other machines or exhaustive network-traffic auditing.

Two `small.en` sentence trials were reported: one longer sentence was transcribed exactly;
the other had a single opening-word substitution while the application name was recognized.
These are qualitative observations, not a word-error-rate benchmark or a controlled comparison
against `base.en`. No personal audio or exact transcript examples are saved here.

The user also verified that switching windows prevented insertion into the new window and
preserved the transcript in Latest transcript. Selected existing text was preserved, with
the new transcript available for manual copy. Returning focus to the original field and
inserting automatically is intentionally not attempted.

The user reported inconsistent tray opening by clicking the icon. The implementation
previously handled double-click only; single-click now opens Settings as well, and an
already-open minimized Settings window is restored and activated.
Ruff, formatting, and mypy passed. An isolated Qt check verified that a single-click
activation creates Settings and restores the same window after minimization, without
installing hotkeys or opening the microphone. Actual Windows tray interaction after this
change was subsequently confirmed by the user.

Notepad-specific testing, clipboard preservation, repeated-session stress, and microphone
error cases remain pending human acceptance.
Release readiness and the full acceptance checklist remain open.

Next quality evaluation: use deliberately chosen nonsensitive sample sentences, compare the existing
`base.en` model against `small.en` on representative speech, and assess recognition quality
together with warm latency. Current decoding uses greedy beam size 1; a wider beam is a
candidate to evaluate rather than a guaranteed correction. Do not add an LLM to conceal
recognition errors, and do not record personal speech or transcripts automatically.

## Vocabulary hints increment

Validation on the development machine: **86 tests passed**, including actual `small.en`
loading and silence/VAD with vocabulary hints while Python socket connections were denied.
Additional tests cover old settings defaulting to no hints, persistence, invalid input,
Settings editing/clearing while preserving model choice, and forwarding hints without
replacing engine output. Ruff check/format and mypy passed.

`scripts/synthetic_speech_check.py` passed cold and warm `small.en` inference with the
nonsensitive hints `computer, speech, recognition`, checking expected content while socket
connections were denied. It generated only synthetic speech, deleted the temporary WAV,
and did not record a microphone or print transcripts. These are integration/silence checks,
not an accuracy comparison or proof that hints always help. Relevant real-voice comparisons
and a broader word-error-rate evaluation remain pending.

The updated Settings preview was rendered with Windows Qt and visually checked. Source
wheel/sdist and the unsigned PyInstaller folder build completed. The executable passed
`--smoke-test` with a separate test configuration, hints enabled, and microphone preparation
disabled (exit 0). This checks startup, not frozen real-microphone recognition acceptance.

## Phase 2 experimental local polishing

Implemented Raw/Polished modes, optional CPU runtime, explicit pinned/hash-verified GGUF
downloads (weights plus LICENSE/README), custom instructions, bounded lazy worker,
time limit, lexical preservation check, raw fallback, and Raw/Result comparison in memory.
The Settings body scrolls independently of Save/Cancel for smaller screens.

Tests cover permitted punctuation/case/filler edits; refusal of changed names, signed
numbers, currency, negations, word order, prompt-instruction responses, added explanations,
control/bidirectional characters and dropping uppercase UM; subprocess reuse, timeout,
retry, shutdown while blocked, limits and corrupt/missing files; and pipeline fallback,
audio clearing before polishing, GUI dispatch, raw retention and late-result suppression.

The initial pipe shutdown implementation reproduced a Windows INVALID_HANDLE failure when
one thread closed a pipe another thread was polling. Reader-owned close fixed this race;
the corresponding real-process test passed. A later full pytest run passed all assertions
but exited with native status 0xC0000409. Isolated combinations and the subsequent full run
exited 0. Test fixtures now explicitly dispose their Qt windows while QApplication is alive
and join their owned executors; this reduces teardown ambiguity but is not proof of the
intermittent native exit's root cause. Keep shutdown stress in release acceptance.

An owned desktop check started actual Qt/tray/target integration using a separate test
configuration with microphone preparation disabled, loaded real `small.en` on silence,
ran real 1.5B polishing on fixed synthetic text, then quit cleanly (exit 0). It never opened
the microphone or inserted into a user application. Synthetic speech → ASR → polishing
also passed offline. Per-model text outcomes and timings are in performance.md.

Polished mode remains experimental: real-voice cross-app acceptance, a larger corpus,
punctuation/meaning preservation evaluation, sustained shutdown trials, and clean-machine
builds are pending. At the end of this initial build, the user had verified Raw mode
workflows; subsequent Polished feedback is recorded below.

Final local validation: **129 tests passed with exit 0**, including the optional real
`small.en` offline check; the preceding 128-test run also exited 0 after explicit fixture
teardown. Ruff check/format and mypy (15 source modules) passed. Wheel/sdist and the unsigned
Phase 2 folder executable built. The frozen executable passed both GUI `--smoke-test`
with Polished selected (no capture) and `check-refiner` using actual 1.5B inference twice
(both exit 0). These are same-host checks, not a clean-machine release certification.

## Polished user trial and overlapping model preparation

The user reports that Polished seems better than Raw, and works with Wi-Fi connected and
disconnected, but processing takes a noticeable amount of time. This is qualitative live
acceptance evidence on this machine, not measured word error rate or latency.

Model preparation now starts on the existing worker only after microphone recording begins.
It sends no warm-up text, and actual refinement reuses the prepared child. Tests cover
audio starting first, recording/release remaining responsive while preparation is pending,
preparation errors preserving transcription/raw fallback, reuse without stale responses,
and closed preparers never reopening. **132 tests passed with exit 0**, including the real
`small.en` offline check. Ruff, formatting and mypy passed. The five real 1.5B fixed-text
trials remained accepted; measured timings and limits are in performance.md.
The owned Qt desktop check also passed with explicit model preparation before real ASR
and polishing, followed by clean shutdown, without microphone use or insertion. Source
wheel/sdist and the updated unsigned folder build completed. Frozen GUI smoke and real
1.5B `check-refiner` both exited 0. Actual microphone capture while loading and real-voice
release-to-result latency for this preparation update remain user acceptance work.

## Phase 3 core and Phase 4 preview foundation

Local validation: **162 tests passed with exit 0**, including real `small.en` offline VAD;
Ruff check/format and mypy passed for 17 source modules. Coverage adds startup command quoting,
profile scoping, rollback on failed config writes, default-off/no-registry-access saves,
windowless source streams, exact microphone/API resolution and ambiguity refusal, per-model
locks, strict job cleanup, actual child cancellation/retry/shutdown, busy-save refusal,
portable ZIP contents/checksum and refusal of weights/audio/local settings.

Native same-host checks:

- A disposable HKCU test key passed write/read/remove with the real registry API. The actual
  Run key was untouched, and no real sign-in entry was enabled for testing.
- Source pythonw.exe passed GUI smoke startup with an owned configuration (exit 0), no
  microphone preparation/capture or insertion. Null streams are handled without log files.
- The actual tiny.en installer was started and cancelled in a dedicated ignored root;
  offline cleanup removed its stage. This passed for source and the frozen executable.
  Installed models were not removed. Synthetic QProcess tests additionally exercise retry.
- Source wheel/sdist and the current unsigned folder build completed. The checked ZIP is
  **121.1 MiB**, excluding separately downloaded models, and includes a SHA-256 sidecar.
  The ZIP passed CRC checks, was extracted to a fresh owned path containing spaces, and the
  extracted executable passed GUI smoke and real 1.5B inference twice (both exit 0).
- Updated Settings screenshots were rendered and visually reviewed without reading personal
  fields, opening microphones, or changing actual startup preferences.

Actual Windows sign-in behavior has not been exercised by logging the user out. No clean
consumer VM is available here (Windows Sandbox executable is absent). A GitHub Windows
runner build is useful integration evidence but cannot replace microphone, consumer-machine,
startup, selection/focus, clipboard, multi-monitor, driver or sustained shutdown acceptance.
Public binary distribution remains gated on the release checklist, exact license/source
audit and installer/signing decision. The manual preview workflow's upload defaults off.


## Per-user installer preview (2026-10-29)

Settings and product guidance now say **Start LocalPhraser upon startup**. The stored
`start_at_login` key is unchanged for existing configurations. Startup remains opt-in.
Updated Settings screenshots use an explicit system font and were visually reviewed.

Local validation: 161 tests passed, one optional local-model test skipped; Ruff check/format
and mypy passed. The rebuilt `dist/installer-preview/LocalPhraser/LocalPhraser.exe` passed
its owned GUI smoke check with microphone preparation disabled. Its portable ZIP passed
packaging integrity checks and has a SHA-256 sidecar. No user startup entry was enabled.

The Inno Setup source uses a per-user install, optional desktop shortcut and optional launch.
Uninstall preserves application data and removes only prefixed startup values pointing to
its own executable. A disposable-runner check covers install, launch, reinstall, uninstall,
Start menu cleanup, data preservation and preservation of other startup entries. Interactive
wizard and running-app upgrade behavior still need consumer-machine acceptance testing.


[Windows preview run 40879826951](https://github.com/RobertBacke/LocalPhraser/actions/runs/40879826951)
passed the full workflow for source commit `29f2ea3`, including real installer compilation
and install/launch/reinstall/uninstall checks. Artifact upload was disabled. This runner is
Windows Server; passing here does not establish Windows 10/11 consumer acceptance.


## Automatic first-launch speech setup (2026-10-29)

Local suite: 167 passed, one optional local-model test skipped. Ruff check/format and mypy
passed. New coverage checks profile persistence before setup, no automatic retries for an
existing profile, smoke-test suppression, refusal to download when config saving fails,
cancellation without re-entry, skipping preinstalled files, recording blocked before setup,
and readiness without saving after installation. Fixture model bytes only test presence;
they are not represented as inference/integrity evidence.

A separate real Windows source-app check used an owned workspace profile, base.en, an
isolated model root, Ctrl+Shift+F10, and microphone preparation disabled. First launch
started one real download, completed manifest/hash verification, and reached readiness
without Save (exit 0). Relaunch used the same persisted profile, started no download, and
passed with Python socket connect/connect_ex denied (exit 0). No microphone recording,
text insertion, actual user startup registration, or private transcript was involved.
This is not a native-library packet audit or a clean consumer-machine test.


The local frozen build at `dist/first-launch-setup/LocalPhraser/LocalPhraser.exe` passed its
owned GUI smoke check (exit 0). The matching portable ZIP passed integrity checks and has
a SHA-256 sidecar. [Windows preview run 40885414192](https://github.com/RobertBacke/LocalPhraser/actions/runs/40885414192)
passed for source commit `ea06b4f`, including tests, frozen launch, packaging, installer
compilation and disposable install/reinstall/uninstall checks. Upload was disabled. These
checks do not replace clean Windows 10/11 consumer acceptance or the bundled license audit.


## Runtime inventory and notice packaging (2026-10-29)

Local suite: 180 passed, one optional model test skipped. Ruff check/format and mypy passed.
New tests check offline/repeatable inventory generation, actual binary SHA-256 changes,
missing declared notices, refusal of known local-data payloads and escaped notice paths,
wheel RECORD notice collection outside metadata directories, supplemental source hashes,
FFmpeg observation retention, and package rejection of absent/stale reports.

The rebuilt `dist/release-inventory/LocalPhraser` folder passed its owned frozen GUI smoke
check with microphone preparation disabled (exit 0). Offline inventory recorded 32 wheel
distributions and 185 native EXE/DLL/PYD files, queried avcodec/avformat/avutil exports in a
separate process, and verified eight supplemental source-text hashes. ONNX Runtime's
LICENSE and ThirdPartyNotices.txt are present under `_internal/third_party`, alongside
Python's runtime license and PyInstaller's bootloader license/exception. The checked ZIP
includes both inventory reports and a SHA-256 sidecar.

FFmpeg libraries self-reported LGPL version 3 or later while their configuration enabled
x264/x265. These are recorded observations, not a completed linked-library/source review.
The corresponding-source, Qt module/replacement, codec, compiler-runtime and clean-machine
items in the release checklist remain open. No binary distribution approval is inferred.
