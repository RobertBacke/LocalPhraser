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

Optional vocabulary hints are text explicitly entered by the user and saved in local
`config.json`. They are passed only to the local speech recognizer. They are never collected
from dictated speech or surrounding documents. Clear the field and Save to remove hints
from the current configuration; user-made backups may retain older settings.

Latest transcript is a single in-memory recovery result, replaced by the next successful
dictation, with Raw and Result versions in Polished mode. Both are explicitly clearable and
cleared on exit. They are not written to settings or disk.
Clipboard is untouched by automatic insertion. Explicit Copy transfers data to the Windows
clipboard; OS clipboard history or sync may retain that copy outside LocalPhraser.

On the first normal launch of a new configuration profile, the app opens Settings and starts
one visible download of the default `base.en` speech model if it is absent. Cancel is available.
The configuration is persisted before downloading; failure, cancellation and later launches
never trigger automatic retries. Existing profiles and `--smoke-test` never start this setup.
Only that first-launch setup, explicit `install-model` / `install-refiner`, and Settings download
actions initiate network requests. Download workers use
Hugging Face Hub HTTPS metadata/download endpoints and their redirected storage/CDN endpoints
to fetch Systran speech or publisher Qwen GGUF artifacts. It records repository/revision/hashes. No speech is supplied.
Installer download metadata may reside under the chosen model directory. Installation occurs
in a separate process; dictation remains offline. Development package installation also
contacts package registries, but it is not application runtime traffic.

Cancelling a download stops only its owned child process and cleans only its UUID-identified
staging directory after exit. Verified models and other jobs remain. Cleanup runs offline;
model staging/lock metadata contains no speech. Startup is off by default and writes a
current-user Run value only after an explicit settings change/Save. That value contains the
application command and absolute config path, not transcripts. It does not enable recording
at sign-in; Keep microphone ready still opens only an inactive stream until recording starts.

Optional polishing passes text over a private multiprocessing pipe to a local CPU worker.
Its model starts loading in the background after the first Polished recording begins,
without receiving audio or transcript text. Text is sent only after recognition finishes.
Preparation may continue after a cancelled recording, keeping the model ready for later use;
switching to Raw or quitting releases it.
It uses only verified local GGUF files; Python socket connections are disabled in that
worker. It does not start a network listener or use llama.cpp's model downloader. Prompts
are not placed in shell commands, process arguments, temporary files, or a disk cache.
Worker output goes to the null device, not logs. The worker resets model context between
requests and drops temporary Python references, but native buffers and immutable strings
cannot be securely erased. Clearing the displayed transcript is not a secure-memory-wipe
guarantee. Selecting Raw or quitting terminates the polishing worker. User-entered polishing
instructions, model choice, and time limit are saved in settings; dictated text is not.

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
