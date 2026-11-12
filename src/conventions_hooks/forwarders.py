"""Functions that only forward their arguments: the ARC-10 check."""

from __future__ import annotations

import ast

from conventions_hooks.findings import Finding


def check(tree: ast.Module, path: str, package: str) -> list[Finding]:
    """Return the ARC-10 findings for one module of `package`.

    A function is reported when its body only calls a function of the same package
    with its own parameters, in order and unchanged. A decorated function is a
    registration or an entry point, so it is left alone, and so are methods, which
    often satisfy a `Protocol`, and public functions over a private one.
    """
    ours = _package_names(tree, package)
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
        and (callee := _forwarded_to(function, ours))
    ]


def _package_names(tree: ast.Module, package: str) -> set[str]:
    """Return the names bound in a module to functions or modules of `package`."""
    names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (
            node.level or (node.module or "").split(".")[0] == package
        ):
            names |= {alias.asname or alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            names |= {
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
                if alias.name.split(".")[0] == package
            }
    return names


def _forwarded_to(
    function: ast.FunctionDef | ast.AsyncFunctionDef, ours: set[str]
) -> str:
    body = function.body
    if body and _docstring(body[0]):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return | ast.Expr):
        return ""
    call = body[0].value
    if isinstance(call, ast.Await):
        call = call.value
    if not isinstance(call, ast.Call) or not _same_arguments(function.args, call):
        return ""
    callee = _dotted(call.func)
    if callee.split(".")[0] not in ours or callee == function.name:
        return ""
    if callee.split(".")[-1].startswith("_") and not function.name.startswith("_"):
        return ""  # A public name over a private implementation is the interface.
    return callee


def _same_arguments(arguments: ast.arguments, call: ast.Call) -> bool:
    positional = [a.arg for a in (*arguments.posonlyargs, *arguments.args)]
    keywords = [a.arg for a in arguments.kwonlyargs]
    passed = [_name(arg) for arg in call.args if not isinstance(arg, ast.Starred)]
    starred = [_name(arg.value) for arg in call.args if isinstance(arg, ast.Starred)]
    named = {k.arg: _name(k.value) for k in call.keywords if k.arg}
    double = [_name(k.value) for k in call.keywords if k.arg is None]
    return (
        passed == positional[: len(passed)]
        and all(named.get(p) == p for p in positional[len(passed) :])
        and set(named) == set(positional[len(passed) :]) | set(keywords)
        and all(named[k] == k for k in keywords)
        and starred == ([arguments.vararg.arg] if arguments.vararg else [])
        and double == ([arguments.kwarg.arg] if arguments.kwarg else [])
    )


def _docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _name(node: ast.expr) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _dotted(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    return ".".join([node.id, *reversed(parts)])
