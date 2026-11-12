"""Waiver comments (`# conventions: TYP-4 - why.`) and the lines that each covers."""

from __future__ import annotations

import ast
import re

WAIVER = re.compile(r"#\s*conventions:\s*([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)")


def waived(source: str, tree: ast.Module) -> dict[int, set[str]]:
    """Return the rules waived at each line of `source`, which parses to `tree`.

    A waiver names one rule, or several with commas between them. At the end of a line
    of code it covers that line, and in a comment after other words its own line and
    the next. Alone on its line it covers the statement that starts right below it:
    every line of a simple statement, and of a compound one (`def`, `class`, `if`,
    `with`, ...) the lines from its first decorator, or from its keyword for a waiver
    below the decorators, to the last line before its body. Comment lines right below
    the waiver continue its reason, and the statement comes after them. Where no
    statement starts there (a blank line, the end of the file, the inside of a
    wrapped statement), it covers that one line.
    """
    # Python counts a new line at "\n" alone; `splitlines` also breaks at a form feed.
    lines = source.split("\n")
    ends = _ends(tree) if WAIVER.search(source) else {}
    covered: dict[int, set[str]] = {}
    for number, line in enumerate(lines, start=1):
        rules = {
            rule.strip() for ids in WAIVER.findall(line) for rule in ids.split(",")
        }
        last = number
        if WAIVER.match(line.lstrip()):
            below = _below(lines, number)
            last = ends.get(below, below)
        elif rules and _is_comment(line):
            last = number + 1
        for row in range(number, last + 1):
            covered.setdefault(row, set()).update(rules)
    return covered


def continuations(source: str) -> set[int]:
    """Return the comment lines that continue the reason of a waiver.

    They are the comment lines right below a line that holds a waiver and no more.
    """
    lines = source.split("\n")
    return {
        row
        for number, line in enumerate(lines, start=1)
        if WAIVER.match(line.lstrip())
        for row in range(number + 1, _below(lines, number))
    }


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _below(lines: list[str], number: int) -> int:
    """Return the first line below line `number` that is no comment line."""
    below = number + 1
    while below <= len(lines) and _is_comment(lines[below - 1]):
        below += 1
    return below


def _ends(tree: ast.Module) -> dict[int, int]:
    """Return the last line a waiver covers, by the line its statement starts at.

    A decorated `def` or `class` is found by its first decorator and by its keyword.
    """
    ends: dict[int, int] = {}
    # `ast.walk` meets an outer statement before the ones inside it, and the first of
    # two on one line before the second: the first statement met owns the line.
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            ends.setdefault(_first_line(node), _last_line(node))
            ends.setdefault(node.lineno, _last_line(node))
    return ends


def _first_line(node: ast.stmt) -> int:
    decorators: list[ast.expr] = getattr(node, "decorator_list", [])
    return min(n.lineno for n in (node, *decorators))


def _last_line(node: ast.stmt) -> int:
    """Return the last line of a statement, for a compound one the last before its body.

    That is the compound statement's own line when its body starts on it.
    """
    if isinstance(node, ast.Match):
        inside = node.cases[0].pattern.lineno
    elif body := getattr(node, "body", None):
        inside = _first_line(body[0])
    else:
        return node.end_lineno or node.lineno
    return max(node.lineno, inside - 1)
