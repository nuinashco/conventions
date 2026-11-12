"""`check-conventions`: the code rules of the guide that an AST can decide.

Usage:

    check-conventions src/pkg/module.py tests/test_module.py

    check-conventions --claude-hook    # Claude Code PostToolUse hook: reads its JSON

In hook mode the edited file's findings go to stderr with exit code 2, which Claude
Code hands back to Claude; a repo without a `[tool.conventions]` table is skipped.
Rules listed in that table's `ignore` are skipped in both modes.

Each check stands in for a rule whose *Check* used to be review alone: no grab-bag
modules (LAY-2), heavy imports kept lazy unless a class base or a decorator needs them
(ARC-8), no branching on a `kind` string (ARC-4), a variant name switched on in one
place of the package (ARC-9), no functions that only forward (ARC-10), registration
outermost (FAM-2), attrs instead of dataclasses and of an `__init__` that no base from
outside the project needs (TYP-4), options keyword-only (STY-4), ASCII only (STY-8),
lowercase error messages (ERR-3), snake_case log events (LOG-2) and test functions
rather than classes (TST-1). In a project with a `src/<pkg>/paths.py`, the repo root
is found and environment variables are read there (ENV-1, ENV-3). A justified
exception is a comment naming the rule with its reason, on the flagged line or alone
above the statement:
`# conventions: STY-4 - OmegaConf calls this resolver by position.`
A file that Python cannot read or parse gets no findings; ruff reports a syntax error.
"""

from __future__ import annotations

import ast
import functools
import itertools
import re
import sys
import tokenize
from collections.abc import Callable, Collection, Iterator, Sequence
from pathlib import Path, PurePath

from attrs import frozen

from conventions_hooks import forwarders, package, switches, waivers
from conventions_hooks.findings import UNREADABLE, Finding, check_edit, check_paths
from conventions_hooks.settings import project_root

GRAB_BAGS = frozenset({"utils", "util", "common", "core", "helpers", "misc"})
GRAB_BAG_SUFFIXES = ("_utils", "_util", "_helpers", "_common")
HEAVY = frozenset(
    {"torch", "vllm", "litellm", "wandb", "boto3", "transformers", "tensorflow", "jax"}
)
HEAVY_PREFIXES = ("google.cloud",)
LOG_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "msg"}
)
LOGGERS = frozenset({"log", "logger"})
EVENT = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")
NON_ASCII = re.compile(r"[^\x00-\x7f]")
EXCEPTION_SUFFIXES = ("Error", "Exception", "Warning")
PLAIN_BASES = frozenset({"Protocol", "Enum", "StrEnum", "IntEnum", "NamedTuple"})
# Bases that say nothing about who owns a class: the project's family bases have them.
UNOWNED_BASES = frozenset({"ABC", "Generic", "object"})
DATACLASS_MAKERS = frozenset({"dataclass", "field", "make_dataclass"})
PYTHON_NAMES = frozenset({"None", "True", "False"})


def main(argv: Sequence[str] | None = None) -> int:
    """Check the files named on the command line, or the file a Claude edit wrote."""
    args = sys.argv[1:] if argv is None else argv
    return check_paths(args, check_file=check_file, usage=__doc__ or "")


def claude_hook(payload: str) -> int:
    """Check the Python file a Claude Code tool call wrote; exit code 2 reports back."""
    return check_edit(payload, check_file=check_file)


def check_file(path: Path) -> list[Finding]:
    """Return the findings for one Python file, judged by its place in its project."""
    try:
        with tokenize.open(path) as file:
            source = file.read()
    except UNREADABLE:
        return []  # Python cannot read it as text.
    root = project_root(path.parent)
    inside = path.absolute().relative_to(root) if root else path
    top = package.top_package(path)
    return check_source(
        source,
        path=str(path),
        relative=str(inside),
        paths_module=bool(root and any(root.glob("src/*/paths.py"))),
        top=top,
        elsewhere=functools.partial(package.switches_elsewhere, path),
        own_packages=_own_packages(root, top),
    )


def _own_packages(root: Path | None, top: Path | None) -> frozenset[str]:
    """Return the names of a project's packages: `top` and the folders under `src/`."""
    names = {top.name} if top else set()
    if root:
        names |= {init.parent.name for init in root.glob("src/*/__init__.py")}
    return frozenset(names)


def check_source(
    source: str,
    *,
    path: str = "<string>",
    relative: str | None = None,
    paths_module: bool = True,
    top: Path | None = None,
    elsewhere: Callable[[], Sequence[switches.Elsewhere]] | None = None,
    own_packages: Collection[str] = (),
) -> list[Finding]:
    """Return the convention findings for one Python source, reported at `path`.

    The file's path from its project's root, `relative` (`path` when not given),
    decides which rules apply: a folder above the project says nothing about it.
    ENV-1 and ENV-3 apply only when `paths_module` says the project has a
    `src/<pkg>/paths.py`. ARC-9 and ARC-10 look past the file: `elsewhere` returns
    the switches in the other modules of its package, and `top` is the folder of
    its top package, given when `path` is the file itself. TYP-4 lets a class keep
    the `__init__` that a base from outside the project needs: `own_packages` names
    the project's packages, and an absolute import of any other module is from
    outside.
    """
    try:
        tree = ast.parse(source)
    except UNREADABLE:
        return []  # Ruff reports the syntax error itself.
    where = _Where.of(relative or path, env=paths_module)
    findings = list(_module_name(where, relative or path, report=path))
    findings += _non_ascii(source, path)
    if where.package:
        findings += _heavy_imports(tree, path)
    findings += _hand_written_inits(tree, path, own_packages)
    for node in ast.walk(tree):
        findings += _check_node(node, where, path)
    waived = waivers.waived(source)
    if not where.test:
        findings += switches.check(
            tree,
            path,
            elsewhere=elsewhere,
            waived={line for line, rules in waived.items() if "ARC-9" in rules},
        )
    if where.package and top:
        findings += forwarders.check(tree, path, top)
    kept = [f for f in findings if f.rule not in waived.get(f.line, ())]
    # A dict keeps findings in the order they were met; a set shuffles those that
    # share a line and a rule from one run to the next.
    return sorted(dict.fromkeys(kept), key=lambda f: (f.line, f.rule))


@frozen
class _Where:
    """What a file's path and its project say about which rules apply to it."""

    test: bool
    package: bool
    paths: bool
    env: bool

    @classmethod
    def of(cls, path: str, *, env: bool) -> _Where:
        pure = PurePath(path)
        test = package.is_test(pure)
        return cls(
            test=test,
            package="src" in pure.parts and not test,
            paths=pure.name == "paths.py",
            env=env,
        )


def _check_node(node: ast.AST, where: _Where, path: str) -> Iterator[Finding]:
    if where.env and isinstance(node, ast.Attribute | ast.Subscript | ast.Compare):
        yield from _paths_rules(node, where, path)
    if isinstance(node, ast.ClassDef):
        yield from _class(node, where, path)
    elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        yield from _registration_order(node.decorator_list, path)
        if not where.test:
            yield from _keyword_only(node, path)
    elif isinstance(node, ast.ImportFrom):
        yield from _dataclass_import(node, path)
    elif isinstance(node, ast.Compare | ast.Match) and not where.test:
        yield from _kind_branch(node, path)
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
        if name.lstrip("_") in GRAB_BAGS or name.endswith(GRAB_BAG_SUFFIXES):
            yield Finding(
                report,
                1,
                "LAY-2",
                f"`{name}` is a grab-bag module; name it after its one responsibility",
            )
            return


def _non_ascii(source: str, path: str) -> Iterator[Finding]:
    for number, line in enumerate(source.split("\n"), start=1):
        if match := NON_ASCII.search(line):
            yield Finding(
                path,
                number,
                "STY-8",
                f"non-ASCII character U+{ord(match[0]):04X}; "
                "write it in ASCII or as an escape",
            )


def _heavy_imports(tree: ast.Module, path: str) -> Iterator[Finding]:
    needed = _needed_at_import(tree)
    for node in _module_level(tree):
        for module, bound in _imported(node):
            # A class base or a decorator cannot wait for a function to import it.
            if _heavy(module) and not bound & needed:
                yield Finding(
                    path,
                    node.lineno,
                    "ARC-8",
                    f"import `{module}` inside the function that needs it",
                )


def _module_level(tree: ast.Module) -> Iterator[ast.stmt]:
    """Yield the statements that run when the module is imported, outside a class.

    The blocks of `if`, `try` and `with` statements are entered, however nested,
    except the block of an `if` that only a type checker reads.
    """
    # A stack, not recursion: a chain of `elif`s nests as deep as it is long.
    stack = tree.body[::-1]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, ast.If):
            blocks = _blocks_that_run(node)
        elif isinstance(node, ast.Try | ast.TryStar):
            handlers = [handler.body for handler in node.handlers]
            blocks = [node.body, *handlers, node.orelse, node.finalbody]
        elif isinstance(node, ast.With):
            blocks = [node.body]
        else:
            continue
        stack += [statement for block in blocks for statement in block][::-1]


def _blocks_that_run(node: ast.If) -> list[list[ast.stmt]]:
    test = node.test
    if _name(test) == "TYPE_CHECKING":
        return [node.orelse]
    if (
        isinstance(test, ast.UnaryOp)
        and isinstance(test.op, ast.Not)
        and _name(test.operand) == "TYPE_CHECKING"
    ):
        return [node.body]
    return [node.body, node.orelse]


def _needed_at_import(tree: ast.Module) -> set[str]:
    """Return the names in the class bases and decorators that run at import.

    Those are the bases of a class and the decorators of a class or function that
    is not nested inside a function.
    """
    needed: list[ast.expr] = []
    for node in _statements(tree, inside_functions=False):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            needed += node.decorator_list
        elif isinstance(node, ast.ClassDef):
            needed += [*node.bases, *node.decorator_list]
    return {
        node.id
        for expression in needed
        for node in ast.walk(expression)
        if isinstance(node, ast.Name)
    }


def _statements(tree: ast.Module, *, inside_functions: bool) -> Iterator[ast.stmt]:
    """Yield the statements of a module, however nested, expressions left unread.

    A function is always yielded; the statements of its body, which run when it is
    called, only with `inside_functions`.
    """
    # A stack, not recursion: a chain of `elif`s nests as deep as it is long.
    # Children go on it last first, so they come off in the order of the source.
    stack: list[ast.AST] = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.stmt):
            yield node
            function = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            if function and not inside_functions:
                continue
        stack += [
            child
            for child in ast.iter_child_nodes(node)
            if isinstance(child, ast.stmt | ast.excepthandler | ast.match_case)
        ][::-1]


def _imported(node: ast.stmt) -> Iterator[tuple[str, set[str]]]:
    """Yield each module an absolute import names, with the names it binds here."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name, {alias.asname or alias.name.split(".", maxsplit=1)[0]}
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        yield node.module, {alias.asname or alias.name for alias in node.names}


def _heavy(module: str) -> bool:
    top = module.split(".", maxsplit=1)[0]
    return top in HEAVY or module.startswith(HEAVY_PREFIXES)


def _hand_written_inits(
    tree: ast.Module, path: str, own_packages: Collection[str]
) -> Iterator[Finding]:
    """Report each `__init__` of a class that could declare attrs fields instead.

    An exception, a Protocol and an enum stay plain classes, and a subclass of a
    class from outside the project is built the way that base says.
    """
    statements = list(_statements(tree, inside_functions=True))
    classes = [node for node in statements if isinstance(node, ast.ClassDef)]
    outside = _outside_names(statements, classes, own_packages)
    for node in classes:
        if _stays_plain(node) or not outside.isdisjoint(_owning_bases(node)):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                yield Finding(
                    path,
                    item.lineno,
                    "TYP-4",
                    "no hand-written `__init__`; declare attrs fields and derive "
                    "state in a classmethod constructor or `__attrs_post_init__`",
                )


def _outside_names(
    statements: Sequence[ast.stmt],
    classes: Sequence[ast.ClassDef],
    own_packages: Collection[str],
) -> set[str]:
    """Return the names that stand for a module or a class from outside the project.

    Those are the names bound by an absolute import of a module that is not one of
    `own_packages`, and the `classes` of this module that descend from one. Bases
    are not followed into other modules: a base imported from the project is its
    own.
    """
    names = {
        name
        for node in statements
        for module, bound in _imported(node)
        if module.split(".", maxsplit=1)[0] not in own_packages
        for name in bound
    }
    subclasses: dict[str, list[str]] = {}
    for node in classes:
        for base in _owning_bases(node):
            subclasses.setdefault(base, []).append(node.name)
    # A queue, not recursion: a line of classes is as deep as it is long.
    queue = list(names)
    while queue:
        for name in subclasses.pop(queue.pop(), ()):
            if name not in names:
                names.add(name)
                queue.append(name)
    return names


def _owning_bases(node: ast.ClassDef) -> list[str]:
    """Return the name each base of a class starts from, where the base has an owner."""
    return [_root(base) for base in node.bases if _name(base) not in UNOWNED_BASES]


def _root(node: ast.expr) -> str:
    """Return the name that `a.b.C[T]` starts from: `a`."""
    while isinstance(node, ast.Attribute | ast.Subscript):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def _stays_plain(node: ast.ClassDef) -> bool:
    bases = {_name(base) for base in node.bases}
    return (
        node.name.endswith(EXCEPTION_SUFFIXES)
        or any(base.endswith(EXCEPTION_SUFFIXES) for base in bases)
        or bool(bases & PLAIN_BASES)
    )


def _class(node: ast.ClassDef, where: _Where, path: str) -> Iterator[Finding]:
    if where.test and _is_test_class(node):
        yield Finding(
            path,
            node.lineno,
            "TST-1",
            "tests are plain functions named as sentences, not classes",
        )
    yield from _registration_order(node.decorator_list, path)
    if _stays_plain(node):
        return
    for decorator in node.decorator_list:
        if _name(decorator) == "dataclass":
            yield Finding(
                path,
                decorator.lineno,
                "TYP-4",
                "classes are attrs (`@frozen` or `@define`), not dataclasses",
            )


def _is_test_class(node: ast.ClassDef) -> bool:
    return any(_name(base).endswith("TestCase") for base in node.bases) or any(
        isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
        and item.name.startswith("test")
        for item in node.body
    )


def _dataclass_import(node: ast.ImportFrom, path: str) -> Iterator[Finding]:
    # Reading a dataclass of a library (`asdict`, `fields`) defines none.
    names = {alias.name for alias in node.names}
    if node.module == "dataclasses" and not node.level and names & DATACLASS_MAKERS:
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
    # A console script's `main(argv=None)` takes the signature its runner passes,
    # and an `@override` method the one its base class has.
    if node.name == "main" or (node.name.startswith("__") and node.name.endswith("__")):
        return
    if any(_name(decorator) == "override" for decorator in node.decorator_list):
        return
    # Defaults fill the parameters from the last one back; a caller cannot name one
    # before `/`, so that one stays as it is.
    named = node.args.args
    optional = min(len(named), len(node.args.defaults))
    for arg in named[len(named) - optional :]:
        yield Finding(
            path,
            arg.lineno,
            "STY-4",
            f"optional parameter `{arg.arg}` goes after `*`, keyword-only",
        )


def _kind_branch(node: ast.Compare | ast.Match, path: str) -> Iterator[Finding]:
    """Report a `kind` attribute set against a string that names a family kind.

    Other attributes are called `kind` too: `inspect.Parameter.kind` is compared with
    constants, and a numpy dtype's with one letter.
    """
    if isinstance(node, ast.Match):
        branches = _is_kind(node.subject) and any(
            _names_a_kind(case.pattern) for case in node.cases
        )
    else:
        sides = itertools.pairwise([node.left, *node.comparators])
        branches = any(
            isinstance(op, ast.Eq | ast.NotEq | ast.In | ast.NotIn)
            and (
                (_is_kind(left) and _names_a_kind(right))
                or (_is_kind(right) and _names_a_kind(left))
            )
            for op, (left, right) in zip(node.ops, sides, strict=True)
        )
    if branches:
        yield Finding(
            path,
            node.lineno,
            "ARC-4",
            "branch on a declared capability (`ClassVar[bool]`), not on `kind`",
        )


def _is_kind(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "kind"


def _names_a_kind(node: ast.expr | ast.pattern) -> bool:
    """Return whether `node` is a string of two characters or more, or holds one."""
    if isinstance(node, ast.MatchAs) and node.pattern:
        node = node.pattern
    if isinstance(node, ast.MatchValue):
        node = node.value
    if isinstance(node, ast.MatchOr):
        return any(map(_names_a_kind, node.patterns))
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return any(map(_names_a_kind, node.elts))
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and len(node.value) > 1
    )


def _paths_rules(
    node: ast.Attribute | ast.Subscript | ast.Compare, where: _Where, path: str
) -> Iterator[Finding]:
    """Report what a project with a `paths.py` does there: ENV-1 and ENV-3."""
    if isinstance(node, ast.Attribute) and _from_dunder_file(node):
        yield Finding(
            path,
            node.lineno,
            "ENV-1",
            "find the repo root with rootutils in `paths.py`, not from `__file__`",
        )
    if where.test or where.paths:
        return
    if read := _environment_read(node):
        yield Finding(
            path,
            read.lineno,
            "ENV-3",
            "read environment variables in YAML (`oc.env`) or in `paths.py`",
        )


def _environment_read(
    node: ast.Attribute | ast.Subscript | ast.Compare,
) -> ast.expr | None:
    """Return the `os.environ` or `os.getenv` that `node` reads a variable through.

    Setting or deleting a variable is no read, and neither is handing the whole
    environment on, as `{**os.environ, "SEED": "0"}` does for a child process.
    """
    if isinstance(node, ast.Compare):
        for op, right in zip(node.ops, node.comparators, strict=True):
            if isinstance(op, ast.In | ast.NotIn) and _is_environ(right):
                return right
        return None
    if isinstance(node, ast.Subscript):
        read = isinstance(node.ctx, ast.Load) and _is_environ(node.value)
        return node.value if read else None
    if node.attr == "getenv" and _name(node.value) == "os":
        return node
    return node.value if node.attr == "get" and _is_environ(node.value) else None


def _is_environ(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and _name(node.value) == "os"
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
        and _is_logger(func.value)
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


def _is_logger(node: ast.expr) -> bool:
    """Return whether `node` is `log`, `_logger`, `LOG` and the like, or `logging`."""
    name = _name(node)
    return name == "logging" or name.lstrip("_").lower() in LOGGERS


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
    words = _literal_text(call.args[0]).split()
    # One word is a name or a path (`FileNotFoundError("Makefile")`), not a message.
    if len(words) < 2:
        return
    if _opens_a_sentence(words[0]):
        yield Finding(path, node.lineno, "ERR-3", "error messages start lowercase")
    if words[-1].endswith(".") and not words[-1].endswith("..."):
        yield Finding(
            path, node.lineno, "ERR-3", "error messages have no trailing period"
        )


def _opens_a_sentence(word: str) -> bool:
    """Return whether `word` is capitalised as prose is: `Missing`, `Can't`, `Rows:`.

    A word in capitals or mixed case, in quotes, or with a dot or a digit in it is a
    name, as Python's own `None`, `True` and `False` are.
    """
    word = word.rstrip(":,;!?.")
    parts = word.split("'")
    if word in PYTHON_NAMES or not all(part.isalpha() for part in parts):
        return False
    letters = "".join(parts)
    # A lone capital is a name (`X`, `N`), except for the article.
    return letters == "A" or (letters[0].isupper() and letters[1:].islower())


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
    # A loop, not recursion: `table[0][1]...` nests as deep as it is long.
    while isinstance(node, ast.Call | ast.Subscript):
        node = node.func if isinstance(node, ast.Call) else node.value
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""
