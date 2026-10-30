"""Create a checked unsigned development ZIP, retaining all shared libraries/notices."""

import argparse
import hashlib
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

if __package__:
    from .bundle_inventory import verify_inventory
else:
    from bundle_inventory import verify_inventory


def package(folder: Path, output: Path) -> Path:
    if folder.is_symlink() or folder.is_junction():
        raise ValueError("Build directory must not be a link or junction.")
    folder, output = folder.resolve(), output.resolve()
    if output.suffix.lower() != ".zip" or output.is_relative_to(folder):
        raise ValueError("Choose a ZIP output outside the build directory.")
    executable = folder / "LocalPhraser.exe"
    with executable.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Not a Windows executable.")
        stream.seek(0x3C)
        offset = int.from_bytes(stream.read(4), "little")
        stream.seek(offset)
        if stream.read(6) != b"PE\x00\x00\x64\x86":
            raise ValueError("Expected a Windows x64 executable.")
    if not (folder / "_internal" / "LICENSE").is_file():
        raise ValueError("Build is missing the application license.")
    if not (folder / "_internal" / "THIRD_PARTY_NOTICES.md").is_file():
        raise ValueError("Build is missing third-party notices.")
    verify_inventory(folder)
    paths = []
    for current, directories, files in os.walk(folder, followlinks=False):
        for name in [*directories, *files]:
            path = Path(current) / name
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(folder):
                raise ValueError("Build contains a link or an external path.")
        for name in files:
            path = Path(current) / name
            if (
                path.suffix.lower() in (".wav", ".mp3", ".gguf", ".safetensors", ".env")
                or name.lower() == "model.bin"
                or name.lower().startswith(".env")
                or name.lower().startswith("history.sqlite3")
                or ".history.sqlite3" in name.lower()
                or path == folder / "config.json"
            ):
                raise ValueError("Build contains model weights, audio, or local settings.")
            paths.append(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".zip.tmp")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(paths):
                archive.write(path, "LocalPhraser/" + path.relative_to(folder).as_posix())
            guide = Path(__file__).resolve().parents[1] / "packaging" / "START_HERE.txt"
            archive.write(guide, "LocalPhraser/START_HERE.txt")
        with ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity verification failed.")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    with output.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=Path("dist/LocalPhraser"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(package(args.folder, args.output))


if __name__ == "__main__":
    main()
