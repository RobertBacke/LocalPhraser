# Roadmap

1. **Current:** Phase 1 Windows MVP implemented with automated validation. User reports
   live microphone dictation/insertion in Codex and Chrome and successful offline dictation
   with `small.en`. Focus-change and selected-text recovery also passed user trials.
   Remaining safety cases, broader compatibility and clean-machine
   packaging remain pending; the application is not release-ready.
2. Measure cold/warm ASR and activation, idle resources, memory, model quality. Improve
   microphone sample-rate compatibility and bounded accessibility-call responsiveness.
   Initial device-start measurements, inactive-stream reuse and background accessibility
   verification are implemented. Immediate-speech acceptance and broader driver measurements
   remain; shortcut selection now uses a focused key/chord recorder. Unsupported-rate
   drivers now get a bounded default-rate fallback and worker-side conversion; synthetic
   rate/aliasing checks and an inactive real-device open passed. Broader devices remain.
   The user subsequently confirmed the shortcut picker works and opening-word capture
   improved. Optional vocabulary hints now guide local recognition of names/technical terms;
   measured accuracy gains still require representative speech evaluation.
   Latest transcript now shows per-stage and total after-release timing in memory. A small
   synthetic base.en/small.en and 4/8-thread comparison is recorded in testing.md; broader
   human-speech accuracy and isolated latency benchmarks remain necessary.
   Manual launches now show Settings, new startup commands use --background, and the last
   sanitized error survives later dictations in memory. A reproduced slow-driver-start
   watchdog timeout is fixed; the user's first-dictation failure still needs live retesting.
   A phrase preview and asynchronous insertion are implemented. Following reported
   32-character truncation, paced ASCII output is restricted to native EDIT controls;
   UIA editors use a complete checked dispatch. Cold speech-model loading now waits until
   capture stops after a real-device test reproduced callback overflow during loading.
   The user now reports quick, accurate live dictation with their own microphone. This is
   qualitative acceptance on their current setup, not a broad-device performance claim.
3. **Phase 2 experimental build implemented:** optional Qwen2.5 0.5B/1.5B Q4 CPU polishing,
   Raw/Polished selection, custom instructions, explicit verified downloads, lazy warm
   process, time limit, lexical preservation and raw fallback. Both models were measured
   on fixed nonsensitive text; 1.5B is the initial choice. Synthetic speech → ASR → refinement
   passed offline. The user subsequently reported improved Polished results both with Wi-Fi
   connected and disconnected, while noting processing delay. Broader preservation corpora and
   clean-machine verification remain. Do not claim Phase 2 acceptance is complete yet.
   Initial loading now begins on the background worker after recording starts, overlapping
   speech rather than waiting until transcription ends. Speech-model verification/loading
   now also starts after microphone capture begins, on the same inference worker before
   polishing-model preparation. Warm inference still costs CPU time.
4. **Phase 3 core implemented:** opt-in per-profile launch upon startup, save rollback,
   cancellable model downloads with owned-job cleanup and per-model locks, exact microphone
   name/API selection, scrollable Settings, and Raw/Result comparison. Disposable registry
   and actual installer cancellation checks passed. Actual sign-in launch, wider device/driver,
   accessibility and multi-monitor acceptance remain; optional dark/light styling is deferred.
   Capture now cancels if callbacks stop for three seconds, including drivers still reporting
   active. Quiet frames stay healthy. Simulated stall/recovery and a ten-cycle real-model
   Qt session check passed; actual device-unplug and longer consumer sessions remain.
5. Release: license/source inventory, locked dependencies, installable signed/unsigned artifact
   policy, clean-machine checks, release notes, contribution templates and benchmark evidence.
   **Phase 4 foundation implemented:** checked portable ZIP plus SHA-256, first-run guide,
   manual Windows preview workflow (upload off by default), contributor/bug-report guidance,
   troubleshooting and release checklist. A per-user unsigned installer and disposable-runner
   install/launch/reinstall/uninstall checks are implemented. First-launch profiles now download
   the default speech model once with visible cancellation, automatic readiness and manual retry.
   Offline runtime inventory, wheel notice collection, supplemental source hashes and
   stale-inventory packaging checks are implemented. Native files now have wheel RECORD
   hash attribution; opt-in synthetic Raw/Polished runtime diagnostics support frozen
   consumer-machine validation with sanitized reports. Owned Qt shutdown checks exercise
   closing during loading, polishing and normal completion with synthetic 48 kHz speech. Exact native-source review, signing,
   clean consumer-machine and sustained-session acceptance still block release readiness.
6. macOS/Linux adapters after the Windows workflow proves dependable. No remote publication
   or stable release without explicit authorization and acceptance evidence.
