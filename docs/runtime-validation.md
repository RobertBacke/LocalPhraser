# Runtime validation

Run this optional check after installing models. It generates a fixed English sentence with
an installed Windows SAPI voice, decodes a temporary WAV, and runs real speech recognition
twice with the selected local model. With a polishing model selected, it also runs real
refinement and checks word preservation. Model checks, CPU inference and child-process
cleanup use the same backends as dictation. The command does not open a microphone, register
a shortcut, insert text, download models, or read a settings profile.

## Run from source

Choose a new report filename for each check:

```powershell
.venv\Scripts\python.exe -m localphraser check-runtime --root .cache/models --model base.en --report .cache/runtime-raw.json
.venv\Scripts\python.exe -m localphraser check-runtime --root .cache/models --model base.en --polishing-model qwen2.5-1.5b --report .cache/runtime-polished.json
```

## Run a trusted frozen build

Use your actual model directory and a new writable report path outside the application
folder. For example, from a command prompt in the folder containing LocalPhraser.exe:

```powershell
$arguments = 'check-runtime --root "{0}\LocalPhraser\models" --model base.en --report "{1}\LocalPhraser-runtime-raw.json"' -f $env:LOCALAPPDATA, $env:TEMP
$check = Start-Process -FilePath .\LocalPhraser.exe -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
$check.ExitCode
```

Add `--capture-rate 48000` (or 44100/96000) to generate synthetic speech at that rate and
exercise the same conversion used for compatible microphone fallback. This simulates the
sample-rate path without using a device.

Add `--polishing-model qwen2.5-1.5b` to exercise polishing after installing that model.
Repeat with different report names to check initialization/shutdown across process launches.
The windowed EXE has no console output; inspect the JSON report after the process exits.
Require both exit code 0 and JSON status passed for a successful cycle. Exit code 1 means
a reported failure; any other nonzero exit also fails the cycle. A native shutdown crash
can happen after writing a passed report, so inspect the process exit code as well.
Existing report files are refused and
never overwritten. A native crash or interrupted run can leave an empty/incomplete report;
treat that as a failed check. The command uses CPU and RAM while testing.

The JSON records app/Python/Windows versions, selected model IDs, fixed stage/status values,
and per-run durations. It excludes transcripts, exception messages, model-directory paths,
settings, hostname and microphone details. Reports stay where you explicitly requested;
they are not uploaded. The generated WAV is deleted before recognition and the working
audio array is cleared at cleanup. No personal audio is used.

## Interpreting results

- `model_verification`: missing/damaged speech model, or failure before synthetic generation.
- `synthetic_speech`: missing/broken SAPI voice, decoding, temporary storage or native dependency.
- `audio_conversion`: rate conversion failed.
- `recognition`: backend failure or absence of the two expected synthetic marker words.
- `polishing`: backend/deadline failure or rejected word changes. Production dictation uses
  its Raw fallback for rejected edits.
- `cleanup`: refinement cleanup failed.
- `complete`: both cold/warm checks passed.

An installed voice capable of English is required. Generation is directed to a file and
does not play aloud. Python socket connections are denied during the check; refinement's
child also denies Python connections. Native-library/OS networking still needs independent
firewall or packet-capture evidence. Missing models produce a failure report and no download.

These checks are runtime sanity evidence, not WER/accuracy, microphone onset, latency
percentiles, clipboard/focus safety, accessibility, startup, GUI shutdown-stress or clean
consumer-machine certification. Per-run durations are small synthetic checks; optional
polishing loading overlaps generation/recognition, so these are not standalone cold-load
benchmarks. Native speech inference and SAPI calls currently have no overall interruptible
deadline. A passed CLI cycle does not resolve the previously observed intermittent native
GUI/test-process shutdown failure. Continue the manual [release checklist](release-checklist.md).


## Owned Qt shutdown checks (source development environment)

`scripts/native_shutdown_check.py` runs an isolated owned Qt Desktop with real local models,
then quits while the refiner is loading, while it is polishing, or after normal completion.
The helper disables keyboard registration, hides its tray, disallows microphone start and
sets automatic insertion off. It supplies only generated synthetic speech to the worker;
Latest transcript is cleared during shutdown. It does not save or load a user profile.

```powershell
.venv\Scripts\python.exe -X faulthandler scripts/native_shutdown_check.py --root .cache/models --temp-dir .cache/shutdown-check --case loading
.venv\Scripts\python.exe -X faulthandler scripts/native_shutdown_check.py --root .cache/models --temp-dir .cache/shutdown-check --case polishing
.venv\Scripts\python.exe -X faulthandler scripts/native_shutdown_check.py --root .cache/models --temp-dir .cache/shutdown-check --case complete
.venv\Scripts\python.exe -X faulthandler scripts/native_shutdown_check.py --root .cache/models --temp-dir .cache/shutdown-check --case complete --cycles 10
```

This helper requires base.en and Qwen2.5 1.5B already installed. Its default synthetic
capture rate is 48 kHz; use --capture-rate 16000 for the direct path. Run each case in a
separate process and require exit 0, including interpreter/native teardown. These short
trials are reproduction tools; success does not identify or rule out the older intermittent
native shutdown crash, nor does it replace sustained sessions on consumer hardware.
For repeated warm sessions, --cycles accepts 1-100 with --case complete. Each cycle must
produce recognized speech and a preserving polishing result; only generated audio is used.
The same Desktop/models remain alive across cycles; latest text is replaced, then cleared
on shutdown. The GUI watchdog allows 45 seconds per requested cycle overall; native calls
still require an external process timeout when diagnosing hangs.
