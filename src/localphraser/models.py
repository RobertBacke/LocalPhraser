"""Explicit model installation and local integrity checks. No import-time networking."""

import hashlib
import json
import os
import shutil
from pathlib import Path

from localphraser.config import MODELS

FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_model(path: Path) -> None:
    try:
        manifest = json.loads((path / "localphraser-manifest.json").read_text(encoding="utf-8"))
        if set(manifest["sha256"]) != set(FILES):
            raise ValueError("Incomplete model manifest.")
        for name in FILES:
            if digest(path / name) != manifest["sha256"][name]:
                raise ValueError("Model integrity check failed.")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Model missing or damaged. Run install-model explicitly.") from exc


def install_model(name: str, root: Path) -> Path:
    """Only caller-authorized CLI/UI setup calls this network operation.

    Resolve the repository once, pin every file to that commit, verify LFS hashes,
    and record provenance and hashes before making the directory available.
    """
    if name not in MODELS:
        raise ValueError("Unsupported model.")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import HfApi, hf_hub_download

    root.mkdir(parents=True, exist_ok=True)
    destination = root / name
    if destination.exists():
        verify_model(destination)
        print("Model already installed and verified. Remove its directory to reinstall.")
        return destination
    repo = f"Systran/faster-whisper-{name}"
    info = HfApi().model_info(repo, files_metadata=True)
    revision = info.sha
    if not revision:
        raise ValueError("Model repository did not return a revision.")
    # A fixed staging name and exclusive creation prevent concurrent partial installs.
    stage = root / f".{name}.installing"
    stage.mkdir()
    try:
        hashes = {}
        siblings = {f.rfilename: f for f in (info.siblings or [])}
        for index, filename in enumerate(FILES, 1):
            print(f"Downloading {index}/{len(FILES)}: {filename}", flush=True)
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
            if metadata.lfs and checksum != metadata.lfs.sha256:
                raise ValueError("Downloaded model hash does not match repository metadata.")
            hashes[filename] = checksum
        (stage / "localphraser-manifest.json").write_text(
            json.dumps({"repository": repo, "revision": revision, "sha256": hashes}, indent=2),
            encoding="utf-8",
        )
        verify_model(stage)
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(f"Installed and verified: {destination}", flush=True)
    return destination
