"""`bin/run-check` runs a project's own hook command and does nothing anywhere else."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

RUN_CHECK = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "conventions"
    / "bin"
    / "run-check"
)


def run_check(
    project: Path, *args: str, stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run(
        [str(RUN_CHECK), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize(
    "pyproject",
    [None, '[project]\nname = "x"\n', "[tool.conventions]\n"],
    ids=["no-pyproject", "not-opted-in", "no-venv"],
)
def test_run_check_exits_0_silently_unless_the_project_can_run_the_check(
    tmp_path, pyproject
):
    if pyproject is not None:
        (tmp_path / "pyproject.toml").write_text(pyproject)

    result = run_check(tmp_path, "check-comments", "--claude-hook", stdin="{}")

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_run_check_runs_the_projects_own_command_with_its_arguments_and_input(opted_in):
    command = opted_in / ".venv" / "bin" / "check-comments"
    command.parent.mkdir(parents=True)
    command.write_text('#!/bin/sh\necho "args: $*"\ncat\nexit 2\n')
    command.chmod(0o755)

    result = run_check(opted_in, "check-comments", "--claude-hook", stdin="payload\n")

    assert (result.returncode, result.stdout) == (2, "args: --claude-hook\npayload\n")


def test_run_check_is_executable_posix_sh():
    assert os.access(RUN_CHECK, os.X_OK)
    assert RUN_CHECK.read_text().startswith("#!/bin/sh\n")
