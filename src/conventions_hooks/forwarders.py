"""Functions that only forward their arguments: the ARC-10 check."""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

from attrs import frozen

from conventions_hooks.findings import Finding

type Function = ast.FunctionDef | ast.AsyncFunctionDef


def check(tree: ast.Module, path: str, top: Path) -> list[Finding]:
    """Return the ARC-10 findings for the module at `path`, in the package at `top`.

    A function is reported when it takes parameters, gives none a default, and its
    body only passes them, in order and unchanged, to a function of the same package.
    A wrapper that adds a default or changes how an argument is passed hides
    something, so it is left alone. So are decorated functions (registrations and
    entry points), methods (they often satisfy a `Protocol`), a public function over
    a private one, and calls that build an object or go through one.
    """
    names = _Names.of(tree, Path(path), top)
    return [
        Finding(
            path,
            function.lineno,
            "ARC-10",
            f"`{function.name}` only forwards its arguments to `{callee}`; call "
            f"`{callee}` instead",
        )
        for function in tree.body
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        and not function.decorator_list
        and (callee := _forwarded_to(function, names))
    ]


@frozen
class _Names:
    """What a module's top-level names refer to in its own package.

    `functions` holds the names a bare call can reach: the module's own functions and
    what it imports from the package that is not a module. `modules` maps each name
    bound to a module of the package to that module's path, less `.py`.
    """

    functions: frozenset[str]
    modules: dict[str, Path]

    @classmethod
    def of(cls, tree: ast.Module, module: Path, top: Path) -> _Names:
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        modules: dict[str, Path] = {}
        for node in tree.body:
            if isinstance(node, ast.Import):
                modules |= _imported_modules(node, top)
            elif isinstance(node, ast.ImportFrom) and (
                base := _source(node, module, top)
            ):
                for alias in node.names:
                    if _is_module(base / alias.name):
                        modules[alias.asname or alias.name] = base / alias.name
                    else:
                        functions.add(alias.asname or alias.name)
        return cls(frozenset(functions), modules)

    def callee(self, func: ast.expr) -> str:
        """Return the dotted name `func` calls when it is a function of the package."""
        head, *rest = _dotted(func) or [""]
        if not rest:
            return head if head in self.functions else ""
        location = self.modules.get(head)
        if location is None:
            return ""
        for part in rest[:-1]:
            location = location / part
            if not _is_module(location):
                return ""  # An attribute of an object: the call is a method's.
        return ".".join([head, *rest])


def _imported_modules(node: ast.Import, top: Path) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for alias in node.names:
        parts = alias.name.split(".")
        if parts[0] != top.name:
            continue
        if alias.asname:
            modules[alias.asname] = top.parent.joinpath(*parts)
        else:
            modules[parts[0]] = top
    return modules


def _source(node: ast.ImportFrom, module: Path, top: Path) -> Path | None:
    """Return where a `from ... import` reads, less `.py`, when it is in the package."""
    parts = node.module.split(".") if node.module else []
    if node.level:
        parents = module.resolve().parents
        if node.level > len(parents):
            return None
        return parents[node.level - 1].joinpath(*parts)
    if parts and parts[0] == top.name:
        return top.parent.joinpath(*parts)
    return None


def _is_module(location: Path) -> bool:
    module = location.with_name(f"{location.name}.py")
    return module.is_file() or (location / "__init__.py").is_file()


def _forwarded_to(function: Function, names: _Names) -> str:
    call = _only_call(function)
    if call is None or not _same_arguments(function.args, call):
        return ""
    callee = names.callee(call.func)
    head, last = callee.partition(".")[0], callee.rpartition(".")[2]
    if not callee or callee == function.name or head in _parameters(function.args):
        return ""
    if last[:1].isupper():
        return ""  # A class: the function says which object is built.
    if last.startswith("_") and not function.name.startswith("_"):
        return ""  # A public name over a private implementation is the interface.
    return callee


def _only_call(function: Function) -> ast.Call | None:
    """Return the call a function's body consists of, past its docstring, if any."""
    body = function.body
    if body and _docstring(body[0]):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return | ast.Expr):
        return None
    call = body[0].value
    if isinstance(call, ast.Await):
        call = call.value
    return call if isinstance(call, ast.Call) else None


def _same_arguments(arguments: ast.arguments, call: ast.Call) -> bool:
    if arguments.defaults or any(arguments.kw_defaults) or not _parameters(arguments):
        return False
    positional = [a.arg for a in (*arguments.posonlyargs, *arguments.args)]
    plain = list(
        itertools.takewhile(lambda a: not isinstance(a, ast.Starred), call.args)
    )
    passed = [_name(arg) for arg in plain]
    starred = [
        _name(arg.value) if isinstance(arg, ast.Starred) else None
        for arg in call.args[len(plain) :]
    ]
    named = {k.arg: _name(k.value) for k in call.keywords if k.arg}
    double = [_name(k.value) for k in call.keywords if k.arg is None]
    by_keyword = [*positional[len(passed) :], *(a.arg for a in arguments.kwonlyargs)]
    return (
        len(passed) >= len(arguments.posonlyargs)
        and passed == positional[: len(passed)]
        and named == {name: name for name in by_keyword}
        and starred == ([arguments.vararg.arg] if arguments.vararg else [])
        and double == ([arguments.kwarg.arg] if arguments.kwarg else [])
    )


def _parameters(arguments: ast.arguments) -> set[str]:
    return {
        a.arg
        for a in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *filter(None, (arguments.vararg, arguments.kwarg)),
        )
    }


def _docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _name(node: ast.expr) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _dotted(node: ast.expr) -> list[str]:
    """Return the names of `a.b.c`, or nothing when `node` is any other expression."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return []
    return [node.id, *reversed(parts)]
