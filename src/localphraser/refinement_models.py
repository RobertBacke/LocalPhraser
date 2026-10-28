"""Explicitly downloaded, publisher-provided Apache-2.0 CPU GGUF catalog."""

from pathlib import Path

from localphraser.config import REFINEMENT_MODELS
from localphraser.models import install_artifacts, verify_artifacts


def artifacts(name: str) -> tuple[str, tuple[str, ...]]:
    if name not in REFINEMENT_MODELS:
        raise ValueError("Unsupported refinement model.")
    size = "0.5B" if name == "qwen2.5-0.5b" else "1.5B"
    return f"Qwen/Qwen2.5-{size}-Instruct-GGUF", (
        f"{name}-instruct-q4_k_m.gguf",
        "LICENSE",
        "README.md",
    )


def install_refiner(name: str, root: Path) -> Path:
    repo, files = artifacts(name)
    return install_artifacts(name, root, repo, files)


def verify_refiner(name: str, root: Path) -> Path:
    _, files = artifacts(name)
    directory = root / name
    verify_artifacts(directory, files)
    return directory / files[0]
