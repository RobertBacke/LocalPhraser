# Troubleshooting

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
starts and can overlap speech. Short recordings may still leave a cold-load wait. A longer
passage needs more ASR and generation time. 1.5B uses more memory than 0.5B; Raw skips the LLM.
Missing/corrupt models, missing optional source runtime, limits, truncation and edits that
change lexical content fall back to Raw. Check the selected model/root and run the README's
`verify-refiner` and `check-refiner` commands without including private transcript text.

## Microphone missing or ambiguous

Choose System default or a device with its audio API shown in Settings. New selections store
the exact name/API and resolve a current index when opening, so ordinary index reordering
does not silently pick another device. Devices with identical names within the same API
cannot be distinguished and are omitted. Older saved names work only when unambiguous;
reselect the device if needed. Hot-plug races and drivers needing another sample rate still
need broader acceptance. Check Windows microphone permission and default input settings.

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
