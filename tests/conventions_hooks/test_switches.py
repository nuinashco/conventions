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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (SHOTGUN, [(10, "ARC-9")]),
        (LONG_CHAIN, [(3, "ARC-9")]),
        (GUARDS, [(3, "ARC-9")]),
        (CONSTANTS, [(3, "ARC-9")]),
    ],
    ids=[
        "same-variant-in-two-functions",
        "three-arms-run-code",
        "three-guard-clauses",
        "three-arms-map-constants",
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
    ],
    ids=["factory", "closed-match", "different-names", "main-guard"],
)
def test_one_switch_in_one_place_passes(source):
    assert found(source) == []


START = (
    "def start(cfg):\n"
    "    if cfg.backend == 'modal':\n        launch()\n"
    "    elif cfg.backend == 'local':\n        run()\n"
)
COST = "def cost(cfg):\n    if cfg.backend == 'modal':\n        return bill()\n"


def test_a_switch_repeated_in_another_module_is_reported_with_its_place():
    other = switches.Elsewhere(
        "src/demo/start.py", switches.switches_of(ast.parse(START))[0]
    )

    findings = switches.check(
        ast.parse(COST), "src/demo/cost.py", elsewhere=lambda: [other]
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
