"""`check-comments`: the comment and docstring rules a tool can check (GUIDE DOC).

Usage:

    check-comments src/pkg/module.py tests/test_module.py

    check-comments --claude-hook    # Claude Code PostToolUse hook: reads its JSON

In hook mode the edited file's findings go to stderr with exit code 2, which Claude
Code hands back to Claude; a repo without a `[tool.conventions]` table is skipped.
Rules listed in that table's `ignore` are skipped in both modes.

Comments read as sentences (a capital letter or a `name` first, end punctuation last,
DOC-5), section banners are not allowed (DOC-4), and a class docstring is a noun phrase,
not an order (DOC-2). Comments that a tool reads are skipped: directives (`# noqa`,
`# type:`, `# pylint:`, ...), `# %%` cell markers, `#:` attribute comments and PEP 723
blocks, and so is any comment on a line that also carries `# noqa`. A justified
exception is a comment naming the rule with its reason, on the flagged line or alone
on the line above it: `# conventions: DOC-5 - the unit of the column.`
A file that Python cannot read or parse is skipped: ruff reports it.
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterator, Sequence
from pathlib import Path

from attrs import frozen

from conventions_hooks import waivers
from conventions_hooks.findings import UNREADABLE, Finding, check_edit, check_paths

DIRECTIVES = (
    "type:",
    "pyright:",
    "pragma",
    "fmt:",
    "isort:",
    "ruff:",
    "mypy:",
    "conventions:",
    "%%",
    "In[",
    "nosec",
    "pylint:",
    "flake8:",
    "ty:",
    "pyre-",
    "pytype:",
    "pyrefly:",
    "basedpyright:",
    "yapf:",
    "codespell:",
    "cspell:",
    "region",
    "endregion",
    "SPDX-License-Identifier:",
)
# A Markdown heading, or a run of rule characters where the comment starts or ends.
BANNER = re.compile(r"^(#([ #]|$)|[-=*~_+#]{3,})|[-=*~_+#]{3,}$")
PEP_723_OPENING = re.compile(r"# /// [A-Za-z0-9-]+")
PEP_723_CLOSING = "# ///"
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
# After one of them an order is the only reading: `Run the job.`, not `Run directory.`
_DETERMINERS = "a an the this that these those each every all any its their one some no"
DETERMINERS = frozenset(_DETERMINERS.split())


@frozen
class Block:
    """Consecutive comment lines read as one text; `inline` when it follows code."""

    line: int
    lines: tuple[str, ...]
    inline: bool


def check_source(source: str, *, path: str = "<string>") -> list[Finding]:
    """Return the comment and docstring findings for one Python source."""
    try:
        tree = ast.parse(source)
        comments = _comments(source)
    except UNREADABLE:
        return []  # Ruff reports the syntax error itself.
    findings = [
        finding for block in _blocks(comments) for finding in _check_block(block, path)
    ]
    findings += _class_docstrings(tree, path)
    waived = waivers.waived(source)
    kept = [f for f in findings if f.rule not in waived.get(f.line, ())]
    return sorted(kept, key=lambda f: (f.line, f.rule))


def main(argv: Sequence[str] | None = None) -> int:
    """Check the files named on the command line, or the file a Claude edit wrote."""
    args = sys.argv[1:] if argv is None else argv
    return check_paths(args, check_file=check_file, usage=__doc__ or "")


def check_file(path: Path) -> list[Finding]:
    """Return the findings for one Python file."""
    try:
        with tokenize.open(path) as file:
            source = file.read()
    except UNREADABLE:
        return []  # Ruff reports a file that cannot be read as text.
    return check_source(source, path=str(path))


def claude_hook(payload: str) -> int:
    """Check the Python file a Claude Code tool call wrote; exit code 2 reports back."""
    return check_edit(payload, check_file=check_file)


def _comments(source: str) -> list[tokenize.TokenInfo]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [token for token in tokens if token.type == tokenize.COMMENT]


def _blocks(comments: Sequence[tokenize.TokenInfo]) -> Iterator[Block]:
    metadata = _metadata_rows(comments)
    current: list[str] = []
    start = column = previous = 0
    for token in comments:
        row, col = token.start
        if row in metadata or _skipped(token):
            continue
        text = token.string.removeprefix("#").strip()
        inline = bool(token.line[:col].strip())
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


def _metadata_rows(comments: Sequence[tokenize.TokenInfo]) -> set[int]:
    """Return the rows of PEP 723 blocks: `# /// script` to the next `# ///`.

    An opening line that no closing line follows starts no block.
    """
    rows: set[int] = set()
    block: list[int] = []
    for token in comments:
        line = token.line.rstrip("\r\n")
        if block:
            block.append(token.start[0])
            if line == PEP_723_CLOSING:
                rows.update(block)
                block = []
        elif PEP_723_OPENING.fullmatch(line):
            block = [token.start[0]]
    return rows


def _skipped(token: tokenize.TokenInfo) -> bool:
    """Return whether a tool reads the comment, so that it need not be a sentence."""
    row = token.start[0]
    text = token.string.removeprefix("#").strip()
    shebang = row == 1 and text.startswith("!")
    encoding = row <= 2 and "coding" in text
    # Linters read `noqa` in any case, also after other text on its line.
    noqa = text.lower().startswith("noqa") or "# noqa" in token.line.lower()
    attribute = token.string.startswith("#:")
    return shebang or encoding or noqa or attribute or text.startswith(DIRECTIVES)


def _check_block(block: Block, path: str) -> Iterator[Finding]:
    paragraphs = [line for line in block.lines if line]
    if not paragraphs:
        return
    banners = [
        i
        for i, text in enumerate(block.lines)
        if text and not block.inline and BANNER.search(text)
    ]
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
        or any(c in word for c in "_./-=()#")  # Code, a path or `#rrggbb`.
    )


def _ends_like_a_sentence(text: str) -> bool:
    end = text.rstrip(CLOSERS)
    return end.endswith((".", "?", "!", ":")) or _url_only(text.rsplit(maxsplit=1)[-1])


def _url_only(text: str) -> bool:
    return text.startswith(("http://", "https://")) and " " not in text


def _class_docstrings(tree: ast.Module, path: str) -> Iterator[Finding]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        words = (ast.get_docstring(node) or "").split()
        if words and _order(words):
            yield Finding(
                path,
                node.lineno,
                "DOC-2",
                f"class docstring opens with an order ({_bare(words[0])!r}); "
                "describe what an instance is",
            )


def _order(words: list[str]) -> bool:
    """Return whether a docstring's first words can only be read as an order.

    Many of the verbs are nouns too (`Run directory of one experiment.`), so the verb
    stands alone, or a determiner or a `name` follows it.
    """
    if len(words) == 1:
        return _bare(words[0]).lower() in ORDERS
    follower = _bare(words[1]).lower() in DETERMINERS or words[1].startswith("`")
    return words[0].lower() in ORDERS and follower


def _bare(word: str) -> str:
    return word.rstrip(".,;:!?")
