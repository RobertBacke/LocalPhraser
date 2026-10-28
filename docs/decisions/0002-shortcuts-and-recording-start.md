# ADR 0002: Explicit shortcut recording and faster microphone activation

Status: implemented; human acceptance of first-word capture after this change remains open.

User trials confirmed offline dictation and safe focus/selection recovery, but reported
missing opening words. The original sequence performed UI Automation verification before
opening a microphone stream on every press. Slow providers/device initialization therefore
prevented those words from being captured at all.

Take a fast native window/focus/caret snapshot, then start audio immediately. Run accessibility
verification on a dedicated MTA worker while capture continues. Recheck the native snapshot,
field identity, selection and caret; use manual recovery when verification is uncertain or
times out. Retain COM ranges on that thread and pass only opaque tokens to the UI. Key-up
processing no longer waits for accessibility verification.

Use [sounddevice inactive streams](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html)
to prepare the selected device in the background and reuse it between recordings. Request
the backend's low-latency setting without imposing a fixed callback block size. Keep
microphone ready is enabled by default, can be disabled, and never starts capture while idle.
This retains a device handle and a cleared bounded buffer; Windows may show microphone
access and some drivers may restrict sharing with other applications. There is no pre-roll.

Replace typed shortcut syntax with focused [Qt key events](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QKeyEvent.html).
Allow Caps Lock, standalone F1–F11, and supported modifier combinations. Temporarily suspend
the saved shortcut during selection, retaining a Caps Lock-specific suppression hook so
selecting it neither toggles capitalization nor starts dictation. Esc/focus loss restores
the saved shortcut. When Caps Lock is still physically held, keep suppression until key-up
before restoring normal dictation; repeat events must not trigger a session.

No recognizer/model changes are made here. Improving capture onset does not guarantee that
the recognizer will choose the correct word; compare actual speech after updating.
