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


Wheel and source archive builds also passed with temporary files kept in the workspace.
The source archive preserved all eight upstream supplemental notice hashes. The local
portable preview is 121.3 MiB and passed ZIP CRC checks; inspection confirmed inventory
reports, ONNX notices, Python license and PyInstaller bootloader terms are present.


[Windows preview run 40891140721](https://github.com/RobertBacke/LocalPhraser/actions/runs/40891140721)
passed for source commit `8558670`: tests/checks, frozen build, offline inventory/native
probe, launch smoke, checked ZIP, installer compilation, and disposable install/reinstall/
uninstall acceptance. Artifact upload was disabled; no public binary release was created.


## Synthetic runtime diagnostics and native RECORD attribution (2026-10-29)

Local suite: 189 passed, one optional model test skipped. Ruff check/format and mypy passed
for 18 source modules. New tests cover Raw/Polished cold/warm check orchestration, rejected
word edits, buffer clearing and refinement cleanup, sanitized failure stages, restoration
of socket patches, refusal to overwrite an existing report, and missing-model failure
without audio generation/downloads. Native attribution requires an exact RECORD SHA-256
match; a matching filename with different bytes receives no attribution.

Source check-runtime passed with the real local base.en and Qwen2.5 1.5B models (exit 0).
The new frozen executable passed Raw synthetic recognition and three separate Polished
process trials, each doing cold/warm recognition and refinement (3/3 Polished trials exit 0).
No microphone or editor insertion was used. A frozen missing-model trial exited 1, wrote
only the expected model_verification failure report, and created no model directory.
Generated audio was temporary and reports contained no recognition output or model paths.
These small CLI trials do not establish GUI shutdown-stress reliability or broad accuracy.

The new bundle again records 32 distributions and 185 native files. 157 native files match
SHA-256 entries from bundled wheel RECORD metadata; 28 are unmatched and separately listed
for Python/runtime/application provenance review. This does not authenticate original wheel
archives, signatures or corresponding source revisions. The portable preview includes
inventory evidence and a SHA-256 sidecar; native-source/codec and consumer acceptance gaps
remain open.


Source archive and wheel builds passed; the wheel contains the diagnostic module. No
synthetic temporary folders remained after the source/frozen checks. For shutdown evidence,
a complete passed JSON report is insufficient on its own: the invoking process must also
exit 0. The runtime validation guide explicitly requires both outcomes.


[Windows preview run 40898119456](https://github.com/RobertBacke/LocalPhraser/actions/runs/40898119456)
passed for source commit `d8b43a8`: tests/checks, frozen build, native inventory, GUI smoke,
frozen missing-model diagnostic/report, portable packaging and installer install/reinstall/
uninstall acceptance. Binary artifact upload was disabled. This does not replace real
model checks on clean Windows 10/11 consumer machines or the remaining release review.


## Capture-rate compatibility and owned Qt shutdown trials (2026-10-29)

Local suite: 209 passed, one optional local-model test skipped. Ruff check/format and mypy
passed for 18 source modules. Coverage includes native-rate inactive stream fallback and
reuse, duration bounds/minimums at the actual capture rate, no retry for unrelated errors,
invalid fallback rates, real resampling at 8/32/44.1/48/96 kHz, chunk continuity, speech-band
tone preservation and above-Nyquist filtering. Worker-thread conversion and clearing of
both captured/converted buffers are checked on success, conversion error and ASR error.

A real default-device test forced only the first 16 kHz attempt to raise the documented
unsupported-rate error, then opened the device's reported 44.1 kHz stream inactive. No
stream start/callback occurred; the stream was closed and its buffer cleared. This verifies
an inactive real-device fallback open, not a naturally failing driver or live recording.

The owned source Qt helper passed six separate 16 kHz process trials (two each for quit
during loading, during polishing, and normal completion), followed by three 48 kHz trials
(one per case), all exit 0. Keyboard registration was disabled, tray hidden, microphone
start forbidden and auto-insertion off. The 48 kHz complete/polishing cases used generated
speech through real worker-side conversion, ASR and local refinement. The opt-in source
check-runtime --capture-rate 48000 also passed cold/warm recognition and polishing with
local base.en and Qwen2.5 1.5B (exit 0). No personal audio or editor input was used.

The previously intermittent native shutdown failure was not reproduced. Nine clean owned
Qt process exits do not establish its root cause or complete sustained-session acceptance.

## Insertion timeout cancellation (2026-10-29)

Windows checks for commits `105ec3b` and `7e151e9` failed the slow-insertion timeout
test: the caller had timed out, but late work could still pass the monotonic deadline
check. Future wait expiration and the separate clock comparison can disagree near the
timeout boundary. Insertion now also checks an explicit cancellation event, set before
the caller returns from waiting. Existing immediate target/focus checks remain required;
this does not make the final native input dispatch atomic with a focus change.

A regression test holds the permission clock before its deadline, lets the Future wait
expire, then releases the blocked insertion provider. It must deliver nothing and retain
no target. Local suite: 210 passed, one optional model test skipped, process exit 0.
Ruff check/format and mypy passed. This failure was an assertion failure, separate from
the previously observed native process-exit issue.

## Speech-model preparation during recording (2026-10-29)

Local suite: 216 passed, process exit 0, with LOCALPHRASER_TEST_MODEL pointing at the
verified base.en model. The optional real-model test ran with Python socket connections
denied. Ruff check/format, mypy and source archive/wheel builds passed.

Tests cover nonblocking preparation after microphone start, serialization with recognition
on the same inference worker, idempotent preparation without inference, retry after failed
construction, sanitized deferred failures, and shutdown skipping later polishing preparation.
The owned Qt helper now uses the actual combined preparation path; loading, polishing and
normal-completion trials with synthetic 48 kHz speech each exited 0. No personal audio,
keyboard registration or editor insertion was used. These are not sustained-session proof.

A single source-process base.en measurement with generated speech and Python connections
blocked observed preparation at 1.232 seconds, first prepared inference at 1.283 seconds,
and warm inference at 0.692 seconds. This identifies loading work that can overlap speech;
it is not a controlled before/after benchmark, a hardware-wide speed claim or a microphone
latency measurement. Short recordings may still wait for loading; native loading remains
noninterruptible and may delay process exit. Cancelled/silent first recordings may load weights.

## Recognition profiling and visible stage timings (2026-10-29)

Local suite: 219 passed, process exit 0, including the real small.en model/VAD test with
Python socket connections denied. Ruff check/format and mypy passed. Tests distinguish
recognition/polishing time from total after-release time, including preparation/dispatch
wait and polishing failure time. Latest transcript clears its timings on replacement,
Clear and shutdown; timings are not written to configuration or logs.

Three fixed Windows SAPI samples (grocery sentence, technical/negation sentence, and faster
speech containing an appointment time) were run three times per configuration, with Python
socket connections denied. Durations were 6.72, 9.00 and 6.62 seconds. Median ASR seconds:

| Model / CPU threads | Grocery | Technical | Faster |
| --- | --- | --- | --- |
| base.en / 4 | 0.759 | 0.808 | 0.812 |
| small.en / 4 | 2.186 | 2.415 | 2.528 |
| small.en / 8 | 2.219 | 2.160 | 2.258 |

All three repeats produced the same normalized word-edit counts per sample: base.en
0/0/3, small.en 0/1/3 at both thread counts, against 19/20/25 reference words. Normalization
lowercases and removes punctuation; number formatting can count as an error. This tiny,
single-voice synthetic sample does not establish model accuracy for human speech or accents.
Eight threads helped two cases modestly and slightly regressed one; defaults/user settings
were retained. Preparation was 1.214 seconds for base.en and 2.241/2.494 seconds for small.en
at four/eight threads. These sequential observations are not isolated hardware benchmarks.

Owned source GUI sessions used generated audio in place of microphone capture and disabled
hotkey registration/automatic insertion. Raw and Polished with small.en completed and exited
0, cleared audio/latest text/timings on shutdown, and displayed the timing breakdown.
Observed Raw total was 3.1 seconds (2.9 recognition); Polished total was 6.7 seconds
(3.0 recognition, 3.7 polishing), with a build running concurrently. An initial standalone
GUI harness lacked a Windows multiprocessing entry guard and failed; the corrected guarded
Polished harness passed. This was a harness correction, not an application fix or a sustained
session reliability claim.

## Callback-stall recovery and repeated sessions (2026-10-29)

The user reports that live microphone dictation now feels quick and fairly accurate. This
is qualitative feedback on the user's current setup, without a new timed speech corpus.

Three added tests first reproduced the old behavior: an active stream without initial or
subsequent callbacks stayed healthy, and stop returned partial audio after a stall. They
failed before the fix and passed afterwards. The recorder now tracks monotonic callback
arrival time, latches an interrupted capture after three seconds without frames, and checks
health before returning stopped audio. Existing GUI watchdog cancellation clears the buffer;
retry opens/reinitializes the stream. No callbacks, logs or transcripts are created while idle.

Local suite: 226 passed, process exit 0, including the real small.en/VAD test with Python
connections denied. Added coverage includes silent-frame liveness, idle stream reuse with
clock reset, failure latching/recovery, completed sample-limit capture after a delayed GUI
poll, and GUI cancellation without transcription. Ruff check/format and mypy passed.

The extended owned Qt helper completed ten consecutive synthetic 48 kHz sessions through
real worker-side conversion, base.en recognition and Qwen2.5 1.5B refinement in one Desktop,
then exited 0. The helper registers no hotkey, captures no microphone, inserts no text and
does not load/save user settings. Each cycle checks speech content and no polishing fallback.
This is a short repeated-session check, not proof of hours-long memory stability or resolution
of the previously observed intermittent native shutdown issue. Driver-stall tests use an
injected active stream and virtual clock; actual physical device unplug still needs acceptance.

## Visible launch, cold-start grace and progressive output (2026-10-29)

The user reports silent manual startup, frequent first-dictation errors, and uneven rendering
of long output. A virtual-clock regression reproduced a cold stream.start blocking for four
seconds and exhausting the old callback deadline before Listening. It failed before the fix
and passed after moving the no-first-frame grace to successful start return. This is a real
reproduced path, not confirmation of the exact error on the user's microphone. The latest
sanitized error now remains in Latest transcript through successes, until Clear/exit.

Manual launches request visible Settings; background and smoke launches stay quiet unless
setup/errors require attention. New startup commands include --background. The actual Run
key is not rewritten automatically; older registrations can be toggled off/on with Save.
The disposable registry command round-trip passed with host permissions; sandbox registry
access was refused, and the actual Run key was untouched.

Local suite: 248 passed, process exit 0, including real small.en/VAD with Python network
connections denied. Ruff check/format, mypy and source archive/wheel builds passed. Coverage
includes manual/background visibility, cold startup grace, retained/cleared error state,
plain-text bounded previews, preview owner dispatch/shutdown suppression, asynchronous
delivery completion/failure/shutdown, per-batch native/UIA caret/focus/deadline checks,
timeout cancellation and whole-message validation before input. Incomplete direct-construction
resampling test fixtures were updated for the new optional preview port.

Five synthetic 48 kHz source GUI sessions with base.en/Qwen1.5B passed through the actual
preview-enabled recognizer and shutdown (exit 0); no microphone or external insertion used.
Owned native EDIT and Qt UIA fixtures passed paced ASCII delivery and selected-text refusal.
An isolated newly created Chrome profile/owned named textarea also passed exact paced
ASCII delivery and subsequent selected-text refusal; unrelated fields were not read/typed.
The owned input checks used normal host permissions because sandbox SendInput is blocked.

An early paced test observed only 28 of the first 32 characters processed after SendInput
returned, motivating the bounded caret-settling wait. The longer fixture needed a larger
read buffer; UIA endpoint comparison uses the underlying COM range because the installed
wrapper forwards its argument incorrectly. Corrected EDIT/Qt/Chrome trials passed.
These tests do not certify Codex's provider, every Chrome field, or the user's first session.
Preview is completed phrases after release, not token-level live captions. Unicode/newlines
use single delivery; partial output can remain after a changed target/timeout, with no retry.

A combined source GUI trial also passed synthetic small.en recognition, preview, Qwen1.5B
polishing and asynchronous paced insertion into an owned external Qt child text-edit field,
with exact final text and clean exit. Earlier combined harnesses used a top-level QTextEdit
exposed as a Window role and were correctly refused; the corrected child-edit fixture
matches the supported field contract. No field checks were relaxed. The Windows venv
redirector's Popen PID differs from the actual GUI host, so field ownership uses the
verified window's native process identity rather than assuming the launcher PID.

The 2,600-character isolated Chrome trial exposed an overly short paced-delivery deadline.
Repeated UIA validation during settling was consolidated into the same final guarded
insert check; only a dedicated no-input caret-mismatch exception can be polled again.
SendInput errors/partial delivery are never retried. The length allowance is now two
seconds plus one second per 200 characters, capped at 30 seconds. Exact delivery passed
in 11.094 seconds, followed by selected-text refusal after explicitly waiting for Chrome's
asynchronous selection to settle. This measures delivery, not ASR latency. Additional
tests cover partial-send non-retry and immediate cancellation on an observed field change.


## First-use overflow and partial delivery follow-up (2026-10-29)

The user reported first-use microphone cancellation and output stopping after 32 ASCII
characters. A real-device metadata-only trial reproduced an input overflow 3.828 seconds
into the first recording while cold `small.en` preparation ran; subsequent recordings had
no callback status flags. No audio was saved or transcribed in these hardware trials.
After moving preparation until after capture stops, three eight-second recordings had
no overflow or watchdog failure. Device-disconnection and overflow checks remain enabled.
The first after-release transcription now includes cold model loading time.

The exact cutoff was not reproduced in the owned Chrome/Qt editors. A regression fixture
models a UIA provider updating its saved caret anchor after input: the previous code stops
after its first batch; the revised code sends the complete message in one checked dispatch.
Paced typing remains available for native EDIT controls. Phrase previews remain enabled;
smooth final typing in UIA editors is deferred until reliable caret tracking is available.
Neither partial SendInput failures nor changed targets are retried.

`scripts/native_browser_check.py` creates an isolated Chrome profile and an owned reactive
contenteditable field with an existing draft. It passed exact delivery of 2,736 synthetic
characters and selected-text refusal. The fixture preserves whitespace and waits for the
browser to process queued input before comparing its synthetic text. An owned Qt editor
also passed generated speech through real `small.en`, phrase preview, local polishing and
complete insertion, with a clean exit. Native EDIT paced insertion and a prefilled Qt field check also passed.
These are not acceptance tests of the user's actual Codex draft or voice. Retesting a fresh
launch and a long message in the user's original applications remains necessary.

Both new regressions were run against the previous implementation and failed, then passed
with the changes. The full local suite passed 247 tests, including the real offline speech
model test; Ruff, formatting and mypy checks passed.
