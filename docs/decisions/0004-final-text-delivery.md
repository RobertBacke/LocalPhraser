# Complete final-text delivery

The user reported an initial few words, a long pause, then the rest appearing together.
The paced path divided output into 32-character batches and revalidated UI Automation
caret state between batches. Editor rendering and accessibility-provider latency made
those intervals unpredictable despite exact delivery passing owned-editor checks.

The desktop pipeline now uses one checked dispatch of the complete recognized/polished
text after recording stops. The floating live preview remains available while speaking.
There is no clipboard replacement. Focus, field identity, caret/selection, modifier and
permission checks still precede dispatch. Failed or partial input is never retried.

An owned reactive Chrome editor received all 2,736 expected characters in one dispatch,
preserved its existing prefix, and refused selected text afterward. Regression coverage
requires the async desktop path to call complete delivery once. The older paced helper
remains a developer comparison path; it is not used by ordinary desktop dictation.

[SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
queues the supplied input events serially. This is not an editor transaction or a guarantee
that every application paints the entire result in one frame. The focus-check/input race
and privileged/unsupported field limitations remain.
