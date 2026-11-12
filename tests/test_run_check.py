"""`scripts/run-check` runs a project's own hook command and stays silent elsewhere."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "conventions"
RUN_CHECK = PLUGIN / "scripts" / "run-check"


def run_check(
    project: Path, *args: str, stdin: str = "", path: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the launcher for `project`; `path` replaces the PATH it finds tools on."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [str(RUN_CHECK), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def install(project: Path, script: str, *, command: str = "check-comments") -> None:
    """Write `script` as `command` in the virtualenv of `project`."""
    path = project / ".venv" / "bin" / command
    path.parent.mkdir(parents=True)
    path.write_text(script)
    path.chmod(0o755)


def install_check_comments(project: Path) -> None:
    """Put the real `check-comments` of this repo in the virtualenv of `project`."""
    path = project / ".venv" / "bin" / "check-comments"
    path.parent.mkdir(parents=True)
    path.symlink_to(Path(sys.executable).with_name("check-comments"))


def path_where_id_names_another_user(folder: Path) -> str:
    """Return a PATH whose `id` gives the number of a user who owns nothing here."""
    fakes = folder / "fakes"
    fakes.mkdir()
    (fakes / "id").write_text(f"#!/bin/sh\necho {os.getuid() + 1}\n")
    (fakes / "id").chmod(0o755)
    return f"{fakes}{os.pathsep}{os.environ['PATH']}"


def edit_that_leaves_a_banner(folder: Path) -> str:
    """Return the hook's input for an edit of a file in `folder` that breaks DOC-4."""
    path = folder / "banner.py"
    path.write_text("# ----------\nx = 1\n")
    return json.dumps({"tool_input": {"file_path": str(path)}})


def test_run_check_exits_0_silently_where_no_virtualenv_has_the_command(opted_in):
    install(opted_in, "#!/bin/sh\necho ran\n", command="check-protected")

    result = run_check(opted_in, "check-comments", "--claude-hook", stdin="{}")

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_run_check_runs_the_projects_own_command_with_its_arguments_and_input(opted_in):
    install(opted_in, '#!/bin/sh\necho "args: $*"\ncat\nexit 2\n')

    result = run_check(opted_in, "check-comments", "--claude-hook", stdin="payload\n")

    assert (result.returncode, result.stdout) == (2, "args: --claude-hook\npayload\n")


def test_run_check_passes_the_exit_code_and_both_outputs_through_unchanged(opted_in):
    install(opted_in, "#!/bin/sh\necho out\nprintf 'two\\nlines\\n\\n' >&2\nexit 3\n")

    result = run_check(opted_in, "check-comments")

    assert (result.returncode, result.stdout, result.stderr) == (
        3,
        "out\n",
        "two\nlines\n\n",
    )


def test_run_check_finds_the_virtualenv_of_the_workspace_above_a_member(tmp_path):
    install(tmp_path, "#!/bin/sh\npwd\n")
    member = tmp_path / "packages" / "member"
    member.mkdir(parents=True)

    result = run_check(member, "check-comments")

    assert (result.returncode, result.stdout) == (0, f"{member}\n")


def test_run_check_prefers_the_virtualenv_nearest_to_the_project(tmp_path):
    member = tmp_path / "packages" / "member"
    install(tmp_path, "#!/bin/sh\necho workspace\n")
    install(member, "#!/bin/sh\necho member\n")

    result = run_check(member, "check-comments")

    assert result.stdout == "member\n"


def test_run_check_finds_the_workspace_of_a_member_reached_through_a_symlink(tmp_path):
    workspace = tmp_path / "workspace"
    install(workspace, "#!/bin/sh\necho workspace\n")
    (workspace / "member").mkdir()
    (tmp_path / "link").symlink_to(workspace / "member")

    result = run_check(tmp_path / "link", "check-comments")

    assert result.stdout == "workspace\n"


def test_run_check_serves_a_git_worktree_from_the_checkout_it_lies_in(tmp_path):
    install(tmp_path, "#!/bin/sh\necho checkout\n")
    worktree = tmp_path / ".claude" / "worktrees" / "fix"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../../../.git/worktrees/fix\n")

    result = run_check(worktree, "check-comments")

    assert result.stdout == "checkout\n"


def test_run_check_never_runs_a_virtualenv_above_the_project_that_another_user_owns(
    tmp_path,
):
    install(tmp_path, "#!/bin/sh\necho planted\n")
    project = tmp_path / "scratch"
    project.mkdir()
    path = path_where_id_names_another_user(tmp_path)

    result = run_check(
        project, "check-comments", "--claude-hook", stdin="{}", path=path
    )

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_run_check_runs_the_virtualenv_of_the_project_itself_whoever_owns_it(tmp_path):
    install(tmp_path, "#!/bin/sh\necho project\n")
    path = path_where_id_names_another_user(tmp_path)

    result = run_check(tmp_path, "check-comments", path=path)

    assert result.stdout == "project\n"


@pytest.mark.parametrize(
    "table",
    ["[ tool.conventions ]\n", '[tool."conventions"]\n', "[tool]\nconventions = {}\n"],
    ids=["spaces-in-the-header", "quoted-key", "inline-table"],
)
def test_run_check_reports_in_a_repo_that_spells_its_table_another_way(tmp_path, table):
    (tmp_path / "pyproject.toml").write_text(table)
    install_check_comments(tmp_path)
    edit = edit_that_leaves_a_banner(tmp_path)

    result = run_check(tmp_path, "check-comments", "--claude-hook", stdin=edit)

    assert (result.returncode, "DOC-4 section banner" in result.stderr) == (2, True)


def test_run_check_reports_for_a_member_that_opts_in_below_a_root_that_does_not(
    tmp_path,
):
    member = tmp_path / "packages" / "member"
    member.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "root"\n')
    (member / "pyproject.toml").write_text("[tool.conventions]\n")
    install_check_comments(tmp_path)
    edit = edit_that_leaves_a_banner(member)

    result = run_check(tmp_path, "check-comments", "--claude-hook", stdin=edit)

    assert (result.returncode, "DOC-4 section banner" in result.stderr) == (2, True)


def test_run_check_says_nothing_in_a_repo_that_has_the_checks_but_no_table(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    install_check_comments(tmp_path)
    edit = edit_that_leaves_a_banner(tmp_path)

    result = run_check(tmp_path, "check-comments", "--claude-hook", stdin=edit)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize(
    "script",
    [
        "#!/moved/project/.venv/bin/python\nimport sys\n",
        "#!/bin/sh\n'''exec' '/moved/project/.venv/bin/python' \"$0\" \"$@\"\n' '''\n",
        "#!/\nimport sys\n",
    ],
    ids=["interpreter-is-gone", "uv-wrapper-of-a-long-path", "interpreter-cannot-run"],
)
def test_run_check_says_how_to_repair_a_command_that_cannot_start(opted_in, script):
    install(opted_in, script)

    result = run_check(opted_in, "check-comments", "--claude-hook", stdin="{}")

    assert (result.returncode, result.stdout, result.stderr) == (
        1,
        "",
        "conventions: .venv/bin/check-comments cannot start; recreate the virtualenv: "
        "rm -rf .venv && uv sync\n",
    )


def test_run_check_is_executable_posix_sh():
    assert os.access(RUN_CHECK, os.X_OK)
    assert RUN_CHECK.read_text().startswith("#!/bin/sh\n")


def test_git_checks_run_check_out_with_lf_line_endings_whatever_autocrlf_says():
    attributes = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", str(RUN_CHECK.relative_to(REPO))],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )

    assert [line.rpartition(": ")[2] for line in attributes.stdout.splitlines()] == [
        "set",
        "lf",
    ]


def test_plugin_has_no_top_level_bin_that_claude_ai_would_refuse_to_install():
    assert not (PLUGIN / "bin").exists()
