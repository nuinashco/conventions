"""The other modules of a file's package, for the checks that look past one file."""

from __future__ import annotations

import ast
import functools
import os
import tokenize
from collections.abc import Iterator
from pathlib import Path, PurePath

from conventions_hooks import switches, waivers
from conventions_hooks.findings import UNREADABLE
from conventions_hooks.settings import project_root


def top_package(path: Path) -> Path | None:
    """Return the outermost package directory that holds `path`, if any."""
    top = None
    folder = path.resolve().parent
    while (folder / "__init__.py").is_file():
        top = folder
        folder = folder.parent
    return top


def is_test(path: PurePath) -> bool:
    """Return whether `path`, from its project's root, names test code.

    That is a file under a `tests` folder, or a pytest file (`test_*.py`, `conftest.py`)
    outside `src/`: under `src/` a file is package code whatever its name.
    """
    pytest_file = path.name.startswith("test_") or path.name == "conftest.py"
    return "tests" in path.parts or (pytest_file and "src" not in path.parts)


def modules(top: Path) -> Iterator[Path]:
    """Yield the modules of the package at `top`, without its tests.

    A file is a test by its path from its project's root, as `is_test` reads it, and
    a `tests` folder is not entered. Outside a project a file is judged by its name
    alone. Only folders with an `__init__.py` are entered, so a virtualenv or a data
    folder that sits inside the package is not read.
    """
    try:
        entries = sorted(top.iterdir())
    except OSError:
        return
    root = project_root(top)
    inside = top.absolute().relative_to(root) if root else PurePath()
    for entry in entries:
        if entry.is_dir():
            if entry.name != "tests" and (entry / "__init__.py").is_file():
                yield from modules(entry)
        elif entry.suffix == ".py" and not is_test(inside / entry.name):
            yield entry


def switches_elsewhere(path: Path) -> list[switches.Elsewhere]:
    """Return the switches in the other modules of `path`'s top package.

    A switch waived with a `# conventions: ARC-9` comment is left out: its module
    accounts for it, so the other modules are not reported against it.
    """
    top = top_package(path)
    if top is None:
        return []
    here = path.resolve()
    return [
        switches.Elsewhere(_beside(path, module), switch)
        for module in modules(top)
        if module != here
        for switch in _switches(module)
    ]


def _beside(path: Path, module: Path) -> str:
    """Return `module` written the way `path` is, relative or not."""
    return os.path.normpath(
        path.parent / os.path.relpath(module, path.resolve().parent)
    )


def _switches(module: Path) -> tuple[switches.Switch, ...]:
    try:
        stat = module.stat()
    except OSError:  # A broken link, or a file removed since the folder was listed.
        return ()
    return _parsed(module, stat.st_mtime_ns, stat.st_size)


@functools.cache
def _parsed(module: Path, mtime_ns: int, size: int) -> tuple[switches.Switch, ...]:
    """Parse a module once per version: one run checks many files of one package.

    `mtime_ns` and `size` only key the cache. A module that Python cannot read or
    parse has no switches here; ruff reports a syntax error in it.
    """
    del mtime_ns, size
    try:
        with tokenize.open(module) as file:
            source = file.read()
        tree = ast.parse(source)
    except (OSError, *UNREADABLE):
        return ()
    waived = waivers.waived(source, tree)
    found = switches.switches_of(tree)
    return tuple(s for s in found if "ARC-9" not in waived.get(s.line, ()))
