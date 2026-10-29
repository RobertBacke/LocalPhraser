# Troubleshooting

## Launch or first dictation is confusing

Manual EXE launches now show Settings. Closing it keeps the app in the system tray;
--background is intended for quiet startup. A second launch of the same configuration
reports the running instance. Older startup entries need startup toggled off/on with Save
to add the new background flag; normal launch does not silently rewrite registry entries.

A cold driver start no longer consumes the callback-stall grace period before capture is
ready. This fixes a reproduced timeout path, not every possible first-recording failure.
Latest transcript retains the last sanitized error through later successes until Clear/exit.
A real-device cold-start test also reproduced an input overflow while speech-model loading
overlapped capture. Loading now waits until recording stops; first transcription therefore
includes cold loading time. Overflow and disconnected-device checks remain enabled.

## Output appears unevenly

Recognized phrases appear in the non-focusing preview after release as the engine produces
them; the model does not emit live per-token microphone captions. Final insertion runs on
the target worker rather than blocking Qt. Longer single-line ASCII output uses
32-character batches, checking the expected caret and original field before each batch.
Supported UI Automation editors rebuild the expected position from a fresh document range,
so saved range anchors moving during edits do not double-advance the expected caret.
Unsupported navigation or a prefix over 32,000 character units uses one checked dispatch.
Final typing starts after recognition and optional polishing finish; this is gradual
delivery, not live microphone captions.
The target gets up to 300 ms to process the previous batch; the GUI wait is capped at
30 seconds and timeout revokes further delivery. Native provider calls cannot be forcibly
interrupted. Unicode and newlines also use a single dispatch. App rendering varies. A moved target or expired deadline
stops further delivery; partial text may remain, so inspect before copying and never retry
automatically. No clipboard contents are changed.

## Nothing is inserted

Open tray → Latest transcript. Switching windows, moving the cursor, selecting existing text,
unsupported fields, held modifiers and read-only/password fields intentionally use recovery
instead of automatic insertion. Review the target before copying, especially after a partial
insertion notice. Returning to the original window does not trigger delayed insertion.

## Recognition misses a word

Speak clearly at a normal level, check the selected microphone and compare `base.en` with
`small.en`. Try a short vocabulary list for relevant names/terms. Polished improves formatting
but refuses word substitutions and does not repair every recognition error. Compare Result
and Raw transcription; neither model's accuracy is guaranteed.

## Polished takes time or returns Raw

First model loading is more expensive than repeated requests. Loading begins after recording
stops to protect microphone callbacks. Polishing preparation can overlap recognition. A longer
passage needs more ASR and generation time. 1.5B uses more memory than 0.5B; Raw skips the LLM.
Missing/corrupt models, missing optional source runtime, limits, truncation and edits that
change lexical content fall back to Raw. Latest transcript distinguishes "Polishing applied",
"no changes needed", "suggested word changes", timeout, and unavailable outcomes. A rejected
word-changing edit means the model ran and the safeguard kept the original words; restarting
does not change that behavior. Successful insertion after a rejected edit does not show an
error toast. Missing models can be installed with Settings → Download polishing model.
Check the selected model/root and run the README's
`verify-refiner` and `check-refiner` commands without including private transcript text.

## Microphone missing or ambiguous

Choose System default or a device with its audio API shown in Settings. New selections store
the exact name/API and resolve a current index when opening, so ordinary index reordering
does not silently pick another device. Devices with identical names within the same API
cannot be distinguished and are omitted. Older saved names work only when unambiguous;
reselect the device if needed. Hot-plug races and drivers needing another sample rate still
need broader acceptance. Check Windows microphone permission and default input settings.

The app cancels recording if the stream stops or no audio callbacks arrive for three seconds,
even if the driver still reports it as active. It clears the incomplete capture rather than
transcribing it. Reconnect/select the microphone and press the shortcut to retry. Quiet audio
does not trigger this timeout while frames continue arriving. Severe scheduling stalls can
also trigger cancellation; this threshold is a recovery policy, not a driver-repair guarantee.

## Download cancelled or failed

Use Cancel download and wait for cleanup before saving/closing Settings or retrying.
Cancellation removes only that job's identified staging directory. Verified models and other
jobs are preserved. A per-model lock prevents concurrent installers. Verify connectivity,
available space and other active downloads after a failure. Corrupt installed models are
refused; the app does not silently replace or delete them.

An OS crash, power loss or denied deletion may leave partial files. New jobs use unique paths,
so abandoned directories do not block retry. Do not recursively delete a whole model root.
The developer cleanup CLI accepts one validated model/job identity and refuses unowned or
linked staging directories. Old `.model.installing` folders from earlier builds are not
automatically deleted. Inspect partial files carefully before removing them manually.

## Launch upon startup

Enable Settings → Start LocalPhraser upon startup, then Save. This is off by default and
uses a current-user Run entry specific to the absolute configuration path. It needs no admin
rights. Source runs use `pythonw.exe`; folder builds use their executable. Windows can delay
startup or disable it through Startup apps; the app does not rewrite registration on launch.

Keep the app/runtime and configuration in place. Disable startup before moving either, then
enable it from the new location if desired. Long combined paths can exceed Windows' Run
command limit; choose a shorter permanent location. Saving settings applies the checkbox
to this profile only. Explicit Copy is still required to alter the clipboard.

## Preview executable does not start

Extract the entire ZIP, including `_internal`, to a permanent local folder. An unsigned
preview may be flagged as unrecognized. Compare its SHA-256 sidecar before use. Do not swap
in DLLs from unrelated software or run the app elevated to bypass unsupported input targets.
Report the Windows version and whether source/frozen launch failed, without private audio,
transcripts, model weights, credentials or personal screenshots.


## A rebuilt EXE asks for a model again

The normal EXE uses the default profile under `%LOCALAPPDATA%\LocalPhraser`. A development
command with `--config .cache/dev/config.json` uses a different profile and may point to
`.cache/models`. Open Settings, choose that existing model directory and the matching model,
then Save; or start the EXE with the same absolute `--config` path as your old command.
Do not run two copies with competing shortcuts. A new profile now downloads base.en once
on first launch. Cancel or failure leaves manual retry available via Download speech model;
later launches never retry automatically. Offline first use requires a model already installed.


## A microphone driver does not accept 16 kHz

The app now retries once at that device's reported default sample rate when PortAudio
specifically reports an unsupported rate. Rates from 8 to 96 kHz are supported, with local
conversion to 16 kHz before recognition. No setting is required. The same duration limit
applies. Device permission, unavailable-device, channel-count and other errors still need
normal troubleshooting; they are not treated as sample-rate failures. Devices with a
reported default above 96 kHz remain unsupported by this fallback. Driver/hot-plug behavior
still needs broader hardware testing.
