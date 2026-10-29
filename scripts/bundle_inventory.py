"""Offline inventory of a trusted Windows folder build; not a license approval tool."""

import argparse
import base64
import csv
import hashlib
import json
import re
import subprocess
import sys
from email.parser import Parser
from importlib.metadata import Distribution
from pathlib import Path, PurePosixPath

REPORTS = {"BUNDLE_INVENTORY.json", "BUNDLE_REVIEW.md"}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def is_notice(name: str) -> bool:
    return name.upper().startswith(
        ("LICENSE", "LICENCE", "COPYING", "NOTICE", "THIRDPARTYNOTICE", "COPYRIGHT")
    )


def collect_notices(metadata_directories: list[Path]) -> list[tuple[str, str]]:
    """Preserve wheel notices outside dist-info that copy_metadata does not include."""
    result = set()
    for directory in metadata_directories:
        distribution = Distribution.at(directory)
        name = re.sub(r"[-_.]+", "-", distribution.metadata["Name"]).lower()
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("Unsafe distribution name.")
        site = directory.resolve().parent
        for record in distribution.files or ():
            if not is_notice(record.name):
                continue
            source = Path(distribution.locate_file(record))
            if not source.resolve().is_relative_to(site) or source.is_symlink():
                raise ValueError("Notice file escapes its installed distribution location.")
            if source.is_file():
                relative = source.resolve().relative_to(site)
                destination = Path("third_party") / name / relative.parent
                result.add((str(source.resolve()), destination.as_posix()))
    return sorted(result)


def checked_files(folder: Path) -> list[Path]:
    if folder.is_symlink() or folder.is_junction():
        raise ValueError("Build directory must not be a link or junction.")
    folder = folder.resolve()
    paths = []
    for path in folder.rglob("*"):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(folder):
            raise ValueError("Build contains a link or external path.")
        if path.is_file() and path.relative_to(folder).as_posix() not in REPORTS:
            if (
                path.suffix.lower() in (".wav", ".mp3", ".gguf", ".safetensors", ".env")
                or path.name.lower() == "model.bin"
                or path.name.lower().startswith(".env")
                or path.relative_to(folder).as_posix().lower() == "config.json"
            ):
                raise ValueError("Build contains model weights, audio, or local settings.")
            paths.append(path)
    return sorted(paths)


def inventory(folder: Path, *, probe: bool = False) -> dict:
    paths = checked_files(folder)
    folder = folder.resolve()
    if not (folder / "LocalPhraser.exe").is_file():
        raise ValueError("Expected a LocalPhraser Windows folder build.")
    files = [
        {
            "path": path.relative_to(folder).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in paths
    ]
    findings = []
    packages = []
    internal = folder / "_internal"
    supplemental = []
    source_index = internal / "third_party/supplemental/SOURCES.json"
    if source_index.is_file():
        for source in json.loads(source_index.read_text(encoding="utf-8"))["sources"]:
            filename = source["file"]
            if (
                filename in ("", ".", "..")
                or Path(filename).name != filename
                or ":" in filename
                or "\\" in filename
            ):
                raise ValueError("Unsafe supplemental license path.")
            path = source_index.parent / filename
            if sha256(path) != source["sha256"]:
                raise ValueError("Supplemental notice hash does not match its source index.")
            supplemental.append({**source, "path": path.relative_to(folder).as_posix()})
    for directory in sorted(internal.glob("*.dist-info")):
        metadata = Parser().parsestr((directory / "METADATA").read_text(encoding="utf-8"))
        name, version = metadata["Name"], metadata["Version"]
        if not name or not version:
            raise ValueError("Bundled distribution has incomplete metadata.")
        notices = [
            item["path"]
            for item in files
            if is_notice(Path(item["path"]).name)
            and (
                item["path"].startswith(directory.relative_to(folder).as_posix() + "/")
                or item["path"].startswith(
                    "_internal/third_party/" + re.sub(r"[-_.]+", "-", name).lower() + "/"
                )
            )
        ]
        for declared in metadata.get_all("License-File", []):
            relative = PurePosixPath(declared.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or ":" in declared:
                raise ValueError("Unsafe declared license path.")
            # PEP 639 wheel licenses live in dist-info/licenses; older wheels differ.
            candidates = [directory / "licenses" / str(relative), directory / str(relative)]
            if not any(path.is_file() for path in candidates):
                findings.append(f"{name}: declared license file absent: {relative}")
        if not notices:
            findings.append(f"{name}: no wheel notice file collected; review supplemental notices.")
        packages.append(
            {
                "name": name,
                "version": version,
                "license_expression": metadata.get("License-Expression"),
                "legacy_license": (metadata.get("License") or "").splitlines()[:1],
                "project_urls": metadata.get_all("Project-URL", []),
                "notices": notices,
            }
        )
    record_hashes: dict[str, list[dict]] = {}
    for directory in sorted(internal.glob("*.dist-info")):
        record = directory / "RECORD"
        if not record.is_file():
            continue
        metadata = Parser().parsestr((directory / "METADATA").read_text(encoding="utf-8"))
        for row in csv.reader(record.read_text(encoding="utf-8").splitlines()):
            if len(row) < 2 or not row[1].startswith("sha256="):
                continue
            encoded = row[1].removeprefix("sha256=")
            digest = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
            )
            if len(digest) != 32:
                raise ValueError("Invalid wheel RECORD SHA-256 value.")
            record_hashes.setdefault(digest.hex(), []).append(
                {
                    "distribution": metadata["Name"],
                    "version": metadata["Version"],
                    "record_path": row[0],
                }
            )
    native = [
        {**item, "wheel_records": record_hashes.get(item["sha256"], [])}
        for item in files
        if Path(item["path"]).suffix.lower() in (".dll", ".pyd", ".exe")
    ]
    matched = sum(bool(item["wheel_records"]) for item in native)
    ffmpeg = []
    if probe:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("probe_ffmpeg.py")), str(folder)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
        ffmpeg = json.loads(completed.stdout)
        if not ffmpeg:
            raise ValueError("FFmpeg probe found no libraries.")
        if any(
            "--enable-libx264" in item["configuration"]
            or "--enable-libx265" in item["configuration"]
            for item in ffmpeg
        ):
            findings.append(
                "FFmpeg enables x264/x265: review their actual binaries/terms even when the "
                "FFmpeg library self-reports LGPL."
            )
    findings += [
        "Exact corresponding sources/build recipes for bundled native libraries need review.",
        "Wheel metadata and self-reported FFmpeg terms are evidence, not distribution approval.",
        "Review Qt module terms, source access and shared-library replacement before release.",
        "Review Python, compiler runtimes, BLAS, PortAudio, VAD and FFmpeg dependencies "
        "separately.",
    ]
    return {
        "schema": 1,
        "scope": "Folder runtime only; excludes these reports, ZIP guide additions "
        "and installer engine.",
        "release_approved": False,
        "packages": packages,
        "native_files": native,
        "native_provenance": {
            "matched_files": matched,
            "unmatched_files": len(native) - matched,
            "basis": "Bundled wheel RECORD hashes only; original wheel archives/signatures "
            "and corresponding sources are not verified by this match.",
        },
        "ffmpeg": ffmpeg,
        "supplemental_sources": supplemental,
        "review_findings": findings,
        "files": files,
    }


def write_inventory(folder: Path, *, probe: bool = False) -> dict:
    report = inventory(folder, probe=probe)
    (folder / "BUNDLE_INVENTORY.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# Bundle review — development preview",
        "",
        "This inventory does not approve public binary distribution.",
        "The original application is MIT; dependencies retain their separate terms.",
        "See BUNDLE_INVENTORY.json for relative file paths, SHA-256, versions and provenance.",
        "No model weights, user settings or speech were inspected to create this report.",
        "",
        f"Distributions: {len(report['packages'])}; native files: {len(report['native_files'])}.",
        "Native files matching wheel RECORD hashes: "
        f"{report['native_provenance']['matched_files']}. "
        "Unmatched files still require separate runtime/build provenance review.",
        "",
        "## Review findings",
        "",
        *["- " + finding for finding in report["review_findings"]],
        "",
        "## FFmpeg binary observations",
        "",
    ]
    for item in report["ffmpeg"]:
        lines += [
            f"- {item['path']}: {item['license']}",
            f"  Configuration: `{item['configuration']}`",
        ]
    lines += ["", "## Native files without a wheel RECORD hash match", ""]
    lines += ["- " + item["path"] for item in report["native_files"] if not item["wheel_records"]]
    (folder / "BUNDLE_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def verify_inventory(folder: Path) -> None:
    """Reject missing/stale reports before packaging a preview."""
    try:
        recorded = json.loads((folder / "BUNDLE_INVENTORY.json").read_text(encoding="utf-8"))
        if recorded["schema"] != 1 or not (folder / "BUNDLE_REVIEW.md").is_file():
            raise ValueError("Incomplete bundle inventory.")
        if recorded["files"] != inventory(folder)["files"]:
            raise ValueError("Bundle changed after inventory; regenerate its reports.")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Generate a bundle inventory before packaging.") from exc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=Path("dist/LocalPhraser"))
    parser.add_argument("--probe-ffmpeg", action="store_true", help="Load only trusted build DLLs")
    args = parser.parse_args()
    result = write_inventory(args.folder, probe=args.probe_ffmpeg)
    print(
        f"Inventoried {len(result['packages'])} distributions; public release review remains open."
    )
