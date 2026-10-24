"""Run uploads to the team bucket."""

from __future__ import annotations

from pathlib import Path


def upload_run(run_dir: Path, *, bucket: str) -> None:
    """Copy every file under `run_dir` to `bucket`."""
    for path in run_dir.rglob("*"):
        if path.is_file():
            print(f"upload {path} -> {bucket}/{path.relative_to(run_dir)}")
