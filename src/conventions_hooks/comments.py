"""`check-comments`: the comment and docstring rules a tool can check (GUIDE DOC).

Usage:

    check-comments src/pkg/module.py tests/test_module.py

    check-comments --claude-hook    # Claude Code PostToolUse hook: reads its JSON

In hook mode the edited file's findings go to stderr with exit code 2, which Claude
Code hands back to Claude.

Comments read as sentences (a capital letter or a `name` first, end punctuation last,
DOC-5), section banners are not allowed (DOC-4), and a class docstring is a noun phrase,
not an order (DOC-2). Directive comments (`# noqa`, `# type:`, `# pyright:`, ...) are
skipped, and so is any comment on a line that also carries `# noqa`.
"""

from __future__ import annotations

import ast
import io
import json
import re
import sys
import tokenize
from collections.abc import Iterator, Sequence
from pathlib import Path

from attrs import frozen

DIRECTIVES = ("noqa", "type:", "pyright:", "pragma", "fmt:", "isort:", "ruff:", "mypy:")
BANNER = re.compile(r"^#|-{3,}|={3,}|\*{3,}|~{3,}|_{3,}|\+{3,}|#{3,}")
CLOSERS = ")]}\"'`"
# Base-form verbs that open an order, not a noun phrase; words that are also common
# nouns (map, set, log, check, package, space) are left out to avoid false alarms.
_ORDER_VERBS = """
add apply bind build call collect compute convert create define download emit ensure
fetch forward generate get handle keep load make manage merge parse provide read
register remove render represent resolve return run save select send serve start stop
track update upload use validate wrap write
"""
ORDERS = frozenset(_ORDER_VERBS.split())


@frozen
class Finding:
    """One broken rule at one place in a file."""

    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


@frozen
class Block:
    """Consecutive comment lines read as one text; `inline` when it follows code."""

    line: int
    lines: tuple[str, ...]
    inline: bool


def check_source(source: str, path: str = "<string>") -> list[Finding]:
    """Return the comment and docstring findings for one Python source."""
    findings = [
        finding for block in _blocks(source) for finding in _check_block(block, path)
    ]
    findings += _class_docstrings(source, path)
    return sorted(findings, key=lambda f: (f.line, f.rule))


def main(argv: Sequence[str] | None = None) -> int:
    """Check the files named on the command line, or the file a Claude edit wrote."""
    args = sys.argv[1:] if argv is None else list(argv)
    if args == ["--claude-hook"]:
        return claude_hook(sys.stdin.read())
    if any(arg.startswith("-") for arg in args):
        print(__doc__)
        return 0 if args in (["-h"], ["--help"]) else 2
    findings = [finding for path in args for finding in check_file(Path(path))]
    for finding in findings:
        print(finding)
    return 1 if findings else 0


def check_file(path: Path) -> list[Finding]:
    """Return the findings for one Python file."""
    return check_source(path.read_text(encoding="utf-8"), str(path))


def claude_hook(payload: str) -> int:
    """Check the Python file a Claude Code tool call wrote; exit code 2 reports back."""
    tool_input = json.loads(payload).get("tool_input") or {}
    path = Path(tool_input.get("file_path") or "")
    if path.suffix != ".py" or not path.is_file():
        return 0
    findings = check_file(path)
    for finding in findings:
        print(finding, file=sys.stderr)
    return 2 if findings else 0


def _blocks(source: str) -> Iterator[Block]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    lines = source.splitlines()
    current: list[str] = []
    start = column = previous = 0
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        row, col = token.start
        text = token.string.removeprefix("#").strip()
        inline = bool(lines[row - 1][:col].strip())
        if _skipped(text, lines[row - 1], row):
            continue
        if current and not inline and row == previous + 1 and col == column:
            current.append(text)
        else:
            if current:
                yield Block(start, tuple(current), inline=False)
            current, start, column = [text], row, col
            if inline:
                yield Block(row, (text,), inline=True)
                current = []
        previous = row
    if current:
        yield Block(start, tuple(current), inline=False)


def _skipped(text: str, line: str, row: int) -> bool:
    shebang = row == 1 and text.startswith("!")
    encoding = row <= 2 and "coding" in text
    return shebang or encoding or text.startswith(DIRECTIVES) or "# noqa" in line


def _check_block(block: Block, path: str) -> Iterator[Finding]:
    paragraphs = [line for line in block.lines if line]
    if not paragraphs:
        return
    banners = [i for i, text in enumerate(block.lines) if text and BANNER.search(text)]
    for offset in banners:
        yield Finding(path, block.line + offset, "DOC-4", "section banner; drop it")
    if banners:
        return  # A banner is no sentence; one finding is enough.
    first, last = paragraphs[0], paragraphs[-1]
    if _url_only(first) and len(paragraphs) == 1:
        return
    if not _starts_like_a_sentence(first):
        yield Finding(
            path, block.line, "DOC-5", "start with a capital letter or a `name`"
        )
    if not _ends_like_a_sentence(last):
        end = block.line + max(i for i, text in enumerate(block.lines) if text)
        yield Finding(path, end, "DOC-5", "end the sentence with a period")


def _starts_like_a_sentence(text: str) -> bool:
    word = text.split(maxsplit=1)[0].rstrip(".,;:!?")
    return bool(word) and (
        word[0].isupper()
        or word[0].isdigit()
        or word[0] in "`\"'(["
        or any(c.isupper() for c in word)  # A name such as cuBLAS or iOS.
        or any(c in word for c in "_./-=()")  # Code or a path.
    )


def _ends_like_a_sentence(text: str) -> bool:
    end = text.rstrip(CLOSERS)
    return end.endswith((".", "?", "!", ":")) or _url_only(text.rsplit(maxsplit=1)[-1])


def _url_only(text: str) -> bool:
    return text.startswith(("http://", "https://")) and " " not in text


def _class_docstrings(source: str, path: str) -> Iterator[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        docstring = ast.get_docstring(node) if isinstance(node, ast.ClassDef) else None
        if docstring and docstring.split()[0].lower() in ORDERS:
            yield Finding(
                path,
                node.lineno,
                "DOC-2",
                f"class docstring opens with an order ({docstring.split()[0]!r}); "
                "describe what an instance is",
            )
