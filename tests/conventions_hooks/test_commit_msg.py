"""Commit messages are one line without articles."""

from __future__ import annotations

import pytest

from conventions_hooks.commit_msg import main, problems


@pytest.mark.parametrize(
    "message",
    [
        "feat: add comment hooks\n",
        "fix(proxy): retry on 429 from upstream\n\n# Please enter commit message.\n",
        "docs: explain `the_x` flag\n",
    ],
    ids=["plain", "git-template-comments", "code-span"],
)
def test_one_line_without_articles_passes(message):
    assert problems(message) == []


@pytest.mark.parametrize(
    ("message", "problem"),
    [
        ("feat: add the hooks\n", "GIT-1 articles in the subject (the)"),
        ("feat: add hooks\n\nWhy it matters.\n", "GIT-2 more than one line"),
        ("feat: add hooks\n\nCo-Authored-By: X <x@y>\n", "GIT-2 more than one line"),
        ("feat: " + "x" * 70 + "\n", "GIT-1 subject is 76 characters"),
        ("\n# only comments\n", "empty message"),
    ],
    ids=["article", "body", "trailer", "too-long", "empty"],
)
def test_broken_messages_name_the_rule_and_the_problem(message, problem):
    [found] = problems(message)

    assert str(found).startswith(problem)


def test_a_repo_that_ignores_a_rule_is_not_held_to_it(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text('[tool.conventions]\nignore = ["GIT-2"]\n')
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("feat: add the hooks\n\nWhy it matters.\n")
    monkeypatch.chdir(tmp_path)

    assert main([str(message)]) == 1
    assert capsys.readouterr().out == (
        "commit message: GIT-1 articles in the subject (the); drop them\n"
    )
