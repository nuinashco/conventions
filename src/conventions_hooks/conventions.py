"""`check-conventions`: the code rules of the guide that an AST can decide.

Usage:

    check-conventions src/pkg/module.py tests/test_module.py

    check-conventions --claude-hook    # Claude Code PostToolUse hook: reads its JSON

In hook mode the edited file's findings go to stderr with exit code 2, which Claude
Code hands back to Claude; a repo without a `[tool.conventions]` table is skipped.
Rules listed in that table's `ignore` are skipped in both modes.

Each check stands in for a rule whose *Check* used to be review alone: no grab-bag
modules (LAY-2), heavy imports kept lazy (ARC-8), no branching on `kind` (ARC-4), a
variant name switched on in one place of the package (ARC-9), no functions that only
forward (ARC-10), registration outermost (FAM-2), attrs instead of `__init__` and
dataclasses (TYP-4), options keyword-only (STY-4), lowercase error messages (ERR-3),
snake_case log events (LOG-2) and test functions rather than classes (TST-1). In a
project with a `src/<pkg>/paths.py`, repo paths and environment go through it (ENV-1,
ENV-3). A justified exception is a comment naming the rule with its reason, on the
flagged line or alone on the line above it:
`# conventions: TYP-4 - the base class from httpx needs __init__.`
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePath

from attrs import frozen

from conventions_hooks import forwarders, package, switches
from conventions_hooks.findings import Finding, check_edit, check_paths
from conventions_hooks.settings import project_root

GRAB_BAGS = frozenset({"utils", "util", "common", "core", "helpers", "misc"})
HEAVY = frozenset(
    {"torch", "vllm", "litellm", "wandb", "boto3", "transformers", "tensorflow", "jax"}
)
HEAVY_PREFIXES = ("google.cloud",)
LOG_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "msg"}
)
LOGGERS = frozenset({"log", "logger"})
EVENT = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")
EXCEPTION_SUFFIXES = ("Error", "Exception", "Warning")
PLAIN_BASES = frozenset({"Protocol", "ABC", "Enum", "StrEnum", "IntEnum", "NamedTuple"})
ALLOW = re.compile(r"#\s*conventions:\s*([A-Z]+-\d+)")


def main(argv: Sequence[str] | None = None) -> int:
    """Check the files named on the command line, or the file a Claude edit wrote."""
    args = sys.argv[1:] if argv is None else argv
    return check_paths(args, check_file=check_file, usage=__doc__ or "")


def claude_hook(payload: str) -> int:
    """Check the Python file a Claude Code tool call wrote; exit code 2 reports back."""
    return check_edit(payload, check_file=check_file)


def check_file(path: Path) -> list[Finding]:
    """Return the findings for one Python file, judged by its place in its project."""
    root = project_root(path.parent)
    inside = path.absolute().relative_to(root) if root else path
    top = package.top_package(path)
    return check_source(
        path.read_text(encoding="utf-8"),
        path=str(path),
        relative=str(inside),
        paths_module=bool(root and any(root.glob("src/*/paths.py"))),
        package_name=top.name if top else "",
        elsewhere=package.switches_elsewhere(path),
    )


def check_source(
    source: str,
    *,
    path: str = "<string>",
    relative: str | None = None,
    paths_module: bool = True,
    package_name: str = "",
    elsewhere: Sequence[switches.Elsewhere] = (),
) -> list[Finding]:
    """Return the convention findings for one Python source, reported at `path`.

    The file's path from its project's root, `relative` (`path` when not given),
    decides which rules apply: a folder above the project says nothing about it.
    ENV-1 and ENV-3 apply only when `paths_module` says the project has a
    `src/<pkg>/paths.py`. `package_name` and `elsewhere`, the switches in the other
    modules of the package, let ARC-9 and ARC-10 look past the file.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # Ruff reports the syntax error itself.
    where = _Where.of(relative or path, env=paths_module)
    findings = list(_module_name(where, relative or path, report=path))
    if where.package:
        findings += _heavy_imports(tree, path)
    for node in ast.walk(tree):
        findings += _check_node(node, where, path)
    if not where.test:
        findings += switches.check(tree, path, elsewhere=elsewhere)
    if where.package and package_name:
        findings += forwarders.check(tree, path, package_name)
    allowed = _allowed(source)
    kept = [f for f in findings if f.rule not in allowed.get(f.line, ())]
    return sorted(set(kept), key=lambda f: (f.line, f.rule))


@frozen
class _Where:
    """What a file's path and its project say about which rules apply to it."""

    test: bool
    package: bool
    paths: bool
    env: bool

    @classmethod
    def of(cls, path: str, *, env: bool) -> _Where:
        parts = PurePath(path).parts
        name = PurePath(path).name
        test = "tests" in parts or name.startswith("test_") or name == "conftest.py"
        return cls(
            test=test,
            package="src" in parts and not test,
            paths=name == "paths.py",
            env=env,
        )


def _check_node(node: ast.AST, where: _Where, path: str) -> Iterator[Finding]:
    if isinstance(node, ast.ClassDef):
        yield from _class(node, where, path)
    elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        yield from _registration_order(node.decorator_list, path)
        if not where.test:
            yield from _keyword_only(node, path)
    elif isinstance(node, ast.ImportFrom | ast.Import):
        yield from _dataclass_import(node, path)
    elif isinstance(node, ast.Compare) and not where.test:
        yield from _kind_comparison(node, path)
    elif isinstance(node, ast.Attribute):
        yield from _attribute(node, where, path)
    elif isinstance(node, ast.Call):
        yield from _log_event(node, path)
    elif isinstance(node, ast.Raise):
        yield from _error_message(node, path)


def _module_name(where: _Where, relative: str, *, report: str) -> Iterator[Finding]:
    if not where.package:
        return
    pure = PurePath(relative)
    names = [*pure.parent.parts[pure.parts.index("src") + 1 :], pure.stem]
    for name in names:
        if name in GRAB_BAGS:
            yield Finding(
                report,
                1,
                "LAY-2",
                f"`{name}` is a grab-bag module; name it after its one responsibility",
            )
            return


def _heavy_imports(tree: ast.Module, path: str) -> Iterator[Finding]:
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
        else:
            continue  # `if TYPE_CHECKING:` blocks and other statements are fine.
        for module in modules:
            if _heavy(module):
                yield Finding(
                    path,
                    node.lineno,
                    "ARC-8",
                    f"import `{module}` inside the function that needs it",
                )


def _heavy(module: str) -> bool:
    top = module.split(".", maxsplit=1)[0]
    return top in HEAVY or module.startswith(HEAVY_PREFIXES)


def _class(node: ast.ClassDef, where: _Where, path: str) -> Iterator[Finding]:
    if where.test and node.name.startswith("Test"):
        yield Finding(
            path,
            node.lineno,
            "TST-1",
            "tests are plain functions named as sentences, not classes",
        )
    yield from _registration_order(node.decorator_list, path)
    bases = {_name(base) for base in node.bases}
    if any(base.endswith(EXCEPTION_SUFFIXES) for base in bases) or bases & PLAIN_BASES:
        return
    if node.name.endswith(EXCEPTION_SUFFIXES):
        return
    for item in node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            yield Finding(
                path,
                item.lineno,
                "TYP-4",
                "no hand-written `__init__`; declare attrs fields and derive state "
                "in a classmethod constructor or `__attrs_post_init__`",
            )
    for decorator in node.decorator_list:
        if _name(decorator) == "dataclass":
            yield Finding(
                path,
                decorator.lineno,
                "TYP-4",
                "classes are attrs (`@frozen` or `@define`), not dataclasses",
            )


def _dataclass_import(
    node: ast.Import | ast.ImportFrom, path: str
) -> Iterator[Finding]:
    modules = (
        [alias.name for alias in node.names]
        if isinstance(node, ast.Import)
        else [node.module or ""]
    )
    if "dataclasses" in modules:
        yield Finding(path, node.lineno, "TYP-4", "use attrs instead of `dataclasses`")


def _registration_order(decorators: list[ast.expr], path: str) -> Iterator[Finding]:
    for index, decorator in enumerate(decorators):
        if index and _is_registration(decorator):
            yield Finding(
                path,
                decorator.lineno,
                "FAM-2",
                "`@...Factory.register(...)` must be the outermost decorator",
            )


def _is_registration(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "register"
        and _name(node.func.value).endswith("Factory")
    )


def _keyword_only(
    node: ast.FunctionDef | ast.AsyncFunctionDef, path: str
) -> Iterator[Finding]:
    # A console script's `main(argv=None)` takes the signature its runner passes.
    if node.name == "main" or (node.name.startswith("__") and node.name.endswith("__")):
        return
    arguments = node.args
    positional = [*arguments.posonlyargs, *arguments.args]
    for arg in positional[len(positional) - len(arguments.defaults) :]:
        yield Finding(
            path,
            arg.lineno,
            "STY-4",
            f"optional parameter `{arg.arg}` goes after `*`, keyword-only",
        )


def _kind_comparison(node: ast.Compare, path: str) -> Iterator[Finding]:
    if not any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops):
        return
    operands = [node.left, *node.comparators]
    if any(isinstance(o, ast.Attribute) and o.attr == "kind" for o in operands):
        yield Finding(
            path,
            node.lineno,
            "ARC-4",
            "branch on a declared capability (`ClassVar[bool]`), not on `kind`",
        )


def _attribute(node: ast.Attribute, where: _Where, path: str) -> Iterator[Finding]:
    if not where.env:
        return
    if _from_dunder_file(node):
        yield Finding(
            path,
            node.lineno,
            "ENV-1",
            "find the repo root with rootutils in `paths.py`, not from `__file__`",
        )
    if where.test or where.paths:
        return
    if _name(node.value) == "os" and node.attr in {"environ", "getenv"}:
        yield Finding(
            path,
            node.lineno,
            "ENV-3",
            "read environment variables in YAML (`oc.env`) or in `paths.py`",
        )


def _from_dunder_file(node: ast.Attribute) -> bool:
    climbs = node.attr == "parents" or (
        node.attr == "parent"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parent"
    )
    return climbs and any(
        isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(node.value)
    )


def _log_event(node: ast.Call, path: str) -> Iterator[Finding]:
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr in LOG_METHODS
        and _name(func.value) in LOGGERS
        and node.args
    ):
        return
    event = node.args[0]
    if isinstance(event, ast.Constant) and isinstance(event.value, str):
        if not EVENT.fullmatch(event.value):
            yield Finding(
                path,
                node.lineno,
                "LOG-2",
                f"event {event.value!r} is not a snake_case id; "
                "put the details in key=value pairs",
            )
    elif isinstance(event, ast.JoinedStr | ast.BinOp) or _is_format(event):
        yield Finding(
            path,
            node.lineno,
            "LOG-2",
            "the event is a constant snake_case id, never a formatted string",
        )


def _is_format(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    )


def _error_message(node: ast.Raise, path: str) -> Iterator[Finding]:
    call = node.exc
    if not (
        isinstance(call, ast.Call)
        and _name(call.func).endswith(EXCEPTION_SUFFIXES)
        and call.args
    ):
        return
    message = _literal_text(call.args[0])
    if not message:
        return
    first = message.split(maxsplit=1)[0]
    if first.isalpha() and first[0].isupper() and first[1:].islower():
        yield Finding(path, node.lineno, "ERR-3", "error messages start lowercase")
    if message.rstrip().endswith("."):
        yield Finding(
            path, node.lineno, "ERR-3", "error messages have no trailing period"
        )


def _literal_text(node: ast.expr) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
            else "x"
            for part in node.values
        )
    return ""


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    return ""


def _allowed(source: str) -> dict[int, set[str]]:
    allowed: dict[int, set[str]] = {}
    for number, line in enumerate(source.splitlines(), start=1):
        rules = set(ALLOW.findall(line))
        allowed.setdefault(number, set()).update(rules)
        if rules and line.lstrip().startswith("#"):
            allowed.setdefault(number + 1, set()).update(rules)
    return allowed
