"""Switches on a variant name: the ARC-9 checks of `check-conventions`."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator, Sequence

from attrs import frozen

from conventions_hooks.findings import Finding

MIN_ARMS = 3
# `kind` comparisons are ARC-4 findings already; dunders and platforms are not variants.
SKIPPED = frozenset({"kind", "__name__", "platform", "name", "os"})


@frozen
class Arm:
    """One branch of a switch: the values it matches and the statements it runs."""

    values: frozenset[str]
    body: tuple[ast.stmt, ...]


@frozen
class Switch:
    """A chain of branches on one variant name, inside one function."""

    key: str
    function: str
    line: int
    arms: tuple[Arm, ...]
    closed: bool

    @property
    def values(self) -> frozenset[str]:
        return frozenset().union(*(arm.values for arm in self.arms))


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
) -> list[Finding]:
    """Return the ARC-9 findings for one module.

    `elsewhere` returns the switches of the package's other modules, and is called
    only when this module has a switch they could repeat. A variant name switched on
    here and there is reported here, in each module that has it. Across modules one
    of the two must have two arms or more, since a lone `if suffix == ".py"` in two
    modules is a test, not a switch.
    """
    switches = switches_of(tree)
    return [
        *_chains(switches, path),
        *_repeated(switches, path),
        *_repeated_elsewhere(switches, path, elsewhere),
    ]


def switches_of(tree: ast.Module) -> list[Switch]:
    """Return the switches on a variant name in the functions of one module.

    The conditional expressions come last: a repeat is looked for in the first switch
    on a name, and an expression further up must not take that place from a statement.
    """
    statements: list[Switch] = []
    conditionals: list[Switch] = []
    for function in _functions(tree):
        nodes = (function, *_own_nodes(function))
        statements += _switches(nodes, function.name)
        conditionals += _conditionals(nodes, function.name)
    return [s for s in statements + conditionals if s.key not in SKIPPED]


def _chains(switches: list[Switch], path: str) -> Iterator[Finding]:
    for switch in switches:
        if len(switch.arms) < MIN_ARMS or switch.closed or _factory(switch):
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
    first: dict[str, Switch] = {}
    for switch in switches:
        if _factory(switch):
            continue
        seen = first.setdefault(switch.key, switch)
        if len(switch.arms) >= MIN_ARMS and not switch.closed:
            continue  # `_chains` reports it.
        if seen.function != switch.function and seen.values & switch.values:
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
    mine = [
        switch
        for switch in switches
        # `_chains` reports a long open chain already.
        if not _factory(switch) and (len(switch.arms) < MIN_ARMS or switch.closed)
    ]
    if not mine or elsewhere is None:
        return
    others = [other for other in elsewhere() if not _factory(other.switch)]
    for switch in mine:
        other = next(
            (
                other
                for other in others
                if other.switch.key == switch.key
                and other.switch.values & switch.values
                and max(len(other.switch.arms), len(switch.arms)) > 1
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
    `elif` chain is.
    """
    run: list[tuple[str, tuple[Arm, ...], bool, int]] = []
    for statement in [*block, None]:
        chain = _if_chain(statement) if isinstance(statement, ast.If) else None
        if chain and run and chain[0] == run[-1][0] and run[-1][2]:
            run.append(chain)
            continue
        if run:
            arms = tuple(arm for _, chain_arms, _, _ in run for arm in chain_arms)
            yield Switch(run[0][0], function, run[0][3], arms, closed=False)
        run = [chain] if chain else []


def _if_chain(node: ast.If) -> tuple[str, tuple[Arm, ...], bool, int] | None:
    """Return the name a chain tests, its arms, whether it lacks `else`, its line."""
    arms: list[Arm] = []
    key = ""
    current: ast.If | None = node
    open_ended = False
    while current is not None:
        test = _test(current.test)
        if test is None or (key and test[0] != key):
            break
        key = test[0]
        arms.append(Arm(test[1], tuple(current.body)))
        orelse = current.orelse
        open_ended = not orelse
        current = (
            orelse[0] if len(orelse) == 1 and isinstance(orelse[0], ast.If) else None
        )
    return (key, tuple(arms), open_ended, node.lineno) if arms else None


def _match(node: ast.Match, function: str) -> Iterator[Switch]:
    key = _key(node.subject)
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
    if key and arms:
        yield Switch(key, function, node.lineno, tuple(arms), closed=closed)


def _conditionals(nodes: Sequence[ast.AST], function: str) -> Iterator[Switch]:
    """Yield each `a if x == "v" else b` as a switch of one arm, at its test's line.

    The arm returns `a`, so an expression that picks between new objects is the
    factory, as the `if` statement that says the same would be.
    """
    for node in nodes:
        if isinstance(node, ast.IfExp) and (test := _test(node.test)):
            arm = Arm(test[1], (ast.Return(value=node.body),))
            yield Switch(test[0], function, node.test.lineno, (arm,), closed=False)


def _test(test: ast.expr) -> tuple[str, frozenset[str]] | None:
    """Return the variant name and values that `x == "a"` or `x in ("a", "b")` tests."""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    left, right, op = test.left, test.comparators[0], test.ops[0]
    if isinstance(op, ast.Eq):
        for name, value in ((left, right), (right, left)):
            if (key := _key(name)) and (values := _strings(value)):
                return key, values
    if (
        isinstance(op, ast.In)
        and (key := _key(left))
        and isinstance(right, ast.Tuple | ast.List | ast.Set)
        and (values := frozenset().union(*map(_strings, right.elts)))
    ):
        return key, values
    return None


def _pattern_values(pattern: ast.pattern) -> frozenset[str]:
    if isinstance(pattern, ast.MatchValue):
        return _strings(pattern.value)
    if isinstance(pattern, ast.MatchOr):
        return frozenset().union(*map(_pattern_values, pattern.patterns))
    return frozenset()


def _strings(node: ast.expr) -> frozenset[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return frozenset({node.value})
    return frozenset()


def _key(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _factory(switch: Switch) -> bool:
    """Return whether every arm builds and returns an object: the one allowed switch."""
    return all(
        len(arm.body) == 1
        and isinstance(arm.body[0], ast.Return)
        and isinstance(arm.body[0].value, ast.Call)
        and _key(arm.body[0].value.func)[:1].isupper()
        for arm in switch.arms
    )


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
