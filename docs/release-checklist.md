# Development preview and release checklist

The source repository is public. This is not a declaration that binaries are release-ready.
Unsigned folder/ZIP and per-user installer previews can be built. Neither is signed, and
automatic updates are not implemented. Models are separate explicit downloads.

## Repeatable build procedure

Use Windows x64 Python 3.12, core requirements-dev.lock, optional requirements-polish.lock,
and the README validation commands. Run PyInstaller with packaging/localphraser.spec, then:

```powershell
python scripts/package_windows.py --folder dist/LocalPhraser --output dist/packages/LocalPhraser-windows-x64-preview.zip
```

The packager checks the x64 PE header and application/third-party notices, retains shared
libraries and metadata, refuses linked/external paths and known weights/audio/local settings,
checks ZIP CRCs, and writes a SHA-256 sidecar. These checks are not a complete secret scanner
or license audit. The archive includes START_HERE instructions for a Python-free first run.

The manual Windows development preview workflow builds/tests on a GitHub Windows runner.
Artifact upload is off by default. Enable upload only after the bundled license/source
review below; artifacts in a public repository are not a private distribution channel.
The workflow does not create a GitHub release or tag. A CI GUI smoke check is not a real
microphone, accessibility, sign-in or clean consumer-machine acceptance test.

## Installer preview

After validating the folder with the ZIP packager, compile `packaging/localphraser.iss`
with [Inno Setup 6.3+](https://jrsoftware.org/isinfo.php). The default input is
`dist/LocalPhraser`; `/DBuildDir=<absolute folder>` overrides it. Output is under
`dist/packages`. The installer uses [non-administrative mode](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm),
installs under the current user's Programs directory, and adds a Start menu shortcut.
Desktop shortcut and immediate launch are optional; launch upon startup remains off.
Quit the tray application before upgrades/removal. The uninstaller removes installed files
and startup entries whose LocalPhraser-prefixed value points exactly to its executable.
It preserves configuration, downloaded models, and entries for other installations.
The saved startup preference remains in preserved settings; re-enable it after reinstalling.

The preview workflow compiles using the runner's Inno Setup and runs
`scripts/check_windows_installer.py` on its disposable Windows runner. That script refuses
ordinary local execution: it installs into a unique path with spaces, launches without
microphone capture, reinstalls, uninstalls, and checks preservation of data and unrelated
startup entries. Installer hashes accompany optional uploads. This is development coverage;
interactive wizard behavior, running-app updates, clean consumer PCs and signing still need
acceptance testing. No public binary release is created.

## Required before public binary distribution

- Complete the exact dependency/native-library license and source inventory. Include copies,
  attribution and any required source access/offers; verify Qt shared-library replacement
  obligations and the actual PyAV/FFmpeg build configuration. See THIRD_PARTY_NOTICES.md.
- Extract and test the archive on a clean Windows 10/11 x64 consumer machine without Python,
  developer DLLs, downloaded models or existing configuration. Record OS/build and hardware.
- Test first-run downloads, offline Raw/Polished dictation, first/warm latency, microphone
  permissions/device loss, selection/focus safety, clipboard preservation and recovery.
- Test cancelled/interrupted downloads, retries, disk-full/corruption cases, source/frozen
  startup paths, opt-in launch upon startup, disabling it, and folder movement/uninstall behavior.
- Run sustained sessions and shutdown stress. Track the intermittent native test-process
  shutdown failure previously observed; later clean exits do not establish its root cause.
- Decide the installer/signing policy and publish accurate unsigned/alpha warnings, checksums,
  model provenance, privacy behavior, release notes and known limitations.
- Do not mark a release stable until essential acceptance criteria are verified. Source
  publication authorization does not automatically authorize a public binary release.
