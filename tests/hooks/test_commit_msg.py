"""Commit messages are one line without articles."""

from __future__ import annotations

import pytest

from conventions_hooks.commit_msg import problems


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
        ("feat: add the hooks\n", "articles in the subject (the)"),
        ("feat: add hooks\n\nWhy it matters.\n", "more than one line"),
        ("feat: add hooks\n\nCo-Authored-By: X <x@y>\n", "more than one line"),
        ("feat: " + "x" * 70 + "\n", "characters"),
        ("\n# only comments\n", "empty message"),
    ],
    ids=["article", "body", "trailer", "too-long", "empty"],
)
def test_broken_messages_name_the_problem(message, problem):
    [found] = problems(message)

    assert problem in found
