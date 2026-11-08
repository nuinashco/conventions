"""The other modules of a file's package, for the checks that look past one file."""

from __future__ import annotations

import ast
import functools
from pathlib import Path

from conventions_hooks import switches


def top_package(path: Path) -> Path | None:
    """Return the outermost package directory that holds `path`, if any."""
    top = None
    folder = path.absolute().parent
    while (folder / "__init__.py").is_file():
        top = folder
        folder = folder.parent
    return top


def switches_elsewhere(path: Path) -> list[switches.Elsewhere]:
    """Return the switches in the other modules of `path`'s top package."""
    top = top_package(path)
    if top is None:
        return []
    here = path.absolute()
    return [
        switches.Elsewhere(str(module.relative_to(top.parent)), switch)
        for module in sorted(top.rglob("*.py"))
        if module != here
        for switch in _switches(module, module.stat().st_mtime_ns)
    ]


@functools.cache
def _switches(module: Path, mtime_ns: int) -> tuple[switches.Switch, ...]:
    """Parse a module once per version; `mtime_ns` is the cache key, not used."""
    del mtime_ns
    try:
        tree = ast.parse(module.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return ()
    return tuple(switches.switches_of(tree))
