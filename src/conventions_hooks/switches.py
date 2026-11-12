"""Switches on a variant name: the ARC-9 checks of `check-conventions`."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Container, Iterator, Sequence

from attrs import frozen

from conventions_hooks.findings import Finding

MIN_ARMS = 3
# A string names a variant when it reads as a name: `modal`, `linear-warmup`, `gpt-4.1`.
# An empty string, a file suffix, a media type or one letter is tested, not switched on.
VALUE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]+")
# Libraries own the `dtype` of an array or a column: it is no variant of the project.
SKIPPED = frozenset({"dtype"})
# Python owns these attributes, by the dotted name of the module or object they are on.
MODULE_NAMES = frozenset(
    {("os", "name"), ("sys", "platform"), ("sys.implementation", "name")}
)


@frozen
class Arm:
    """One branch of a switch: the values it matches and the statements it runs."""

    values: frozenset[str]
    body: tuple[ast.stmt, ...]


@frozen
class Switch:
    """A chain of branches on one variant name, inside one function.

    It is reported at `line`, and `lines` are where a waiver of it may stand: the
    line of each `if` in a run of guard clauses.
    """

    key: str
    function: str
    line: int
    arms: tuple[Arm, ...]
    lines: tuple[int, ...]

    @property
    def values(self) -> frozenset[str]:
        return frozenset().union(*(arm.values for arm in self.arms))

    def waived(self, waived: Container[int]) -> bool:
        """Return whether a waiver covers the line of any `if` of the switch."""
        return any(line in waived for line in self.lines)


@frozen
class Elsewhere:
    """A switch in another module of the same package, and where to point at it."""

    path: str
    switch: Switch


def check(
    tree: ast.Module,
    path: str,
    *,
    elsewhere: Callable[[], Sequence[Elsewhere]] | None = None,
    waived: Container[int] = (),
) -> list[Finding]:
    """Return the ARC-9 findings for one module.

    A chain of three arms is reported, and so is a variant name that two functions
    switch on with a value in common. The factory, whose every arm builds an object,
    is not reported, but a second function that branches on its values is. `waived`
    holds the lines where a comment waives ARC-9: a switch with an `if` at one of
    them is not reported and does not count against the others of this module.

    `elsewhere` returns the switches of the package's other modules, and is called
    only when this module has a switch they could repeat. A variant name switched on
    here and there is reported here, in each module that has it. Across modules one
    of the two must be the factory or have two arms or more: a lone
    `if cfg.backend == "modal"` in each of two modules is not reported, though in two
    functions of one module it is.
    """
    switches = [s for s in switches_of(tree) if not s.waived(waived)]
    return [
        *_chains(switches, path),
        *_repeated(switches, path),
        *_repeated_elsewhere(switches, path, elsewhere),
    ]


def switches_of(tree: ast.Module) -> list[Switch]:
    """Return the switches on a variant name in the functions of one module.

    A switch tests one name against strings that read as names. A `match` that ends
    in `assert_never`, a dunder, a name in `SKIPPED` or `MODULE_NAMES`, a `kind`
    attribute and the `type` of a `device` give none, so nothing is reported for them
    or counted against them.
    """
    found: list[Switch] = []
    for function in _functions(tree):
        nodes = (function, *_own_nodes(function))
        found += _switches(nodes, function.name)
        found += _conditionals(nodes, function.name)
    return [s for s in found if s.key not in SKIPPED and not _dunder(s.key)]


def _chains(switches: list[Switch], path: str) -> Iterator[Finding]:
    for switch in switches:
        if len(switch.arms) < MIN_ARMS or _factory(switch):
            continue
        if all(_constant(arm.body) for arm in switch.arms):
            yield Finding(
                path,
                switch.line,
                "ARC-9",
                f"{len(switch.arms)} arms on `{switch.key}` only map values to "
                "constants; use a dict",
            )
        else:
            yield Finding(
                path,
                switch.line,
                "ARC-9",
                f"{len(switch.arms)} arms on `{switch.key}` run different code; make "
                "each value a class (a family item or a Protocol implementation) "
                "chosen once in a factory",
            )


def _repeated(switches: list[Switch], path: str) -> Iterator[Finding]:
    """Yield each short switch that repeats an earlier one of another function.

    The factories and the long chains, which this never reports, come first, so a
    short switch is compared with them wherever it stands.
    """
    earlier: dict[str, list[Switch]] = {}
    for switch in sorted(switches, key=_short):
        seen = next(
            (
                other
                for other in earlier.get(switch.key, ())
                if other.function != switch.function and other.values & switch.values
            ),
            None,
        )
        earlier.setdefault(switch.key, []).append(switch)
        if seen and _short(switch):
            yield Finding(
                path,
                switch.line,
                "ARC-9",
                f"`{switch.key}` is also switched on in `{seen.function}` (line "
                f"{seen.line}); make each value a class chosen once in a factory",
            )


def _repeated_elsewhere(
    switches: list[Switch],
    path: str,
    elsewhere: Callable[[], Sequence[Elsewhere]] | None,
) -> Iterator[Finding]:
    mine = [switch for switch in switches if _short(switch)]
    if not mine or elsewhere is None:
        return
    others = elsewhere()
    for switch in mine:
        other = next(
            (
                other
                for other in others
                if other.switch.key == switch.key
                and other.switch.values & switch.values
                and (
                    _factory(other.switch)
                    or max(len(other.switch.arms), len(switch.arms)) > 1
                )
            ),
            None,
        )
        if other:
            yield Finding(
                path,
                switch.line,
                "ARC-9",
                f"`{switch.key}` is also switched on in `{other.switch.function}` "
                f"({other.path}:{other.switch.line}); make each value a class chosen "
                "once in a factory",
            )


def _functions(
    tree: ast.Module,
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def _switches(nodes: Sequence[ast.AST], function: str) -> Iterator[Switch]:
    for node in nodes:
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and not _elif_tail(node, field):
                yield from _runs(block, function)
        if isinstance(node, ast.Match):
            yield from _match(node, function)


def _own_nodes(function: ast.AST) -> Iterator[ast.AST]:
    """Yield the nodes of a function, leaving out the functions nested in it."""
    # A stack, not recursion: a long sum or chain of calls nests thousands deep.
    # Children go on it last first, so they come off in the order of the source.
    stack = [*ast.iter_child_nodes(function)][::-1]
    while stack:
        node = stack.pop()
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            yield node
            stack += [*ast.iter_child_nodes(node)][::-1]


def _elif_tail(node: ast.AST, field: str) -> bool:
    return (
        field == "orelse"
        and isinstance(node, ast.If)
        and len(node.orelse) == 1
        and isinstance(node.orelse[0], ast.If)
    )


def _runs(block: list[ast.stmt], function: str) -> Iterator[Switch]:
    """Yield the `if`/`elif` chains of one block, and its runs of `if`s on one name.

    Consecutive guard clauses (`if fmt == "csv": return ...`) are one switch, as an
    `elif` chain is. A guard on the same name whose strings do not read as names
    (`if fmt == "":`) is no arm and does not end the run; the switch is at the line
    of the first `if` that has an arm.
    """
    run: list[tuple[str, tuple[Arm, ...], bool, int]] = []
    for statement in [*block, None]:
        chain = _if_chain(statement) if isinstance(statement, ast.If) else None
        if chain and run and chain[0] == run[-1][0] and run[-1][2]:
            run.append(chain)
            continue
        arms = tuple(arm for _, chain_arms, _, _ in run for arm in chain_arms)
        if arms:
            line = next(line for _, chain_arms, _, line in run if chain_arms)
            lines = tuple(line for _, _, _, line in run)
            yield Switch(run[0][0], function, line, arms, lines)
        run = [chain] if chain else []


def _if_chain(node: ast.If) -> tuple[str, tuple[Arm, ...], bool, int] | None:
    """Return the name a chain tests, its arms, whether it lacks `else`, its line.

    A test on a string that does not read as a name is no arm, and the chain goes on
    below it, as a `match` goes on below such a `case`.
    """
    arms: list[Arm] = []
    key = ""
    current: ast.If | None = node
    open_ended = False
    while current is not None:
        test = _test(current.test)
        if test is None or (key and test[0] != key):
            break
        key = test[0]
        if test[1]:
            arms.append(Arm(test[1], tuple(current.body)))
        orelse = current.orelse
        open_ended = not orelse
        current = (
            orelse[0] if len(orelse) == 1 and isinstance(orelse[0], ast.If) else None
        )
    return (key, tuple(arms), open_ended, node.lineno) if key else None


def _match(node: ast.Match, function: str) -> Iterator[Switch]:
    """Yield a `match` on a variant name, unless it ends in `assert_never`.

    The closed `match` is what ARC-9 asks for when a set gains operations, and each
    operation is one more function with such a `match`.
    """
    key = _subject(node.subject)
    arms = [
        Arm(values, tuple(case.body))
        for case in node.cases
        if (values := _pattern_values(case.pattern))
    ]
    closed = any(
        isinstance(call, ast.Call) and _key(call.func) == "assert_never"
        for case in node.cases
        for call in ast.walk(ast.Module(body=case.body, type_ignores=[]))
    )
    if key and arms and not closed:
        yield Switch(key, function, node.lineno, tuple(arms), (node.lineno,))


def _conditionals(nodes: Sequence[ast.AST], function: str) -> Iterator[Switch]:
    """Yield each `a if x == "v1" else b` as a switch of one arm, at its test's line.

    The arm returns `a`, so an expression that picks between new objects is the
    factory, as the `if` statement that says the same would be.
    """
    for node in nodes:
        if isinstance(node, ast.IfExp) and (test := _test(node.test)) and test[1]:
            arm = Arm(test[1], (ast.Return(value=node.body),))
            line = node.test.lineno
            yield Switch(test[0], function, line, (arm,), (line,))


def _test(test: ast.expr) -> tuple[str, frozenset[str]] | None:
    """Return the name and values that `x == "v1"` or `x in ("v1", "v2")` tests.

    The values are the strings that read as names: a test on other strings only, as
    `x == ""` is, gives the name and no value.
    """
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    left, right, op = test.left, test.comparators[0], test.ops[0]
    if isinstance(op, ast.Eq):
        for name, value in ((left, right), (right, left)):
            if (key := _subject(name)) and _string(value):
                return key, _strings(value)
    if (
        isinstance(op, ast.In)
        and (key := _subject(left))
        and isinstance(right, ast.Tuple | ast.List | ast.Set)
        and any(map(_string, right.elts))
    ):
        return key, frozenset().union(*map(_strings, right.elts))
    return None


def _pattern_values(pattern: ast.pattern) -> frozenset[str]:
    if isinstance(pattern, ast.MatchValue):
        return _strings(pattern.value)
    if isinstance(pattern, ast.MatchOr):
        return frozenset().union(*map(_pattern_values, pattern.patterns))
    return frozenset()


def _string(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _strings(node: ast.expr) -> frozenset[str]:
    """Return the string `node` is, when it reads as a name and can name a variant."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and VALUE.fullmatch(node.value)
    ):
        return frozenset({node.value})
    return frozenset()


def _subject(node: ast.expr) -> str:
    """Return the variant name that a test or a `match` is on, or "" for none.

    A `kind` attribute is left to ARC-4, which reports each branch on one, and the
    `type` of a `device` is a name of torch. A call, as `platform.system()` is, gives
    none.
    """
    if isinstance(node, ast.Attribute) and (
        node.attr == "kind"
        or (node.attr == "type" and _key(node.value) == "device")
        or (_dotted(node.value), node.attr) in MODULE_NAMES
    ):
        return ""
    return _key(node)


def _dotted(node: ast.expr) -> str:
    """Return the dotted name `node` is, as `sys.implementation`, or "" for none."""
    # A loop, not recursion: a chain of attributes can nest thousands deep.
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join([node.id, *reversed(parts)]) if isinstance(node, ast.Name) else ""


def _dunder(name: str) -> bool:
    """Return whether Python owns `name`, as it owns `__name__` and `__qualname__`."""
    return name.startswith("__") and name.endswith("__")


def _key(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _short(switch: Switch) -> bool:
    """Return whether a switch is reported only where it repeats another one.

    The factory never is, and `_chains` reports a chain of three arms already.
    """
    return len(switch.arms) < MIN_ARMS and not _factory(switch)


def _factory(switch: Switch) -> bool:
    """Return whether every arm builds an object: the one allowed switch.

    Every arm returns the object, or every arm assigns it to the same name.
    """
    built = {_built(arm.body) for arm in switch.arms}
    return len(built) == 1 and None not in built


def _built(body: tuple[ast.stmt, ...]) -> str | None:
    """Return where an arm puts the object it builds: `return`, or the name it assigns.

    After any imports the arm is one statement, which returns or assigns to a name a
    call of a class or of a method on a class: `Runner(cfg)`, `runners.Runner(cfg)`,
    `Runner.from_config(cfg)`. An arm that does anything else gives `None`.
    """
    *imports, last = body
    if not all(isinstance(s, ast.Import | ast.ImportFrom) for s in imports):
        return None
    match last:
        case ast.Return(value=ast.Call(func=func)):
            return "return" if _constructor(func) else None
        case ast.Assign(targets=[ast.Name(id=name)], value=ast.Call(func=func)):
            return name if _constructor(func) else None
        case _:
            return None


def _constructor(func: ast.expr) -> bool:
    """Return whether a call to `func` builds an object, going by its capital letter.

    The letter comes after any leading underscores: `_Wall()` builds a private class.
    """
    if _capital(_key(func)):
        return True
    return isinstance(func, ast.Attribute) and _capital(_key(func.value))


def _capital(name: str) -> bool:
    return name.lstrip("_")[:1].isupper()


def _constant(body: tuple[ast.stmt, ...]) -> bool:
    if len(body) != 1:
        return False
    statement = body[0]
    if isinstance(statement, ast.Return | ast.Assign):
        value = statement.value
        return value is not None and _literal(value)
    return False


def _literal(node: ast.expr) -> bool:
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return False
    return True
