"""`check-commit-msg`: one-line commit messages without articles (GUIDE GIT-1, GIT-2).

Usage:

    check-commit-msg .git/COMMIT_EDITMSG    # pre-commit passes the message file

Lines starting with `#` (git's template) and trailing blank lines are ignored.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path

ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
CODE = re.compile(r"`[^`]*`")
MAX_LENGTH = 72


def problems(message: str) -> list[str]:
    """Return what breaks the one-line, no-article rule; empty when it holds."""
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ["empty message"]
    found = []
    if len(lines) > 1:
        found.append("more than one line; drop the body and trailers")
    subject = lines[0]
    if len(subject) > MAX_LENGTH:
        found.append(
            f"subject is {len(subject)} characters; keep it under {MAX_LENGTH}"
        )
    words = ARTICLES.findall(CODE.sub("", subject))
    if articles := sorted({word.lower() for word in words}):
        found.append(f"articles in the subject ({', '.join(articles)}); drop them")
    return found


def main(argv: Sequence[str] | None = None) -> int:
    """Check the message file pre-commit passes; exit 1 when it breaks the rule."""
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 1 or args[0].startswith("-"):
        print(__doc__)
        return 0 if args in (["-h"], ["--help"]) else 2
    found = problems(Path(args[0]).read_text(encoding="utf-8"))
    for problem in found:
        print(f"commit message: {problem}")
    return 1 if found else 0
