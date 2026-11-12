"""The per-file checks run everywhere from the command line, as hooks only on opt-in."""

from __future__ import annotations

import json
from pathlib import Path

from conventions_hooks.findings import Finding, check_edit, check_paths


def two_findings(path: Path) -> list[Finding]:
    return [
        Finding(str(path), 1, "STY-4", "first"),
        Finding(str(path), 2, "DOC-5", "second"),
    ]


def edit(path: Path, *, cwd: Path | None = None) -> str:
    return json.dumps(
        {"cwd": str(cwd or path.parent), "tool_input": {"file_path": str(path)}}
    )


def test_the_command_line_checks_a_repo_that_has_not_opted_in(tmp_path, capsys):
    module = tmp_path / "module.py"
    module.write_text("x = 1\n")

    assert check_paths([str(module)], check_file=two_findings, usage="") == 1
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_the_command_line_leaves_out_ignored_rules(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text('[tool.conventions]\nignore = ["STY-4"]\n')
    module = tmp_path / "module.py"
    module.write_text("x = 1\n")

    assert check_paths([str(module)], check_file=two_findings, usage="") == 1
    assert capsys.readouterr().out == f"{module}:2: DOC-5 second\n"


def test_the_command_line_skips_a_deleted_file_and_says_so(tmp_path, capsys):
    module = tmp_path / "module.py"
    module.write_text("x = 1\n")
    deleted = tmp_path / "deleted.py"

    code = check_paths([str(deleted), str(module)], check_file=two_findings, usage="")

    assert code == 1
    output = capsys.readouterr()
    assert output.err == f"skipped {deleted}: not a file\n"
    assert len(output.out.splitlines()) == 2


def test_the_command_line_passes_when_only_deleted_files_are_left(tmp_path):
    deleted = tmp_path / "deleted.py"

    assert check_paths([str(deleted)], check_file=two_findings, usage="") == 0


def test_the_command_line_stops_on_a_broken_table(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text('[tool.conventions]\nignore = "STY-4"\n')

    assert check_paths([str(tmp_path / "m.py")], check_file=two_findings, usage="") == 2
    assert "must list rule IDs" in capsys.readouterr().err


def test_the_hook_says_nothing_where_the_repo_has_not_opted_in(tmp_path, capsys):
    module = tmp_path / "module.py"
    module.write_text("x = 1\n")

    assert check_edit(edit(module), check_file=two_findings) == 0
    assert capsys.readouterr() == ("", "")


def test_the_hook_says_nothing_where_the_table_is_broken(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text("[tool.conventions\n")
    module = tmp_path / "module.py"
    module.write_text("x = 1\n")

    assert check_edit(edit(module), check_file=two_findings) == 0
    assert capsys.readouterr() == ("", "")


def test_the_hook_hands_the_kept_findings_back_with_exit_code_2(opted_in, capsys):
    (opted_in / "pyproject.toml").write_text('[tool.conventions]\nignore = ["DOC-5"]\n')
    (opted_in / "src").mkdir()
    module = opted_in / "src" / "module.py"
    module.write_text("x = 1\n")

    assert (
        check_edit(edit(Path("src/module.py"), cwd=opted_in), check_file=two_findings)
        == 2
    )
    assert capsys.readouterr().err.splitlines() == [f"{module}:1: STY-4 first"]


def test_the_hook_skips_files_that_are_not_python(opted_in, capsys):
    notes = opted_in / "notes.md"
    notes.write_text("# notes\n")

    assert check_edit(edit(notes), check_file=two_findings) == 0
    assert capsys.readouterr() == ("", "")
