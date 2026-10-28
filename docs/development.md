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
and target-app acceptance, and benchmark results. No remote publishing is configured.

No launch-at-login registration is made in the MVP. No existing user files are migrated.
Older configuration files default `keep_microphone_ready` to true when loaded. The setting
is persisted on Save and can be disabled without altering model selection or the shortcut.
Malformed settings are refused without overwriting them. A stale `.installing` model folder
left after an installer is terminated must be removed manually before retrying installation.

Windowed builds route otherwise-missing Python standard streams to the null device, never
to a log file. The source installer's detailed file progress is visible in Settings; a
windowed executable may show only the running/completed installation status. Exact frozen
model installation still needs clean-machine validation before distribution.

The PyInstaller specification restricts its build-process PATH to the Python runtime and
Windows directories before dependency discovery. A reproduced build failure came from an
unrelated Poppler ICU DLL on the host PATH shadowing Windows ICU. Do not remove this isolation
without rechecking the frozen Qt launch on a clean build. No global PATH settings are changed.
