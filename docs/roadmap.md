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
   remain; shortcut selection now uses a focused key/chord recorder.
   The user subsequently confirmed the shortcut picker works and opening-word capture
   improved. Optional vocabulary hints now guide local recognition of names/technical terms;
   measured accuracy gains still require representative speech evaluation.
3. **Phase 2 experimental build implemented:** optional Qwen2.5 0.5B/1.5B Q4 CPU polishing,
   Raw/Polished selection, custom instructions, explicit verified downloads, lazy warm
   process, time limit, lexical preservation and raw fallback. Both models were measured
   on fixed nonsensitive text; 1.5B is the initial choice. Synthetic speech → ASR → refinement
   passed offline. The user subsequently reported improved Polished results both with Wi-Fi
   connected and disconnected, while noting processing delay. Broader preservation corpora and
   clean-machine verification remain. Do not claim Phase 2 acceptance is complete yet.
   Initial loading now begins on the background worker after recording starts, overlapping
   speech rather than waiting until transcription ends. Warm inference still costs CPU time.
4. Desktop polish: opt-in login startup, stronger model lifecycle/cancellation, device identity,
   accessibility and multi-monitor verification. Add screenshots after verified UI capture.
   Settings now scroll with Save/Cancel outside the scroll area; Raw/Result tabs support
   comparison. Next implementation priorities are startup preferences and model lifecycle.
5. Release: license/source inventory, locked dependencies, installable signed/unsigned artifact
   policy, clean-machine checks, release notes, contribution templates and benchmark evidence.
6. macOS/Linux adapters after the Windows workflow proves dependable. No remote publication
   or stable release without explicit authorization and acceptance evidence.
