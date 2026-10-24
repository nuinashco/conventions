"""`review-comments`: ask Claude whether staged comments say only what code can't.

Usage:

    pre-commit run review-comments --hook-stage manual    # the staged diff

    review-comments --claude-hook    # Claude Code Stop hook: the working tree's diff

Sends the diff and the guide's comment rules to `claude -p` with every tool and hook
disabled, and fails when its structured verdict is FAIL. Comments, docstrings and
`Field` descriptions are judged (DOC-2 to DOC-7). As a Stop hook it skips turns that add
no comment lines and diffs it has already passed, and reports findings to Claude with
exit code 2. Set REVIEW_COMMENTS_MODEL to choose a model. Needs the Claude Code CLI,
logged in. The labelled cases in the conventions repo (`make test-judges`) measure it.
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
from typing import Any

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
Review only the comments, docstrings and pydantic `Field(description=...)` strings that
the diff on stdin adds or changes, against the rules on stdin. Flag:
- a comment that restates the code, narrates what the next lines do, or explains how
  instead of why; a constant, workaround or unit whose reason is missing;
- a docstring that repeats the signature or documents what the types already say;
- a description that repeats its field's name, value or type instead of listing the
  options or saying what the key and value can't (DOC-7).
Ignore code style and everything else. Flag only what clearly breaks a rule: when
unsure, leave it out, and an empty list of findings is a normal result. Quote each
flagged text exactly, then give the verdict: FAIL if there is any finding, else PASS.
"""
SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                    "quote": {"type": "string"},
                    "rule": {"type": "string"},
                    "problem": {"type": "string"},
                    "fix": {
                        "type": "string",
                        "description": "the rewrite, or: delete it",
                    },
                },
                "required": ["path", "line", "quote", "rule", "problem", "fix"],
            },
        },
        "verdict": {"enum": ["PASS", "FAIL"]},
    },
    "required": ["findings", "verdict"],
}

type Ask = Callable[[list[str], str], str]


class ReviewError(Exception):
    """The review could not run: no `claude` CLI, or it failed."""


def review(diff: str, rules: str, *, ask: Ask) -> tuple[bool, str]:
    """Return whether the diff's comments pass, and the findings as text."""
    if not diff.strip():
        return True, ""
    answer = ask(command(), f"# Rules\n\n{rules}\n\n# Diff\n\n{diff}")
    verdict = parse(answer)
    findings = [
        f"{f['path']}:{f['line']}: {f['rule']} {f['problem']} ({f['quote']!r}); "
        f"{f['fix']}"
        for f in verdict["findings"]
    ]
    passed = verdict["verdict"] == "PASS" and not findings
    return passed, "\n".join([verdict["verdict"], *findings])


def parse(answer: str) -> dict[str, Any]:
    """Return the structured verdict from `claude -p --output-format json`."""
    try:
        verdict = json.loads(answer).get("structured_output")
    except (json.JSONDecodeError, AttributeError) as e:
        raise ReviewError(f"claude returned no JSON: {answer[:200]}") from e
    if not isinstance(verdict, dict) or verdict.get("verdict") not in {"PASS", "FAIL"}:
        raise ReviewError(f"claude returned no verdict: {answer[:200]}")
    return verdict


def command() -> list[str]:
    """Return the `claude` command line: print mode, JSON verdict, no tools or hooks.

    Hooks stay off because the project's own Stop hook would run this review again
    inside the review, and so on until the timeout.
    """
    args = [
        "claude",
        "-p",
        "--tools",
        "",
        "--no-session-persistence",
        "--settings",
        json.dumps({"disableAllHooks": True}),
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA),
    ]
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
    """Return whether the diff adds a line that may hold a comment or description."""
    added = (line[1:] for line in diff.splitlines() if line.startswith("+"))
    markers = ("#", '"""', "'''", "description=")
    return any(
        any(m in text for m in markers) for text in added if not text.startswith("++")
    )


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=check, cwd=cwd
    )
    return result.stdout.strip()
