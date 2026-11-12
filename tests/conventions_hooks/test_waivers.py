"""A waiver comment covers its own line, or the line below when it stands alone."""

from __future__ import annotations

from conventions_hooks.waivers import waived


def test_a_waiver_at_the_end_of_a_line_covers_that_line():
    source = "x = 1\ny = os.environ  # conventions: ENV-3 - no paths.py here.\nz = 2\n"

    assert {line: rules for line, rules in waived(source).items() if rules} == {
        2: {"ENV-3"}
    }


def test_a_waiver_alone_on_its_line_covers_the_line_below():
    source = "# conventions: ARC-9 - the launcher alone knows backends.\nx = 1\ny = 2\n"

    found = waived(source)

    assert (found[2], found.get(3, set())) == ({"ARC-9"}, set())


def test_a_comment_that_names_no_rule_waives_nothing():
    assert not any(waived("x = 1  # conventions are fine.\n").values())
