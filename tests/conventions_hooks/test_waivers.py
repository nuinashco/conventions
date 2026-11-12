"""A waiver comment covers its own line, or the statement below when it stands alone."""

from __future__ import annotations

import ast

import pytest

from conventions_hooks.waivers import continuations, waived

ALONE = "# conventions: STY-4 - the caller passes it by position.\n"


def covered(source: str) -> dict[int, set[str]]:
    found = waived(source, ast.parse(source))
    return {line: rules for line, rules in found.items() if rules}


def test_a_waiver_at_the_end_of_a_line_covers_that_line():
    source = "x = 1\ny = os.environ  # conventions: ENV-3 - no paths.py here.\nz = 2\n"

    assert covered(source) == {2: {"ENV-3"}}


def test_a_waiver_alone_on_its_line_covers_the_line_below():
    source = "# conventions: ARC-9 - the launcher alone knows backends.\nx = 1\ny = 2\n"

    found = waived(source, ast.parse(source))

    assert (found[2], found.get(3, set())) == ({"ARC-9"}, set())


def test_lines_are_counted_as_python_counts_them_past_a_form_feed():
    source = "x = 1\n\x0c\ny = os.environ  # conventions: ENV-3 - no paths.py here.\n"

    assert covered(source) == {3: {"ENV-3"}}


def test_a_comment_that_names_no_rule_waives_nothing():
    assert covered("x = 1  # conventions are fine.\n") == {}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "# conventions: ENV-1, ENV-3 - it runs before paths.py.\nx = 1\n",
            {1: {"ENV-1", "ENV-3"}, 2: {"ENV-1", "ENV-3"}},
        ),
        (
            "x = 1  # conventions: ENV-1,ENV-3 - it runs before paths.py.\n",
            {1: {"ENV-1", "ENV-3"}},
        ),
        (
            "x = 1  # conventions: ENV-1 , ENV-3 ,STY-4 - it runs before paths.py.\n",
            {1: {"ENV-1", "ENV-3", "STY-4"}},
        ),
        (
            "x = 1  # conventions: ENV-1, see ENV-3 for the reason.\n",
            {1: {"ENV-1"}},
        ),
    ],
    ids=["comma-and-space", "comma", "spaces-around-commas", "id-in-the-reason"],
)
def test_one_comment_waives_every_rule_in_its_list(source, expected):
    assert covered(source) == expected


@pytest.mark.parametrize(
    ("statement", "lines"),
    [
        ("x = load(\n    a,\n    b,\n)\ny = 2\n", [1, 2, 3, 4, 5]),
        ("def f(\n    a,\n    b=1,\n) -> int:\n    return a\n", [1, 2, 3, 4, 5]),
        ("async def f(\n    a, b=1\n): ...\n", [1, 2, 3]),
        ("@frozen\n@total\nclass A:\n    x: int\n", [1, 2, 3, 4]),
        ("class A:\n    @property\n    def b(self): ...\n", [1, 2]),
        ("if a: b = load(\n    c\n)\n", [1, 2]),
        ("while (\n    a\n    and b\n):\n    step()\n", [1, 2, 3, 4, 5]),
        ("with (\n    open(a) as f,\n):\n    f.read()\n", [1, 2, 3, 4]),
        ("for a in (\n    b\n):\n    step()\nelse:\n    stop()\n", [1, 2, 3, 4]),
        ("try:\n    a()\nfinally:\n    b()\n", [1, 2]),
        ("match a:\n    case 1:\n        b = 1\n", [1, 2]),
        ("x = 1; y = load(\n    a\n)\n", [1, 2]),
    ],
    ids=[
        "wrapped-call",
        "wrapped-signature",
        "wrapped-async-signature",
        "decorated-class",
        "class-whose-body-opens-with-a-decorator",
        "body-on-the-first-line",
        "wrapped-condition",
        "wrapped-with",
        "wrapped-for",
        "try",
        "match",
        "first-of-two-on-a-line",
    ],
)
def test_a_waiver_alone_covers_the_statement_below_up_to_its_body(statement, lines):
    assert sorted(covered(ALONE + statement)) == lines


def test_comment_lines_right_below_a_waiver_continue_its_reason():
    source = (
        "# conventions: STY-4 - OmegaConf passes resolver arguments by position, and\n"
        "# a second line finishes the reason.\n"
        "def env_or(\n    variable, default=''\n):\n"
        "    return variable or default\n"
        "# Another comment.\n"
    )

    assert sorted(covered(source)) == [1, 2, 3, 4, 5]
    assert continuations(source) == {2}


def test_the_lines_below_a_comment_that_only_quotes_a_waiver_are_no_reason():
    source = (
        "# A waiver reads `# conventions: TYP-4 - why` and stands above the\n"
        "# class that it is for.\n"
        "class A: ...\n"
    )

    assert continuations(source) == set()


def test_each_of_two_waivers_one_above_the_other_covers_the_statement_below():
    source = (
        "# conventions: STY-4 - the caller passes it by position.\n"
        "# conventions: ARC-10 - kept for the old import path.\n"
        "def f(a, b=1): ...\n"
    )

    assert covered(source)[3] == {"STY-4", "ARC-10"}


@pytest.mark.parametrize(
    ("below", "lines"),
    [
        ("\nx = load(\n    a\n)\n", [1, 2]),
        ("", [1, 2]),
        ("# The reason goes on.\n\nx = load(\n    a\n)\n", [1, 2, 3]),
    ],
    ids=["blank-line", "nothing", "blank-line-after-the-reason"],
)
def test_a_waiver_with_no_statement_right_below_covers_the_line_below(below, lines):
    assert sorted(covered(ALONE + below)) == lines


def test_a_waiver_inside_a_wrapped_statement_covers_the_line_below():
    source = (
        "x = load(\n"
        "    # conventions: ENV-3 - no paths.py here.\n"
        "    os.environ['A'],\n"
        "    os.environ['B'],\n"
        ")\n"
    )

    assert sorted(covered(source)) == [2, 3]


def test_a_waiver_at_the_end_of_a_first_line_does_not_cover_the_lines_below():
    source = "def f(  # conventions: STY-4 - passed by position.\n    a, b=1\n): ...\n"

    assert sorted(covered(source)) == [1]
