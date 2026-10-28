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
3. Phase 2: evaluate permissively licensed 0.5–3B quantized local refinement models; add
   Raw/Polished selection, limits and raw fallback only after preservation/latency evaluation.
4. Desktop polish: opt-in login startup, stronger model lifecycle/cancellation, device identity,
   accessibility and multi-monitor verification. Add screenshots after verified UI capture.
5. Release: license/source inventory, locked dependencies, installable signed/unsigned artifact
   policy, clean-machine checks, release notes, contribution templates and benchmark evidence.
6. macOS/Linux adapters after the Windows workflow proves dependable. No remote publication
   or stable release without explicit authorization and acceptance evidence.
