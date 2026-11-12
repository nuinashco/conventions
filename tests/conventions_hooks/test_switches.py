"""Switches on a variant name are reported where they repeat or grow too long."""

from __future__ import annotations

import ast

import pytest

from conventions_hooks import switches


def found(source: str) -> list[tuple[int, str]]:
    findings = switches.check(ast.parse(source), "src/demo/runner.py")
    return [(f.line, f.rule) for f in findings]


SHOTGUN = """
def start(cfg):
    if cfg.backend == "modal":
        launch_modal()
    elif cfg.backend == "local":
        launch_local()


def cost(cfg):
    if cfg.backend == "modal":
        return price_modal()
    return 0.0
"""

LONG_CHAIN = """
def score(pred, gold, *, metric):
    if metric == "f1":
        return f1(pred, gold)
    elif metric == "em":
        return exact(pred, gold)
    elif metric == "bleu":
        return bleu(pred, gold)
    raise UnknownMetricError(metric)
"""

GUARDS = """
def render(rows, *, fmt):
    if fmt == "csv":
        return to_csv(rows)
    if fmt == "json":
        return to_json(rows)
    if fmt == "md":
        return to_markdown(rows)
    raise UnknownFormatError(fmt)
"""

CONSTANTS = """
def fraction(split):
    match split:
        case "train":
            return 0.8
        case "val":
            return 0.1
        case "test":
            return 0.1
"""

# The "Bad" example of ARC-9 in the guide.
CONDITIONAL = """
def start(cfg: RunConfig) -> None:
    if cfg.backend == "modal":
        ...
    elif cfg.backend == "local":
        ...


def cost_usd(cfg: RunConfig) -> float:
    return 0.3 if cfg.backend == "modal" else 0.0
"""

CONDITIONALS = """
def label(mode):
    return "T" if mode == "train" else "E"


def steps(mode):
    return (
        100
        if mode in ("train", "tune")
        else 10
    )
"""

# The first switch on `device` stays the one of `setup`, which `teardown` repeats.
BELOW_A_CONDITIONAL = """
def label(cfg):
    return "GPU" if cfg.device == "cuda" else "CPU"


def setup(cfg):
    if cfg.device == "cpu":
        pin()


def teardown(cfg):
    if cfg.device == "cpu":
        unpin()
"""

# Walked in the order of the source, `stop` meets "x" first, so `halt` repeats it.
NESTED_FIRST = """
def stop(mode, items):
    for item in items:
        for part in item:
            if mode == "x":
                drop(part)
    while items:
        if mode == "y":
            items.pop()


def halt(mode):
    if mode == "x":
        leave()
"""

# The same below the first level: the two loops are children of one `for`.
NESTED_SIBLINGS = """
def stop(mode, items):
    for item in items:
        while item:
            if mode == "x":
                drop(item)
        while items:
            if mode == "y":
                items.pop()


def halt(mode):
    if mode == "x":
        leave()
"""


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (SHOTGUN, [(10, "ARC-9")]),
        (LONG_CHAIN, [(3, "ARC-9")]),
        (GUARDS, [(3, "ARC-9")]),
        (CONSTANTS, [(3, "ARC-9")]),
        (CONDITIONAL, [(10, "ARC-9")]),
        (CONDITIONALS, [(9, "ARC-9")]),
        (BELOW_A_CONDITIONAL, [(12, "ARC-9")]),
        (NESTED_FIRST, [(13, "ARC-9")]),
        (NESTED_SIBLINGS, [(13, "ARC-9")]),
    ],
    ids=[
        "same-variant-in-two-functions",
        "three-arms-run-code",
        "three-guard-clauses",
        "three-arms-map-constants",
        "conditional-expression-repeats-a-chain",
        "two-conditional-expressions",
        "statements-below-a-conditional-expression",
        "nested-switch-met-first",
        "nested-siblings-in-source-order",
    ],
)
def test_switches_on_a_variant_name_are_reported(source, expected):
    assert found(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # The factory: every arm builds and returns an object.
        "def build(name):\n"
        "    if name == 'a':\n        return A()\n"
        "    elif name == 'b':\n        return B()\n"
        "    elif name == 'c':\n        return C()\n",
        # A closed set that gains operations stays a match ending in `assert_never`.
        "def describe(shape):\n    match shape.form:\n"
        "        case 'circle':\n            draw()\n"
        "        case 'square':\n            fill()\n"
        "        case 'line':\n            stroke()\n"
        "        case _:\n            assert_never(shape.form)\n",
        # Two arms in one function, different variant names elsewhere.
        "def a(x):\n    if x.mode == 'fast':\n        go()\n\n\n"
        "def b(x):\n    if x.split == 'fast':\n        go()\n",
        "if __name__ == '__main__':\n    main()\n",
        # The factory written as a conditional expression.
        "def build(cfg):\n"
        "    return Modal() if cfg.backend == 'modal' else Local()\n\n\n"
        "def cost(cfg):\n    if cfg.backend == 'modal':\n        return bill()\n",
        # Deeper than the recursion limit.
        "def total(a):\n    return " + " + ".join(["a"] * 3000) + "\n",
    ],
    ids=[
        "factory",
        "closed-match",
        "different-names",
        "main-guard",
        "factory-as-conditional-expression",
        "long-sum",
    ],
)
def test_one_switch_in_one_place_passes(source):
    assert found(source) == []


START = (
    "def start(cfg):\n"
    "    if cfg.backend == 'modal':\n        launch()\n"
    "    elif cfg.backend == 'local':\n        run()\n"
)
COST = "def cost(cfg):\n    if cfg.backend == 'modal':\n        return bill()\n"
COST_IN_ONE_LINE = "def cost(cfg):\n    return 0.3 if cfg.backend == 'modal' else 0.0\n"


@pytest.mark.parametrize(
    "source", [COST, COST_IN_ONE_LINE], ids=["statement", "conditional-expression"]
)
def test_a_switch_repeated_in_another_module_is_reported_with_its_place(source):
    other = switches.Elsewhere(
        "src/demo/start.py", switches.switches_of(ast.parse(START))[0]
    )

    findings = switches.check(
        ast.parse(source), "src/demo/cost.py", elsewhere=lambda: [other]
    )

    assert [(f.line, f.rule) for f in findings] == [(2, "ARC-9")]
    assert "`start` (src/demo/start.py:2)" in findings[0].message


@pytest.mark.parametrize(
    "source",
    [
        "def run(cfg):\n    return launch(cfg.backend)\n",
        LONG_CHAIN,
        "def build(cfg):\n"
        "    if cfg.backend == 'modal':\n        return Modal()\n"
        "    elif cfg.backend == 'local':\n        return Local()\n",
    ],
    ids=["no-switch", "long-chain-reported-already", "factory"],
)
def test_other_modules_are_read_only_for_a_switch_they_could_repeat(source):
    def unread() -> list[switches.Elsewhere]:
        raise AssertionError("the package was read")

    switches.check(ast.parse(source), "src/demo/runner.py", elsewhere=unread)
