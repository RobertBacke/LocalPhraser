# Development preview and release checklist

The source repository is public. This is not a declaration that binaries are release-ready.
An unsigned folder/ZIP can be built locally; a ZIP does not provide installation, signing,
automatic updates or an uninstaller. Models are separate explicit downloads.

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

## Required before public binary distribution

- Complete the exact dependency/native-library license and source inventory. Include copies,
  attribution and any required source access/offers; verify Qt shared-library replacement
  obligations and the actual PyAV/FFmpeg build configuration. See THIRD_PARTY_NOTICES.md.
- Extract and test the archive on a clean Windows 10/11 x64 consumer machine without Python,
  developer DLLs, downloaded models or existing configuration. Record OS/build and hardware.
- Test first-run downloads, offline Raw/Polished dictation, first/warm latency, microphone
  permissions/device loss, selection/focus safety, clipboard preservation and recovery.
- Test cancelled/interrupted downloads, retries, disk-full/corruption cases, source/frozen
  startup paths, opt-in sign-in startup, disabling it, and folder movement/uninstall behavior.
- Run sustained sessions and shutdown stress. Track the intermittent native test-process
  shutdown failure previously observed; later clean exits do not establish its root cause.
- Decide the installer/signing policy and publish accurate unsigned/alpha warnings, checksums,
  model provenance, privacy behavior, release notes and known limitations.
- Do not mark a release stable until essential acceptance criteria are verified. Source
  publication authorization does not automatically authorize a public binary release.
