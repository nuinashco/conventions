"""`review-comments`: ask Claude whether new comments say only what code can't.

Usage:

    uv run review-comments    # the staged diff

    review-comments --claude-hook    # async Stop hook: comments new in the working tree

Sends a diff of `*.py` files and the guide's comment rules (DOC, shipped with this
package) to `claude -p`, run without built-in tools, MCP servers or hooks, and fails
with the findings of its structured verdict. Comments, docstrings and `Field`
descriptions are judged (DOC-2 to DOC-7). Needs the Claude Code CLI, logged in: each
review is one call on that account, with the CLI's default model unless
REVIEW_COMMENTS_MODEL names another. A diff over 200,000 characters is not sent, and
the command says so. The labelled cases in the conventions repo (`make test-judges`)
measure the judge.

A `[tool.conventions]` table whose `ignore` lists DOC-2 to DOC-7 turns the review off,
and findings under any rule it lists are dropped. On the command line that table is
the one at the repo root, and the staged diff is sent whole.

As a Stop hook the plugin runs it with `asyncRewake`: Claude hands back at once and is
woken, by exit code 2, only when there are findings. The hook reads the working tree's
diff against HEAD, untracked files included, and reviews a file when the nearest
`pyproject.toml` above it has the table. `.git/review-comments` holds a digest of each
line sent that is still in that diff, and the findings handed to Claude for the files
still in it. Only the hunks that add a line with `#`, a triple quote or `description=`
that is not listed there are sent, each under the header of its file, so a turn that
adds no such line sends nothing, and a finding listed there is not handed over again.
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
from importlib import resources
from pathlib import Path
from typing import Any

from conventions_hooks.settings import Settings, SettingsError

# Written by `build-rules` from rules/doc.md, so the judge applies the rules of the
# version a project pins.
RULES_FILE = "doc_rules.md"
JUDGED = frozenset({"DOC-2", "DOC-3", "DOC-4", "DOC-5", "DOC-6", "DOC-7"})
# Each review is a model call the user pays for, and a diff this long is a generated
# file more often than new comments.
MAX_DIFF_CHARS = 200_000
# What an added line holds when it may be a comment, a docstring or a description.
MARKERS = ("#", '"""', "'''", "description=")
# The format the hunks are split in, whatever the user's git settings say: plain text,
# renames paired, paths as they are named after `a/` and `b/`, three lines of context.
DIFF = (
    "-c",
    "core.quotePath=false",
    "diff",
    "--no-color",
    "--no-ext-diff",
    "--find-renames",
    "--src-prefix=a/",
    "--dst-prefix=b/",
    "--unified=3",
)
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
    """The review could not run: no `claude` CLI, too long a diff, or a failed call."""


def review(
    diff: str, rules: str, *, ask: Ask, ignore: frozenset[str] = frozenset()
) -> tuple[bool, str]:
    """Return whether the diff's comments pass, and the findings as text.

    Findings under a rule in `ignore` are dropped; with every judged rule ignored the
    judge is not asked.
    """
    if not diff.strip() or ignore >= JUDGED:
        return True, ""
    verdict = _judge(diff, rules, ask=ask)
    return _report(verdict, [f for f in verdict["findings"] if f["rule"] not in ignore])


def _judge(diff: str, rules: str, *, ask: Ask) -> dict[str, Any]:
    """Return the judge's verdict on `diff`.

    Raises:
        ReviewError: the diff is over `MAX_DIFF_CHARS`, or `claude` gave no verdict.
    """
    if len(diff) > MAX_DIFF_CHARS:
        raise ReviewError(
            f"the new comments span {len(diff)} characters of diff, over the limit of "
            f"{MAX_DIFF_CHARS}; not reviewed"
        )
    return parse(ask(command(), f"# Rules\n\n{rules}\n\n# Diff\n\n{diff}"))


def _report(verdict: dict[str, Any], kept: list[dict[str, Any]]) -> tuple[bool, str]:
    """Return whether the review passes on the `kept` findings, and them as text."""
    findings = [
        f"{f['path']}:{f['line']}: {f['rule']} {f['problem']} ({f['quote']!r}); "
        f"{f['fix']}"
        for f in kept
    ]
    # A FAIL whose every finding was dropped passes; a FAIL without findings does not.
    passed = not findings and (
        verdict["verdict"] == "PASS" or bool(verdict["findings"])
    )
    return passed, "\n".join(["PASS" if passed else "FAIL", *findings])


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

    `--tools ""` removes only the built-in tools; `--strict-mcp-config` without an
    `--mcp-config` leaves no MCP server to offer one. Hooks stay off because the
    project's own Stop hook would run this review again inside the review, and so on
    until the timeout.
    """
    args = [
        "claude",
        "-p",
        "--tools",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--settings",
        json.dumps({"disableAllHooks": True}),
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA),
    ]
    # conventions: ENV-3 - a hook has no paths.py; its one setting is this variable.
    if model := os.environ.get("REVIEW_COMMENTS_MODEL"):
        args += ["--model", model]
    return [*args, INSTRUCTIONS]


def comment_rules() -> str:
    """Return the guide's comment and docstring rules (DOC) as markdown."""
    text = resources.files(__package__).joinpath(RULES_FILE).read_text(encoding="utf-8")
    header, _, rest = text.partition("\n")
    return rest.strip() if header.startswith("<!--") else text.strip()


def ask_claude(args: list[str], stdin: str, *, timeout_s: float = 600) -> str:
    """Run `claude` with `stdin` and return its answer."""
    if shutil.which(args[0]) is None:
        raise ReviewError("the Claude Code CLI (`claude`) is not on PATH; install it")
    try:
        result = subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        raise ReviewError(f"claude gave no answer in {timeout_s:g} seconds") from e
    if result.returncode != 0:
        raise ReviewError(f"claude failed: {result.stderr.strip() or result.stdout}")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    """Review the staged diff, or the working tree's as a Claude Code Stop hook."""
    args = sys.argv[1:] if argv is None else argv
    if args and args != ["--claude-hook"]:
        print(__doc__)
        return 0 if args in (["-h"], ["--help"]) else 2
    toplevel = _git("rev-parse", "--show-toplevel", check=False)
    if args == ["--claude-hook"]:
        if not toplevel:
            return 0
        return claude_hook(sys.stdin.read(), Path(toplevel), ask=ask_claude)
    if not toplevel:
        print("error: not inside a git repository; run it from one", file=sys.stderr)
        return 2
    diff = _git("diff", "--cached", "--unified=3", "--", "*.py")
    try:
        ignore = Settings.of(Path(toplevel)).ignore
        passed, answer = review(diff, comment_rules(), ask=ask_claude, ignore=ignore)
    except (SettingsError, ReviewError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if answer:
        print(answer)
    return 0 if passed else 1


def claude_hook(payload: str, root: Path, *, ask: Ask) -> int:
    """Review what is new since the last review; exit 2 hands findings to Claude."""
    # An active stop hook means Claude is answering an earlier review: one per turn.
    if json.loads(payload).get("stop_hook_active"):
        return 0
    state = Path(_git("rev-parse", "--absolute-git-dir", cwd=root)) / "review-comments"
    seen, told = _read(state)
    diffs = working_diff(root)
    diff, lines = _new_hunks(diffs, seen)
    # Findings Claude chose to leave, for example because the user asked for that text,
    # would otherwise wake it again whenever their hunk is sent again.
    handed = {finding for finding in told if finding[0] in diffs}
    passed, answer = True, ""
    if diff:
        try:
            verdict = _judge(diff, comment_rules(), ask=ask)
        except ReviewError as e:
            print(f"review-comments: {e}", file=sys.stderr)
            return 1
        fresh = [
            f
            for f in verdict["findings"]
            if f["rule"] not in (_ignored(root, f["path"]) or ())
            and _key(f) not in handed
        ]
        passed, answer = _report(verdict, fresh)
        handed |= {_key(f) for f in fresh if f["path"] in diffs}
    if (lines, handed) != (seen, told):
        state.write_text(
            json.dumps({"lines": sorted(lines), "findings": sorted(handed)})
        )
    if passed:
        return 0
    print(answer, file=sys.stderr)
    return 2


def working_diff(root: Path) -> dict[str, str]:
    """Return the diff against HEAD of each changed or untracked Python file to review.

    A file is reviewed when the nearest `pyproject.toml` above it has a
    `[tool.conventions]` table that leaves a judged rule on.
    """
    commands: dict[str, tuple[str, ...]] = {}
    tracked = _git(
        *DIFF, "HEAD", "--name-status", "-z", "--", "*.py", cwd=root, check=False
    )
    changed = iter(tracked.split("\0"))
    for status in changed:
        if status:
            paths = [next(changed)]
            if status[0] in "RC":
                # A rename or copy names both files; diffed as a pair they show only
                # the lines that changed on the way.
                paths.append(next(changed))
            commands[paths[-1]] = ("--literal-pathspecs", *DIFF, "HEAD", "--", *paths)
    untracked = _git(
        "ls-files", "-z", "--others", "--exclude-standard", "--", "*.py", cwd=root
    )
    for path in untracked.split("\0"):
        if path:
            commands[path] = (*DIFF, "--no-index", "--", os.devnull, path)
    return {
        path: _git(*args, cwd=root, check=False)
        for path, args in commands.items()
        if (ignore := _ignored(root, path)) is not None and not ignore >= JUDGED
    }


def _new_hunks(diffs: dict[str, str], seen: set[str]) -> tuple[str, set[str]]:
    """Return the hunks with a candidate line not in `seen`, and all candidate lines.

    A hunk stays under the header of its file, so the judge still sees the path and
    the line numbers.
    """
    parts: list[str] = []
    lines: set[str] = set()
    for path, diff in diffs.items():
        header, *hunks = re.split(r"\n(?=@@ )", diff)
        new = []
        for hunk in hunks:
            digests = _candidates(path, hunk)
            lines |= digests
            if digests - seen:
                new.append(hunk)
        if new:
            parts += [header, *new]
    return "\n".join(parts), lines


def _candidates(path: str, hunk: str) -> set[str]:
    """Return a digest of each line `hunk` adds that may hold a comment.

    The digest covers the path and the line without its indentation, so a reviewed
    line stays reviewed when the code around it moves.
    """
    added = (line[1:].strip() for line in hunk.split("\n") if line.startswith("+"))
    return {
        hashlib.sha256(f"{path}\0{text}".encode()).hexdigest()
        for text in added
        if any(marker in text for marker in MARKERS)
    }


def _ignored(root: Path, path: str) -> frozenset[str] | None:
    """Return the rules the table nearest to `path` turns off; None without a table."""
    try:
        settings = Settings.of((root / path).parent)
    except SettingsError:
        return None  # The command line reports a broken table; the hook fails open.
    return settings.ignore if settings.enabled else None


def _read(state: Path) -> tuple[set[str], set[tuple[str, str, str]]]:
    """Return the digests of the lines sent and the findings handed over so far.

    Both are empty for a missing file and for one in another format, such as the
    digest of the whole diff that earlier versions wrote.
    """
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
        findings = {(str(p), str(r), str(q)) for p, r, q in data["findings"]}
        return set(data["lines"]), findings
    except (OSError, ValueError, TypeError, KeyError):
        return set(), set()


def _key(finding: dict[str, Any]) -> tuple[str, str, str]:
    return finding["path"], finding["rule"], finding["quote"]


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=check,
        cwd=cwd,
    )
    return result.stdout.rstrip("\n")
