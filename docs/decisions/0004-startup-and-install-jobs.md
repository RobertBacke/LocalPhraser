# 0004 — Opt-in startup and cancellable owned install jobs

Status: implemented, consumer sign-in/clean-machine acceptance pending.

Use a current-user Windows Run value identified by the absolute configuration path's hash.
Microsoft documents its [per-user semantics, command limit and possible startup delays](https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys).
Startup is off by default. Save applies opt-in changes, using pythonw.exe for source or the
folder executable for frozen runs, with an absolute quoted configuration path. Failure to
save configuration restores the prior entry where possible. Normal launches never rewrite
registration or override Windows Startup apps approval. Multiple opted-in profiles can
conflict over their shortcuts; users should normally enable only their daily-use profile.

Windows QProcess termination can end an installer without Python finally cleanup. Keep
downloads isolated in UUID staging directories, with an ownership marker and per-model
kernel-backed file lock. A killed process releases its lock. After exit, a separate cleanup
process validates exact catalog/job identity and path containment and refuses links/junctions
or unowned files. It never removes the published model. Do not attempt broad root cleanup.
Qt documents [QProcess termination/kill behavior](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html).

Interrupted/denied cleanup may leave residues, but unique jobs permit retry without deleting
another installation. Atomically publish only verified artifacts; never silently replace a
corrupt installed model. The source/frozen CLI exposes a narrow job cleanup command so the
UI can keep filesystem deletion off its event thread during normal cancellation. App exit
performs bounded process shutdown followed by best-effort owned-stage cleanup.

Persist microphone name plus audio API, not a transient numeric index. Resolve before each
new stream, and refuse ambiguous names/duplicates rather than selecting a different input.
This does not solve identically named physical devices or hot-plug races; native endpoint
identity would require a further platform adapter.
