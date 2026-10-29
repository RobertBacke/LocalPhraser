# Contributing

LocalPhraser is an experimental Windows desktop utility. Keep the offline dictation path
working independently of optional polishing. Changes should be small enough to review and
include meaningful tests for behavior, failure handling, thread/process cleanup and privacy.

Use Python 3.12 x64 and the setup commands in README. Before submitting a change, run:

```powershell
python -m pytest
python -m ruff check src tests scripts packaging
python -m ruff format --check src tests scripts packaging
python -m mypy src
python -m build --no-isolation
```

For native behavior, use the opt-in scripts against owned fixtures; unit mocks do not prove
cross-application compatibility. Label measurements with hardware, versions, cold/warm state,
sample count and limitations. Record architectural decisions and remaining acceptance work.

Do not commit model weights, credentials, local configuration, recordings, personal dictated
text, generated binaries or caches. Use fixed nonsensitive examples; remove private content
from issue reports and screenshots. Avoid exception logging that could include transcripts.
Model downloads must remain explicit; no silent cloud inference or telemetry.

Original code is MIT. Preserve third-party terms and attribution, and update the inventory
when adding dependencies. Public binary distribution needs the release checklist and exact
bundled license/source review, even for an experimental build.
