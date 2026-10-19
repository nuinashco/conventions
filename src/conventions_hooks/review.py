"""`review-comments`: ask Claude whether staged comments say only what code can't.

Usage:

    pre-commit run review-comments --hook-stage manual    # the staged diff

    review-comments --claude-hook    # Claude Code Stop hook: the working tree's diff

Sends the diff and the guide's comment rules to `claude -p` with every tool disabled,
and fails when the answer starts with FAIL. As a Stop hook it skips turns that add no
comment lines and diffs it has already passed, and reports findings to Claude with exit
code 2. Set REVIEW_COMMENTS_MODEL to choose a model. Needs the Claude Code CLI, logged
in.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

GUIDE_FILES = ("CONVENTIONS.md", "GUIDE.md")
SECTION = re.compile(
    r"^## 8\. Comments and docstrings.*?(?=^## )", re.DOTALL | re.MULTILINE
)
FALLBACK_RULES = """\
- A comment explains what the code cannot say: an external constraint, a non-obvious
  reason, a unit, where a value came from, what None means. It never restates the code,
  never narrates the next lines, and there are no section banners.
- Docstrings are one line where possible: imperative for functions, a noun phrase for
  classes. Args/Returns/Raises sections only for what types cannot express.
- Comments are sentences: a capital letter first, a period last.
"""
INSTRUCTIONS = """\
Review only the comments and docstrings that the diff on stdin adds or changes, against
the rules on stdin. Flag a comment that restates the code, narrates what the next lines
do, or explains how instead of why; a docstring that repeats the signature or documents
what the types already say; and a constant, workaround or unit whose reason is missing.
Ignore code style and everything that is not a comment or a docstring.
Answer PASS on the first line if nothing breaks the rules. Otherwise answer FAIL on the
first line, then one line per finding: `path:line: RULE problem; rewrite as: ...` or
`...; delete it`.
"""

type Ask = Callable[[list[str], str], str]


class ReviewError(Exception):
    """The review could not run: no `claude` CLI, or it failed."""


def review(diff: str, rules: str, *, ask: Ask) -> tuple[bool, str]:
    """Return whether the diff's comments pass, and Claude's answer."""
    if not diff.strip():
        return True, ""
    answer = ask(command(), f"# Rules\n\n{rules}\n\n# Diff\n\n{diff}").strip()
    first = answer.splitlines()[0].strip().upper() if answer else ""
    return first.startswith("PASS"), answer


def command() -> list[str]:
    """Return the `claude` command line: print mode, no tools, no saved session."""
    args = ["claude", "-p", "--tools", "", "--no-session-persistence"]
    if model := os.environ.get("REVIEW_COMMENTS_MODEL"):
        args += ["--model", model]
    return [*args, INSTRUCTIONS]


def rules(root: Path) -> str:
    """Return the guide's comment section from the repo, or a built-in summary."""
    for name in GUIDE_FILES:
        path = root / name
        if path.is_file() and (
            match := SECTION.search(path.read_text(encoding="utf-8"))
        ):
            return match.group(0).strip()
    return FALLBACK_RULES


def ask_claude(args: list[str], stdin: str) -> str:
    """Run `claude` with `stdin` and return its answer."""
    if shutil.which(args[0]) is None:
        raise ReviewError("the Claude Code CLI (`claude`) is not on PATH; install it")
    result = subprocess.run(
        args, input=stdin, capture_output=True, text=True, check=False, timeout=600
    )
    if result.returncode != 0:
        raise ReviewError(f"claude failed: {result.stderr.strip() or result.stdout}")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    """Review the staged diff, or the working tree's as a Claude Code Stop hook."""
    args = sys.argv[1:] if argv is None else argv
    if args and args != ["--claude-hook"]:
        print(__doc__)
        return 0 if args in (["-h"], ["--help"]) else 2
    root = Path(_git("rev-parse", "--show-toplevel"))
    if args == ["--claude-hook"]:
        return claude_hook(sys.stdin.read(), root, ask=ask_claude)
    diff = _git("diff", "--cached", "--unified=3", "--", "*.py")
    try:
        passed, answer = review(diff, rules(root), ask=ask_claude)
    except ReviewError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if answer:
        print(answer)
    return 0 if passed else 1


def claude_hook(payload: str, root: Path, *, ask: Ask) -> int:
    """Review the comments the working tree adds; exit 2 hands findings to Claude."""
    if json.loads(payload).get("stop_hook_active"):
        return 0  # Claude is answering an earlier review; one round per turn.
    diff = working_diff(root)
    if not adds_comments(diff):
        return 0
    marker = Path(_git("rev-parse", "--absolute-git-dir", cwd=root)) / "review-comments"
    digest = hashlib.sha256(diff.encode()).hexdigest()
    if marker.is_file() and marker.read_text() == digest:
        return 0
    try:
        passed, answer = review(diff, rules(root), ask=ask)
    except ReviewError as e:
        print(f"review-comments: {e}", file=sys.stderr)
        return 1
    if passed:
        marker.write_text(digest)
        return 0
    print(answer, file=sys.stderr)
    return 2


def working_diff(root: Path) -> str:
    """Return the diff of tracked and untracked Python files against HEAD."""
    diffs = [_git("diff", "HEAD", "--unified=3", "--", "*.py", cwd=root, check=False)]
    untracked = _git(
        "ls-files", "--others", "--exclude-standard", "--", "*.py", cwd=root
    )
    diffs += [
        _git("diff", "--no-index", "--", os.devnull, path, cwd=root, check=False)
        for path in untracked.splitlines()
    ]
    return "\n".join(diff for diff in diffs if diff)


def adds_comments(diff: str) -> bool:
    """Return whether the diff adds a line that may hold a comment or docstring."""
    added = (line[1:] for line in diff.splitlines() if line.startswith("+"))
    return any(
        "#" in text or '"""' in text or "'''" in text
        for text in added
        if not text.startswith("++")
    )


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=check, cwd=cwd
    )
    return result.stdout.strip()
