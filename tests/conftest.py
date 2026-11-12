"""Fixtures the tests share: a repo that opts in, and a package to check."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def opted_in(tmp_path: Path) -> Path:
    """Return a directory whose pyproject.toml has an empty `[tool.conventions]`."""
    (tmp_path / "pyproject.toml").write_text("[tool.conventions]\n")
    return tmp_path


@pytest.fixture
def demo_package(tmp_path: Path) -> Callable[[dict[str, str]], Path]:
    """Return a function that writes modules under `src/demo/`, a package per folder."""

    def write(files: dict[str, str]) -> Path:
        folder = tmp_path / "src" / "demo"
        for name, source in {"__init__.py": "", **files}.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            (path.parent / "__init__.py").touch()
            path.write_text(source)
        return folder

    return write
