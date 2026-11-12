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
`# type:`, `# pylint:`, `# SPDX-`, ...), `# %%` cell markers and the text of a jupytext
markdown cell, `#:` attribute comments and PEP 723 blocks, and so is any comment on a
line that also carries `# noqa`. A justified exception is a comment naming the rule
with its reason, on the flagged line or alone above the flagged statement or comment:
`# conventions: DOC-5 - the unit of the column.`
A file that Python cannot decode or parse gets no findings; ruff reports a syntax error.
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
from conventions_hooks.findings import (
    UNREADABLE,
    Finding,
    check_edit,
    check_paths,
    merged,
)

DIRECTIVES = (
    "type:",
    "pyright:",
    "fmt:",
    "isort:",
    "ruff:",
    "mypy:",
    "conventions:",
    "%%",
    "In[",
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
    "SPDX-",
)
# Directives that are words count only as whole words: `# regions without ...` is prose.
WORD_DIRECTIVE = re.compile(r"(pragma|nosec|region|endregion)\b")
# Jupytext's cell markers; the text of a markdown cell follows its marker as comments.
CELL = re.compile(r"#\s*%%")
MARKDOWN_CELL = re.compile(r"#\s*%%.*\[(markdown|md)\]")
# Tokens that are no code: a markdown cell runs on past them.
LAYOUT = frozenset({tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT})
# A Markdown heading, or a run of rule characters where the comment starts or ends.
BANNER = re.compile(r"^(#([ #]|$)|[-=*~_+#]{3,})|[-=*~_+#]{3,}$")
PEP_723_OPENING = re.compile(r"# /// [A-Za-z0-9-]+")
PEP_723_CLOSING = "# ///"
CLOSERS = ")]}\"'`"
# Base-form verbs that open an order, not a noun phrase, whatever follows them.
_ORDER_VERBS = """
add apply bind collect convert create define emit ensure fetch generate get keep make
manage provide read register remove render represent resolve save select send serve
validate wrap write
"""
# Verbs that are common nouns too: one opens an order only where it stands alone, or
# before a determiner or a `name` (`Run the job.`, not `Run directory.`). Other such
# words (map, set, log, check, package, space) are in neither list: they would raise
# false alarms.
_NOUN_VERBS = """
build call compute download forward handle load merge parse return run start stop track
update upload use
"""
NOUN_ORDERS = frozenset(_NOUN_VERBS.split())
ORDERS = frozenset(_ORDER_VERBS.split()) | NOUN_ORDERS
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
    reasons = waivers.continuations(source)
    judged = [token for token in comments if token.start[0] not in reasons]
    findings = [
        finding for block in _blocks(judged) for finding in _check_block(block, path)
    ]
    findings += _class_docstrings(tree, path)
    waived = waivers.waived(source, tree)
    kept = [f for f in findings if f.rule not in waived.get(f.line, ())]
    return sorted(merged(kept), key=lambda f: (f.line, f.rule))


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
        return []  # Python cannot read it as text.
    return check_source(source, path=str(path))


def claude_hook(payload: str) -> int:
    """Check the Python file a Claude Code tool call wrote; exit code 2 reports back."""
    return check_edit(payload, check_file=check_file)


def _comments(source: str) -> list[tokenize.TokenInfo]:
    """Return the comment tokens of a source, but the text of jupytext markdown cells.

    A markdown cell runs from its `# %% [markdown]` marker at the margin to the next
    line of code or the next `# %%` marker, blank lines included.
    """
    comments: list[tokenize.TokenInfo] = []
    markdown = False
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            markdown = markdown and token.type in LAYOUT
        elif token.start[1] == 0 and CELL.match(token.string):
            markdown = bool(MARKDOWN_CELL.match(token.string))
            comments.append(token)
        elif not markdown:
            comments.append(token)
    return comments


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

    A block is comment lines at the margin, one after another: an opening line starts
    none when another kind of line, or the end of the file, comes before a closing one.
    """
    rows: set[int] = set()
    block: list[int] = []
    for token in comments:
        line = token.line.rstrip("\r\n")
        if block and token.start != (block[-1] + 1, 0):
            block = []
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
    directive = text.startswith(DIRECTIVES) or WORD_DIRECTIVE.match(text)
    return shebang or encoding or noqa or attribute or bool(directive)


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

    A verb that is a noun too (`Run directory of one experiment.`) is an order where
    it stands alone, or where a determiner or a `name` follows it; another verb is one
    whatever follows. A word in capitals (`GET request ...`) is a name.
    """
    first = _bare(words[0])
    if len(first) > 1 and first.isupper():
        return False
    if len(words) == 1:
        return _bare(words[0]).lower() in ORDERS
    verb = words[0].lower()
    follower = _bare(words[1]).lower() in DETERMINERS or words[1].startswith("`")
    return verb in ORDERS and (follower or verb not in NOUN_ORDERS)


def _bare(word: str) -> str:
    return word.rstrip(".,;:!?")
