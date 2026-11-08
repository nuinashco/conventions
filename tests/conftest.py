"""Fixtures the tests share: a directory whose repo opts in to the conventions."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def opted_in(tmp_path: Path) -> Path:
    """Return a directory whose pyproject.toml has an empty `[tool.conventions]`."""
    (tmp_path / "pyproject.toml").write_text("[tool.conventions]\n")
    return tmp_path
