"""`check-commit-msg`: one-line commit messages without articles (GUIDE GIT-1, GIT-2).

Usage:

    check-commit-msg .git/COMMIT_EDITMSG    # pre-commit passes the message file

The message is one line (GIT-2). Its subject has at most 72 characters and no articles:
`a`, `an` and `the` count where they are words of the sentence, not inside a name, a
path or backticks. A subject of the shape `type(scope)!: text` also has a lowercase
type, and its text starts in lowercase and ends without a period (GIT-1); the
`conventional-pre-commit` hook reports every other shape.

The message is cleaned first, as git cleans it: the scissors line of `git commit -v`
and everything below it are dropped, then the comment lines (`#`, or the prefix git is
configured with), the blank lines around the message and the whitespace that ends the
subject. A subject that starts with `Merge ` is git's own and is not judged. Rules
listed in `ignore` of the repo's `[tool.conventions]` table are not checked.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

from attrs import frozen

from conventions_hooks.settings import Settings, SettingsError

# An article is a word of the sentence when no part of a name, a path or a quote
# touches it: `A/B`, `a.py`, `the-thing` and `'the'` hold none.
ARTICLES = re.compile(r"""(?<![\w/.'"*-])(a|an|the|An|The)(?![\w/.'"*-])""")
CODE = re.compile(r"`[^`]*`")
CONVENTIONAL = re.compile(r"(?P<type>\w+)(\([^()]*\))?!?:\s+(?P<text>.+)")
MAX_LENGTH = 72
DEFAULT_COMMENT = "#"
# Git writes this line, after its comment prefix, above the diff of `git commit -v`.
SCISSORS = "------------------------ >8 ------------------------"


@frozen
class Problem:
    """One way a commit message breaks a rule; `rule` is empty when none applies."""

    rule: str
    text: str

    def __str__(self) -> str:
        return f"{self.rule} {self.text}" if self.rule else self.text


def problems(message: str, *, comment: str = DEFAULT_COMMENT) -> list[Problem]:
    """Return what breaks GIT-1 and GIT-2 in `message`; empty when they hold.

    The message is cleaned first, as git cleans it; `comment` is the prefix of the
    lines git drops.
    """
    lines = _cleaned(message, comment=comment)
    if not lines:
        return [Problem("", "empty message")]
    subject = lines[0]
    if subject.startswith("Merge "):
        return []  # Git wrote this subject itself, from the names of the branches.
    found = []
    if len(lines) > 1:
        found.append(Problem("GIT-2", "more than one line; drop the body and trailers"))
    return [*found, *_subject_problems(subject)]


def main(argv: Sequence[str] | None = None) -> int:
    """Check the message file pre-commit passes; exit 1 when it breaks the rule."""
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 1 or args[0].startswith("-"):
        print(__doc__)
        return 0 if args in (["-h"], ["--help"]) else 2
    try:
        settings = Settings.of(Path.cwd())
    except SettingsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    # The diff of `git commit -v` holds the bytes of the files, in any encoding.
    message = Path(args[0]).read_text(encoding="utf-8", errors="replace")
    comment = _comment_prefix()
    found = [p for p in problems(message, comment=comment) if settings.keeps(p.rule)]
    for problem in found:
        print(f"commit message: {problem}")
    return 1 if found else 0


def _cleaned(message: str, *, comment: str) -> list[str]:
    """Return the lines git keeps of a message file, the subject first."""
    lines = message.splitlines()
    scissors = f"{comment} {SCISSORS}"
    if scissors in lines:
        del lines[lines.index(scissors) :]
    kept = "\n".join(line.rstrip() for line in lines if not line.startswith(comment))
    return kept.strip("\n").splitlines()


def _subject_problems(subject: str) -> Iterator[Problem]:
    if len(subject) > MAX_LENGTH:
        yield Problem(
            "GIT-1",
            f"subject is {len(subject)} characters; the limit is {MAX_LENGTH}",
        )
    words = ARTICLES.findall(CODE.sub("", subject))
    if articles := sorted({word.lower() for word in words}):
        yield Problem(
            "GIT-1",
            f"articles in the subject ({', '.join(articles)}); drop them, or put a "
            "literal word in backticks",
        )
    shape = CONVENTIONAL.fullmatch(subject)
    if shape is None:
        return  # The `conventional-pre-commit` hook reports a subject of another shape.
    if shape["type"] != shape["type"].lower():
        yield Problem("GIT-1", f"type `{shape['type']}` is not lowercase")
    if shape["text"][0].isupper():
        yield Problem(
            "GIT-1",
            "subject starts with a capital letter; write it in lowercase, or put a "
            "name in backticks",
        )
    if shape["text"].endswith("."):
        yield Problem("GIT-1", "subject ends with a period; drop it")


def _comment_prefix() -> str:
    """Return the prefix of the lines git drops from a message in this repo."""
    try:
        # Git itself marks a line: before 2.45 it reads `core.commentChar` alone, later
        # the last of that key and `core.commentString`. With `auto` it picks a prefix
        # for each message and answers here with `#`, its first choice.
        result = subprocess.run(
            ["git", "stripspace", "--comment-lines"],
            input="x\n",
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:  # `git` is not installed.
        return DEFAULT_COMMENT
    prefix, marked, _ = result.stdout.partition(" x\n")
    if result.returncode != 0 or not (prefix and marked):
        return DEFAULT_COMMENT
    return prefix
