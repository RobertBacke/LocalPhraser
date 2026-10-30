"""Explicit model installation and local integrity checks. No import-time networking."""

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from filelock import FileLock

from localphraser.config import MODELS, REFINEMENT_MODELS

FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


def model_files(name: str) -> tuple[str, ...]:
    return (*FILES[:-1], "vocabulary.json") if name.startswith("distil-") else FILES


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_model(path: Path) -> None:
    verify_artifacts(path, model_files(path.name))


def verify_artifacts(path: Path, files: tuple[str, ...]) -> None:
    try:
        manifest = json.loads((path / "localphraser-manifest.json").read_text(encoding="utf-8"))
        if set(manifest["sha256"]) != set(files):
            raise ValueError("Incomplete model manifest.")
        for name in files:
            if digest(path / name) != manifest["sha256"][name]:
                raise ValueError("Model integrity check failed.")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Model missing or damaged. Run install-model explicitly.") from exc


def install_model(name: str, root: Path, *, job_id: str | None = None) -> Path:
    """Only caller-authorized CLI/UI setup calls this network operation.

    Resolve the repository once, pin every file to that commit, verify LFS hashes,
    and record provenance and hashes before making the directory available.
    """
    if name not in MODELS:
        raise ValueError("Unsupported model.")
    repo = (
        f"Systran/faster-distil-whisper-{name.removeprefix('distil-')}"
        if name.startswith("distil-")
        else f"Systran/faster-whisper-{name}"
    )
    return install_artifacts(name, root, repo, model_files(name), job_id=job_id)


def staging_path(name: str, root: Path, job_id: str) -> Path:
    if name not in (*MODELS, *REFINEMENT_MODELS) or len(job_id) != 32:
        raise ValueError("Invalid installation identity.")
    if any(char not in "0123456789abcdef" for char in job_id):
        raise ValueError("Invalid installation identity.")
    root = root.resolve()
    stage = root / f".{name}.{job_id}.installing"
    if stage.is_symlink() or stage.is_junction() or stage.resolve().parent != root:
        raise ValueError("Installation path is not an owned staging directory.")
    return stage


def cleanup_install(name: str, root: Path, job_id: str) -> None:
    """Remove only one identified job, never the published model or other jobs."""
    stage = staging_path(name, root, job_id)
    if not stage.exists():
        return
    marker = stage / ".localphraser-job"
    if not marker.exists():
        stage.rmdir()  # Only an empty directory from the mkdir/marker-write gap is safe.
        return
    if marker.is_symlink() or marker.read_text(encoding="ascii") != job_id:
        raise ValueError("Staging ownership could not be verified.")
    shutil.rmtree(stage)


def install_artifacts(
    name: str, root: Path, repo: str, files: tuple[str, ...], *, job_id: str | None = None
) -> Path:
    """Internal catalog-only installer; callers supply fixed names and file lists."""
    job_id = uuid.uuid4().hex if job_id is None else job_id
    staging_path(name, root, job_id)  # Validate before creating or acquiring anything.
    root.mkdir(parents=True, exist_ok=True)
    # Kernel-backed lock releases on forced termination; its empty file may remain.
    with FileLock(str(root / f".{name}.install.lock"), timeout=0):
        return _install_artifacts(name, root, repo, files, job_id)


def _install_artifacts(
    name: str, root: Path, repo: str, files: tuple[str, ...], job_id: str
) -> Path:
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import HfApi, hf_hub_download

    root.mkdir(parents=True, exist_ok=True)
    destination = root / name
    if destination.exists():
        verify_artifacts(destination, files)
        print("Model already installed and verified. Remove its directory to reinstall.")
        return destination
    info = HfApi().model_info(repo, files_metadata=True)
    revision = info.sha
    if not revision:
        raise ValueError("Model repository did not return a revision.")
    stage = staging_path(name, root, job_id)
    stage.mkdir()
    (stage / ".localphraser-job").write_text(job_id, encoding="ascii")
    try:
        hashes = {}
        siblings = {f.rfilename: f for f in (info.siblings or [])}
        for index, filename in enumerate(files, 1):
            print(f"Downloading {index}/{len(files)}: {filename}", flush=True)
            downloaded = Path(
                hf_hub_download(
                    repo,
                    filename,
                    revision=revision,
                    local_dir=stage,
                )
            )
            checksum = digest(downloaded)
            metadata = siblings[filename]
            if filename.endswith(".gguf") and not metadata.lfs:
                raise ValueError("GGUF download requires an upstream SHA-256 hash.")
            if metadata.lfs and checksum != metadata.lfs.sha256:
                raise ValueError("Downloaded model hash does not match repository metadata.")
            hashes[filename] = checksum
        (stage / "localphraser-manifest.json").write_text(
            json.dumps({"repository": repo, "revision": revision, "sha256": hashes}, indent=2),
            encoding="utf-8",
        )
        verify_artifacts(stage, files)
        stage.rename(destination)
    finally:
        if stage.exists():
            cleanup_install(name, root, job_id)
    print(f"Installed and verified: {destination}", flush=True)
    return destination
