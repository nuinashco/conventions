"""Findings of the per-file checks, and the two ways a check reports them."""

from __future__ import annotations

import json
import sys
import tokenize
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from attrs import frozen

from conventions_hooks.settings import Settings, SettingsError

# What Python raises for a file it cannot read or parse; the checks skip such a file.
# Besides a syntax error: bytes outside the declared encoding or a lone surrogate
# (`ValueError`), a coding cookie that names no text encoding (`LookupError`), and
# nesting too deep for the compiler (`RecursionError`) or the parser (`MemoryError`).
# Catch it around the read and the parse alone: a bug in a check raises the same.
UNREADABLE = (
    SyntaxError,
    tokenize.TokenError,
    ValueError,
    LookupError,
    RecursionError,
    MemoryError,
)


@frozen
class Finding:
    """One broken rule at one place in a file."""

    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


type CheckFile = Callable[[Path], list[Finding]]


def merged(findings: Iterable[Finding]) -> list[Finding]:
    """Return one finding per path, line and rule, its messages joined by `; `.

    Two findings that share all three are one defect: a message that is capitalised
    and ends with a period, a comment that neither starts nor ends as a sentence.
    Findings and messages keep the order they were met in, a message said twice once.
    """
    messages: dict[tuple[str, int, str], list[str]] = {}
    for finding in findings:
        said = messages.setdefault((finding.path, finding.line, finding.rule), [])
        if finding.message not in said:
            said.append(finding.message)
    return [
        Finding(path, line, rule, "; ".join(said))
        for (path, line, rule), said in messages.items()
    ]


def check_paths(args: Sequence[str], *, check_file: CheckFile, usage: str) -> int:
    """Check the files in `args`, or the file a Claude edit wrote; return the exit code.

    The command line checks every file it is given, whether or not its repo opted in,
    and leaves out the rules the repo's `ignore` turns off. It skips, with a note, a
    path that is no file: `git ls-files` still names one deleted but not yet staged.
    """
    if list(args) == ["--claude-hook"]:
        return check_edit(sys.stdin.read(), check_file=check_file)
    if any(arg.startswith("-") for arg in args):
        print(usage)
        return 0 if list(args) in (["-h"], ["--help"]) else 2
    known: dict[Path, Settings] = {}
    findings: list[Finding] = []
    for arg in args:
        path = Path(arg)
        try:
            if path.parent not in known:
                known[path.parent] = Settings.of(path.parent)
        except SettingsError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        if not path.is_file():
            print(f"skipped {path}: not a file", file=sys.stderr)
            continue
        settings = known[path.parent]
        findings += [f for f in check_file(path) if settings.keeps(f.rule)]
    for finding in findings:
        print(finding)
    return 1 if findings else 0


def check_edit(payload: str, *, check_file: CheckFile) -> int:
    """Check the Python file a Claude Code tool call wrote; exit code 2 reports back.

    A repo without a `[tool.conventions]` table, or with one that does not parse, is
    left alone: the hook then exits 0 and says nothing.
    """
    data = json.loads(payload)
    raw = (data.get("tool_input") or {}).get("file_path")
    if not raw:
        return 0
    path = Path(data.get("cwd") or ".") / raw
    if path.suffix != ".py" or not path.is_file():
        return 0
    try:
        settings = Settings.of(path.parent)
    except SettingsError:
        return 0
    if not settings.enabled:
        return 0
    findings = [f for f in check_file(path) if settings.keeps(f.rule)]
    for finding in findings:
        print(finding, file=sys.stderr)
    return 2 if findings else 0
