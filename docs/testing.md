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

Immediate natural speech after key-down still needs a user trial after restarting the new
version. Microphone readiness can be disabled in Settings; verify this releases the device
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
change remains for the user to confirm.

Notepad-specific testing, clipboard preservation, repeated-session stress, and microphone
error cases remain pending human acceptance.
Release readiness and the full acceptance checklist remain open.

Next quality evaluation: use deliberately chosen nonsensitive sample sentences, compare the existing
`base.en` model against `small.en` on representative speech, and assess recognition quality
together with warm latency. Current decoding uses greedy beam size 1; a wider beam is a
candidate to evaluate rather than a guaranteed correction. Do not add an LLM to conceal
recognition errors, and do not record personal speech or transcripts automatically.
