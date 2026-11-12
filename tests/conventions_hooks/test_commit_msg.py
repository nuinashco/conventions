"""Commit messages are one line without articles."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from conventions_hooks.commit_msg import main, problems

VERBOSE = """\
docs: describe demo usage
# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#\tmodified:   README.md
#
# ------------------------ >8 ------------------------
# Do not modify or remove the line above.
# Everything below it will be ignored.
diff --git a/README.md b/README.md
index 1c3d2a7..8d9f3b2 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # demo
+note
"""
SUBJECT = "docs: describe demo usage"
# Within the limit alone, past it behind the `fixup! ` or `amend! ` that git adds.
LONG = "feat: add loader that reads sharded parquet files from object storage"
EDITOR = f"""\
#!/bin/sh
{{ echo '{SUBJECT}'; cat "$1"; }} > "$1.new" && mv "$1.new" "$1"
"""


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """Return a repo to run the hook in, which only its own config sets up."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def commit(repo: Path, options: Sequence[str], *, editor: str = "true") -> None:
    """Commit a change to a file, with `check-commit-msg` as the commit-msg hook."""
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.parent.mkdir(exist_ok=True)  # A git without a template folder makes none.
    command = Path(sys.executable).with_name("check-commit-msg")
    hook.write_text(f'#!/bin/sh\nexec "{command}" "$1"\n')
    hook.chmod(0o755)
    with (repo / "notes.txt").open("a") as notes:
        notes.write("note\n")
    identity = {
        f"GIT_{role}_{field}": value
        for role in ("AUTHOR", "COMMITTER")
        for field, value in (("NAME", "Tester"), ("EMAIL", "tester@example.com"))
    }
    env = {**os.environ, **identity, "GIT_EDITOR": editor}
    subprocess.run(["git", "add", "notes.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", *options],
        cwd=repo,
        env=env,
        capture_output=True,
        check=False,
    )


def subjects(repo: Path) -> str:
    log = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return log.stdout


def commit_in_an_editor(repo: Path) -> str:
    """Commit with `git commit -v` in an editor; return the subjects in the log.

    The editor writes the subject above the template that git put in the message.
    """
    editor = repo / ".git" / "editor"
    editor.write_text(EDITOR)
    editor.chmod(0o755)
    commit(repo, ["-v"], editor=str(editor))
    return subjects(repo)


@pytest.mark.parametrize(
    "message",
    [
        "feat: add comment hooks\n",
        "fix(proxy): retry on 429 from upstream\n\n# Please enter commit message.\n",
        "docs: explain `the_x` flag\n",
        "\n\nfeat: add comment hooks\n",
        "feat: " + "x" * 66 + "  \n",
        VERBOSE,
        "fix: `Settings` reads nearest table\n",
    ],
    ids=[
        "plain",
        "git-template-comments",
        "code-span",
        "leading-blank-lines",
        "72-characters-then-spaces",
        "diff-of-commit-verbose",
        "name-in-backticks-first",
    ],
)
def test_one_line_without_articles_passes(message):
    assert problems(message) == []


@pytest.mark.parametrize(
    "subject",
    [
        "test: add A/B comparison",
        "docs: describe plan A",
        "fix: move helpers out of a.py",
        "fix: rename the-thing",
        "fix: stop AN-123 crash on start",
        "fix: reject 'the' as stop word",
        'fix: reject "an" as stop word',
        "perf: speed up a* search",
    ],
    ids=[
        "slash",
        "capital-letter",
        "file-name",
        "hyphen",
        "ticket",
        "single-quotes",
        "double-quotes",
        "star",
    ],
)
def test_article_letters_in_a_name_or_a_path_are_not_articles(subject):
    assert problems(f"{subject}\n") == []


@pytest.mark.parametrize(
    "message",
    [
        "Merge branch 'fix/the-thing'\n",
        "Merge branch 'fix/the-thing' into a-b\n\n* fix/the-thing:\n  docs: add t\n",
        "Merge tag 'v1.0' of the origin\n",
        f"fixup! {LONG}\n",
        f"amend! {LONG}\n\n{LONG}\n",
        "squash! feat: add loader\n\nRead the shards in order.\n",
        f"fixup! fixup! {LONG}\n",
    ],
    ids=[
        "merge",
        "with-log-of-merge",
        "tag",
        "fixup",
        "amend",
        "squash",
        "fixup-twice",
    ],
)
def test_subject_that_git_writes_is_not_judged(message):
    assert problems(message) == []


def test_commits_that_git_writes_for_autosquash_pass_the_hook(git_repo):
    for options in (["-m", LONG], ["--fixup", "HEAD"], ["--fixup=amend:HEAD~1"]):
        commit(git_repo, options)

    assert subjects(git_repo) == f"amend! {LONG}\nfixup! {LONG}\n{LONG}\n"


def test_subject_of_another_shape_is_left_to_conventional_pre_commit():
    assert problems("Add loader.\n") == []


@pytest.mark.parametrize(
    ("message", "problem"),
    [
        (
            "feat: add the hooks\n",
            "GIT-1 articles in the subject (the); drop them, or put a literal word in "
            "backticks",
        ),
        ("The loader fails\n", "GIT-1 articles in the subject (the)"),
        ("An apple falls\n", "GIT-1 articles in the subject (an)"),
        ("feat: add hooks\n\nWhy it matters.\n", "GIT-2 more than one line"),
        ("feat: add hooks\n\nCo-Authored-By: X <x@y>\n", "GIT-2 more than one line"),
        (
            "feat: " + "x" * 67 + "\n",
            "GIT-1 subject is 73 characters; the limit is 72",
        ),
        ("\n# only comments\n", "empty message"),
        ("Feat: add loader\n", "GIT-1 type `Feat` is not lowercase"),
        (
            "feat: Add loader\n",
            "GIT-1 subject starts with a capital letter; write it in lowercase, or put "
            "a name in backticks",
        ),
        ("feat: add loader.\n", "GIT-1 subject ends with a period; drop it"),
    ],
    ids=[
        "article",
        "capitalised-article",
        "capitalised-an",
        "body",
        "trailer",
        "too-long",
        "empty",
        "uppercase-type",
        "capital-letter",
        "period",
    ],
)
def test_broken_messages_name_the_rule_and_the_problem(message, problem):
    [found] = problems(message)

    assert str(found).startswith(problem)


def test_every_part_of_git_1_that_a_subject_breaks_is_reported():
    found = problems("Fix(proxy)!: Retry on a 429 from upstream.\n")

    assert [str(problem) for problem in found] == [
        "GIT-1 articles in the subject (a); drop them, or put a literal word in "
        "backticks",
        "GIT-1 type `Fix` is not lowercase",
        "GIT-1 subject starts with a capital letter; write it in lowercase, or put a "
        "name in backticks",
        "GIT-1 subject ends with a period; drop it",
    ]


def test_comment_prefix_of_the_repo_replaces_the_hash():
    message = (
        "docs: describe demo usage\n"
        "; Please enter the commit message for your changes.\n"
        "; ------------------------ >8 ------------------------\n"
        "diff --git a/README.md b/README.md\n"
    )

    assert (
        problems(message, comment=";"),
        [problem.rule for problem in problems(message)],
    ) == ([], ["GIT-2"])


@pytest.mark.parametrize(
    ("config", "prefix"),
    [
        ([], "#"),
        (["core.commentChar", ";"], ";"),
        (["core.commentChar", "auto"], "#"),
    ],
    ids=["not-set", "comment-char", "auto"],
)
def test_comment_lines_start_with_the_prefix_git_is_configured_with(
    git_repo, capsys, config, prefix
):
    if config:
        subprocess.run(["git", "config", *config], cwd=git_repo, check=True)
    message = git_repo / "COMMIT_EDITMSG"
    message.write_text(
        f"docs: describe demo usage\n{prefix} Please enter the commit message.\n"
    )

    assert (main([str(message)]), capsys.readouterr().out) == (0, "")


@pytest.mark.parametrize(
    "keys",
    [
        [],
        [("core.commentChar", "#"), ("core.commentString", "//")],
        [("core.commentString", "//"), ("core.commentChar", ";")],
    ],
    ids=["not-set", "char-then-string", "string-then-char"],
)
def test_commit_written_in_an_editor_passes_whichever_comment_keys_git_reads(
    git_repo, keys
):
    for key, value in keys:
        subprocess.run(["git", "config", key, value], cwd=git_repo, check=True)

    assert commit_in_an_editor(git_repo) == f"{SUBJECT}\n"


def test_diff_that_is_not_utf_8_below_the_scissors_line_is_dropped_like_any_other(
    git_repo, capsys
):
    message = git_repo / "COMMIT_EDITMSG"
    message.write_bytes(VERBOSE.encode() + b"+caf\xe9\n")

    assert (main([str(message)]), capsys.readouterr().out) == (0, "")


@pytest.mark.parametrize(
    ("answer", "prefix"),
    [('echo "// $line"', "//"), ('echo "; $line"; exit 1', "#")],
    ids=["several-characters-of-a-newer-git", "git-fails"],
)
def test_comment_prefix_is_the_one_that_git_marks_a_line_with(
    tmp_path, monkeypatch, capsys, answer, prefix
):
    git = tmp_path / "git"
    git.write_text(f"#!/bin/sh\nread -r line\n{answer}\n")
    git.chmod(0o755)
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(f"docs: describe demo usage\n{prefix} Please enter it.\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert (main([str(message)]), capsys.readouterr().out) == (0, "")


def test_machine_without_git_drops_the_lines_that_start_with_a_hash(
    tmp_path, monkeypatch, capsys
):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("docs: describe demo usage\n# Please enter the message.\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert (main([str(message)]), capsys.readouterr().out) == (0, "")


def test_a_repo_that_ignores_a_rule_is_not_held_to_it(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text('[tool.conventions]\nignore = ["GIT-2"]\n')
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("feat: add the hooks\n\nWhy it matters.\n")
    monkeypatch.chdir(tmp_path)

    assert main([str(message)]) == 1
    assert capsys.readouterr().out == (
        "commit message: GIT-1 articles in the subject (the); drop them, or put a "
        "literal word in backticks\n"
    )
