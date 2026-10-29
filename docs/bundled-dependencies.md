# Bundled dependency review

This is an engineering inventory of the Windows preview, not approval to distribute it.
The original LocalPhraser source remains MIT. Dependency/native-library terms are separate.

## Repeatable offline evidence

Build with `packaging/localphraser.spec`, then run:

```powershell
python scripts/bundle_inventory.py --folder dist/LocalPhraser --probe-ffmpeg
python scripts/package_windows.py --output dist/packages/LocalPhraser-windows-x64-preview.zip
```

Only probe DLLs from a trusted build. The FFmpeg probe runs in a separate short-lived process,
uses explicit bundled paths and DLL directories, and records version/configuration/license
exports. It neither starts the app nor opens a microphone or model. The inventory makes no
network requests. It rejects links, escaped paths and known audio/model/settings payloads.
It records relative paths, byte sizes and SHA-256 values for runtime files, including native
EXE/DLL/PYD files. Its own reports, guide additions during ZIP creation, and the installer
engine are outside that runtime manifest's scope. It is not a complete transitive SBOM.

Wheel distribution names/versions, declared license metadata and Project-URL values are
retained as publisher-provided evidence. `License-File` references are checked for local
presence. Missing notice files become review findings. Supplementary texts have individually
checked source hashes. Neither metadata nor the inventory independently proves provenance.
Packaging refuses an absent inventory or any runtime file change after inventory generation.
Regenerate reports after rebuilding or changing a library. Public uploads remain off by default.

## Notice omissions addressed

The old folder contained Python dist-info metadata, but some wheels store licenses elsewhere.
ONNX Runtime 1.31.1's `LICENSE` and `ThirdPartyNotices.txt` were installed in its package folder
and absent from the old bundle. The specification now copies wheel RECORD entries named
LICENSE/LICENCE, COPYING, NOTICE, ThirdPartyNotices or COPYRIGHT into `_internal/third_party`.
This also retains additional NumPy package notices without copying unrelated package data.

The build interpreter's Python license and the installed PyInstaller bootloader license with
exception are retained. The Qt for Python/Shiboken 6.12.0 wheel metadata declares LGPL/GPL
alternatives but its collected license file contains commercial terms. Supplemental GNU
LGPLv3 and GPLv3 texts are included from the Qt 6.12.0 source tag. CTranslate2, FlatBuffers,
and tokenizers wheels also lacked separate notice files; version-tagged upstream texts
are provided alongside PortAudio and Silero VAD terms. The collector also recognizes
tqdm's LICENCE spelling; a version-tagged supplemental copy is included. Files and hashes are recorded in
`packaging/licenses/SOURCES.json`. These are supplemental terms, not matched source archives.

## FFmpeg observations requiring further review

The installed PyAV 19.0.2 Windows wheel bundles FFmpeg. The measured avcodec, avformat and
avutil DLLs self-report **LGPL version 3 or later**, with `--enable-version3` and shared
linking. Their configuration also enables `libx264` and `libx265`. These observations are
recorded separately; the reported FFmpeg label does not settle linked codec terms.
Upstream [FFmpeg licensing documentation](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md)
identifies external codec libraries that can affect distribution terms. The
[PyAV FFmpeg build repository](https://github.com/PyAV-Org/pyav-ffmpeg) supplies build context.
The inventory now matches native bytes against SHA-256 entries in bundled wheel RECORD
files. The preceding preview matched 157 of 185 native files; the JSON report lists every
matching distribution/version/record path and separately lists unmatched files. Most
unmatched files are Python/Windows runtimes, plus the application executable. This identifies
wheel-record correspondence; original wheel archives/signatures and exact source archives
remain unverified by the comparison. A filename alone never establishes a match.

Exact source revisions, patches, build recipes and codec dependency correspondence still
need investigation before public binary distribution. No licensing conclusion is inferred
from the self-reported string alone.

## Remaining release work

- Map exact bundled native files to their matching sources, patches and build configuration.
- Review Qt modules/third-party notices, source availability and actual ability to load
  interface-compatible replacement shared libraries against the
  [Qt license terms](https://doc.qt.io/qt-6/licensing.html).
- Finish FFmpeg and linked codec dependency review, including required source access/notices.
- Review compiler/Windows runtimes, BLAS, PortAudio's devel build, VAD asset correspondence,
  Python's bundled libraries, and the separately generated Inno Setup installer engine.
- Complete clean Windows 10/11 consumer acceptance, shutdown stress and signing policy.

The generated `release_approved` field stays false: this tool collects evidence and does not
issue legal approval. See [release checklist](release-checklist.md) for acceptance requirements.
