# Development

Use the README's Python 3.12 x64 virtual environment commands. The project is source-layout
packaged with Hatchling. `requirements-dev.lock` captures the resolved development environment;
install it with `uv pip sync --python .venv\Scripts\python.exe requirements-dev.lock` and then
`uv pip install --python .venv\Scripts\python.exe --no-deps -e .`.

Run pytest, Ruff check/format, mypy, and build before contributions. Tests inject hardware,
OS and ASR ports rather than requiring personal speech. Avoid logging raw exceptions from
dictation providers, which may contain sensitive text. Match actual verification to claims.
CI runs on Windows Python 3.12; CI mocks do not certify cross-application behavior.

`--smoke-test --config <absolute-test-path>` starts Qt, tray, UIA and hotkey registration
for 1.5 seconds without recording or typing. Use a disposable config directory.

Build `packaging/localphraser.spec` with PyInstaller on Windows. Keep the folder intact.
The development executable is unsigned and may trigger Windows SmartScreen. Public releases
need clean-machine tests, dependency/license inventory, installer, signing decision, microphone
and target-app acceptance, and benchmark results. The public GitHub repository runs Windows
checks; automated binary releases are not configured.

Launch upon startup is opt-in and off in older configurations. Registration changes only on
Settings Save when enabled or toggled; launches do not rewrite it. Each absolute config path
has a distinct current-user Run value. A failed settings save attempts registry rollback.
Source startup uses the same environment's pythonw.exe with an absolute config path; frozen
startup uses its current executable. Windows startup delays/disablement remain OS-managed.
Older configuration files default `keep_microphone_ready` to true when loaded. The setting
is persisted on Save and can be disabled without altering model selection or the shortcut.
Malformed settings are refused without overwriting them. Download jobs now use unique
UUID staging directories and kernel-backed per-model file locks. Settings cancels its
owned process, waits for exit, then runs offline cleanup separately from the UI. Cleanup
validates catalog/job identity, resolved containment, absence of links/junctions and an
ownership marker; it never removes published models. Startup failures, OS crashes, denied
deletion or old fixed-name staging folders may leave residue; new jobs still can retry.
Do not remove a whole model root to recover one failed download.

New microphone selections persist exact name plus host API, resolving a fresh index before
opening. Unique old names remain usable and migrate on Save when unambiguous. Indistinguishable
duplicates are omitted/refused. System default remains the default, and no device is opened
by merely enumerating the list. Broader driver/sample-rate/hot-plug acceptance remains open.

Older configurations also default to empty vocabulary hints. Hints are an explicitly entered,
single-line string limited to 300 characters. The UI passes them through faster-whisper's
`hotwords` argument; blank hints become `None`. Recognition output is not post-replaced.
The engine may truncate hints to its prompt token budget, so concise lists work best.

Phase 2 has an optional `polish` extra. The tested Windows CPU wheel and its added
dependencies are pinned in `requirements-polish.lock`, using the upstream documented CPU
index; install this after the core environment. A generic PyPI install may need a C++
compiler, so prefer the tested wheel command in README. PyInstaller includes llama.cpp only
when installed in the build environment; Raw-only builds do not require it. Model weights
remain separate setup downloads. Do not remove `freeze_support` from either entry point.

The user must explicitly select Polished; older settings retain Raw and default to the
initial Qwen2.5 1.5B model choice, built-in instructions, and a 15-second deadline.
`check-refiner --root <model-root>` runs two fixed synthetic text checks without a microphone
or transcript output. `scripts/benchmark_refinement.py` reports per-case acceptance, latency,
own-child peak RSS, and hardware; it is not a statistical accuracy benchmark.

Windowed builds route otherwise-missing Python standard streams to the null device, never
to a log file. The source installer's detailed file progress is visible in Settings; a
windowed executable may show only the running/completed installation status. Exact frozen
model installation still needs clean-machine validation before distribution.

The PyInstaller specification restricts its build-process PATH to the Python runtime and
Windows directories before dependency discovery. A reproduced build failure came from an
unrelated Poppler ICU DLL on the host PATH shadowing Windows ICU. Do not remove this isolation
without rechecking the frozen Qt launch on a clean build. No global PATH settings are changed.
