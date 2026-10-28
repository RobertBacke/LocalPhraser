# Privacy and network behavior

Audio capture starts only during an explicitly started recording. With **Keep microphone
ready** enabled (the default), the selected device is opened in advance but its stream stays
stopped while idle. No idle callbacks, captured audio, or rolling pre-recording buffer are
used. Windows may show device access even while stopped. Disabling this setting closes the
device after every recording. Changing settings, errors, and exit release the device.
Recorded audio is bounded RAM;
buffers are zeroed best-effort on success, cancellation and errors. Python/native runtimes,
memory paging and OS crash dumps prevent a secure-erasure guarantee. No audio temp files.

ASR receives arrays, not file paths; CPU inference and Silero VAD run locally. The runtime
sets HF_HUB_OFFLINE and uses a verified local model directory with local_files_only=True.
No dictated content is logged. Exceptions shown to users are sanitized. No analytics,
accounts, telemetry, history database, updater, or cloud inference client.

Latest transcript is a single in-memory recovery result, replaced by the next successful
dictation, explicitly clearable, and cleared on exit. It is not written to settings or disk.
Clipboard is untouched by automatic insertion. Explicit Copy transfers data to the Windows
clipboard; OS clipboard history or sync may retain that copy outside LocalPhraser.

Only `install-model` and Settings → Download initiate network requests. The installer uses
Hugging Face Hub HTTPS metadata/download endpoints and their redirected storage/CDN endpoints
to fetch Systran model artifacts. It records repository/revision/hashes. No speech is supplied.
Installer download metadata may reside under the chosen model directory. Installation occurs
in a separate process; dictation remains offline. Development package installation also
contacts package registries, but it is not application runtime traffic.

Caps Lock uses a dedicated keyboard-hook message thread that inspects only the virtual-key
identifier, consumes Caps Lock press/release, and immediately forwards all unrelated events
without collecting them. This prevents capitalization toggles. Switching shortcuts or quitting
removes the hook. Modifier shortcuts use Windows registration and query only their chord
while held. Insertion checks only modifier states. UIA reads focused field metadata,
empty-selection position, and editability, not surrounding document content. No key logger,
admin requirement, privilege bypass or broad filesystem access. User-writable config/model
folders are used. Models are executable-library inputs: use the documented trusted source.

For exact-class standard Windows EDIT controls, bounded native messages retrieve only
selection offsets and styles. The production app does not retrieve full field contents.
The opt-in developer test reads its own disposable fixture contents to assert delivery.

Verify by installing a model, checking hashes, disconnecting networking, and repeating
dictation in supported applications. Tests also deny Python socket creation during model
verification and offline inference tests. Native-library networking is not exhaustively
audited; use Windows firewall/packet capture for stronger independent verification.
